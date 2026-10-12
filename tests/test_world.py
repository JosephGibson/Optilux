"""The world verbs (docs/plans/m2.md M2.P04): the snapshot's copy, manifest, tree hash and the
player's uuid on a fixture world; the restore in place on a temp tree (changed, added and removed
files, folders, a leftover part file, a snapshot changed after it was taken); the data pack's
bytes; Chunky's selections from bench_263's views file and its lines read from latest.log; the
kill's selector and the answers it is judged by; the world prep set reached by install and
launch; the counts prep must hold."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from optilux import REPO_ROOT, launch, platform, record, world

PLAT = platform.load(REPO_ROOT)
UUID = "51ff11bb-8719-3a7c-b3f6-cb4a2d1c5a79"
BENCH, _ = record.load_views(REPO_ROOT, "bench_263")


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


# The data pack.


def test_the_view_function_sets_time_and_weather_in_the_overworld_and_returns_1() -> None:
    rain = next(v for v in BENCH["views"] if v["id"] == "rain")
    assert world.view_function(rain, "bench_263") == (
        b"# optilux:view/rain from config/views/bench_263.json (optilux world prep)\n"
        b"execute in minecraft:overworld run time set 6000\n"
        b"execute in minecraft:overworld run weather thunder\n"
        b"return 1\n"
    )


def test_pack_mcmeta_declares_the_platforms_data_format_alone() -> None:
    data = world.pack_mcmeta(PLAT.data["formats"]["dataPack"], "bench_263")
    assert data == (
        b'{\n "pack": {\n  "description": "Optilux view functions from '
        b'config/views/bench_263.json",\n  "min_format": [\n   121,\n   0\n  ],\n'
        b'  "max_format": [\n   121,\n   0\n  ]\n }\n}\n'
    )
    assert "pack_format" not in json.loads(data)["pack"]
    with pytest.raises(world.WorldError, match=r"not <major>\.<minor>"):
        world.pack_format("x.1")


def test_the_pack_holds_one_function_per_view_and_prunes_stale_ones(tmp_path: Path) -> None:
    files = world.pack_files(BENCH, "121.0")
    assert sorted(files) == sorted(
        ["pack.mcmeta"]
        + [f"data/optilux/function/view/{v['id']}.mcfunction" for v in BENCH["views"]]
    )
    live = tmp_path / "w"
    tree(live / "datapacks" / "optilux", {"data/optilux/function/view/gone.mcfunction": b"x"})
    found = world.write_pack(live, files)
    assert listing(live / "datapacks" / "optilux") == files
    assert found["pruned"] == ["data/optilux/function/view/gone.mcfunction"]
    assert len(found["written"]) == 12
    again = world.write_pack(live, files)
    assert (again["written"], again["pruned"]) == ([], [])


# Chunky.


def test_chunky_selections_cover_the_views_plus_the_render_distance() -> None:
    found = world.selections(BENCH)
    assert [(s.world, s.shape, s.x, s.z, s.radius_x, s.radius_z) for s in found] == [
        ("minecraft:overworld", "rectangle", -169, 577, 486, 621),
        ("minecraft:the_nether", "rectangle", 111, -153, 408, 457),
        ("minecraft:the_end", "square", 57, -19, 289, 289),
        ("minecraft:the_end", "square", 318, 1055, 289, 289),
    ]
    assert found[2].views == ("end_dragon",) and found[3].views == ("end_city",)
    assert len(found[0].views) == 7 and set(found[1].views) == {"nether_crimson", "nether_soul"}
    for task in found:
        for view in BENCH["views"]:
            if view["id"] in task.views:
                assert abs(view["x"] - task.x) + world.MARGIN <= task.radius_x
                assert abs(view["z"] - task.z) + world.MARGIN <= task.radius_z


def test_chunky_commands_carry_the_lines_it_answers_with() -> None:
    overworld, _, end, _ = world.selections(BENCH)
    assert overworld.commands() == [
        ("/chunky world minecraft:overworld", "World changed to "),
        ("/chunky shape rectangle", "Shape changed to "),
        ("/chunky center -169 577", "Center changed to -169, 577."),
        ("/chunky radius 486 621", "Radius changed for x to 486, and for z to 621."),
    ]
    assert end.commands()[-1] == ("/chunky radius 289", "Radius changed to 289.")


def test_latest_log_is_read_on_from_where_it_stood(tmp_path: Path) -> None:
    log = tmp_path / "latest.log"
    log.write_bytes(b"[1] before\n")
    tail = world.LogTail(log)
    with log.open("ab") as handle:
        handle.write("[2] §2[Chunky] §rWorld changed to x.\n[3] half".encode())
    assert tail.poll() == ["[2] [Chunky] World changed to x."]
    with log.open("ab") as handle:
        handle.write(b" line\n")
    assert tail.poll() == ["[3] half line"]
    log.write_bytes(b"[4] rolled\n")  # a shorter file is read from its start
    assert tail.poll() == ["[4] rolled"]
    tail.unread(["[3] again"])  # a reader's extra lines come back first
    assert tail.poll() == ["[3] again"]


UPDATE = (
    "[18:01:02] [Server thread/INFO]: [Chunky] Task running for minecraft:overworld. Processed: "
    "{n} chunks ({p}%), ETA: 0:01:00, Rate: 80.0 cps, Current: -10, 20"
)


def test_a_task_ends_at_its_finished_line_and_counts_its_updates() -> None:
    state = world.TaskState("minecraft:overworld")
    lines = [
        "[CHAT] [Chunky] Task started in minecraft:overworld for the rectangle region centered "
        "at -169, 577 with radius 486, 621.",
        UPDATE.format(n=10, p="0.21"),
        UPDATE.replace("overworld", "the_nether").format(n=99, p="9.00"),
    ]
    assert world.read_task(state, lines) is True
    assert (state.started, state.chunks, state.percent, state.updates) == (True, 10, 0.21, 1)
    assert world.read_task(state, [UPDATE.format(n=10, p="0.21")]) is False  # no progress
    done = (
        "[18:03:04] [Server thread/INFO]: [Chunky] Task finished for minecraft:overworld. "
        "Processed: 4758 chunks (100,00%), Total time: 0:02:02"
    )
    assert world.read_task(state, [done]) is True
    assert state.done == {
        "chunks": 4758,
        "percent": 100.0,
        "seconds": 122,
        "line": done,
        "from": "console",
    }


def test_a_task_reads_its_confirmation_stop_and_no_tasks_lines() -> None:
    state = world.TaskState("minecraft:the_end")
    world.read_task(
        state,
        [
            "[CHAT] A task was already started for this world. To continue running it, type "
            "'/chunky continue'. To start a new task, type '/chunky confirm'.",
            "[CHAT] Task already started for minecraft:the_end!",
            "[CHAT] No tasks running.",
            "[x] Task stopped for minecraft:the_end.",
        ],
    )
    assert (state.confirm, state.already, state.no_tasks, state.stopped) == (True,) * 4


# Entities.


def test_the_kill_spares_the_player_the_dragon_the_crystals_and_the_tag() -> None:
    assert world.kill_command() == (
        "/kill @e[type=!minecraft:player,type=!minecraft:ender_dragon,"
        "type=!minecraft:end_crystal,tag=!optilux_bench,distance=..256]"
    )
    assert world.count_command(world.selector()) == "/execute if entity " + world.selector()


def answer(succeeded: bool, messages: list[str], failures: list[str]) -> dict:
    return {"succeeded": succeeded, "messages": messages, "failures": failures}


def test_a_count_is_read_from_the_games_own_words_never_guessed() -> None:
    assert world.parse_count(answer(True, ["Test passed. Count: 7"], [])) == 7
    assert world.parse_count(answer(False, [], ["Test failed"])) == 0
    for bad in (
        answer(True, ["Test passed. count: 7"], []),
        answer(True, [], []),
        answer(False, [], ["Unknown command"]),
    ):
        with pytest.raises(world.WorldError, match="fix: read"):
            world.parse_count(bad)


def test_positions_are_read_per_mob_and_sorted() -> None:
    found = world.parse_positions(
        answer(
            True,
            [
                "Sheep has the following entity data: [-366.15d, 64.0d, 250.32d]",
                "Cow has the following entity data: [-370.5d, 63.0d, 251.0d]",
            ],
            [],
        )
    )
    assert found == [
        {"name": "Cow", "x": -370.5, "y": 63.0, "z": 251.0},
        {"name": "Sheep", "x": -366.15, "y": 64.0, "z": 250.32},
    ]
    with pytest.raises(world.WorldError):
        world.parse_positions(answer(True, ["Sheep has 3 legs"], []))


def test_no_tick_is_stepped_beside_the_dragon_fight() -> None:
    by_id = {v["id"]: v for v in BENCH["views"]}
    assert world.ticks_allowed(by_id["end_dragon"]) is False
    assert world.ticks_allowed(by_id["end_city"]) is True
    assert world.ticks_allowed(by_id["nether_soul"]) is True


def test_the_counts_prep_must_hold() -> None:
    mobs = [{"name": f"m{i}", "x": 0.0, "y": 0.0, "z": float(i)} for i in range(7)]
    done = {"entities": {"tagged": 7}, "end_dragon": {"endCrystals": 10}}
    assert world.check_counts(BENCH, done, mobs, mobs) == []
    moved = [*mobs[:6], {**mobs[6], "z": 9.5}]
    assert "moved" in world.check_counts(BENCH, done, mobs, moved)[0]
    short = {"entities": {"tagged": 6}, "end_dragon": {"endCrystals": 9}}
    assert len(world.check_counts(BENCH, short, mobs, mobs)) == 2


# The world prep set.


def test_install_and_launch_reach_the_world_prep_set_beside_the_tiers() -> None:
    assert PLAT.sets == [*PLAT.tiers, platform.WORLD_PREP]
    assert PLAT.chain(platform.WORLD_PREP) == ["bench", platform.WORLD_PREP]
    files = {p.file for p in PLAT.tier_files(platform.WORLD_PREP) if p.kind == "mod"}
    bench = {p.file for p in PLAT.tier_files("bench") if p.kind == "mod"}
    assert files - bench == {"Chunky-Fabric-1.5.3.jar"}
    with pytest.raises(platform.PlatformError, match=r"fix: one of bench, .*worldPrep"):
        PLAT.chain("absent")


# Chunky's wait and the kill on a fake game: each command's answer and the latest.log lines it
# prints come from a script.


class FakeProcess:
    returncode = None

    def poll(self) -> None:
        return None


class FakeLaunched:
    process = FakeProcess()


class FakeClient:
    def __init__(self, script) -> None:
        self.script = script
        self.sent: list[str] = []
        self.lines: list[str] = []
        self.ticks: list[int] = []

    def command(self, text: str, timeout: float = 10.0, check: bool = True) -> dict:
        self.sent.append(text)
        answer, lines = self.script(text, self)
        self.lines += lines
        return answer

    def ticks_step(self, n: int, timeout: float) -> dict:
        self.ticks.append(n)
        return {"ticks": n}


class FakeSession:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.launched = FakeLaunched()
        self.said: list[str] = []

    def step(self, name, call, show=None):
        return call()

    def say(self, text: str) -> None:
        self.said.append(text)


class FakeTail:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def poll(self) -> list[str]:
        found, self.client.lines = self.client.lines, []
        return found

    def unread(self, lines: list[str]) -> None:
        self.client.lines = lines + self.client.lines


OK = {"succeeded": True, "messages": [], "failures": []}
W = "minecraft:the_end"
TASK = world.selections(BENCH)[2]
STARTED = f"[CHAT] [Chunky] Task started in {W} for the square region centered at 57, -19."


def chat_update(n: int, percent: str) -> str:
    return f"[CHAT] Task running for {W}. Processed: {n} chunks ({percent}%), ETA: 0:00:01"


def finished(n: int, percent: str, total: str) -> str:
    return f"[x] Task finished for {W}. Processed: {n} chunks ({percent}%), Total time: {total}"


def fake_prep(monkeypatch, script) -> tuple[world.Prep, FakeClient, list[str]]:
    for name, value in (("STALL", 0.3), ("PROGRESS_ASK", 0.05), ("POLL", 0.01)):
        monkeypatch.setattr(world, name, value)
    monkeypatch.setattr(world, "ECHO_TIMEOUT", 1.0)
    echoes = dict(TASK.commands())

    def answer(text: str, client: FakeClient):
        if text.startswith("/chunky world "):
            return OK, [f"[CHAT] [Chunky] World changed to {text.split()[-1]}."]
        if text in echoes:
            return OK, [f"[CHAT] [Chunky] {echoes[text]}x"]
        return script(text, client)

    client = FakeClient(answer)
    s = FakeSession(client)
    return world.Prep(s, FakeTail(client), {}), client, s.said  # type: ignore[arg-type]


def test_a_task_ends_at_the_consoles_finished_line(monkeypatch) -> None:
    done = "[Server thread/INFO]: [Chunky] " + finished(1369, "100.00", "0:00:41")[4:]

    def script(text, client):
        return OK, [STARTED, done] if text == "/chunky start" else []

    p, _, _ = fake_prep(monkeypatch, script)
    found = world.run_task(p, TASK, lambda: None)
    assert found["done"]["from"] == "console" and found["done"]["chunks"] == 1369
    assert found["unfrozen"] is False and found["done"]["seconds"] == 41


def test_without_console_lines_the_end_is_read_from_chunky_progress(monkeypatch) -> None:
    """P9's other branch: only chat answers reach latest.log."""
    asked = {"progress": 0}

    def script(text, client):
        if text == "/chunky start":
            return OK, [STARTED]
        if text == "/chunky progress":
            asked["progress"] += 1
            if asked["progress"] == 1:
                return OK, [chat_update(900, "65.74")]
            return OK, ["[CHAT] [Chunky] No tasks running."]
        if text == "/chunky continue":
            return OK, ["[CHAT] [Chunky] No tasks to continue."]
        return OK, []

    p, client, _ = fake_prep(monkeypatch, script)
    found = world.run_task(p, TASK, lambda: None)
    assert found["done"]["from"] == "chunky progress" and "/chunky continue" in client.sent
    assert found["updatesFromConsole"] == 0


