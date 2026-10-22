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
from conftest import copy_config

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
    copy_config(tmp_path)
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


def test_an_end_views_function_also_sets_the_ends_own_clock() -> None:
    """plans/m3.md P22, D56: the End flash follows the End's clock, which `/time` names with
    `of`; the overworld's and the Nether's views leave it alone."""
    for view in record.every_view(BENCH):
        lines = world.view_function(view, "bench_263").decode("utf-8").splitlines()
        clock = [line for line in lines if "the_end" in line]
        if view["dim"] == world.END:
            assert clock == [f"time of minecraft:the_end set {view['time']}"], view["id"]
            assert lines[-2:] == [clock[0], "return 1"]
        else:
            assert clock == [] and lines[-1] == "return 1", view["id"]
    assert sum(v["dim"] == world.END for v in BENCH["views"]) == 2  # end_dragon, end_city


def test_the_ends_clock_is_read_from_the_games_own_words() -> None:
    said = answer(True, ["Clock minecraft:the_end is at 6000 tick(s)"], [])
    assert world.parse_clock(said) == 6000
    for bad in (
        answer(True, ["Clock minecraft:overworld is at 6000 tick(s)"], []),
        answer(True, ["The time is 6000"], []),
        answer(False, [], ["Unknown clock"]),
    ):
        with pytest.raises(world.WorldError, match="fix: read"):
            world.parse_clock(bad)


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
    every = record.every_view(BENCH)  # the coverage views' too (plans/m3.md D64)
    assert len(every) == 14 and sorted(files) == sorted(
        ["pack.mcmeta"] + [f"data/optilux/function/view/{v['id']}.mcfunction" for v in every]
    )
    live = tmp_path / "w"
    tree(live / "datapacks" / "optilux", {"data/optilux/function/view/gone.mcfunction": b"x"})
    found = world.write_pack(live, files)
    assert listing(live / "datapacks" / "optilux") == files
    assert found["pruned"] == ["data/optilux/function/view/gone.mcfunction"]
    assert len(found["written"]) == 15
    again = world.write_pack(live, files)
    assert (again["written"], again["pruned"]) == ([], [])


# Chunky.


def test_chunky_selections_cover_the_views_plus_the_render_distance() -> None:
    found = world.selections(BENCH)
    assert [(s.world, s.shape, s.x, s.z, s.radius_x, s.radius_z) for s in found] == [
        ("minecraft:overworld", "rectangle", -26, 658, 629, 702),  # x -655..603, z -44..1360
        ("minecraft:the_nether", "rectangle", 111, -153, 408, 457),
        ("minecraft:the_end", "square", 57, -19, 289, 289),
        ("minecraft:the_end", "square", 318, 1055, 289, 289),
    ]
    assert found[2].views == ("end_dragon",) and found[3].views == ("end_city",)
    assert len(found[0].views) == 10 and set(found[1].views) == {"nether_crimson", "nether_soul"}
    assert found[0].views[7:] == ("coverage_items", "coverage_mobs", "coverage_beacon")
    for task in found:
        for view in record.every_view(BENCH):
            if view["id"] in task.views:
                assert abs(view["x"] - task.x) + world.MARGIN <= task.radius_x
                assert abs(view["z"] - task.z) + world.MARGIN <= task.radius_z


