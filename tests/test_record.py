"""The run record (docs/run-record.md, docs/plans/m1.md 0.01.08 and 0.01.09): the tree hash on a
fixture tree, the run spec's checks on fixtures (every refusal naming its fix), the views file,
the identity and the record writer against the identity key list, the system facts on a fake
machine; run's readers: the jcmd outputs and the broken-pack writer on a fixture zip."""

import copy
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from optilux import REPO_ROOT, launch, platform, record
from optilux.verbs import run

PLAT = platform.load(REPO_ROOT)
SUITE = json.loads((REPO_ROOT / platform.SUITE).read_text(encoding="utf-8"))
PACK = launch.reference_pack(PLAT).file
VIEWS = REPO_ROOT / record.VIEWS / "provisional.json"


# The tree hash.


def tree(root: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def test_the_tree_hash_is_the_sha256_of_the_sorted_manifest(tmp_path: Path) -> None:
    folder = tree(tmp_path / "w", {"level.dat": b"L", "region/r.0.0.mca": b"R", "a/b": b"B"})
    (folder / "empty").mkdir()  # an empty folder holds no file and adds nothing
    lines = [
        f"{hashlib.sha256(b'B').hexdigest()}  a/b\n",
        f"{hashlib.sha256(b'L').hexdigest()}  level.dat\n",
        f"{hashlib.sha256(b'R').hexdigest()}  region/r.0.0.mca\n",
    ]
    expected = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    assert record.tree_hash(folder) == (expected, 3)
    assert record.tree_text(record.tree_files(folder)) == "".join(lines)


def test_the_tree_hash_moves_with_a_content_a_name_or_a_new_file(tmp_path: Path) -> None:
    files = {"level.dat": b"L", "players/data/u.dat": b"P"}
    base = record.tree_hash(tree(tmp_path / "a", files))[0]
    assert record.tree_hash(tree(tmp_path / "b", files))[0] == base  # another folder, same tree
    assert record.tree_hash(tree(tmp_path / "c", {**files, "level.dat": b"M"}))[0] != base
    renamed = {"level.dat": b"L", "players/data/v.dat": b"P"}
    assert record.tree_hash(tree(tmp_path / "d", renamed))[0] != base
    assert record.tree_hash(tree(tmp_path / "e", {**files, "session.lock": b"x"}))[0] != base


def test_a_missing_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(record.RecordError, match="fix:"):
        record.tree_hash(tmp_path / "absent")


# The run spec.


def spec() -> dict:
    return {
        "name": "m1-acceptance-test",
        "kind": "acceptance",
        "views": "provisional",
        "world": "spike",
        "variants": [{"pack": PACK, "profile": None}],
        "tier": "bench",
        "resourcePacks": "standard",
        "items": ["A10", "A1", "A2", "A3"],
        "notes": "a fixture",
    }


@pytest.fixture
def fixture_root(tmp_path: Path) -> tuple[Path, Path]:
    """A root with the views file, its snapshot and a saves folder holding the world."""
    views = tmp_path / record.VIEWS
    views.mkdir(parents=True)
    shutil.copyfile(VIEWS, views / VIEWS.name)
    (tmp_path / record.SNAPSHOTS / "provisional").mkdir(parents=True)
    saves = tmp_path / "saves"
    tree(saves / "spike", {"level.dat": b"L"})
    return tmp_path, saves


def check(root: Path, saves: Path, data) -> record.Spec:
    return record.check_spec(root, data, PLAT, SUITE, saves, PACK)


def test_a_valid_spec_is_taken_with_its_items_in_run_order(fixture_root) -> None:
    root, saves = fixture_root
    found = check(root, saves, spec())
    assert (found.name, found.kind, found.views, found.world) == (
        "m1-acceptance-test",
        "acceptance",
        "provisional",
        "spike",
    )
    assert found.items == ("A1", "A2", "A3", "A10")
    assert (found.pack, found.tier, found.resource_packs) == (PACK, "bench", "standard")


def drop(key: str):
    def change(data: dict) -> None:
        del data[key]

    return change


def put(key: str, value):
    def change(data: dict) -> None:
        data[key] = value

    return change


REFUSALS = [
    (drop("world"), "lacks world"),
    (put("seed", 1), "unknown seed"),
    (put("name", "Bad Name"), "is not"),
    (put("name", "x" * 41), "is not"),
    (put("kind", "measurement"), "acceptance runs only"),
    (put("kind", "smoke"), "one of measurement"),
    (put("mode", "quick"), "mode is for measurement"),
    (put("treatment", "mods"), "treatment is for measurement"),
    (put("tier", "dev"), "bench tier"),
    (put("views", "final"), "no views file"),
    (put("views", "../x"), "names no views file"),
    (put("world", "absent"), "no folder"),
    (put("world", "../spike"), "no folder"),
    (put("variants", [{"pack": "other.zip", "profile": None}]), "one variant"),
    (put("variants", [{"pack": PACK, "profile": "played"}]), "profiles come with M2"),
    (put("resourcePacks", "deterministic"), "standard set only"),
    (put("items", []), "no acceptance item"),
    (put("items", ["A1", "A1"]), "twice"),
    (put("items", ["A13"]), "no acceptance item"),
    (put("items", ["A5"]), "later milestone"),
    (put("reloads", 15), "multiple of 10"),
    (put("reloads", -10), "multiple of 10"),
    (put("reloads", True), "multiple of 10"),
    (put("reloads", 290), "over capture.reloadCap 288"),
    (put("notes", 3), "notes must be text"),
]


@pytest.mark.parametrize(("change", "says"), REFUSALS)
def test_each_refusal_names_its_fix(fixture_root, change, says: str) -> None:
    root, saves = fixture_root
    data = spec()
    change(data)
    with pytest.raises(record.RecordError) as refused:
        check(root, saves, data)
    assert says in str(refused.value)
    assert "fix:" in str(refused.value)


def test_a_spec_that_is_no_object_is_refused(fixture_root) -> None:
    root, saves = fixture_root
    with pytest.raises(record.RecordError, match="fix:"):
        check(root, saves, ["not", "an", "object"])


def test_a_used_run_name_is_refused(fixture_root) -> None:
    root, saves = fixture_root
    (root / record.RAW / "m1-acceptance-test").mkdir(parents=True)
    with pytest.raises(record.RecordError, match="single-use"):
        check(root, saves, spec())


def test_a_views_file_without_its_snapshot_is_refused(fixture_root) -> None:
    root, saves = fixture_root
    (root / record.SNAPSHOTS / "provisional").rmdir()
    with pytest.raises(record.RecordError, match="no snapshot snapshots/provisional/; fix:"):
        check(root, saves, spec())


def test_the_reload_budget_is_checked(fixture_root) -> None:
    root, saves = fixture_root
    suite = copy.deepcopy(SUITE)
    suite["capture"]["reloadCap"] = 1
    with pytest.raises(record.RecordError, match="reloadCap 1; fix:"):
        record.check_spec(root, spec(), PLAT, suite, saves, PACK)


def test_the_0_01_09_items_and_f4s_reloads_are_taken(fixture_root) -> None:
    root, saves = fixture_root
    data = {**spec(), "items": ["A9", "A10", "A7", "A4"], "reloads": 50}
    found = check(root, saves, data)
    assert found.items == ("A4", "A7", "A9", "A10") and found.reloads == 50
    assert check(root, saves, spec()).reloads == 0
    # The session's reloads: two at the start, A4's two, F4's fifty.
    suite = copy.deepcopy(SUITE)
    suite["capture"]["reloadCap"] = 53
    with pytest.raises(record.RecordError, match="plans 54 reloads"):
        record.check_spec(root, data, PLAT, suite, saves, PACK)


# The views file.


def test_the_committed_views_file_holds_one_view_per_dimension() -> None:
    data, path = record.load_views(REPO_ROOT, "provisional")
    assert path == VIEWS
    assert [view["dim"] for view in data["views"]] == list(record.DIMENSIONS)


def test_the_bench_views_file_holds_the_suite_roles_in_order() -> None:
    # 0.01.11: one view per suite.json view role, in its order, with the role's dimension, time
    # and weather; the world's seed is set beside it.
    dims = dict(zip(("overworld", "nether", "end"), record.DIMENSIONS, strict=True))
    data, _ = record.load_views(REPO_ROOT, "bench_263")
    roles = SUITE["viewRoles"]
    assert [view["id"] for view in data["views"]] == [role["id"] for role in roles]
    for view, role in zip(data["views"], roles, strict=True):
        assert view["dim"] == dims[role["dim"]], view["id"]
        assert (view["time"], view["weather"]) == (role["time"], role["weather"]), view["id"]
    assert SUITE["world"]["seed"] == 263


def views_with(change) -> dict:
    data = json.loads(VIEWS.read_text(encoding="utf-8"))
    change(data["views"])
    return data


BAD_VIEWS = [
    (lambda views: views[0].update(dim="minecraft:moon"), "dim"),
    (lambda views: views[0].update(pitch=91.0), "outside -90..90"),
    (lambda views: views[0].update(x=float("nan")), "finite"),
    (lambda views: views[0].update(time=1.5), "no tick count"),
    (lambda views: views[0].update(weather="snow"), "weather"),
    (lambda views: views[1].update(id=views[0]["id"]), "listed twice"),
    (lambda views: views[0].pop("yaw"), "missing"),
    (lambda views: views[0].update(roll=0), "unknown"),
]


@pytest.mark.parametrize(("change", "says"), BAD_VIEWS)
def test_a_bad_view_is_refused(tmp_path: Path, change, says: str) -> None:
    folder = tmp_path / record.VIEWS
    folder.mkdir(parents=True)
    (folder / "provisional.json").write_text(json.dumps(views_with(change)), encoding="utf-8")
    with pytest.raises(record.RecordError) as refused:
        record.load_views(tmp_path, "provisional")
    assert says in str(refused.value) and "fix:" in str(refused.value)


# The identity and the record.


def doc_identity_keys() -> list[str]:
    """The record keys run-record.md#identity lists, one bullet each, in order."""
    text = (REPO_ROOT / "docs/run-record.md").read_text(encoding="utf-8")
    section = text.split("## Identity", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- `(\w+)`:", section, flags=re.MULTILINE)


def test_the_identity_keys_are_the_docs() -> None:
    assert doc_identity_keys() == list(record.IDENTITY_KEYS)


class FakeMachine(record.Machine):
    def __init__(self, width: int = 3840, height: int = 2160) -> None:
        self.size = (width, height)

    def displays(self) -> list[dict]:
        return [
            {"name": "\\\\.\\DISPLAY1", "adapter": "GPU X", "flags": 0x1},
            {"name": "\\\\.\\DISPLAY2", "adapter": "GPU X", "flags": 0x5},
        ]

    def display_mode(self, name: str) -> dict:
        assert name == "\\\\.\\DISPLAY2"  # the primary
        return {"width": self.size[0], "height": self.size[1], "hz": 240, "dpiAware": True}

    def registry(self, key: str, value: str):
        return {"HwSchMode": 2, "UBR": 9457}[value]

    def driver(self, adapter: str) -> str | None:
        return "1.2.3" if adapter == "GPU X" else None

    def windows_build(self) -> int:
        return 26200


def options() -> dict[str, str]:
    return launch.written_options(SUITE["display"], {})


def test_the_system_facts_come_from_the_primary_display() -> None:
    found, recorded = record.system_facts(FakeMachine(), options(), SUITE["display"])
    assert found == {
        "gpu": "GPU X",
        "hags": True,
        "resolution": "3840x2160",
        "windowMode": "borderless fullscreen",
        "windowsBuild": 26200,
    }
    assert recorded["driver"] == "1.2.3" and recorded["windowsRevision"] == 9457
    assert recorded["display"] == {"name": "\\\\.\\DISPLAY2", "hz": 240, "displays": 2}


def test_a_display_or_window_mode_off_the_suite_is_refused() -> None:
    with pytest.raises(record.RecordError, match="runs 2560x1440.*never changes system"):
        record.system_facts(FakeMachine(2560, 1440), options(), SUITE["display"])
    windowed = {**options(), "fullscreen": "false"}
    with pytest.raises(record.RecordError, match="give windowed.*fix:"):
        record.system_facts(FakeMachine(), windowed, SUITE["display"])


def test_the_java_version_must_be_the_running_games(tmp_path: Path) -> None:
    home = tmp_path / "jdk"
    home.mkdir()
    (home / "release").write_text('JAVA_RUNTIME_VERSION="25.0.4.1+1-LTS"\n', encoding="utf-8")
    profile = json.loads((REPO_ROOT / "config/java/bench.json").read_text(encoding="utf-8"))
    found = record.java_identity(home, profile, "25.0.4.1+1-LTS")
    assert found["version"] == "25.0.4.1+1-LTS" and found["heap"]["xmx"] == 6144
    with pytest.raises(record.RecordError, match="fix:"):
        record.java_identity(home, profile, "21.0.1")


def built_identity() -> dict:
    system, _ = record.system_facts(FakeMachine(), options(), SUITE["display"])
    return record.identity(
        plat=PLAT,
        tier="bench",
        spec_path=platform.spec_path(REPO_ROOT, PLAT.id),
        mods=["b" * 128, "a" * 128],
        world={"snapshot": "snapshots/provisional", "treeSha256": "c" * 64, "files": 3},
        views_path=VIEWS,
        packs=[{"file": "Faithful.zip", "sha512": "d" * 128}],
        settings={"options": options(), "sodiumOptions": "e" * 64, "token": True},
        suite=SUITE,
        java={"runtime": "jdk", "version": "25", "heap": {}, "args": []},
        system=system,
    )


def test_the_identity_holds_exactly_the_key_list() -> None:
    found = built_identity()
    assert tuple(found) == record.IDENTITY_KEYS
    record.check_identity(found)
    assert found["mods"] == ["a" * 128, "b" * 128]  # sorted
    assert found["platform"]["tiers"] == ["bench"]


def test_a_note_never_moves_the_suite_hash_and_a_value_does() -> None:
    base = record.suite_identity(SUITE)["sha256"]
    noted = copy.deepcopy(SUITE)
    noted["capture"]["why"] = "another note"
    noted["capture"]["settleWhy"] = "another"
    noted["modes"]["quick"]["estMinutes"] = 99
    assert record.suite_identity(noted)["sha256"] == base
    moved = copy.deepcopy(SUITE)
    moved["capture"]["gpuWarmupS"] = 31
    assert record.suite_identity(moved)["sha256"] != base


def test_the_platform_hash_covers_the_loaded_tiers_only() -> None:
    base = record.platform_identity(PLAT, "bench")["sha256"]
    other = platform.Platform(PLAT.id, PLAT.path, copy.deepcopy(PLAT.data))
    other.data["tiers"]["dev"]["purpose"] = "changed"
    assert record.platform_identity(other, "bench")["sha256"] == base
    other.data["tiers"]["bench"]["purpose"] = "changed"
    assert record.platform_identity(other, "bench")["sha256"] != base


def a_record(**changes) -> dict:
    found = {
        "schema": 1,
        "name": "m1-acceptance-test",
        "kind": "acceptance",
        "status": "ok",
        "identity": built_identity(),
        "acceptance": [{"item": "A10", "pass": True, "evidence": {"selftest": {}}}],
    }
    found.update(changes)
    return found


def test_the_writer_writes_once_lf(tmp_path: Path) -> None:
    path = record.write_record(tmp_path, a_record())
    assert path == tmp_path / record.RECORDS / "m1-acceptance-test.json"
    data = path.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    assert json.loads(data)["identity"]["system"]["gpu"] == "GPU X"
    with pytest.raises(record.RecordError, match="never overwritten"):
        record.write_record(tmp_path, a_record())


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (lambda i: i.pop("world"), "lacks \\['world'\\]"),
        (lambda i: i.update(seed=1), "adds \\['seed'\\]"),
        (lambda i: i.update(system=None), "leaves \\['system'\\] empty"),
        (lambda i: i.update(mods=[]), "leaves \\['mods'\\] empty"),
    ],
)
def test_the_writer_refuses_an_identity_off_the_key_list(tmp_path: Path, change, says) -> None:
    found = a_record()
    change(found["identity"])
    with pytest.raises(record.RecordError, match=says):
        record.write_record(tmp_path, found)
    assert not (tmp_path / record.RECORDS).exists()