def test_a_stopped_task_found_by_chunky_continue_is_awaited_again(monkeypatch) -> None:
    state = {"progress": 0}

    def script(text, client):
        if text == "/chunky start":
            return OK, [STARTED]
        if text == "/chunky progress":
            state["progress"] += 1
            if state["progress"] == 2:
                return OK, ["[CHAT] No tasks running."]
            return OK, [chat_update(10 * state["progress"], "1.00")]
        if text == "/chunky continue":
            return OK, [f"[CHAT] Task continuing for {W}.", finished(1369, "100.00", "0:01:00")]
        return OK, []

    p, _, _ = fake_prep(monkeypatch, script)
    assert world.run_task(p, TASK, lambda: None)["done"]["from"] == "console"


def test_a_task_without_progress_is_unfrozen_once_then_stops_prep(monkeypatch) -> None:
    def script(text, client):
        if text == "/chunky start":
            return OK, [STARTED]
        return OK, [chat_update(5, "0.37")] if text == "/chunky progress" else []

    p, _, said = fake_prep(monkeypatch, script)
    unfrozen: list[bool] = []
    with pytest.raises(world.WorldError, match=r"frozen nor unfrozen.*section 7"):
        world.run_task(p, TASK, lambda: unfrozen.append(True))
    assert unfrozen == [True] and "unfreezing (D45)" in said[0]


