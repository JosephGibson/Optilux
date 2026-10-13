"""The measured session (docs/plans/m2.md M2.P05): the schedule and its reloads, the laps and the
settle; each validity flag (the cut and the summaries: tests/test_presentmon.py); the variant
files' bytes and the twins; the spec's refusals; D42's machine check; and the
runner end to end on a fake game (the protocol fake, a fake PresentMon): a quick run of the
baseline and its twin, the focus end, a failed selftest ending the session, and a run killed
mid-session leaving an aborted record through the next run's orphan finisher (D41)."""

import copy
import hashlib
import json
import os
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest

from optilux import (
    REPO_ROOT,
    cli,
    launch,
    measure,
    modclient,
    modfake,
    platform,
    presentmon,
    record,
    session,
    world,
)
from optilux.verbs import run as run_verb

PLAT = platform.load(REPO_ROOT)
SUITE = json.loads((REPO_ROOT / platform.SUITE).read_text(encoding="utf-8"))
PACK = launch.reference_pack(PLAT).file
VIEWS, _ = record.load_views(REPO_ROOT, "bench_263")
FIXTURES = Path(__file__).parent / "fixtures" / "run"
FLIP = measure.INDEPENDENT_FLIP
PLAYED = record.profile_options(REPO_ROOT, SUITE, "played")


# The schedule, its reloads, the laps and the settle.


def variant(vid: str, role: str = "candidate", timers: bool = False) -> measure.Variant:
    return measure.Variant(vid, role, f"{vid}.zip", PACK, "played", dict(PLAYED), timers)


def test_the_schedule_brackets_each_candidate_between_two_baselines() -> None:
    found = [variant("baseline", "baseline"), variant("c1"), variant("twin", "twin")]
    order = [(v.id, r) for v, r in measure.schedule(found, 2)]
    assert order == [
        ("baseline", 1),
        ("c1", 1),
        ("baseline", 1),
        ("twin", 1),
        ("baseline", 1),
        ("c1", 2),
        ("baseline", 2),
        ("twin", 2),
        ("baseline", 2),
    ]


def test_the_reload_budget_counts_selftests_reload_and_the_warm_up_pass() -> None:
    """P12's figures: full mode with 5 candidates and the twin plans 288, quick 44; a calibration
    session of 5 twins 244 and 38; the exit's quick run of the baseline and its twin 14."""
    assert record.planned_reloads(11, 6, 2) == 288
    assert record.planned_reloads(3, 6, 1) == 44
    assert record.planned_reloads(11, 5, 2) == 244
    assert record.planned_reloads(3, 5, 1) == 38
    assert record.planned_reloads(3, 1, 1) == 14


def ticks(views: list[dict]) -> tuple[list[list[str]], int]:
    """Two laps as the session runs them: the order of each, and the weather ticks stepped."""
    ramped, stepped, laps = None, 0, []
    for _ in range(2):
        order = measure.lap(views, ramped)
        laps.append([v["id"] for v in order])
        for view in order:
            if view["dim"] == session.OVERWORLD and ramped != view["weather"]:
                stepped += 1
                ramped = view["weather"]
    return laps, stepped


def test_the_laps_change_the_weather_three_times_at_most_never_outside_the_overworld() -> None:
    laps, stepped = ticks(VIEWS["views"])
    clear = ["forest_noon", "ocean_sunset", "cave", "night", "underwater", "entities"]
    rest = ["nether_crimson", "nether_soul", "end_dragon", "end_city"]
    assert laps[0] == [*clear, "rain", *rest]
    assert laps[1] == ["rain", *clear, *rest]  # the thunder the first lap left comes first
    assert stepped == 3  # into clear, into thunder, back: never at an End view
    quick = [v for v in VIEWS["views"] if v["id"] in SUITE["modes"]["quick"]["views"]]
    laps, stepped = ticks(quick)
    assert laps == [["forest_noon", "nether_crimson", "end_dragon"]] * 2 and stepped == 1


def test_the_settle_is_the_largest_that_applies() -> None:
    capture = SUITE["capture"]
    assert measure.settle_for(capture, False, False) == capture["settleS"]["afterReload"]
    assert measure.settle_for(capture, True, False) == 1.5
    assert measure.settle_for(capture, True, True) == capture["settleS"]["afterDimensionChange"]


# The window cut: rows of frames n = 100..140, frame n's HEAD stamp at n x 7 ms, its swap stamp
# 0.1 ms before, its row's CPU start `offset` ms after the HEAD stamp.

HEADER = (
    "Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,"
    "AllowsTearing,PresentMode,CPUStartQPCTime,FrameTime,CPUBusy,CPUWait,GPULatency,GPUTime,"
    "GPUBusy,GPUWait,DisplayLatency,DisplayedTime,AnimationError,AnimationTime,MsFlipDelay,"
    "AllInputToPhotonLatency,ClickToPhotonLatency"
)


def row(n: int, offset: float = 0.05, pid: int = 4242, **values: Any) -> dict:
    found = {name: "0" for name in HEADER.split(",")}
    found.update(
        Application="javaw.exe",
        ProcessID=str(pid),
        SwapChainAddress="0x1",
        PresentMode=FLIP,
        CPUStartQPCTime=f"{n * 7 + offset:.4f}",
        FrameTime="7.0000",
        GPUBusy="6.9000",
        GPULatency="14.0000",
    )
    found.update({key: str(value) for key, value in values.items()})
    return found


def mark(n: int) -> dict:
    return {
        "frameIndex": n,
        "sinceReload": n,
        "qpcNs": n * 7_000_000,
        "swapQpcNs": n * 7_000_000 - 100_000,
    }


def line_of(rows: list[dict]) -> presentmon.Timeline:
    return presentmon.timeline(rows, 4242)


# The summaries and each validity flag.


def test_a9s_borderless_window_raises_every_flag_that_shows_it() -> None:
    """0.01.09's A9 ran borderless with PNG writers: present mode and CPU-bound frames."""
    frames = json.loads((FIXTURES / "a9-5-frames.json").read_text(encoding="utf-8"))["frames"]
    _, rows = presentmon.read_rows(FIXTURES / "a9-5-presentmon.csv", complete=True)
    line = presentmon.timeline(rows, int(rows[0]["ProcessID"]))
    found = presentmon.cut_window(line, frames[10], frames[110], 100)
    summary = presentmon.summary(found["rows"])
    flags = measure.flags_of("baseline", summary, found, [], SUITE["validity"])
    assert "presentMode" in flags and "cpuLimited" in flags and "cut" not in flags


def good() -> tuple[dict, dict]:
    rows = [row(n) for n in range(100, 300)]
    cut = {"rows": rows, "edges": [0, 0], "problems": []}
    return presentmon.summary(rows), cut


FLAGS = [
    (lambda s, c: c.update(problems=["the start edge is 2 rows off"]), "baseline", "cut"),
    (lambda s, c: s.update(frames=99), "baseline", "fewFrames"),
    (lambda s, c: s.update(notNumbers=1), "baseline", "notNumbers"),
    (lambda s, c: s.update(halvesPct=3.1), "baseline", "halves"),
    (
        lambda s, c: s.update(presentModes={FLIP: 199, "Composed: Flip": 1}),
        "baseline",
        "presentMode",
    ),
    (lambda s, c: s.update(gpuBusyOverFrameTime=0.89), "baseline", "cpuLimited"),
    (lambda s, c: s.update(gpuBusyOverFrameTime=0.89), "candidate", "leftGpuBound"),
    (lambda s, c: s.update(gpuBusyOverFrameTime=0.89), "twin", "leftGpuBound"),
]


@pytest.mark.parametrize(("change", "role", "flag"), FLAGS)
def test_each_validity_flag(change, role: str, flag: str) -> None:
    summary, cut = good()
    assert measure.flags_of(role, summary, cut, [], SUITE["validity"]) == []
    change(summary, cut)
    found = measure.flags_of(role, summary, cut, [], SUITE["validity"])
    assert found == [flag]
    assert (flag in measure.INVALIDATING_FLAGS) is (flag != "leftGpuBound")


