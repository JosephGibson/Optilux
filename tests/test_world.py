"""The world verbs' snapshot and restore (docs/plans/m2.md M2.P04): the copy, manifest, tree
hash and the player's uuid on a fixture world; the restore in place on a temp tree (changed,
added and removed files, folders, a leftover part file, an interrupted or failed swap, a
snapshot changed after it was taken, another world than the snapshot's)."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from optilux import REPO_ROOT, launch, platform, record, world

PLAT = platform.load(REPO_ROOT)
UUID = "51ff11bb-8719-3a7c-b3f6-cb4a2d1c5a79"


def tree(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def listing(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class Host:
    """The processes world.py asks for: none, or one running from the game folder."""

    def __init__(self, procs: list[launch.ProcessInfo] | None = None) -> None:
        self.procs = procs or []

    def processes(self) -> list[launch.ProcessInfo]:
        return self.procs


def quiet(text: str) -> None:
    pass


WORLD = {
    "level.dat": b"L",
    "region/r.0.0.mca": b"R" * 100,
    f"players/data/{UUID}.dat": b"P",
    f"players/data/{UUID}.dat_old": b"O",
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A root holding the repo's config and a game whose saves/ holds world `w`."""
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    tree(saves(tmp_path) / "w", WORLD)
    (saves(tmp_path) / "w" / "datapacks").mkdir()
    return tmp_path


def saves(root: Path) -> Path:
    return root / "runtime" / PLAT.id / launch.GAME / launch.SAVES


# The snapshot.


def test_a_snapshot_copies_the_world_with_its_manifest_hash_and_player(root: Path) -> None:
    facts = world.snapshot(root, "w", "w", Host(), quiet, note="a test")
    folder, manifest, facts_path = world.snapshot_paths(root, "w")
    assert listing(folder) == listing(saves(root) / "w")
    assert (folder / "datapacks").is_dir()  # an empty folder is copied, though never hashed
    digest, _, text = record.tree(folder)
    assert manifest.read_bytes() == text.encode("utf-8")
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == digest == facts["treeSha256"]
    assert text.splitlines()[0] == f"{hashlib.sha256(b'L').hexdigest()}  level.dat"
    assert (facts["files"], facts["bytes"], facts["playerUuid"]) == (4, 103, UUID)
    assert (facts["world"], facts["platform"], facts["note"]) == ("w", PLAT.id, "a test")
    assert json.loads(facts_path.read_text(encoding="utf-8")) == facts
    assert b"\r" not in manifest.read_bytes() + facts_path.read_bytes()


def test_a_retaken_snapshot_replaces_the_old_and_its_leftovers(root: Path) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    folder = world.snapshot_paths(root, "w")[0]
    tree(folder, {"stale.dat": b"S"})
    tree(folder.with_name(".w.new"), {"half": b"H"})  # an interrupted snapshot's copy
    (saves(root) / "w" / "level.dat").write_bytes(b"L2")
    facts = world.snapshot(root, "w", "w", Host(), quiet)
    assert listing(folder) == listing(saves(root) / "w")
    assert facts["treeSha256"] == record.tree_hash(saves(root) / "w")[0]
    assert sorted(p.name for p in folder.parent.iterdir()) == ["w", "w.json", "w.manifest"]


def test_the_player_uuid_comes_from_the_one_player_file(tmp_path: Path) -> None:
    assert world.player_uuid(tree(tmp_path / "a", {"level.dat": b"L"})) is None
    assert world.player_uuid(tree(tmp_path / "b", {f"players/data/{UUID}.dat": b"P"})) == UUID
    two = tree(
        tmp_path / "c",
        {
            f"players/data/{UUID}.dat": b"P",
            f"players/data/{'0' * 8}-0000-0000-0000-{'0' * 12}.dat": b"Q",
        },
    )
    with pytest.raises(world.WorldError, match="2 player files; fix:"):
        world.player_uuid(two)


def game_process(root: Path) -> launch.ProcessInfo:
    java = root / "runtime" / "java" / "bin" / "java.exe"
    game = root / "runtime" / PLAT.id / launch.GAME
    return launch.ProcessInfo(7, "java.exe", str(java), str(game), ["java", "-cp", "x"])


def test_snapshot_and_restore_refuse_while_a_game_runs(root: Path) -> None:
    host = Host([game_process(root)])
    with pytest.raises(world.WorldError, match=r"pid 7 java\.exe.*fix: quit it first"):
        world.snapshot(root, "w", "w", host, quiet)
    world.snapshot(root, "w", "w", Host(), quiet)
    with pytest.raises(world.WorldError, match="fix: quit it first"):
        world.restore(root, "w", "w", host, quiet)