def test_chunky_commands_carry_the_lines_it_answers_with() -> None:
    overworld, _, end, _ = world.selections(BENCH)
    assert overworld.commands() == [
        ("/chunky world minecraft:overworld", "World changed to "),
        ("/chunky shape rectangle", "Shape changed to "),
        ("/chunky center -26 658", "Center changed to -26, 658."),
        ("/chunky radius 629 702", "Radius changed for x to 629, and for z to 702."),
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


def held() -> dict:
    """coverage_counts' answer for a site holding all its content."""
    x, y, z = world.SIGN
    return {
        "entities": {item.name: 1 for item in world.CONTENT},
        "blocks": dict.fromkeys((name for name, _ in world.block_tests()), True),
        "sign": [f'{x}, {y}, {z} has the following block data: "Optilux"'],
    }


def test_the_counts_prep_must_hold() -> None:
    mobs = [{"name": f"m{i}", "x": 0.0, "y": 0.0, "z": float(i)} for i in range(7)]
    done = {"entities": {"tagged": 7}, "end_dragon": {"endCrystals": 10}}
    assert world.check_counts(BENCH, done, mobs, mobs, held()) == []
    moved = [*mobs[:6], {**mobs[6], "z": 9.5}]
    assert "moved" in world.check_counts(BENCH, done, mobs, moved, held())[0]
    short = {"entities": {"tagged": 6}, "end_dragon": {"endCrystals": 9}}
    assert len(world.check_counts(BENCH, short, mobs, mobs, held())) == 2
    assert world.check_counts(BENCH, done, mobs, mobs) == [
        "coverage: the site was not counted after the sweep"
    ]
    perf = {k: v for k, v in BENCH.items() if k != record.COVERAGE}
    assert world.check_counts(perf, done, mobs, mobs) == []  # no list, nothing to count


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
        self.sent.append(f"ticks {n}")  # its place among the commands
        return {"ticks": n}

    def camera_place(self, pose: dict, timeout: float) -> dict:
        self.sent.append(f"camera.place {pose['x']} {pose['z']}")
        return {"pose": dict(pose), "arrivedSeconds": 0.0}

    def ready(self, stable: int, settle: float, timeout: float) -> dict:
        return {"seconds": settle}

    def hud_set(self, hide_gui: bool) -> dict:
        self.sent.append(f"hideGui {hide_gui}")
        return {"hideGui": hide_gui}


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


# The coverage site (plans/m3.md D64).

SUITE = json.loads((REPO_ROOT / platform.SUITE).read_text(encoding="utf-8"))
COVER = {v["id"]: v for v in BENCH[record.COVERAGE]}


def test_the_site_holds_suite_jsons_content_inside_its_box_beneath_its_views() -> None:
    """Each of suite.json coverageViews' items has its part: three NoAI mobs, the armor stand,
    the item frame, the dropped item, the enchanted item, the sign, the beacon on its base, the
    campfire, a view with the hand; each entity inside the site's box on the floor, each view
    over the floor."""
    names = {item.name for item in world.CONTENT} | {name for name, *_ in world.BLOCKS}
    assert SUITE["coverageViews"]["content"] == [
        "NoAI mobs",
        "armor stand",
        "item frame",
        "dropped item",
        "sign text",
        "beacon",
        "enchanted item",
        "held torch (creative mode; spectator shows no hand)",
        "particle source",
    ]
    assert {"armor stand", "item frame", "dropped item", "enchanted item"} <= names
    assert {"sign", "beacon", "campfire"} <= names
    mobs = [item for item in world.CONTENT if "NoAI:1b" in item.data]
    assert [item.name for item in mobs] == ["mooshroom", "polar bear", "fox"]
    assert [vid for vid, v in COVER.items() if v["hand"]] == ["coverage_beacon"]
    (_, (x0, y0, z0), (x1, _, z1), _) = world.FILLS[0]
    box = f"x={x0},y={y0},z={z0},dx={x1 - x0},dy=10,dz={z1 - z0}"
    assert box == world.SITE
    for item in world.CONTENT:
        x, y, z = item.pos
        assert x0 <= x <= x1 + 1 and z0 <= z <= z1 + 1 and y0 + 1 <= y <= y0 + 2, item.name
    for name, (x, y, z), *_ in world.BLOCKS:
        assert x0 <= x <= x1 and z0 <= z <= z1 and y == y0 + 1, name
    for view in COVER.values():
        assert view["dim"] == world.OVERWORLD and view["y"] > y0 + 1
        assert x0 <= view["x"] <= x1 and z0 <= view["z"] <= z1, view["id"]


def test_the_build_commands_carry_the_tag_and_decimal_positions() -> None:
    commands = dict(world.coverage_commands())
    assert list(commands)[:6] == ["floor", "beacon base", "beacon", "campfire", "planks", "sign"]
    assert commands["floor"] == "/fill 306 100 1061 322 100 1077 minecraft:smooth_stone"
    assert commands["beacon base"] == "/fill 313 100 1063 315 100 1065 minecraft:iron_block"
    assert commands["sign"] == (
        "/setblock 313 101 1072 minecraft:oak_sign[rotation=8]"
        '{front_text:{messages:["Optilux","coverage","",""]}}'
    )
    assert commands["mooshroom"] == (
        '/summon minecraft:mooshroom 308.0 101.0 1066.5 {Tags:["optilux_bench"],'
        "PersistenceRequired:1b,Rotation:[-90.0f,0.0f],NoAI:1b,Silent:1b}"
    )
    assert commands["dropped item"] == (
        '/summon minecraft:item 317.0 101.0 1072.0 {Tags:["optilux_bench"],'
        'PersistenceRequired:1b,Rotation:[0.0f,0.0f],Item:{id:"minecraft:diamond",count:1},'
        "NoGravity:1b,Age:-32768s,PickupDelay:32767s}"
    )
    assert "Facing:2b,Fixed:1b," in commands["item frame"]
    assert "block_pos:[I;315,101,1072]" in commands["item frame"]
    for item in world.CONTENT:
        # A whole number would be centred on its block by the command (x 308 summons at 308.5).
        assert all("." in part for part in commands[item.name].split()[2:5]), item.name
        assert item.selector().startswith(f"@e[type={item.kind},tag=optilux_bench,x=306,")
    assert world.sign_command() == "/data get block 313 101 1072 front_text.messages[0]"
    tests = dict(world.block_tests())
    assert len(tests) == 4 + 9 + 4
    assert tests["campfire at 311 101 1064"] == (
        "/execute if block 311 101 1064 minecraft:campfire[lit=true]"
    )


def test_a_block_test_is_read_from_the_games_own_words() -> None:
    assert world.parse_test(answer(True, ["Test passed"], [])) is True
    assert world.parse_test(answer(False, [], ["Test failed"])) is False
    for bad in (answer(True, ["Test passed. Count: 1"], []), answer(False, [], ["Unknown block"])):
        with pytest.raises(world.WorldError, match="fix: read"):
            world.parse_test(bad)


def test_the_site_must_hold_one_of_each_every_block_and_the_signs_text() -> None:
    assert world.coverage_problems(held()) == []
    found = held()
    found["entities"].update(fox=0, mooshroom=2)
    found["blocks"]["beacon at 314 101 1064"] = False
    found["sign"] = ['313, 101, 1072 has the following block data: ""']
    assert world.coverage_problems(found) == [
        "coverage: 2 mooshroom counted, not 1",
        "coverage: 0 fox counted, not 1",
        "coverage: no beacon at 314 101 1064",
        "coverage: the sign reads ['313, 101, 1072 has the following block data: \"\"'], not "
        "'Optilux'",
    ]


def counted(n: int) -> dict:
    if n == 0:
        return answer(False, [], ["Test failed"])
    return answer(True, [f"Test passed. Count: {n}"], [])


def site(old: tuple[int, ...] = (0,), unchanged: bool = False, failing: str = "", kept: int = 0):
    """A script for the coverage step: the bench-tagged entities in the site's box read in turn
    from `old` (its last repeated, as entities load after their chunks), `kept` once they are
    killed; nothing for the kill, each build command done (or its block already as asked), one of
    each entity, every block and the sign's text."""
    reads = list(old)

    def script(text: str, client: FakeClient):
        if text.startswith("/execute if entity @e[tag=optilux_bench,x="):
            if any(sent.startswith("/kill @e[tag=optilux_bench,x=") for sent in client.sent):
                return counted(kept), []
            return counted(reads.pop(0) if len(reads) > 1 else reads[0]), []
        if text.startswith("/execute if entity @e[type=!"):  # the kill's
            return counted(0), []
        if text.startswith("/execute if entity"):
            return counted(1), []
        if text.startswith("/execute if block"):
            return answer(True, ["Test passed"], []), []
        if text.startswith("/data get block"):
            return answer(True, ['313, 101, 1072 has the following block data: "Optilux"'], []), []
        if failing and text.startswith(failing):
            return answer(False, [], ["Unable to summon entity"]), []
        if unchanged and text.startswith("/fill"):
            return answer(False, [], ["No blocks were filled"]), []
        if unchanged and text.startswith("/setblock"):
            return answer(False, [], ["Could not set the block"]), []
        return answer(True, ["done"], []), []

    return script


def test_the_coverage_step_builds_the_site_then_counts_it(monkeypatch) -> None:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    client = FakeClient(site())
    found = world.build_coverage(kill_prep(client), COVER["coverage_items"])
    assert found["old"] == 0 and not client.ticks
    assert not any(text.startswith("/kill @e[tag=optilux_bench") for text in client.sent)
    old = [text for text in client.sent if text.startswith("/execute if entity @e[tag=")]
    assert len(old) == 1 + int(world.POSITIONS_WAIT)  # a new site: read once a second, none
    built = [text for text in client.sent if text.startswith(("/fill", "/setblock", "/summon"))]
    assert built == [text for _, text in world.coverage_commands()]
    assert client.sent[0] == "camera.place 314.5 1067.5"  # the site's chunks loaded first
    assert client.sent.index(built[0]) < client.sent.index(world.sign_command())
    assert world.coverage_problems(found["counts"]) == []


def test_a_rebuilt_site_kills_its_old_content_first_and_takes_blocks_as_they_are(
    monkeypatch,
) -> None:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    client = FakeClient(site(old=(0, 0, 7), unchanged=True))  # loaded two reads late
    found = world.build_coverage(kill_prep(client), COVER["coverage_items"])
    kill = f"/kill @e[tag=optilux_bench,{world.SITE}]"
    assert found["old"] == 7 and client.ticks == [world.KILL_TICKS]
    at = client.sent.index(kill)
    assert client.sent[at + 1] == f"ticks {world.KILL_TICKS}"
    assert at < client.sent.index(world.coverage_commands()[0][1])
    assert found["placed"]["floor"] == ["No blocks were filled"]
    client = FakeClient(site(old=(7,), kept=2))
    with pytest.raises(world.WorldError, match="2 of the old content left after its kill"):
        world.build_coverage(kill_prep(client), COVER["coverage_items"])


def test_a_build_command_that_fails_stops_prep(monkeypatch) -> None:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    client = FakeClient(site(failing="/summon minecraft:fox"))
    with pytest.raises(world.WorldError, match=r"coverage: fox: /summon minecraft:fox .* did not"):
        world.build_coverage(kill_prep(client), COVER["coverage_items"])


def prep_view(
    monkeypatch, client: FakeClient, view: dict, ramped: str | None = None
) -> tuple[dict, str | None]:
    monkeypatch.setattr(world.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(world, "frame", lambda p, view, raw, resolution: {"file": "f"})
    prep = kill_prep(client)
    return world.prepare_view(prep, view, ramped, world.OVERWORLD, SUITE, Path("raw"))


def test_a_coverage_view_steps_its_ticks_at_its_pose_and_shows_its_hand(monkeypatch) -> None:
    client = FakeClient(site())
    facts, ramped = prep_view(monkeypatch, client, COVER["coverage_beacon"])
    assert client.ticks == [SUITE["capture"]["ticksAfterWeatherChange"], 100]
    assert (facts["viewTicks"], facts["gui"], ramped) == (100, True, "clear")
    kinds = ("camera.place", "ticks", "hideGui", "/gamemode")
    shown = [t for t in client.sent if t.startswith(kinds)]
    assert shown == [
        "camera.place 314.5 1071.0",
        f"ticks {SUITE['capture']['ticksAfterWeatherChange']}",
        "ticks 100",  # its own, with the camera there, after the weather's
        "/gamemode creative",
        "hideGui False",
        "hideGui True",
        "/gamemode spectator",
    ]
    client = FakeClient(site())
    facts, _ = prep_view(monkeypatch, client, COVER["coverage_items"])
    assert "viewTicks" not in facts and facts["gui"] is False


def clocked(text: str, client: FakeClient):
    """An End view's script: the End's clock at 6000, nothing for the kill, no dragon."""
    if text == "/time of minecraft:the_end query time":
        return answer(True, ["Clock minecraft:the_end is at 6000 tick(s)"], []), []
    if text.startswith("/execute if entity @e[type=minecraft:ender_dragon"):
        return counted(0), []
    return site()(text, client)


def test_a_views_own_ticks_never_step_beside_the_dragon_fight(monkeypatch) -> None:
    client = FakeClient(clocked)
    with pytest.raises(world.WorldError, match="100 ticks would be stepped beside the dragon"):
        prep_view(monkeypatch, client, {**VIEW["end_dragon"], "hand": False, "ticks": 100})
    assert not client.ticks


def test_a_views_own_ticks_outside_the_overworld_leave_its_ramp_unknown(monkeypatch) -> None:
    """Every view's function sets the overworld's weather; ticks stepped in another dimension
    move it toward that weather, so the overworld's ramp is no longer known."""
    client = FakeClient(clocked)
    view = {**VIEW["end_city"], "hand": False, "ticks": 20}
    assert prep_view(monkeypatch, client, view, "thunder")[1] is None and client.ticks == [20]
    assert prep_view(monkeypatch, FakeClient(clocked), view, "clear")[1] == "clear"


def test_an_end_view_reads_the_ends_clock_back_after_its_function(monkeypatch) -> None:
    def script(time: int):
        def answer_it(text: str, client: FakeClient):
            if text == "/time of minecraft:the_end query time":
                return answer(True, [f"Clock minecraft:the_end is at {time} tick(s)"], []), []
            crystals = text.startswith("/execute if entity @e[type=minecraft:end_crystal,")
            if text.startswith("/execute if entity"):
                return counted(10 if crystals else 0), []
            return answer(True, ["done"], []), []

        return answer_it

    end_city = VIEW["end_city"]
    facts, _ = prep_view(monkeypatch, FakeClient(script(6000)), end_city)
    assert facts["endClock"] == 6000
    with pytest.raises(world.WorldError, match="the End's clock reads 0 after the view's function"):
        prep_view(monkeypatch, FakeClient(script(0)), end_city)