def test_an_invalidating_event_inside_the_window_flags_it_and_one_outside_does_not() -> None:
    events = [
        {"event": "reload.done", "frameIndex": 99},  # the capture's own reload, before it
        {"event": "window.end", "frameIndex": 130},
        {"event": "focus.lost", "frameIndex": 129},  # in the window's last frame
        {"event": "hook.error", "frameIndex": 130},  # in frame end, after the window
    ]
    inside = measure.window_events(events, 110, 130)
    assert [e["event"] for e in inside] == ["focus.lost"]
    summary, cut = good()
    assert measure.flags_of("baseline", summary, cut, inside, SUITE["validity"]) == ["event"]


def test_a_captured_window_holds_its_summaries_and_timer_rows() -> None:
    line = line_of([row(n) for n in range(100, 300)])
    stopped = {
        "frames": [
            {
                "frameIndex": n,
                "passes": [
                    {"name": "a", "depth": 0, "gpuNanos": 4_000_000},
                    {"name": "b", "depth": 1, "gpuNanos": 1_000_000},
                    {"name": "b", "depth": 1, "gpuNanos": 500_000},
                ],
            }
            for n in range(105, 250)
            if n != 200
        ],
        "dropped": {"late": 1, "full": 0, "overflow": 0, "lost": 0},
        "unmatchedPops": 0,
        "cutPasses": 0,
    }
    timers = measure.timers_summary(stopped, 110, 240)
    assert (timers["frames"], timers["missing"], timers["topLevelMs"]) == (129, 1, 4.0)
    assert timers["passes"] == {"a": {"depth": 0, "ms": 4.0}, "b": {"depth": 1, "ms": 1.5}}
    entry = {
        "index": 3,
        "pass": 2,
        "view": "forest_noon",
        "variant": "baseline",
        "role": "baseline",
        "round": 1,
        "settleS": 1.5,
        "window": {"start": mark(110), "end": mark(240), "frames": 130},
        "timers": timers,
    }
    found = measure.captured(entry, line, [], SUITE["validity"])
    assert (found["rows"], found["frames"], found["edges"], found["valid"]) == (
        130,
        130,
        [0, 0],
        True,
    )
    assert found["flags"] == ["timersDropped"] and found["presentMode"] == FLIP
    assert found["gpuBusyMs"] == 6.9 and found["timers"]["residualMs"] == pytest.approx(2.9)
    assert "byFrame" not in found["timers"]


# The variants and their files.


def test_the_variant_files_are_the_settings_file_and_iris_properties_naming_the_pack(
    tmp_path: Path,
) -> None:
    twin = measure.Variant("twin", "twin", f"optilux-twin1-{PACK}", PACK, "played", PLAYED, False)
    files = measure.variant_files(tmp_path, SUITE["display"], "bench", twin)
    settings = files[tmp_path / "shaderpacks" / f"optilux-twin1-{PACK}.txt"]
    assert settings == (
        b"ANISOTROPIC_FILTER=4\nATM_FOG_MULT=0.50\nBLOCK_REFLECT_QUALITY=1\nBORDER_FOG=false\n"
        b"CAVE_FOG=false\nENTITY_SHADOW=-1\nFXAA_DEFINE=-1\nLIGHTSHAFT_QUALI_DEFINE=0\n"
        b"RAIN_STYLE=2\nRP_MODE=0\nSHADER_STYLE=4\nWATER_REFLECT_QUALITY=1\n"
        b"shadowDistance=96.0\n"
    )  # the profile's own text: 0.50 keeps its zero, the pack's list holds "0.50"
    iris = files[tmp_path / "config" / "iris.properties"]
    assert (
        iris
        == launch.iris_text(launch.iris_properties(SUITE["display"], "bench", twin.pack)).encode()
    )
    assert iris.startswith(f"shaderPack=optilux-twin1-{PACK}\n".encode())


def test_the_twins_are_byte_copies_checked_by_sha512(tmp_path: Path) -> None:
    packs = tmp_path / "shaderpacks"
    packs.mkdir()
    (packs / PACK).write_bytes(b"PK\x03\x04 a pack")
    digest = hashlib.sha512(b"PK\x03\x04 a pack").hexdigest()
    found = [variant("baseline", "baseline")] + [
        measure.Variant(f"twin-{n}", "twin", f"optilux-twin{n}-{PACK}", PACK, "played", {}, False)
        for n in (1, 2)
    ]
    owned: list[Path] = []
    made = measure.make_twins(tmp_path, found, packs / PACK, digest, owned.append)
    assert [m["file"] for m in made] == [f"optilux-twin1-{PACK}", f"optilux-twin2-{PACK}"]
    assert [p.name for p in owned] == [m["file"] for m in made]  # taken before each copy
    assert (packs / f"optilux-twin2-{PACK}").read_bytes() == (packs / PACK).read_bytes()
    again: list[Path] = []
    with pytest.raises(session.RunError, match="exists in shaderpacks"):
        measure.make_twins(tmp_path, found, packs / PACK, digest, again.append)
    assert again == []  # a copy already there is not this run's: never taken, never deleted
    assert measure.remove_files(owned) == {"removed": [p.name for p in owned], "kept": []}
    assert sorted(p.name for p in packs.iterdir()) == [PACK]


def test_the_effective_options_must_equal_the_written_ones() -> None:
    base = variant("baseline", "baseline")
    values = {**PLAYED, "SHADOW_QUALITY": "2"}
    assert measure.effective_problems(base, values) == []
    moved = {**values, "ATM_FOG_MULT": "0.95", "BORDER_FOG": True}
    assert measure.effective_problems(base, moved) == [
        "ATM_FOG_MULT reads '0.95', written '0.50'",
        "BORDER_FOG reads True, written False",
    ]
    assert measure.effective_problems(base, {})[0] == "ANISOTROPIC_FILTER is no option of the pack"


# D42: the machine to itself.


def test_the_3d_engines_users_come_from_typeperf_on_the_adapter_alone() -> None:
    text = (FIXTURES / "typeperf.txt").read_text(encoding="utf-8")
    found = measure.gpu_users(text, "0x11d82")
    assert found and all(pct < measure.GPU_MAX_PCT for pct in found.values())
    assert found[14916] == pytest.approx(0.050218 / 3)  # one sample of three on this adapter
    other = measure.gpu_users(text, "0x13a2b")  # a second adapter: 13 engines of pid 14916
    assert 1180 in found and 1180 not in other and other[14916] == 0.0
    with pytest.raises(record.RecordError, match="no 3D engine of the display's adapter 0x99"):
        measure.gpu_users(text, "0x99")  # nothing read is no pass (D42)
    with pytest.raises(record.RecordError, match="no counter table"):
        measure.gpu_users("Error: No valid counters.\n", "0x11d82")


class Machine:
    """D42's readings: input seconds and the 3D engine's users per check, the clock virtual."""

    def __init__(self, checks: list[tuple[float, dict[int, float]]]) -> None:
        self.checks = checks
        self.now = 0.0
        self.slept: list[float] = []

    def idle_seconds(self) -> float:
        return self.checks[0][0]

    def gpu_engine(self, samples: int) -> str:
        users = self.checks.pop(0)[1] if len(self.checks) > 1 else self.checks[0][1]
        names = [
            f"\\\\PC\\GPU Engine(pid_{p}_luid_0x00000000_0x00011D94_phys_0_eng_0_engtype_3D)"
            "\\Utilization Percentage"
            for p in users
        ]
        values = [f"{v:.6f}" for v in users.values()]
        lines = ['"(PDH-CSV 4.0)",' + ",".join(f'"{n}"' for n in names)]
        lines += ['"t",' + ",".join(f'"{v}"' for v in values)] * samples
        return "\n".join(lines) + "\n"

    def processes(self) -> list:
        return [launch.ProcessInfo(77, "obs64.exe", None, None, [])]

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_the_machine_check_waits_for_idle_input_and_a_free_gpu(monkeypatch) -> None:
    host = Machine([(5.0, {1: 0.3}), (40.0, {1: 0.3, 77: 12.0}), (40.0, {1: 0.3})])
    said: list[str] = []
    found = measure.machine_to_itself(host, "0x11d94", said.append)  # type: ignore[arg-type]
    assert found["checks"] == 3 and found["idleSeconds"] == 40.0
    assert host.slept[0] == 25.0  # until 30 s without input
    assert "obs64.exe (pid 77) at 12.0 % of the 3D engine" in said[1]
    busy = Machine([(100.0, {77: 50.0})])
    with pytest.raises(record.RecordError) as refused:
        measure.machine_to_itself(busy, "0x11d94", said.append)  # type: ignore[arg-type]
    assert "obs64.exe (pid 77) at 50.0 %" in str(refused.value) and "fix:" in str(refused.value)
    assert busy.now >= measure.MACHINE_WAIT