def test_a_failed_session_may_lack_its_identity_an_ok_one_never(tmp_path: Path) -> None:
    record.write_record(tmp_path, a_record(status="failed", identity=None))
    with pytest.raises(record.RecordError, match="identity is no object"):
        record.write_record(tmp_path, a_record(name="m1-other", identity=None))


def test_the_writer_checks_status_and_items(tmp_path: Path) -> None:
    with pytest.raises(record.RecordError, match="status"):
        record.write_record(tmp_path, a_record(status="fine"))
    with pytest.raises(record.RecordError, match="no boolean pass"):
        record.write_record(
            tmp_path, a_record(acceptance=[{"item": "A2", "pass": "yes", "evidence": {}}])
        )
    with pytest.raises(record.RecordError, match="holds no item"):
        record.write_record(tmp_path, a_record(acceptance=[]))


# run's readers.


def test_thread_names_come_from_a_jcmd_dump() -> None:
    dump = (
        "2026-10-07 00:00:00\nFull thread dump OpenJDK 64-Bit Server VM (25.0.4.1+1-LTS):\n\n"
        '"Render thread" #1 [1234] prio=5 os_prio=0 cpu=1.00ms\n'
        "   java.lang.Thread.State: RUNNABLE\n"
        '"optilux-pipe" #40 daemon prio=5\n'
        '"Server thread" #50 prio=5\n'
    )
    assert run.thread_names(dump) == ["Render thread", "optilux-pipe", "Server thread"]