def test_a_finished_line_short_of_every_chunk_stops_prep(monkeypatch) -> None:
    short = finished(900, "65.74", "0:00:10")

    def script(text, client):
        return OK, [STARTED, short] if text == "/chunky start" else []

    p, _, _ = fake_prep(monkeypatch, script)
    with pytest.raises(world.WorldError, match=r"finished at 65\.74 %"):
        world.run_task(p, TASK, lambda: None)


def test_a_missing_echo_names_what_chunky_said(monkeypatch) -> None:
    p, client, _ = fake_prep(monkeypatch, lambda text, client: (OK, []))
    client.script = lambda text, c: (OK, ["[CHAT] [Chunky] Usage: /chunky world <world>"])
    with pytest.raises(world.WorldError, match="Usage: /chunky world"):
        world.run_task(p, TASK, lambda: None)


def counts(full: list[int], others: list[int]):
    """A script answering the kill's counts in turn: everything it selects, and all but debris
    ("Test failed" for none)."""

    def script(text, client):
        if text.startswith("/execute if entity"):
            n = (others if "type=!minecraft:item" in text else full).pop(0)
            if n == 0:
                return {"succeeded": False, "messages": [], "failures": ["Test failed"]}, []
            return {"succeeded": True, "messages": [f"Test passed. Count: {n}"], "failures": []}, []
        return {"succeeded": True, "messages": ["Killed 3 entities"], "failures": []}, []

    return script