# The spec of a measured run.


@pytest.fixture
def bench_root(tmp_path: Path) -> tuple[Path, Path]:
    """A root with the config, bench_263's snapshot folder and its live world."""
    root = tmp_path / "root"
    shutil.copytree(REPO_ROOT / "config", root / "config")
    (root / record.SNAPSHOTS / "bench_263").mkdir(parents=True)
    saves = root / "saves"
    (saves / "bench_263").mkdir(parents=True)
    (saves / "bench_263" / "level.dat").write_bytes(b"L")
    return root, saves


def measured(**changes: Any) -> dict:
    found = {
        "name": "m2-quick-test",
        "kind": "measurement",
        "mode": "quick",
        "views": "bench_263",
        "world": "bench_263",
        "variants": [{"id": "baseline", "pack": PACK, "profile": "played"}],
        "tier": "bench",
        "resourcePacks": "standard",
        "calibration": None,
        "notes": "a fixture",
    }
    found.update(changes)
    return found


def test_a_measured_spec_carries_its_variants_views_and_reloads(bench_root) -> None:
    root, saves = bench_root
    spec = record.check_spec(root, measured(), PLAT, SUITE, saves, PACK)
    assert (spec.mode, spec.calibration, spec.heap, spec.items) == ("quick", None, False, ())
    assert spec.view_ids == ("forest_noon", "nether_crimson", "end_dragon")
    assert spec.planned == 14 and spec.variants[0]["options"] == PLAYED
    found = measure.variants(spec, SUITE)
    assert [(v.id, v.role, v.pack) for v in found] == [
        ("baseline", "baseline", PACK),
        ("twin", "twin", f"optilux-twin1-{PACK}"),
    ]
    shadows = {
        "id": "shadows-off",
        "pack": PACK,
        "profile": "played",
        "options": {"SHADOW_QUALITY": "-1"},
    }
    full = record.check_spec(
        root,
        measured(mode="full", variants=[measured()["variants"][0], shadows]),
        PLAT,
        SUITE,
        saves,
        PACK,
    )
    assert full.planned == record.planned_reloads(11, 2, 2) and len(full.view_ids) == 11
    assert (spec.rounds, full.rounds) == (1, 2)  # the modes' own R
    assert full.variants[1]["options"] == {**PLAYED, "SHADOW_QUALITY": "-1"}
    calibration = record.check_spec(root, measured(kind="calibration"), PLAT, SUITE, saves, PACK)
    twins = measure.variants(calibration, SUITE)
    assert [v.id for v in twins] == ["baseline", "twin-1", "twin-2", "twin-3", "twin-4", "twin-5"]
    assert calibration.planned == 38


BASE = {"id": "baseline", "pack": PACK, "profile": "played"}
TIMED = {**BASE, "id": "timed", "timers": True}
SPEC_REFUSALS = [
    (dict(mode=None), "measures a mode's schedule"),
    (dict(mode="slow"), "one of quick, full"),
    (dict(calibration="quick-abc"), "no calibration exists before"),
    (dict(items=["A1"]), "takes none"),
    (dict(reloads=10), "F4's acceptance table"),
    (dict(heap="yes"), "true or false"),
    (dict(treatment="mods"), "JVM track"),
    (dict(variants=[]), "lists none"),
    (dict(variants=[{**BASE, "pack": "other.zip"}]), "the reference pack"),
    (dict(variants=[{**BASE, "id": "twin"}]), "starts with twin"),
    (dict(variants=[BASE, BASE]), "listed twice"),
    (dict(variants=[{**BASE, "profile": "fancy"}]), "profile 'fancy'"),
    (dict(variants=[{**BASE, "options": {"SHADOW_QUALITY": -1}}]), "the pack's own text"),
    (dict(variants=[{**BASE, "options": {"BAD KEY": "1"}}]), "no option name"),
    (dict(variants=[{**BASE, "timers": 1}]), "timers 1"),
    (dict(variants=[{**BASE, "seed": 1}]), "unknown ['seed']"),
    (dict(kind="calibration", variants=[BASE, TIMED]), "the baseline alone"),
    (dict(kind="calibration", variants=[{**BASE, "timers": True}]), "timer twins, M4's"),
    (dict(kind="calibration", heap=True), "the budget runs read it"),
    (dict(kind="acceptance", items=[]), "some of A8, A11"),
    (dict(kind="acceptance", items=["A8"]), "A8 compares the baseline"),
    (dict(kind="acceptance", items=["A11"], variants=[BASE, TIMED]), "A11 times every variant"),
    (dict(kind="acceptance", items=["A2"]), "takes A8, A11"),
    (dict(rounds=1), "a budget run's"),
    (dict(dimensions=["minecraft:overworld"]), "a budget run's"),
    (dict(kind="acceptance", items=["A8"], variants=[BASE, TIMED], heap=True, rounds=1), "budget"),
    (dict(heap=True, rounds=0), "a positive count"),
    (dict(heap=True, rounds=True), "a positive count"),
    (dict(heap=True, dimensions=[]), "each once"),
    (dict(heap=True, dimensions=["minecraft:overworld"] * 2), "each once"),
    (dict(heap=True, dimensions=["overworld"]), "each once"),
    (dict(keepViews=["forest_noon"]), "a budget run's"),
    (dict(alone=True), "a budget run's"),
    (dict(windows=False), "a budget run's"),
    (dict(heap=True, keepViews=[]), "each once"),
    (dict(heap=True, keepViews=["forest_noon"] * 2), "each once"),
    (dict(heap=True, keepViews=["night"]), "some of the mode's views here"),
    (dict(heap=True, keepViews=[["forest_noon"]]), "each once"),
    (dict(heap=True, dimensions=[{"dim": "x"}]), "each once"),
    (dict(heap=True, alone="yes"), "true or false"),
    (dict(heap=True, windows=0), "true or false"),
    (dict(heap=True, alone=True, variants=[BASE, {**BASE, "id": "other"}]), "the baseline only"),
    (dict(heap=True, windows=False, variants=[{**BASE, "timers": True}]), "timers false"),
]


@pytest.mark.parametrize(("changes", "says"), SPEC_REFUSALS)
def test_each_measured_refusal_names_its_fix(bench_root, changes: dict, says: str) -> None:
    root, saves = bench_root
    with pytest.raises(record.RecordError) as refused:
        record.check_spec(root, measured(**changes), PLAT, SUITE, saves, PACK)
    assert says in str(refused.value) and "fix:" in str(refused.value)