def test_the_helpers_lines_are_sorted_by_kind() -> None:
    log = "\n".join(
        [
            "[00:00:01] [main/INFO]: optilux-helper: inert (no token): no pipe, no thread, no "
            "mixin",
            "[00:00:01] [main/INFO]: optilux-helper: mixin optilux.helper.mixin.X not applied to "
            "net.minecraft.Y: inert (no token)",
            "[00:00:02] [main/INFO]: optilux-helper: mixin optilux.helper.mixin.X applied to "
            "net.minecraft.Y",
            "[00:00:02] [main/INFO]: optilux-helper: active: frame clock on "
            "QueryPerformanceCounter",
            "[00:00:03] [main/INFO]: unrelated",
        ]
    )
    found = run.helper_lines(log)
    assert [len(found[key]) for key in ("inert", "declined", "applied", "active")] == [1, 1, 1, 1]


def test_a_pngs_size_comes_from_its_header() -> None:
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (3840).to_bytes(4, "big")
    assert run.png_size(header + (2160).to_bytes(4, "big")) == (3840, 2160)
    assert run.png_size(b"GIF89a") is None


def test_tp_literals_keep_an_integer_integer() -> None:
    # /tp centres integer x and z only (+0.5): the command text must keep the JSON's kind.
    found = [run.literal(v) for v in (-525, 91.0, -79.5, 495.0)]
    assert found == ["-525", "91.0", "-79.5", "495.0"]