def kill_prep(client: FakeClient) -> world.Prep:
    return world.Prep(FakeSession(client), FakeTail(client), {})  # type: ignore[arg-type]


VIEW = {v["id"]: v for v in BENCH["views"]}


def test_ticks_follow_only_a_kill_that_took_more_than_debris(monkeypatch) -> None:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    client = FakeClient(counts([30, 3, 0, 2, 0, 0], [25, 0, 0]))
    found = world.clear_view(kill_prep(client), VIEW["entities"])
    assert (found["kills"], found["ticks"]) == (3, 1) and client.ticks == [world.KILL_TICKS]
    assert sum(text.startswith("/kill") for text in client.sent) == 3


def test_debris_beside_the_dragon_fight_is_killed_without_ticks(monkeypatch) -> None:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    client = FakeClient(counts([2, 0, 0], [0]))
    found = world.clear_view(kill_prep(client), VIEW["end_dragon"])
    assert found["kills"] == 1 and not client.ticks


def test_a_mob_beside_the_dragon_fight_stops_prep_before_any_kill() -> None:
    client = FakeClient(counts([1], [1]))
    with pytest.raises(world.WorldError, match="nothing was killed; fix: the user clears"):
        world.clear_view(kill_prep(client), VIEW["end_dragon"])
    assert not any(text.startswith("/kill") for text in client.sent) and not client.ticks


def test_a_kill_that_never_clears_stops_after_its_rounds(monkeypatch) -> None:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    rounds = world.KILL_ROUNDS
    client = FakeClient(counts([4] * (rounds + 1), [0] * rounds))
    with pytest.raises(world.WorldError, match=f"4 entities left after {rounds} kills"):
        world.clear_view(kill_prep(client), VIEW["cave"])
    assert not client.ticks  # debris alone: never a tick


def test_the_selectors_split_debris_from_the_rest() -> None:
    assert world.selector(debris=False) == (
        "@e[type=!minecraft:player,type=!minecraft:ender_dragon,type=!minecraft:end_crystal,"
        "type=!minecraft:item,type=!minecraft:experience_orb,type=!minecraft:falling_block,"
        "tag=!optilux_bench,distance=..256]"
    )