def test_a_measured_spec_without_its_calibration_or_over_the_cap_is_refused(bench_root) -> None:
    root, saves = bench_root
    data = measured()
    del data["calibration"]
    with pytest.raises(record.RecordError, match="write calibration null"):
        record.check_spec(root, data, PLAT, SUITE, saves, PACK)
    suite = copy.deepcopy(SUITE)
    suite["capture"]["reloadCap"] = 13
    with pytest.raises(record.RecordError, match=r"plans 14 reloads.*over capture\.reloadCap 13"):
        record.check_spec(root, measured(), PLAT, suite, saves, PACK)
    suite = copy.deepcopy(SUITE)
    suite["modes"]["quick"]["views"] = ["forest_noon", "nowhere"]
    with pytest.raises(record.RecordError, match="names nowhere"):
        record.check_spec(root, measured(), PLAT, suite, saves, PACK)
    a8 = measured(
        kind="acceptance", items=["A8", "A11"], variants=[{**BASE, "timers": True}, TIMED]
    )
    with pytest.raises(record.RecordError, match="A8 compares"):
        record.check_spec(root, a8, PLAT, SUITE, saves, PACK)
    both = measured(kind="acceptance", items=["A8"], variants=[BASE, TIMED])
    assert record.check_spec(root, both, PLAT, SUITE, saves, PACK).items == ("A8",)


SHADOWS = {**BASE, "id": "shadows-off", "options": {"SHADOW_QUALITY": "-1"}}


def test_the_budget_pair_plans_68_and_44_reloads(bench_root) -> None:
    """F14's controlled pair (plans/m2.md M2.P06): full mode at R 1 with the baseline, shadows
    off and the twin plans 68 reloads over the eleven views, 44 over the overworld's seven."""
    root, saves = bench_root
    pair = measured(mode="full", variants=[BASE, SHADOWS], heap=True, rounds=1)
    full = record.check_spec(root, pair, PLAT, SUITE, saves, PACK)
    assert (full.rounds, full.planned, len(full.view_ids)) == (1, 68, 11)
    overworld = record.check_spec(
        root, {**pair, "dimensions": ["minecraft:overworld"]}, PLAT, SUITE, saves, PACK
    )
    assert overworld.planned == 44
    assert overworld.view_ids == (
        "forest_noon",
        "ocean_sunset",
        "cave",
        "rain",
        "night",
        "underwater",
        "entities",
    )
    suite = copy.deepcopy(SUITE)
    suite["modes"]["quick"]["views"] = ["forest_noon"]
    nether = measured(heap=True, dimensions=["minecraft:the_nether"])
    with pytest.raises(record.RecordError, match="none of the mode's views lies there"):
        record.check_spec(root, nether, PLAT, suite, saves, PACK)
    plain = measured(kind="acceptance", items=["A1"], variants=[{"pack": PACK, "profile": None}])
    plain = {k: v for k, v in plain.items() if k not in ("mode", "calibration")}
    with pytest.raises(record.RecordError, match="rounds is for measured runs"):
        record.check_spec(root, {**plain, "rounds": 1}, PLAT, SUITE, saves, PACK)
    with pytest.raises(record.RecordError, match="windows is for measured runs"):
        record.check_spec(root, {**plain, "windows": False}, PLAT, SUITE, saves, PACK)


def test_the_diagnosis_plans_42_and_44_reloads_at_one_view(bench_root) -> None:
    """M2.P06's diagnosis (plans/m2.md): at forest_noon the baseline alone at R 19 plans 42
    reloads, its slots all the baseline's and no twin; the pair's switches without windows at R 10
    plan 44."""
    root, saves = bench_root
    alone = measured(mode="full", heap=True, rounds=19, keepViews=["forest_noon"], alone=True)
    spec = record.check_spec(root, alone, PLAT, SUITE, saves, PACK)
    assert (spec.view_ids, spec.planned, spec.alone, spec.windows) == (
        ("forest_noon",),
        42,
        True,
        True,
    )
    found = measure.variants(spec, SUITE)
    assert [v.id for v in found] == ["baseline"]
    slots = measure.schedule(found, spec.rounds, spec.alone)
    assert len(slots) == 1 + 2 * 19 and {v.id for v, _ in slots} == {"baseline"}
    switches = measured(
        mode="full",
        heap=True,
        rounds=10,
        keepViews=["forest_noon"],
        windows=False,
        variants=[BASE, SHADOWS],
    )
    spec = record.check_spec(root, switches, PLAT, SUITE, saves, PACK)
    assert (spec.planned, spec.windows) == (44, False)
    assert [v.id for v in measure.variants(spec, SUITE)] == ["baseline", "shadows-off", "twin"]


# The runner on a fake game.

TOKEN = "t" * 43
GAME_PID = 4242
LUID = "luid_0x00000000_0x00011D94"  # FakeMachine.hags's 0x11d94
PM_PID = 5151
JAVA_RELEASE = b'IMPLEMENTOR="Eclipse Adoptium"\nJAVA_RUNTIME_VERSION="25.0.4.1+1-LTS"\n'
JAVA_PROFILE = json.loads((REPO_ROOT / "config/java/bench.json").read_text(encoding="utf-8"))
# The pack's defaults as the fake loads them: the played profile's keys at Unbound's defaults
# (m1-acceptance-10's shaders.options) and one key the profile leaves alone.
DEFAULTS = {
    "ANISOTROPIC_FILTER": "0",
    "ATM_FOG_MULT": "0.95",
    "BLOCK_REFLECT_QUALITY": "3",
    "BORDER_FOG": True,
    "CAVE_FOG": True,
    "ENTITY_SHADOW": "1",
    "FXAA_DEFINE": "1",
    "LIGHTSHAFT_QUALI_DEFINE": "2",
    "RAIN_STYLE": "1",
    "RP_MODE": "1",
    "WATER_REFLECT_QUALITY": "2",
    "shadowDistance": "192.0",
    "SHADER_STYLE": "4",
    "SHADOW_QUALITY": "2",
}