class FakeClient:
    """`command` answers as 26.3's /time set does."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = failures

    def command(self, text: str, timeout: float, check: bool = True) -> dict:
        # Run in the overworld: 26.3 sets the sender's dimension's clock, the Nether has none.
        assert text == "/execute in minecraft:overworld run time set 6000" and check is False
        return {"succeeded": not self.failures, "messages": [], "failures": self.failures}


def test_time_already_at_the_views_value_counts_as_set() -> None:
    already = ["Clock minecraft:overworld is already set to 6000 tick(s)"]
    assert run.set_time(FakeClient([]), 6000)["succeeded"] is True
    assert run.set_time(FakeClient(already), 6000)["failures"] == already
    with pytest.raises(run.modclient.ModError, match="time set 6000"):
        run.set_time(FakeClient(["Unknown or incomplete command"]), 6000)
    with pytest.raises(run.modclient.ModError):
        run.set_time(FakeClient(["Clock minecraft:overworld is already set to 600 tick(s)"]), 6000)


# F4: GC.heap_info as Temurin 25 prints it (tests/fixtures/run/gc-heap-info.txt, a JVM started with
# the bench heap, 2026-10-07), and the older line without a committed size.


def test_the_heap_after_gc_comes_from_gc_heap_info() -> None:
    text = (REPO_ROOT / "tests" / "fixtures" / "run" / "gc-heap-info.txt").read_text("utf-8")
    assert run.heap_info(text) == {
        "heap": "garbage-first heap",
        "reservedKiB": 6291456,
        "committedKiB": 6291456,
        "usedKiB": 23182,
    }
    older = (
        "1234:\r\n garbage-first heap   total 6291456K, used 725195K [0x0000000680000000, "
        "0x0000000800000000)\n Metaspace       used 151234K, committed 152000K, reserved "
        "1179648K\n"
    )
    found = run.heap_info(older)
    assert (found["usedKiB"], found["committedKiB"], found["metaspaceUsedKiB"]) == (
        725195,
        None,
        151234,
    )
    with pytest.raises(run.RunError, match="no heap line"):
        run.heap_info("1234:\nCommand executed successfully\n")


# A4: the broken copy of a fixture zip.


def fixture_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as out:
        out.writestr(zipfile.ZipInfo("shaders/", (2024, 1, 2, 3, 4, 6)), b"")
        entry = zipfile.ZipInfo("shaders/world0/final.fsh", (2024, 1, 2, 3, 4, 6))
        entry.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(entry, b'#version 130\n#include "/program/final.glsl"\n')
        stored = zipfile.ZipInfo("shaders/shaders.properties", (2023, 5, 6, 7, 8, 10))
        out.writestr(stored, b"sliders=A B\n" * 40)
        deflated = zipfile.ZipInfo("shaders/program/final.glsl", (2023, 5, 6, 7, 8, 12))
        deflated.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(deflated, b"void main() {}\n" * 50)
    return path


def test_the_broken_pack_differs_in_its_program_alone(tmp_path: Path) -> None:
    source = fixture_zip(tmp_path / "Pack.zip")
    before = source.read_bytes()
    packs = tmp_path / "shaderpacks"
    packs.mkdir()
    target = packs / f"{run.A4_PREFIX}Pack.zip"
    facts = run.write_broken_pack(source, target, run.A4_PROGRAM, run.A4_BODY)
    assert source.read_bytes() == before
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target) as new:
        assert new.namelist() == old.namelist()
        for a, b in zip(old.infolist(), new.infolist(), strict=True):
            assert (b.date_time, b.compress_type) == (a.date_time, a.compress_type)
            wanted = run.A4_BODY if a.filename == run.A4_PROGRAM else old.read(a)
            assert new.read(b) == wanted
    assert facts["entries"] == 4 and facts["program"] == run.A4_PROGRAM
    assert facts["brokenSha256"] == hashlib.sha256(run.A4_BODY).hexdigest()
    assert run.A4_IDENTIFIER.encode() in run.A4_BODY
    with pytest.raises(run.RunError, match="exists"):
        run.write_broken_pack(source, target, run.A4_PROGRAM, run.A4_BODY)
    with pytest.raises(run.RunError, match="holds no shaders/world9"):
        run.write_broken_pack(source, packs / "x.zip", "shaders/world9/final.fsh", b"")
    game = tmp_path
    assert [p.name for p in run.broken_copies(game)] == [target.name]
    assert run.remove_broken(game) == {"removed": [target.name], "kept": []}
    assert run.broken_copies(game) == [] and source.is_file()