def test_the_world_and_id_are_refused_unless_plain(root: Path) -> None:
    with pytest.raises(world.WorldError, match="not one folder name"):
        world.snapshot(root, "w", "../w", Host(), quiet)
    with pytest.raises(world.WorldError, match="is not"):
        world.snapshot(root, "W x", "w", Host(), quiet)
    with pytest.raises(world.WorldError, match=r"no world .* with a level\.dat"):
        world.snapshot(root, "w", "absent", Host(), quiet)


# The restore.


def test_a_restore_copies_changed_and_missing_files_and_deletes_added_ones(root: Path) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    live = saves(root) / "w"
    snapped = listing(live)
    (live / "level.dat").write_bytes(b"changed")
    (live / "region" / "r.0.0.mca").unlink()
    tree(live, {"region/r.1.0.mca": b"new", "added/deep/file.dat": b"A"})
    (live / "datapacks").rmdir()
    found = world.restore(root, "w", "w", Host(), quiet)
    assert listing(live) == snapped
    assert sorted(found["copied"]) == ["level.dat", "region/r.0.0.mca"]
    assert sorted(found["deleted"]) == ["added/deep/file.dat", "region/r.1.0.mca"]
    assert (found["kept"], found["files"], found["checkedAgainstFacts"]) == (2, 4, True)
    assert not (live / "added").exists()  # a folder the snapshot lacks is pruned once empty
    assert (live / "datapacks").is_dir()  # the snapshot's empty folder is made
    assert found["treeSha256"] == record.tree_hash(world.snapshot_paths(root, "w")[0])[0]


def test_a_restore_finishes_an_interrupted_one_and_settles_file_folder_swaps(
    tmp_path: Path,
) -> None:
    snap = tree(tmp_path / "snap", {"a/b.dat": b"B", "c": b"C"})
    live = tree(tmp_path / "live", {"a": b"file where a folder was", "c/inner": b"I"})
    tree(live, {"x.dat.optilux-restore": b"half"})  # a part file an interrupted restore left
    found = world.restore_tree(snap, live)
    assert listing(live) == listing(snap)
    assert "x.dat.optilux-restore" in found["deleted"]


def test_a_restore_of_a_missing_live_world_copies_it_whole(root: Path) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    snapped = listing(saves(root) / "w")
    shutil.rmtree(saves(root) / "w")
    found = world.restore(root, "w", "w", Host(), quiet)
    assert listing(saves(root) / "w") == snapped
    assert len(found["copied"]) == 4 and not found["deleted"]


def test_a_restore_into_another_world_than_the_snapshots_is_refused(root: Path) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    tree(saves(root) / "other", {"level.dat": b"mine"})
    with pytest.raises(world.WorldError, match="overwrite another world; fix: name saves/w"):
        world.restore(root, "w", "other", Host(), quiet)
    assert listing(saves(root) / "other") == {"level.dat": b"mine"}


def test_a_swap_interrupted_between_its_renames_is_recovered(root: Path) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    folder = world.snapshot_paths(root, "w")[0]
    taken = listing(folder)
    folder.rename(folder.with_name(".w.old"))  # killed after the first rename
    found = world.restore(root, "w", "w", Host(), quiet)
    assert listing(folder) == taken and found["checkedAgainstFacts"] is True
    assert not folder.with_name(".w.old").exists()


def test_a_failed_swap_puts_the_old_snapshot_back(root: Path, monkeypatch) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    folder = world.snapshot_paths(root, "w")[0]
    taken = listing(folder)
    (saves(root) / "w" / "level.dat").write_bytes(b"L2")
    real = world.os.replace

    def second_fails(src, dst) -> None:
        if Path(src).name == ".w.new":
            raise PermissionError("held open")
        real(src, dst)

    monkeypatch.setattr(world.os, "replace", second_fails)
    with pytest.raises(world.WorldError, match="the old snapshot is kept"):
        world.snapshot(root, "w", "w", Host(), quiet)
    assert listing(folder) == taken


def test_a_snapshot_changed_after_it_was_taken_is_refused(root: Path) -> None:
    world.snapshot(root, "w", "w", Host(), quiet)
    tree(world.snapshot_paths(root, "w")[0], {"level.dat": b"edited"})
    before = listing(saves(root) / "w")
    with pytest.raises(world.WorldError, match="changed after it was taken; fix: retake"):
        world.restore(root, "w", "w", Host(), quiet)
    assert listing(saves(root) / "w") == before  # nothing written


def test_a_restore_without_a_snapshot_names_the_verb(root: Path) -> None:
    with pytest.raises(world.WorldError, match="fix: `optilux world snapshot w`"):
        world.restore(root, "w", "w", Host(), quiet)


def test_a_snapshot_taken_before_the_verb_restores_unchecked(root: Path) -> None:
    shutil.copytree(saves(root) / "w", root / record.SNAPSHOTS / "old")
    found = world.restore(root, "old", "w", Host(), quiet)
    assert found["checkedAgainstFacts"] is False and not found["copied"]