class Process:
    """A started process of the fake machine: running until it is closed, quit or killed;
    `current` is its row of the host's table when it was attached."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.killed = False
        self.current: dict | None = None

    def same(self, kept: dict) -> bool:
        return self.current is not None and self.current["createTime"] == kept["createTime"]

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 0  # a quit or WM_CLOSE: the game saves and exits
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


class PresentMon(presentmon.Host):
    """PresentMon on the fake mod's frame clock: a row per frame from frame 0 to the fake's frame
    + 10, each CPU start 0.05 ms after its HEAD stamp (A9's mapping), Independent Flip, GPUBusy
    6.9 of 7.0 ms; the CSV rewritten as the waits poll and at the stop."""

    def __init__(self, fake: modfake.Fake) -> None:
        self.fake = fake
        self.process = Process(PM_PID)
        self.output: Path | None = None
        self.now = 0.0

    def write(self) -> None:
        assert self.output is not None
        last = self.fake._frame + 10
        rows = [",".join(row(n).values()) for n in range(last + 1)]
        self.output.write_bytes(("﻿" + "\r\n".join([HEADER, *rows]) + "\r\n").encode())

    def start(self, command: list[str], log: Path) -> Process:
        self.output = Path(command[command.index("--output_file") + 1])
        self.write()
        return self.process

    def ctrl_break(self, pid: int) -> int:
        self.write()
        self.process.returncode = 0
        return 0

    def clock(self) -> float:
        self.now += 0.05
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.write()


class Host(session.RunHost):
    """The fake machine: no game before the launch, the processes `table` names, D42's readings
    idle and free, a virtual clock."""

    def __init__(self, fake: modfake.Fake) -> None:
        self.fake = fake
        self.pm = PresentMon(fake)
        self.game = Process(GAME_PID)
        self.table: dict[int, dict] = {}
        self.sessions: list[str] = []
        self.stopped: list[str] = []
        self.closed: list[int] = []
        self.now = 0.0

    def processes(self) -> list:
        return []

    def logman(self) -> str:
        rows = "\n".join(f"{name}  Trace  Running" for name in self.sessions)
        return f"Data Collector Set  Type  Status\n------\n{rows}\n\nThe command completed.\n"

    def presentmon(self) -> presentmon.Host:
        return self.pm

    def process_facts(self, pid: int) -> dict | None:
        return self.table.get(pid)

    def attach(self, pid: int) -> Any:
        process = self.game if pid == GAME_PID else self.pm.process
        process.current = self.table.get(pid)
        return process

    def connections(self, pid: int) -> list[dict]:
        return [{"remote": "13.107.246.40:443", "status": "ESTABLISHED"}]

    def stop_session(self, name: str) -> str:
        self.stopped.append(name)
        self.sessions.remove(name)
        self.pm.process.returncode = 0
        return "The command completed successfully."

    def idle_seconds(self) -> float:
        return 120.0

    def gpu_engine(self, samples: int) -> str:
        return Machine([(120.0, {77: 0.3})]).gpu_engine(samples)

    def gpu_memory(self) -> str:
        """typeperf's GPU memory on the fake's adapter: the game's dedicated memory 1 GiB plus
        64 MiB a reload, the rest fixed."""
        mib = 1024**2
        values = {
            f"GPU Process Memory(pid_{GAME_PID}_{LUID}_phys_0)\\Dedicated Usage": (
                1024 + 64 * reloads(self.fake)
            )
            * mib,
            f"GPU Process Memory(pid_{GAME_PID}_{LUID}_phys_0)\\Shared Usage": 100 * mib,
            f"GPU Process Memory(pid_77_{LUID}_phys_0)\\Dedicated Usage": 5 * mib,
            f"GPU Adapter Memory({LUID}_phys_0)\\Dedicated Usage": 4096 * mib,
            f"GPU Adapter Memory({LUID}_phys_0)\\Shared Usage": 200 * mib,
        }
        header = ",".join(['"(PDH-CSV 4.0)"', *(f'"\\\\PC\\{k}"' for k in values)])
        row = ",".join(['"10/13/2026 05:00:00.000"', *(f'"{v:.6f}"' for v in values.values())])
        return f"\n{header}\n{row}\nExiting, please wait...\n"

    def available_memory(self) -> int:
        return 16 * 1024**3

    def windows(self, pid: int) -> list[int]:
        return [1] if pid == GAME_PID and self.game.returncode is None else []

    def close(self, hwnd: int) -> bool:
        self.closed.append(hwnd)
        self.game.returncode = 0
        return True

    def clock(self) -> float:
        self.now += 0.01
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A root holding the repo's config and package, bench_263's snapshot and live world, the
    reference pack as a small zip pinned by its sha512, the game's options and latest.log, the
    stand-ins for PresentMon and the JDK; launch and the mod's pipe faked by the protocol fake
    serving the client over a socket pair. Returns (root, spec path, fake, host)."""
    root = tmp_path / "root"
    shutil.copytree(REPO_ROOT / "config", root / "config")
    shutil.copytree(
        REPO_ROOT / "optilux", root / "optilux", ignore=shutil.ignore_patterns("__pycache__")
    )
    snap = root / record.SNAPSHOTS / "bench_263"
    snap.mkdir(parents=True)
    (snap / "level.dat").write_bytes(b"L")
    for name, data in world.pack_files(VIEWS, PLAT.data["formats"]["dataPack"]).items():
        path = snap / "datapacks" / world.PACK / name  # as world prep writes them
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    game = root / "runtime" / PLAT.id / "game"
    (game / "saves" / "bench_263").mkdir(parents=True)
    (game / "saves" / "bench_263" / "level.dat").write_bytes(b"L")
    (game / "options.txt").write_text("version:4892\nao:true\n", encoding="utf-8")
    (game / "logs").mkdir()
    (game / "shaderpacks").mkdir()
    pack = game / "shaderpacks" / PACK
    with zipfile.ZipFile(pack, "w") as out:
        out.writestr("shaders/shaders.properties", "# a fake pack\n")
    plat_path = root / "config" / "platforms" / f"{PLAT.id}.json"
    data = json.loads(plat_path.read_text(encoding="utf-8"))
    data[platform.REFERENCE_PACKS][0]["sha512"] = hashlib.sha512(pack.read_bytes()).hexdigest()
    plat_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tools = root / "runtime" / "tools"
    tools.mkdir(parents=True)
    (tools / "PresentMon.exe").write_bytes(b"MZ")
    pins = json.loads((root / "config" / "tools.json").read_text(encoding="utf-8"))
    pins["presentmon"].update(file="PresentMon.exe", sha256=hashlib.sha256(b"MZ").hexdigest())
    (root / "config" / "tools.json").write_text(json.dumps(pins), encoding="utf-8")
    java = root / "runtime" / "java" / JAVA_PROFILE["runtime"]["build"]
    java.mkdir(parents=True)
    (java / "release").write_bytes(JAVA_RELEASE)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(measured()), encoding="utf-8")
    fake = modfake.Fake(TOKEN, pid=GAME_PID)
    fake.game_dir = game
    fake.defaults = dict(DEFAULTS)
    host = Host(fake)
    host.table[os.getpid()] = {"pid": os.getpid(), "createTime": 1.0, "exe": "python.exe"}
    ready = run_verb.prepare(root, spec_path, FakeMachine())  # read only: the launch's facts

    def fake_launch(root_: Path, world: str, tier: str, token: bool, overrides, say, host_):
        assert not (game / "shaderpacks" / f"{PACK}.txt").exists()  # launch refuses one
        pre = launch.prelaunch(SUITE["display"], tier, PACK, {})
        options = launch.write_prelaunch(game, pre)
        (game / launch.LOG).write_text("[00:00:01] [main/INFO]: a session\n", encoding="utf-8")
        identity = ready.identity
        facts = {
            "gate": {"amd": {}, "java": []},
            "command": {"arguments": ["java"], "check": "equal"},
            "hashes": {
                "packs": [{**p, "kind": "resourcePack"} for p in identity["resourcePacks"]["packs"]]
            },
            "mods": {"sha512": list(identity["mods"])},
            "settings": launch.settings_facts(pre, True),
            "optionsFile": options,
        }
        host.table[GAME_PID] = {
            "pid": GAME_PID,
            "createTime": 2.0,
            "exe": str(java / "bin" / "java.exe"),
            "name": "java.exe",
            "cwd": str(game),
            "cmdline": ["java"],
        }
        host.table[PM_PID] = {
            "pid": PM_PID,
            "createTime": 3.0,
            "exe": str(tools / "PresentMon.exe"),
        }
        host.sessions.append(f"optilux-{json.loads(spec_path.read_text())['name']}")
        return launch.Launched(host.game, GAME_PID, TOKEN, game / launch.LOG, game, pre, facts)

    def fake_open_mod(launched, root_, host_, say, log):
        client_end, mod_end = modfake.socket_streams()
        threading.Thread(target=fake.serve, args=(mod_end,), daemon=True).start()
        client = modclient.Client(client_end, TOKEN, log, GAME_PID)
        hello = client.hello()
        hello["versions"] = {"java": "25.0.4.1+1-LTS"}
        return client, {"hello": hello, "requestLog": "requests.jsonl"}

    monkeypatch.setattr(launch, "launch", fake_launch)
    monkeypatch.setattr(launch, "open_mod", fake_open_mod)
    monkeypatch.setattr(run_verb, "REPO_ROOT", root)
    monkeypatch.setattr(run_verb, "RunHost", lambda: host)
    monkeypatch.setattr(record, "Machine", FakeMachine)
    return root, spec_path, fake, host


class FakeMachine(record.Machine):
    """The system facts of tests/test_record.py's fake machine."""

    def hags(self, name: str) -> tuple[int, str]:
        return 0b1011, "0x11d94"

    def displays(self) -> list[dict]:
        return [{"name": "\\\\.\\DISPLAY1", "adapter": "GPU X", "flags": 0x5}]

    def display_mode(self, name: str) -> dict:
        return {"width": 3840, "height": 2160, "hz": 240, "dpiAware": True}

    def registry(self, key: str, value: str):
        return {"HwSchMode": 2, "UBR": 9457}[value]

    def driver(self, adapter: str) -> str | None:
        return "1.2.3"

    def windows_build(self) -> int:
        return 26200


def reloads(fake: modfake.Fake) -> int:
    return sum(1 for m in fake.received if m.get("cmd") == "shaders.reload")


def test_a_quick_run_measures_the_baseline_and_its_twin(fake_run, capsys) -> None:
    root, spec_path, fake, _ = fake_run
    assert cli.main(["run", str(spec_path)]) == 0
    out = capsys.readouterr().out
    assert "launch (announced): the session, tier bench, world bench_263" in out
    found = json.loads((root / record.RECORDS / "m2-quick-test.json").read_text(encoding="utf-8"))
    assert (found["status"], found["reason"], found["kind"], found["mode"]) == (
        "ok",
        None,
        "measurement",
        "quick",
    )
    assert found["calibration"] is None and found["notes"] == "a fixture"
    captures = found["captures"]
    assert len(captures) == 3 + 3 * 3 and all(c["valid"] for c in captures)
    assert all(c["rows"] == c["frames"] and c["edges"] == [0, 0] for c in captures)
    assert all(c["presentMode"] == FLIP and c["flags"] == [] for c in captures)
    assert [(c["pass"], c["view"], c["variant"], c["round"]) for c in captures[:6]] == [
        (1, "forest_noon", "baseline", 0),
        (1, "nether_crimson", "baseline", 0),
        (1, "end_dragon", "baseline", 0),
        (2, "forest_noon", "baseline", 1),
        (2, "forest_noon", "twin", 1),
        (2, "forest_noon", "baseline", 1),
    ]
    assert [c["settleS"] for c in captures[:6]] == [1.5, 4.0, 4.0, 4.0, 1.5, 1.5]
    # The planned reloads: the fake answered one shaders.reload per capture and the start's;
    # selftest's own reload is the plan's 14th.
    assert reloads(fake) + 1 == 14
    twin = found["variants"][1]
    assert (twin["id"], twin["role"], twin["pack"]) == ("twin", "twin", f"optilux-twin1-{PACK}")
    assert twin["effective"]["fromBaseline"] == {} and twin["options"] == PLAYED
    base = found["variants"][0]["effective"]["values"]
    assert base == {**DEFAULTS, **PLAYED}
    session_facts = found["session"]
    assert session_facts["laps"] == [["forest_noon", "nether_crimson", "end_dragon"]] * 2
    assert session_facts["weatherTicks"] == [{"view": "forest_noon", "ticks": 120}]
    assert session_facts["presentmon"]["stop"]["exitCode"] == 0
    assert session_facts["machine"]["idleSeconds"] == 120.0
    assert found["recorded"]["connectionsAtJoin"][0]["remote"] == "13.107.246.40:443"
    assert set(session_facts["timeSplit"]) >= {"launch", "start", "warmupPass", "measuredPass"}
    raw = root / found["raw"]
    assert (raw / "journal.json").is_file() and not (raw / "partial.json").exists()
    packs = root / "runtime" / PLAT.id / "game" / "shaderpacks"
    assert sorted(p.name for p in packs.iterdir()) == [PACK]  # twin and settings files gone
    assert len((root / record.RECORDS / "m2-quick-test.json").read_bytes()) < 200_000


def test_the_entities_view_shows_the_gui_in_creative_and_puts_both_back(fake_run) -> None:
    root, spec_path, fake, host = fake_run
    suite_path = root / platform.SUITE
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    suite["modes"]["quick"]["views"] = ["entities", "end_city"]
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok", found["reason"]
    texts = [
        m["args"].get("text") or ("hideGui" if "hideGui" in m["args"] else None)
        for m in fake.received
        if m["cmd"] in ("command", "hud.set")
    ]
    at = texts.index("/gamemode creative")
    assert texts[at + 1] == "hideGui" and fake.received  # hideGui false right after creative
    assert "/gamemode spectator" in texts[at:]
    assert fake.game["hideGui"] is True and texts.count("/gamemode creative") == 2  # both laps


def test_a_focus_lost_ends_the_session_invalid(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    original = fake._window
    seen = {"windows": 0}

    def window(args: dict) -> dict:
        found = original(args)
        seen["windows"] += 1
        if seen["windows"] == 3:
            fake.emit("focus.lost", {})
        return found

    monkeypatch.setattr(fake, "_window", window)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "invalid" and "focus.lost" in found["reason"]
    assert "D42" in found["reason"] and host.closed == [1]  # the game was ended
    assert len(found["captures"]) == 2  # the third window's capture was never kept
    assert found["session"]["presentmon"]["stop"]["exitCode"] == 0
    packs = root / "runtime" / PLAT.id / "game" / "shaderpacks"
    assert sorted(p.name for p in packs.iterdir()) == [PACK]


def test_a_failed_selftest_ends_the_session(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    original = fake._render

    def render(name: str, args: dict) -> dict:
        found = original(name, args)
        if name == "selftest":
            return {**found, "pass": False, "checks": {"capture": {"pass": False}}}
        return found

    monkeypatch.setattr(fake, "_render", render)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and "selftest failed" in found["reason"]
    assert "(capture)" in found["reason"] and "c5" in found["reason"]
    assert reloads(fake) == 0 and found["captures"] == []


class Killed(BaseException):
    """The runner's process killed from outside: nothing after it runs in the run."""


def test_a_run_killed_mid_session_is_finished_by_the_next_run_as_aborted(
    fake_run, monkeypatch
) -> None:
    root, spec_path, _, host = fake_run
    calls = {"n": 0}
    heap_row = measure.heap_row

    def killed(m: measure.Measured) -> None:
        calls["n"] += 1
        if calls["n"] == 3:  # after the session start's and two captures'
            raise Killed
        heap_row(m)

    monkeypatch.setattr(measure, "heap_row", killed)
    with pytest.raises(Killed):
        run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    raw = root / record.RAW / "m2-quick-test"
    journal = json.loads((raw / "partial.json").read_text(encoding="utf-8"))
    assert len(journal["captures"]) == 2 and not (root / record.RECORDS).exists()
    # A hard kill ends nothing: the game runs on, PresentMon's session too, the files stay.
    host.game.returncode = None
    host.closed = []
    host.sessions.append("optilux-m2-quick-test")
    host.pm.process.returncode = None
    packs = root / "runtime" / PLAT.id / "game" / "shaderpacks"
    for name in journal["files"]:
        (root / name).write_bytes(b"left by the kill")
    del host.table[os.getpid()]  # the killed runner is gone
    host.table[os.getpid() + 1] = {"pid": os.getpid() + 1, "createTime": 9.0, "exe": "python.exe"}
    said: list[str] = []
    finished = measure.finish_orphans(root, host, said.append)
    assert [f["name"] for f in finished] == ["m2-quick-test"]
    found = json.loads((root / record.RECORDS / "m2-quick-test.json").read_text(encoding="utf-8"))
    assert found["status"] == "aborted" and "without writing its record" in found["reason"]
    assert found["identity"] == journal["identity"] and len(found["captures"]) == 2
    assert all(c["valid"] and c["rows"] == c["frames"] for c in found["captures"])
    orphan = found["session"]["orphan"]
    assert orphan["game"].startswith("WM_CLOSE") and host.closed == [1]
    assert orphan["presentmon"] == "exited after its ETW session stopped"
    assert host.stopped == ["optilux-m2-quick-test"]
    assert sorted(p.name for p in packs.iterdir()) == [PACK]
    assert (raw / "journal.json").is_file() and not (raw / "partial.json").exists()
    assert measure.finish_orphans(root, host, said.append) == []  # finished once


def test_an_orphans_pids_are_checked_before_anything_is_ended(fake_run, monkeypatch) -> None:
    root, spec_path, _, host = fake_run
    calls = {"n": 0}

    def killed(m: measure.Measured) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise Killed

    monkeypatch.setattr(measure, "heap_row", killed)
    with pytest.raises(Killed):
        run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    # The runner still runs: not an orphan.
    with pytest.raises(record.RecordError, match="still going"):
        measure.finish_orphans(root, host, print)
    del host.table[os.getpid()]
    # The game's pid now names another process (Windows reuses pids): it is left alone.
    host.game.returncode = None
    host.closed = []
    host.table[GAME_PID] = {**host.table[GAME_PID], "createTime": 99.0}
    del host.table[PM_PID]
    found = measure.finish_orphans(root, host, print)[0]
    assert found["session"]["orphan"]["game"] == "gone" and host.closed == []
    assert host.game.returncode is None and found["status"] == "aborted"
    assert found["captures"][0]["valid"] is True  # PresentMon was gone: its CSV complete


def test_a8_is_admitted_with_its_timers_on_variant_and_never_passes_unjudged(fake_run) -> None:
    root, spec_path, fake, host = fake_run
    timed = {"id": "timed", "pack": PACK, "profile": "played", "timers": True}
    spec = measured(name="m2-a8-test", kind="acceptance", items=["A8"])
    spec["variants"] = [spec["variants"][0], timed]
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and found["reason"] == "items failed: A8"
    entry = found["acceptance"][0]
    assert (entry["item"], entry["pass"]) == ("A8", False)
    assert "M2.P07" in entry["evidence"]["unjudged"]
    timed_captures = [c for c in found["captures"] if c["variant"] == "timed"]
    assert len(timed_captures) == 3 and all(c["valid"] for c in timed_captures)
    timers = timed_captures[0]["timers"]
    assert timers["missing"] == 0 and timers["frames"] == timed_captures[0]["frames"]
    assert timers["topLevelMs"] == pytest.approx(6.85)  # FAKE_PASSES' depth-0 sum
    assert timers["residualMs"] == pytest.approx(6.9 - 6.85)
    assert all("timers" not in c for c in found["captures"] if c["variant"] != "timed")
    starts = [m for m in fake.received if m["cmd"] == "timers.start"]
    assert [m["args"]["maxFrames"] for m in starts] == [10000] * 3


def test_the_heap_is_read_at_the_start_and_every_tenth_reload(fake_run, monkeypatch) -> None:
    root, spec_path, _, host = fake_run
    spec_path.write_text(json.dumps(measured(name="m2-heap-test", heap=True)), encoding="utf-8")
    heap = (FIXTURES / "gc-heap-info.txt").read_text(encoding="utf-8")
    asked: list[str] = []

    def jcmd(path: Path, pid: int, command: str) -> str:
        asked.append(command)
        return heap if command == "GC.heap_info" else "Command executed successfully\n"

    monkeypatch.setattr(host, "jcmd", jcmd, raising=False)
    monkeypatch.setattr(host, "private_bytes", lambda pid: 900 * 1024**2, raising=False)
    monkeypatch.setattr(host, "available_memory", lambda: 16 * 1024**3, raising=False)
    monkeypatch.setattr(host, "physical_memory", lambda: 32 * 1024**3)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok", found["reason"]
    table = found["heapTable"]
    assert [r["reloads"] for r in table["rows"]] == [2, 10]  # the start's two, then the tenth
    assert asked == ["GC.run", "GC.heap_info"] * 2
    assert table["perReload"] == {"heapMiB": 0.0, "privateMiB": 0.0, "gpuMiB": 64.0}
    assert table["physicalMiB"] == 32768
    assert table["rows"][0]["gpu"] == {
        "processDedicatedMiB": 1088.0,  # 1 GiB and the start-of-run reload's 64 MiB
        "processSharedMiB": 100.0,
        "adapterDedicatedMiB": 4096.0,
        "adapterSharedMiB": 200.0,
    }
    assert all(c["gpuMemory"]["processDedicatedMiB"] > 1024 for c in found["captures"])


def test_a_budget_run_keeps_its_rounds_and_dimensions(fake_run, monkeypatch) -> None:
    """Full mode at R 1 in the Nether alone: two views, the baseline and its twin, 10 reloads."""
    root, spec_path, fake, host = fake_run
    spec = measured(
        name="m2-budget-test",
        mode="full",
        heap=True,
        rounds=1,
        dimensions=["minecraft:the_nether"],
    )
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    heap = (FIXTURES / "gc-heap-info.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(
        host,
        "jcmd",
        lambda path, pid, command: heap if command == "GC.heap_info" else "",
        raising=False,
    )
    monkeypatch.setattr(host, "private_bytes", lambda pid: 900 * 1024**2, raising=False)
    monkeypatch.setattr(host, "physical_memory", lambda: 32 * 1024**3)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok", found["reason"]
    captures = found["captures"]
    assert len(captures) == 2 + 2 * 3 and all(c["valid"] for c in captures)
    assert {c["view"] for c in captures} == {"nether_crimson", "nether_soul"}
    assert {c["round"] for c in captures if c["pass"] == 2} == {1}
    assert reloads(fake) + 1 == 10  # selftest's, the start's, 2 warm-up, 2 x (1 + 2 x 1 x 1)
    assert [r["reloads"] for r in found["heapTable"]["rows"]] == [2, 10]


def test_the_diagnosis_runs_the_baseline_alone_in_every_slot(fake_run, monkeypatch) -> None:
    """M2.P06's diagnosis on the fake: the baseline alone in every slot at one view, no twin
    copied; then (the next test) the pair's switches with no window measured, every capture's GPU
    memory read."""
    root, spec_path, fake, host = fake_run
    heap = (FIXTURES / "gc-heap-info.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(
        host,
        "jcmd",
        lambda path, pid, command: heap if command == "GC.heap_info" else "",
        raising=False,
    )
    monkeypatch.setattr(host, "private_bytes", lambda pid: 900 * 1024**2, raising=False)
    monkeypatch.setattr(host, "physical_memory", lambda: 32 * 1024**3)
    alone = measured(
        name="m2-diag-alone",
        mode="full",
        heap=True,
        rounds=2,
        keepViews=["forest_noon"],
        alone=True,
    )
    spec_path.write_text(json.dumps(alone), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok", found["reason"]
    assert found["session"]["twins"] == [] and [v["id"] for v in found["variants"]] == ["baseline"]
    captures = found["captures"]
    assert len(captures) == 1 + 1 + 2 * 2 and all(c["valid"] for c in captures)
    assert {(c["view"], c["variant"]) for c in captures} == {("forest_noon", "baseline")}
    assert reloads(fake) + 1 == 2 + 1 + 5


def test_the_diagnosis_runs_the_switches_without_windows(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    heap = (FIXTURES / "gc-heap-info.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(
        host,
        "jcmd",
        lambda path, pid, command: heap if command == "GC.heap_info" else "",
        raising=False,
    )
    monkeypatch.setattr(host, "private_bytes", lambda pid: 900 * 1024**2, raising=False)
    monkeypatch.setattr(host, "physical_memory", lambda: 32 * 1024**3)
    switches = measured(
        name="m2-diag-switches",
        mode="full",
        heap=True,
        rounds=1,
        keepViews=["forest_noon"],
        windows=False,
        variants=[BASE, SHADOWS],
    )
    spec_path.write_text(json.dumps(switches), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok", found["reason"]
    captures = found["captures"]
    assert [c["variant"] for c in captures] == [
        "baseline",
        "baseline",
        "shadows-off",
        "baseline",
        "twin",
        "baseline",
    ]
    assert all(c["flags"] == ["noWindow"] and not c["valid"] for c in captures)
    assert all("gpuBusyMs" not in c and c["settleS"] is None for c in captures)
    assert all(c["gpuMemory"]["adapterDedicatedMiB"] == 4096.0 for c in captures)
    assert reloads(fake) + 1 == 2 + 1 + 5
    assert not [m for m in fake.received if m.get("cmd") == "window.measure"]


def test_a_budget_run_stops_before_a_reload_under_2_gib_available(fake_run, monkeypatch) -> None:
    root, spec_path, _, host = fake_run
    heap = (FIXTURES / "gc-heap-info.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(
        host,
        "jcmd",
        lambda path, pid, command: heap if command == "GC.heap_info" else "",
        raising=False,
    )
    monkeypatch.setattr(host, "private_bytes", lambda pid: 900 * 1024**2, raising=False)
    monkeypatch.setattr(host, "physical_memory", lambda: 32 * 1024**3)
    monkeypatch.setattr(host, "available_memory", lambda: 1024**3)
    spec_path.write_text(json.dumps(measured(name="m2-guard-test", heap=True)), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed"
    assert "1.0 GiB of physical memory available, under 2 GiB" in found["reason"]


def test_gpu_memory_reads_the_game_and_its_adapter_on_the_luid() -> None:
    """A real typeperf sample (dwm.exe, pid 2020, on two adapters): the display adapter's
    columns only, in MiB; a pid typeperf did not list or no table is refused."""
    text = (FIXTURES / "typeperf-gpu-memory.csv").read_text(encoding="utf-8")
    assert measure.gpu_memory(text, 2020, "0x108fa") == {
        "processDedicatedMiB": 994.7,
        "processSharedMiB": 15.2,
        "adapterDedicatedMiB": 2071.0,
        "adapterSharedMiB": 219.6,
    }
    other = measure.gpu_memory(text, 2020, "0x12bfe")
    assert other["processDedicatedMiB"] == 0.0 and other["adapterSharedMiB"] == 0.0
    with pytest.raises(record.RecordError, match="no processDedicatedMiB, processSharedMiB"):
        measure.gpu_memory(text, 4242, "0x108fa")
    with pytest.raises(record.RecordError, match="no counter table"):
        measure.gpu_memory("Error: no such counter\n", 2020, "0x108fa")
    unread = text.replace('"1043030016.000000"', '" "')  # pid 2020's dedicated on 0x108fa
    with pytest.raises(record.RecordError, match="reads ' ', no number"):
        measure.gpu_memory(unread, 2020, "0x108fa")


def test_a_snapshot_whose_view_functions_left_the_views_file_is_refused(fake_run) -> None:
    root, spec_path, _, _ = fake_run
    function = (
        root
        / record.SNAPSHOTS
        / "bench_263"
        / "datapacks"
        / world.PACK
        / world.FUNCTIONS
        / "nether_crimson.mcfunction"
    )
    function.write_bytes(function.read_bytes().replace(b"time set 6000", b"time set 7000"))
    with pytest.raises(record.RecordError) as refused:
        run_verb.prepare(root, spec_path, FakeMachine())
    assert "for nether_crimson; fix: `optilux world prep bench_263`" in str(refused.value)


def test_an_orphans_record_keeps_its_variant_fields_and_its_own_validity(
    fake_run, monkeypatch
) -> None:
    root, spec_path, _, host = fake_run
    calls = {"n": 0}

    def killed(m: measure.Measured) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise Killed

    monkeypatch.setattr(measure, "heap_row", killed)
    with pytest.raises(Killed):
        run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    suite_path = root / platform.SUITE
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    suite["validity"]["minFrames"] = 10_000  # edited after the run: its own block judges it
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    del host.table[os.getpid()]
    found = measure.finish_orphans(root, host, print)[0]
    assert all(c["valid"] for c in found["captures"])
    base, twin = found["variants"]
    assert base["options"] == PLAYED and base["sha512"] and base["effective"]["values"]
    assert twin["effective"] is None  # killed before the twin's first reload


def test_the_games_own_screens_never_end_the_session_but_another_screen_does(
    fake_run, monkeypatch
) -> None:
    root, spec_path, fake, host = fake_run
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok", found["reason"]
    counts = found["session"]["events"]["counts"]
    assert counts["screen.opened"] == 5 + 2  # five dimension changes' loading screens, the quit's
    run_verb.close_journal(root / found["raw"])  # as `run` does once the record is written
    fake.quit.clear()  # a second launch of the fake game
    host.game, host.pm = Process(GAME_PID), PresentMon(fake)
    spec_path.write_text(json.dumps(measured(name="m2-chat-test")), encoding="utf-8")
    original = fake._window

    def window(args: dict) -> dict:
        answer = original(args)
        fake.emit("screen.opened", {"screen": "net.minecraft.client.gui.screens.ChatScreen"})
        return answer

    monkeypatch.setattr(fake, "_window", window)
    ended = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert ended["status"] == "invalid", ended["reason"]
    assert "ChatScreen" in ended["reason"]
    assert len(ended["captures"]) == 0  # the first window's capture was never kept


def test_a_focus_lost_in_the_gpu_warm_up_ends_the_session(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    hold = launch.hold

    def held(process, host_, seconds: float) -> None:
        fake.emit("focus.lost", {})
        time.sleep(0.5)  # the hold's 30 s in real time: the reader thread has queued it
        hold(process, host_, seconds)

    monkeypatch.setattr(launch, "hold", held)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "invalid" and "warm-up: focus.lost" in found["reason"]
    assert found["captures"] == [] and host.closed == [1]


def test_a_camera_that_left_its_view_fails_the_run(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    original = fake._game

    def game(name: str, args: dict) -> dict:
        answer = original(name, args)
        if name == "camera.get":
            answer["pose"] = {**answer["pose"], "y": answer["pose"]["y"] - 0.5}  # it fell
        return answer

    monkeypatch.setattr(fake, "_game", game)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and "left the view during the capture" in found["reason"]


def test_a_run_deletes_the_files_it_wrote_and_no_other(fake_run, monkeypatch) -> None:
    root, spec_path, _, host = fake_run
    packs = root / "runtime" / PLAT.id / "game" / "shaderpacks"
    twin = packs / f"optilux-twin1-{PACK}"
    twin.write_bytes(b"left by someone")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and "exists in shaderpacks" in found["reason"]
    assert twin.read_bytes() == b"left by someone"  # not this run's: kept, as its fix says
    twin.unlink()
    run_verb.close_journal(root / found["raw"])

    def no_mod(*args: object, **kwargs: object):
        raise launch.LaunchError("the mod session: frames.index stood still")

    monkeypatch.setattr(launch, "open_mod", no_mod)
    spec_path.write_text(json.dumps(measured(name="m2-nomod-test")), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and "frames.index stood still" in found["reason"]
    assert found["session"]["filesCleanup"]["removed"] == [twin.name]
    assert sorted(p.name for p in packs.iterdir()) == [PACK]


def test_a_presentmon_that_died_has_its_etw_session_stopped(fake_run, monkeypatch) -> None:
    root, spec_path, _, host = fake_run

    def died(m: measure.Measured) -> None:
        host.pm.process.returncode = 3  # PresentMon gone before its stop: its session left

    monkeypatch.setattr(measure, "heap_row", died)
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and "PresentMon exited with code 3" in found["reason"]
    assert host.stopped == ["optilux-m2-quick-test"]
    assert found["session"]["presentmon"]["sessionStopped"].startswith("The command completed")


def test_an_orphans_presentmon_found_gone_without_its_stop_leaves_its_captures_bare(
    fake_run, monkeypatch
) -> None:
    root, spec_path, _, host = fake_run
    calls = {"n": 0}

    def killed(m: measure.Measured) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise Killed

    monkeypatch.setattr(measure, "heap_row", killed)
    monkeypatch.setattr(measure, "stop_presentmon", lambda m, pm: None)  # killed before it
    with pytest.raises(Killed):
        run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    del host.table[os.getpid()]
    del host.table[PM_PID]  # PresentMon gone: its CSV may be short
    found = measure.finish_orphans(root, host, print)[0]
    assert found["session"]["orphan"]["presentmon"] == "gone"
    assert [c["valid"] for c in found["captures"]] == [False, False]
    assert "may lack its last rows" in found["captures"][0]["unsummarized"]


def test_a_process_windows_will_not_read_never_matches_a_journal(monkeypatch) -> None:
    class Guarded:
        pid = 4

        def __init__(self, pid: int) -> None:
            pass

        def create_time(self) -> float:
            return 1.0

        def exe(self) -> str:
            raise session.psutil.AccessDenied(4)

        name = cwd = cmdline = exe

    monkeypatch.setattr(session.psutil, "Process", Guarded)
    found = session.RunHost().process_facts(4)
    assert found == {
        "pid": 4,
        "createTime": 1.0,
        "exe": None,
        "name": None,
        "cwd": None,
        "cmdline": None,
    }
