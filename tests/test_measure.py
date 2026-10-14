"""The measured session (docs/plans/m2.md M2.P05): the schedule and its reloads, the laps and the
settle; each validity flag (the cut and the summaries: tests/test_presentmon.py); the variant
files' bytes and the twins; the spec's refusals; D42's machine check; and the
runner end to end on a fake game (the protocol fake, a fake PresentMon): a quick run of the
baseline and its twin, the focus end, a failed selftest ending the session, and a run killed
mid-session leaving an aborted record through the next run's orphan finisher (D41)."""

import copy
import hashlib
import io
import json
import os
import re
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
from optilux.verbs import calibrate as calibrate_verb
from optilux.verbs import compare as compare_verb
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
        order = record.lap(views, ramped)
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


def test_a11s_residual_is_unjudged_when_a_timer_frame_has_no_gpubusy() -> None:
    """The critique's finding 4: frame start's row lies outside the cut at a [1, 1] edge, so its
    NA escapes `notNumbers`; the residual is none rather than a median of fewer frames."""
    rows = [row(n) for n in range(20)]
    by_frame = {5: 6_850_000, 6: 6_850_000, 7: 6_800_000}
    assert measure.residual_ms(line_of(rows), {"frameRow": 5}, 5, by_frame) == pytest.approx(0.05)
    rows[5] = row(5, GPUBusy="NA")
    assert measure.residual_ms(line_of(rows), {"frameRow": 5}, 5, by_frame) is None
    assert measure.residual_ms(line_of(rows[:6]), {"frameRow": 5}, 5, by_frame) is None


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


PASS = {"id": "passthrough", "pack": record.PASSTHROUGH, "profile": None}
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def test_the_passthrough_zip_is_a_shaders_folder_and_an_empty_properties_file() -> None:
    """plans/m2.md D46: two entries, stored and empty, at the zip epoch with Unix attributes (a
    directory with the MS-DOS directory bit, a file rw-r--r--), so every build writes these 242
    bytes; Iris takes a zip whose tree holds a `shaders` directory."""
    data = measure.passthrough_zip()
    assert data == measure.passthrough_zip() and len(data) == 242
    assert hashlib.sha256(data).hexdigest() == (
        "834e06b82a6026d575b9c08f0a827a3d56717c19a7b2b8f3b3c848456c457517"
    )
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        entries = [
            (
                i.filename,
                i.file_size,
                i.compress_type,
                i.date_time,
                i.create_system,
                i.external_attr,
            )
            for i in archive.infolist()
        ]
        assert zipfile.Path(archive, "shaders/").is_dir()
    assert entries == [
        ("shaders/", 0, zipfile.ZIP_STORED, ZIP_EPOCH, 3, (0o40755 << 16) | 0x10),
        ("shaders/shaders.properties", 0, zipfile.ZIP_STORED, ZIP_EPOCH, 3, 0o100644 << 16),
    ]


def test_the_passthrough_pack_is_written_and_owned_before_the_launch(tmp_path: Path) -> None:
    packs = tmp_path / "shaderpacks"
    packs.mkdir()
    base = variant("baseline", "baseline")
    through = measure.Variant(
        "passthrough", "candidate", record.PASSTHROUGH, record.PASSTHROUGH, None, {}, False
    )
    assert measure.make_passthrough(tmp_path, [base], print) is None  # no variant runs it
    owned: list[Path] = []
    made = measure.make_passthrough(tmp_path, [base, through], owned.append)
    digest = hashlib.sha512(measure.passthrough_zip()).hexdigest()
    assert made == {"file": record.PASSTHROUGH, "sha512": digest}
    assert owned == [packs / record.PASSTHROUGH]  # taken before it is written
    assert (packs / record.PASSTHROUGH).read_bytes() == measure.passthrough_zip()
    assert measure.variant_sha512(through, "ref") == digest
    assert measure.variant_sha512(base, "ref") == "ref"
    again: list[Path] = []
    with pytest.raises(session.RunError, match="exists in shaderpacks"):
        measure.make_passthrough(tmp_path, [base, through], again.append)
    assert again == []  # a file already there is not this run's: never taken, never deleted


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


class Displays:
    """The AC display timeout, the console display's state and the input's seconds, each call
    logged in order (an execution state by its flags); `fails` names calls that raise OSError."""

    def __init__(self, timeout: int, idle: float, state: int | None = 1, fails=()) -> None:
        self.timeout = timeout
        self.idle = idle
        self.state = state
        self.fails = fails
        self.calls: list[str | int] = []

    def answer(self, call: str | int, value: Any = None) -> Any:
        self.calls.append(call)
        if call in self.fails:
            raise OSError(f"{call} failed")
        return value

    @property
    def states(self) -> list[int]:
        return [c for c in self.calls if isinstance(c, int)]

    def display_timeout(self) -> int:
        return self.answer("timeout", self.timeout)

    def execution_state(self, flags: int) -> None:
        self.answer(flags)

    def display_state(self) -> int | None:
        return self.answer("state", self.state)

    def idle_seconds(self) -> float:
        return self.answer("idle", self.idle)


HOLD = measure.ES_CONTINUOUS | measure.ES_DISPLAY_REQUIRED


def test_the_displays_are_held_on_through_a_measured_run_then_released() -> None:
    host = Displays(600, 45.04)
    said: list[str] = []
    with measure.displays_on(host, said.append) as held:  # type: ignore[arg-type]
        assert host.calls == ["timeout", "idle", 0x80000002, "state"]  # read after the request
    assert held == {
        "request": "ES_CONTINUOUS | ES_DISPLAY_REQUIRED",
        "state": "on",
        "acTimeoutS": 600,
        "idleSeconds": 45.0,
    }
    assert host.states == [HOLD, measure.ES_CONTINUOUS] and "timeout 600 s" in said[0]
    # A process after a measured one: input past the timeout, the displays held on by the last
    # request's timer; dimmed still presents. A session breaking still releases.
    for later in (Displays(600, 7200.0), Displays(600, 7200.0, state=2)):
        with pytest.raises(KeyError), measure.displays_on(later, said.append):  # type: ignore[arg-type]
            raise KeyError("the session broke")
        assert later.states == [HOLD, measure.ES_CONTINUOUS]


@pytest.mark.parametrize(("state", "shown"), [(0, "off"), (None, "unread"), (7, "unread")])
def test_displays_read_off_or_unread_refuse_the_run_and_release_the_request(state, shown) -> None:
    off = Displays(600, 30.0, state=state)
    with pytest.raises(record.RecordError) as refused:  # noqa: SIM117 the body never runs
        with measure.displays_on(off, print):  # type: ignore[arg-type]
            raise AssertionError("held with the displays off")
    assert f"the displays read {shown} (input 30 s ago, the display timeout 600 s on AC)" in str(
        refused.value
    )
    assert "fix: wake them" in str(refused.value) and off.states == [HOLD, measure.ES_CONTINUOUS]


def test_a_failed_power_call_is_refused_or_said_never_raised_as_os_error() -> None:
    said: list[str] = []
    for failing in ("timeout", "idle", HOLD):
        host = Displays(600, 30.0, fails=(failing,))
        with pytest.raises(record.RecordError, match=r"the display request: .* failed; fix:"):  # noqa: SIM117
            with measure.displays_on(host, said.append):  # type: ignore[arg-type]
                raise AssertionError("held without a request")
        assert measure.ES_CONTINUOUS not in host.states  # nothing taken, nothing released
    unread = Displays(600, 30.0, fails=("state",))
    with pytest.raises(record.RecordError, match="the displays read unread"):  # noqa: SIM117
        with measure.displays_on(unread, said.append):  # type: ignore[arg-type]
            raise AssertionError("held unread")
    assert unread.states == [HOLD, measure.ES_CONTINUOUS] and "not read: state failed" in said[0]
    release = Displays(600, 30.0, fails=(measure.ES_CONTINUOUS,))
    with measure.displays_on(release, said.append) as held:  # type: ignore[arg-type]
        assert held["state"] == "on"
    assert "the request's release failed (2147483648 failed)" in said[-1]


@pytest.mark.windows
def test_the_power_calls_answer_on_windows() -> None:
    host = session.RunHost()
    assert host.display_timeout() >= 0
    assert host.display_state() in (0, 1, 2, None)
    host.execution_state(measure.ES_CONTINUOUS)  # this thread's request cleared: none held


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
    with_shadows = measured(mode="full", variants=[measured()["variants"][0], shadows])
    wide = copy.deepcopy(SUITE)
    wide["capture"]["reloadCap"] = 288  # the planning, before plans/m2.md D43's cap of 20
    full = record.check_spec(root, with_shadows, PLAT, wide, saves, PACK)
    assert full.planned == record.planned_reloads(11, 2, 2) and len(full.view_ids) == 11
    assert (spec.rounds, full.rounds) == (1, 2)  # the modes' own R
    assert full.variants[1]["options"] == {**PLAYED, "SHADOW_QUALITY": "-1"}
    calibration = record.check_spec(root, measured(kind="calibration"), PLAT, SUITE, saves, PACK)
    twins = measure.variants(calibration, SUITE)
    assert [v.id for v in twins] == ["baseline", "twin-1", "twin-2"]  # twinsPerSession 2
    assert calibration.planned == 20  # 2 + 3 + 3 x (1 + 2 x 1 x 2): the cap exactly


def test_the_cap_of_20_holds_quick_mode_and_splits_full_mode_into_six_launches(bench_root):
    """plans/m2.md D43 (suite.json capture.reloadCap 20; run-record.md#split-sessions): quick
    mode's twin and one candidate plan 20 in one launch with the warm-up pass; over a cap of 19
    they split without it; full mode's twin and one candidate at R 2 cut the lap into 6 launches,
    2 views each (2 + 2 x 9 = 20) and end_city alone; a view alone over the cap is refused; a
    budget run (heap true) passes the cap in one launch."""
    root, saves = bench_root
    assert SUITE["capture"]["reloadCap"] == 20
    pair = measured(variants=[BASE, SHADOWS])
    quick = record.check_spec(root, pair, PLAT, SUITE, saves, PACK)
    assert (quick.planned, quick.groups, quick.warmup) == (20, (), True)
    tight = copy.deepcopy(SUITE)
    tight["capture"]["reloadCap"] = 19
    split = record.check_spec(root, pair, PLAT, tight, saves, PACK)
    assert split.groups == (("forest_noon", "nether_crimson", "end_dragon"),)
    assert (split.warmup, split.planned) == (False, 2 + 3 * 5)
    full = record.check_spec(root, {**pair, "mode": "full"}, PLAT, SUITE, saves, PACK)
    assert full.groups == (
        ("forest_noon", "ocean_sunset"),
        ("cave", "night"),
        ("underwater", "entities"),
        ("rain", "nether_crimson"),
        ("nether_soul", "end_dragon"),
        ("end_city",),
    )
    assert full.planned == 5 * 20 + (2 + 9) and full.warmup is False
    assert all(record.planned_reloads(len(g), 2, 2, False) <= 20 for g in full.groups)
    tight["capture"]["reloadCap"] = 10
    with pytest.raises(record.RecordError, match=r"one view alone plans 11 reloads.*reloadCap 10"):
        record.check_spec(root, {**pair, "mode": "full"}, PLAT, tight, saves, PACK)
    budget = {**pair, "mode": "full", "heap": True}
    found = record.check_spec(root, budget, PLAT, SUITE, saves, PACK)
    assert (found.planned, found.groups) == (112, ())


def test_the_survey_keeps_each_launchs_warm_up_pass_at_r_1(bench_root) -> None:
    """The survey's exception (run-record.md#split-sessions): a calibration-null measurement run
    may set rounds and warmup true: at R 1 with the twin and one candidate, 3 views a launch
    (2 + 3 + 3 x 5 = 20), so full mode's 11 views take 4 launches."""
    root, saves = bench_root
    survey = measured(mode="full", variants=[BASE, SHADOWS], rounds=1, warmup=True)
    spec = record.check_spec(root, survey, PLAT, SUITE, saves, PACK)
    assert spec.warmup is True and [len(g) for g in spec.groups] == [3, 3, 3, 2]
    assert record.planned_reloads(3, 2, 1, True) == 20
    plain = record.check_spec(root, {**survey, "warmup": None}, PLAT, SUITE, saves, PACK)
    assert plain.warmup is False and [len(g) for g in plain.groups] == [3, 3, 3, 2]


def test_the_survey_measures_the_passthrough_pack_as_a_candidate(bench_root) -> None:
    """M2.P08's survey (plans/m2.md D46): the baseline, the passthrough pack and the twin of the
    baseline's zip, 3 views a launch at R 1 with the warm-up pass."""
    root, saves = bench_root
    survey = measured(mode="full", variants=[BASE, PASS], rounds=1, warmup=True)
    spec = record.check_spec(root, survey, PLAT, SUITE, saves, PACK)
    assert [len(g) for g in spec.groups] == [3, 3, 3, 2] and spec.warmup is True
    assert spec.variants[1] == {**PASS, "options": {}, "timers": False}
    found = measure.variants(spec, SUITE)
    assert [(v.id, v.role, v.pack, v.source) for v in found] == [
        ("baseline", "baseline", PACK, PACK),
        ("passthrough", "candidate", record.PASSTHROUGH, record.PASSTHROUGH),
        ("twin", "twin", f"optilux-twin1-{PACK}", PACK),
    ]


def test_a_split_sessions_name_leaves_room_for_its_parts(bench_root) -> None:
    root, saves = bench_root
    pair = measured(mode="full", variants=[BASE, SHADOWS])
    record.check_spec(root, {**pair, "name": "s" * 36}, PLAT, SUITE, saves, PACK)
    with pytest.raises(record.RecordError, match="a name of at most 36 characters"):
        record.check_spec(root, {**pair, "name": "s" * 37}, PLAT, SUITE, saves, PACK)
    assert record.part_name("cal-full-x-1", 6) == "cal-full-x-1-p6"
    assert record.part_name("cal-full-x-1", 6, 1) == "cal-full-x-1-p6b"


BASE = {"id": "baseline", "pack": PACK, "profile": "played"}
TIMED = {**BASE, "id": "timed", "timers": True}
SPEC_REFUSALS = [
    (dict(mode=None), "measures a mode's schedule"),
    (dict(mode="slow"), "one of quick, full"),
    (dict(calibration="quick-abc"), "is no calibration id"),
    (dict(calibration="quick-" + "0" * 64), "`optilux calibrate --mode quick` for this identity"),
    (dict(kind="calibration", calibration="quick-" + "0" * 64), "judged by no calibration"),
    (dict(heap=True, calibration="quick-" + "0" * 64), "which no measured run it would judge runs"),
    (
        dict(mode="full", kind="acceptance", items=["A8"], variants=[BASE, TIMED]),
        "judged by a calibration",
    ),
    (dict(kind="acceptance", items=["A8"], variants=[BASE, TIMED]), "run on full mode's schedule"),
    (dict(warmup=1), "true, or leave it out"),
    (dict(items=["A1"]), "takes none"),
    (dict(reloads=10), "F4's acceptance table"),
    (dict(heap="yes"), "true or false"),
    (dict(treatment="mods"), "JVM track"),
    (dict(variants=[]), "lists none"),
    (dict(variants=[{**BASE, "pack": "other.zip"}]), "the reference pack"),
    (dict(variants=[PASS]), "the passthrough after it in a measurement run"),
    (dict(variants=[BASE, {**PASS, "profile": "played"}]), "profile null, no options"),
    (dict(variants=[BASE, {**PASS, "options": {"SHADOW_QUALITY": "-1"}}]), "no options"),
    (dict(variants=[BASE, {**PASS, "timers": True}]), "timers false"),
    (
        dict(mode="full", kind="acceptance", items=["A8"], variants=[BASE, TIMED, PASS]),
        "as a measurement run's candidate",
    ),
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
    (
        dict(kind="acceptance", items=["A11"], variants=[{**BASE, "timers": True}, TIMED]),
        "a candidate unlike the baseline",
    ),
    (dict(kind="acceptance", items=["A2"]), "takes A8, A11"),
    (dict(kind="calibration", rounds=1), "a calibration-null measurement run's"),
    (dict(kind="calibration", warmup=True), "a calibration-null measurement run's"),
    (dict(warmup=False), "true, or leave it out"),
    (dict(dimensions=["minecraft:overworld"]), "a budget run's"),
    (
        dict(
            mode="full",
            kind="acceptance",
            items=["A8"],
            variants=[BASE, TIMED],
            heap=True,
            rounds=1,
        ),
        "budget",
    ),
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
    with pytest.raises(record.RecordError, match="does not name its calibration; fix: the id"):
        record.check_spec(root, data, PLAT, SUITE, saves, PACK)
    suite = copy.deepcopy(SUITE)
    suite["capture"]["reloadCap"] = 4
    with pytest.raises(record.RecordError, match=r"one view alone plans 5 reloads.*reloadCap 4"):
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
    both = measured(mode="full", kind="acceptance", items=["A8"], variants=[BASE, TIMED])
    with pytest.raises(record.RecordError, match="judged by a calibration"):
        record.check_spec(root, both, PLAT, SUITE, saves, PACK)


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
        self.states: list[int] = []

    def processes(self) -> list:
        return []

    def display_timeout(self) -> int:
        return 600

    def display_state(self) -> int | None:
        return 1

    def execution_state(self, flags: int) -> None:
        self.states.append(flags)

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


def test_a_run_writes_the_passthrough_pack_measures_it_and_deletes_it(fake_run) -> None:
    """D46 on the fake: the passthrough written before the launch, loaded at its reloads with no
    options, recorded with its own sha512 and whole (empty) option map, deleted after the quit."""
    root, spec_path, _, _ = fake_run
    spec_path.write_text(json.dumps(measured(variants=[BASE, PASS])), encoding="utf-8")
    assert cli.main(["run", str(spec_path)]) == 0
    found = json.loads((root / record.RECORDS / "m2-quick-test.json").read_text(encoding="utf-8"))
    assert found["status"] == "ok"
    base, through, twin = found["variants"]
    assert (through["id"], through["role"], through["pack"], through["profile"]) == (
        "passthrough",
        "candidate",
        record.PASSTHROUGH,
        None,
    )
    digest = hashlib.sha512(measure.passthrough_zip()).hexdigest()
    assert through["sha512"] == digest and twin["sha512"] == base["sha512"] != digest
    assert through["effective"] == {"sha256": record.sha256_of({}), "count": 0, "values": {}}
    assert found["session"]["passthrough"] == {"file": record.PASSTHROUGH, "sha512": digest}
    measured_through = [c for c in found["captures"] if c["variant"] == "passthrough"]
    assert [c["view"] for c in measured_through] == ["forest_noon", "nether_crimson", "end_dragon"]
    packs = root / "runtime" / PLAT.id / "game" / "shaderpacks"
    assert sorted(p.name for p in packs.iterdir()) == [PACK]  # passthrough and settings gone


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


def calibration_data(
    identity: dict, mode: str, views: list[str], rounds: int, generation: int = 1
) -> dict:
    """A calibration's content: 20 null candidates within 0.3 % at `views` (every threshold the
    0.5 % floor), 2 twins a session, the suite's twin monitor."""
    digest = record.identity_hash(identity)
    nulls = [
        {
            "session": f"cal-{n // 2}",
            "twin": f"twin-{n % 2 + 1}",
            "ratios": {v: 1 + ((n % 7) - 3) / 1000 for v in views},
        }
        for n in range(20)
    ]
    return {
        "schema": 1,
        "id": record.calibration_id(mode, digest, generation),
        "generation": generation,
        "mode": mode,
        "createdAt": "2026-10-13T00:00:00+00:00",
        "identityHash": digest,
        "identity": identity,
        "resourcePacks": "standard",
        "views": views,
        "rounds": rounds,
        "twinsPerSession": 2,
        "falseRate": 0.05,
        "floorPct": 0.5,
        "twinMonitor": {"window": 20, "maxExceed": 2},
        "baseline": {"pack": PACK, "profile": "played"},
        "sessions": [f"cal-{n}" for n in range(10)],
        "nulls": nulls,
        "thresholds": {},
    }


def write_calibration(root: Path, data: dict) -> str:
    folder = root / record.CALIBRATIONS
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{data['id']}.json").write_text(json.dumps(data), encoding="utf-8")
    return data["id"]


def fake_calibration(
    root: Path, spec_path: Path, mode: str = "quick", generation: int = 1, **changes: Any
) -> str:
    """A calibration of the fake run's own identity (`changes` replacing its keys) written under
    the root's config/calibrations/, at the root suite's views and R of the mode; its id."""
    identity = {**run_verb.prepare(root, spec_path, FakeMachine()).identity, **changes}
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    views = list(record.mode_views(suite, mode, VIEWS))
    rounds = suite["modes"][mode]["rounds"]
    return write_calibration(root, calibration_data(identity, mode, views, rounds, generation))


def small_full(root: Path) -> None:
    """The root's full mode at quick mode's three views and R 1: the twin and one candidate in
    one launch of 20 reloads (A8 and A11 run in full mode, plans/m2.md M2.P10)."""
    set_suite(
        root, modes__full={"views": ["forest_noon", "nether_crimson", "end_dragon"], "rounds": 1}
    )


def test_a8_is_judged_by_its_calibration_on_its_timers_on_variant(fake_run) -> None:
    root, spec_path, fake, host = fake_run
    small_full(root)
    cid = fake_calibration(root, spec_path, mode="full")
    timed = {"id": "timed", "pack": PACK, "profile": "played", "timers": True}
    spec = measured(
        name="m2-a8-test", mode="full", kind="acceptance", items=["A8"], calibration=cid
    )
    spec["variants"] = [spec["variants"][0], timed]
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    found = run_verb.perform(root, spec_path, host, FakeMachine(), print, print)
    assert (found["status"], found["reason"], found["calibration"]) == ("ok", None, cid)
    entry = found["acceptance"][0]
    assert (entry["item"], entry["pass"]) == ("A8", True)  # the fake's timers cost nothing
    evidence = entry["evidence"]
    assert evidence["calibration"] == cid and evidence["twin"] is True
    assert evidence["geoMeanDelta"] == 0.0 and evidence["beyond"] == {}
    assert "verdicts" not in found  # an acceptance run's verdicts are its items
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


# The calibration a run names (plans/m2.md M2.P07; measurement.md#calibration).


def test_a_judged_run_writes_its_verdicts_and_the_twin_monitor(fake_run) -> None:
    root, spec_path, _, host = fake_run
    cid = fake_calibration(root, spec_path)
    spec = measured(name="m2-judged-test", calibration=cid, variants=[BASE, SHADOWS])
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    found, path = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert (found["status"], found["calibration"]) == ("ok", cid), found["reason"]
    judged = found["verdicts"]
    assert judged["calibration"] == cid
    assert judged["views"] == ["forest_noon", "nether_crimson", "end_dragon"]
    assert judged["session"] == "ok" and judged["twin"]["inside"] is True
    shadows = judged["candidates"][0]
    assert shadows["variant"] == "shadows-off" and shadows["geoMeanDelta"] == 0.0
    assert shadows["verdict"] == "inconclusive" and "inconclusive, run full" in shadows["why"]
    assert judged["thresholds"]["geoMean"] == 0.5 and judged["thresholds"]["k"] == 1
    assert judged["twinMonitor"] == {
        "window": 20,
        "maxExceed": 2,
        "twins": 1,
        "exceeded": 0,
        "recalibrate": False,
    }
    assert "shadows-off inconclusive" in run_verb.summary_line(found)
    # The next run under the calibration counts this one's twin.
    assert record.judged_twins(root, cid) == [False]
    assert path == root / record.RECORDS / "m2-judged-test.json"


@pytest.mark.parametrize("key", record.IDENTITY_KEYS)
def test_run_refuses_a_calibration_of_another_identity_naming_the_key(fake_run, key) -> None:
    root, spec_path, _, _ = fake_run
    cid = fake_calibration(root, spec_path, **{key: {"other": key}})
    spec = measured(calibration=cid, variants=[BASE, SHADOWS])
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(record.RecordError) as refused:
        run_verb.prepare(root, spec_path, FakeMachine())
    message = str(refused.value)
    assert re.search(rf"another identity: {key}[. ].*differ", message)
    assert "fix: `optilux calibrate --mode quick` for this identity" in message


def test_run_refuses_a_calibration_of_another_mode_or_resource_pack_set(fake_run) -> None:
    root, spec_path, _, _ = fake_run
    cid = fake_calibration(root, spec_path, mode="full")
    spec = measured(calibration=cid, variants=[BASE, SHADOWS])
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(record.RecordError, match="is full mode's, the spec runs quick"):
        run_verb.prepare(root, spec_path, FakeMachine())
    spec_path.write_text(json.dumps(measured()), encoding="utf-8")
    cid = fake_calibration(root, spec_path)
    path = root / record.CALIBRATIONS / f"{cid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "resourcePacks": "deterministic"}), encoding="utf-8")
    spec_path.write_text(json.dumps(measured(calibration=cid, variants=[BASE, SHADOWS])), "utf-8")
    with pytest.raises(record.RecordError, match="covers the deterministic resource-pack set"):
        run_verb.prepare(root, spec_path, FakeMachine())


def test_a_calibration_whose_content_left_its_id_is_refused(bench_root) -> None:
    root, _ = bench_root
    identity = {key: {"sha256": key} for key in record.IDENTITY_KEYS}
    digest = record.identity_hash(identity)
    data = calibration_data(identity, "quick", ["forest_noon"], 1)
    folder = root / record.CALIBRATIONS
    write_calibration(root, data)
    assert record.load_calibration(root, f"quick-{digest}")["identity"] == identity
    for change, says in (
        ({"rounds": 0}, "rounds or twinsPerSession is no positive count"),
        ({"views": []}, "views is no list of view ids"),
        ({"falseRate": 1.5}, "falseRate or floorPct is out of range"),
        ({"twinMonitor": {"window": 0}}, "twinMonitor holds no window and maxExceed"),
        ({"nulls": [{"ratios": {"forest_noon": 0}}]}, "lacks a positive ratio"),
        ({"generation": 2}, "disagrees with its content"),
    ):
        write_calibration(root, {**data, **change})
        with pytest.raises(record.RecordError, match=says):
            record.load_calibration(root, f"quick-{digest}")
    write_calibration(root, data)
    edited = {**data, "identity": {**identity, "suite": {"sha256": "moved"}}}
    (folder / f"quick-{digest}.json").write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(record.RecordError, match="disagrees with its content"):
        record.load_calibration(root, f"quick-{digest}")
    del data["nulls"]
    (folder / f"quick-{digest}.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(record.RecordError, match="lacks nulls"):
        record.load_calibration(root, f"quick-{digest}")


def test_a8s_second_session_names_the_first_whose_views_wait(bench_root) -> None:
    """`remeasures` (plans/m2.md M2.P10): the first A8 session's entry waits on views beyond their
    threshold, under the spec's calibration; anything else is refused."""
    root, saves = bench_root
    identity = {key: {"sha256": key} for key in record.IDENTITY_KEYS}
    views = list(record.mode_views(SUITE, "full", VIEWS))
    cid = write_calibration(root, calibration_data(identity, "full", views, 2))
    evidence = {"beyond": {"end_dragon": 0.8}, "remeasure": ["end_dragon"], "calibration": cid}
    entry = {"item": "A8", "pass": None, "evidence": {**evidence, "pending": "x"}}
    second = measured(
        mode="full", kind="acceptance", items=["A8"], variants=[BASE, TIMED], calibration=cid
    )
    first = {"status": "ok", "spec": second, "acceptance": [entry]}
    (root / record.RECORDS).mkdir(parents=True)
    (root / record.RECORDS / "m2-a8-1.json").write_text(json.dumps(first), encoding="utf-8")
    spec = record.check_spec(root, {**second, "remeasures": "m2-a8-1"}, PLAT, SUITE, saves, PACK)
    assert spec.first is not None and spec.first["remeasure"] == ["end_dragon"]
    assert spec.cal is not None and spec.cal["id"] == cid
    other = {**second, "variants": [BASE, {**TIMED, "options": {"SHADOW_QUALITY": "-1"}}]}
    for changed in ({**first, "status": "failed"}, {**first, "spec": other}):
        (root / record.RECORDS / "m2-a8-3.json").write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(record.RecordError, match="re-measure an ok first session's variants"):
            record.check_spec(root, {**second, "remeasures": "m2-a8-3"}, PLAT, SUITE, saves, PACK)
    with pytest.raises(record.RecordError, match="A8's second session"):
        record.check_spec(root, {**measured(), "remeasures": "m2-a8-1"}, PLAT, SUITE, saves, PACK)
    passed = {"acceptance": [{"item": "A8", "pass": True, "evidence": evidence}]}
    (root / record.RECORDS / "m2-a8-2.json").write_text(json.dumps(passed), encoding="utf-8")
    with pytest.raises(record.RecordError, match="waits on no view to re-measure"):
        record.check_spec(root, {**second, "remeasures": "m2-a8-2"}, PLAT, SUITE, saves, PACK)
    with pytest.raises(record.RecordError, match="no record"):
        record.check_spec(root, {**second, "remeasures": "m2-a8-9"}, PLAT, SUITE, saves, PACK)


def test_an_item_waits_with_pass_null_only_beside_its_pending_reason() -> None:
    waits = {"item": "A8", "pass": None, "evidence": {"pending": "a second session"}}
    record.check_acceptance([waits])
    with pytest.raises(record.RecordError, match="neither boolean nor null"):
        record.check_acceptance([{**waits, "evidence": {}}])


# calibrate (plans/m2.md M2.P07): its sessions' count first, each launch, the resume.


def small_calibration(root: Path, sessions: int) -> None:
    """The root's suite asking `sessions` calibration sessions of 2 twins, at a false rate whose
    order level exists for 2 x `sessions` nulls (k = floor(0.25 x (2 x sessions + 1)) >= 1)."""
    path = root / platform.SUITE
    suite = json.loads(path.read_text(encoding="utf-8"))
    suite["statistics"]["calibration"]["minSessionsPerMode"] = sessions
    suite["statistics"]["falseRate"] = 0.25
    path.write_text(json.dumps(suite), encoding="utf-8")


def fresh_games(monkeypatch, fake: modfake.Fake, host: Host) -> None:
    """Each launch a new game: its process and PresentMon's running, the fake's world as new."""
    launched = launch.launch

    def relaunch(*args: Any) -> launch.Launched:
        host.game.returncode = None
        host.pm.process.returncode = None
        fake.quit.clear()
        fake.game = modfake.initial_game()
        fake._said_hello = False
        return launched(*args)

    monkeypatch.setattr(launch, "launch", relaunch)


def test_calibrate_announces_its_count_then_resumes_after_a_stop(fake_run, monkeypatch) -> None:
    root, _, fake, host = fake_run
    small_calibration(root, 3)
    fresh_games(monkeypatch, fake, host)
    original = fake._window
    seen = {"windows": 0}

    def window(args: dict) -> dict:  # the second session's first measured window: focus lost
        found = original(args)
        seen["windows"] += 1
        if seen["windows"] == 18 + 4:  # a session: 3 warm-up and 15 measured windows
            fake.emit("focus.lost", {})
        return found

    monkeypatch.setattr(fake, "_window", window)
    said: list[str] = []
    announced: list[str] = []
    outcome = calibrate_verb.calibrate(
        root, "quick", host, FakeMachine(), said.append, announced.append
    )
    digest = outcome["identityHash"]
    names = [calibrate_verb.session_name("quick", digest, n) for n in (1, 2, 3, 4)]
    assert "0 whole, 3 to run, 3 launch(es)" in announced[0]
    assert any(a.startswith("launch (announced): the session") for a in announced[1:])
    assert outcome["ran"] == names[:2] and "does not count: status invalid" in outcome["stopped"]
    assert not (root / record.CALIBRATIONS).exists()
    assert host.states == [HOLD, measure.ES_CONTINUOUS]  # one request over both sessions
    first = record.read_record(root, names[0])["session"]["displays"]
    assert first == record.read_record(root, names[1])["session"]["displays"]
    monkeypatch.setattr(fake, "_window", original)
    said.clear()
    announced.clear()
    outcome = calibrate_verb.calibrate(
        root, "quick", host, FakeMachine(), said.append, announced.append
    )
    assert "1 whole, 2 to run, 2 launch(es)" in announced[0]
    assert f"{calibrate_verb.PREFIX}: passed over {names[1]} (status invalid" in said[0]
    assert outcome["ran"] == names[2:] and outcome["stopped"] is None
    cal = record.load_calibration(root, outcome["calibration"])
    assert cal["sessions"] == [names[0], names[2], names[3]] and len(cal["nulls"]) == 6
    assert (
        cal["identity"]
        == run_verb.prepare(
            root, calibrate_verb.session_spec("cal-x", "quick", PACK), FakeMachine(), fresh=False
        ).identity
    )
    assert cal["views"] == ["forest_noon", "nether_crimson", "end_dragon"] and cal["rounds"] == 1
    assert cal["thresholds"]["geoMean"] == 0.5 and cal["baseline"]["profile"] == "played"
    assert {n["twin"] for n in cal["nulls"]} == {"twin-1", "twin-2"}
    said.clear()
    again = calibrate_verb.calibrate(root, "quick", host, FakeMachine(), said.append, print)
    assert again["ran"] == [] and "exists for this identity; nothing to run" in said[0]
    (root / outcome["path"]).unlink()  # every session whole, no calibration: none to run
    rewritten = calibrate_verb.calibrate(root, "quick", host, FakeMachine(), print, print)
    assert rewritten["ran"] == [] and rewritten["stopped"] is None
    assert len(host.states) == 4  # the two calibrate calls that ran sessions held them


def test_calibrate_names_a_session_by_its_identity_within_40_characters() -> None:
    digest = "f" * 64
    name = calibrate_verb.session_name("quick", digest, 10)
    assert name == "cal-quick-ffffffffffff-10" and record.NAME.fullmatch(name)


# D43's split (run-record.md#split-sessions) on the fake: groups, parts, resume, session record.


def set_suite(root: Path, **changes: Any) -> None:
    """The root's suite with `changes` as section.key=value paths (capture__reloadCap=12)."""
    path = root / platform.SUITE
    suite = json.loads(path.read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        section, key = dotted.split("__")
        suite[section][key] = value
    path.write_text(json.dumps(suite), encoding="utf-8")


def lose_focus_at(monkeypatch, fake: modfake.Fake, nth: int) -> None:
    """focus.lost after the nth window from now (D42 ends that launch invalid)."""
    original = fake._window
    seen = {"windows": 0}

    def window(args: dict) -> dict:
        found = original(args)
        seen["windows"] += 1
        if seen["windows"] == nth:
            fake.emit("focus.lost", {})
        return found

    monkeypatch.setattr(fake, "_window", window)


def launches(fake: modfake.Fake) -> int:
    return sum(1 for m in fake.received if m.get("cmd") == "world.wait")


def test_a_split_session_runs_its_parts_then_writes_its_session_record(
    fake_run, monkeypatch, capsys
) -> None:
    """Over a cap of 12, quick mode's twin and one candidate (5 reloads a view without the
    warm-up pass) run as 2 launches: forest_noon and nether_crimson (12), end_dragon (7)."""
    root, spec_path, fake, host = fake_run
    set_suite(root, capture__reloadCap=12)
    fresh_games(monkeypatch, fake, host)
    cid = fake_calibration(root, spec_path)
    spec = measured(name="m2-split-test", variants=[BASE, SHADOWS], calibration=cid)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    assert cli.main(["run", str(spec_path), "--check"]) == 0
    assert "split: 2 launches of views (D43): forest_noon, nether_crimson; end_dragon" in (
        capsys.readouterr().out
    )
    said: list[str] = []
    announced: list[str] = []
    found, path = run_verb.run_session(
        root, spec_path, host, FakeMachine(), said.append, announced.append
    )
    assert path == root / record.RECORDS / "m2-split-test.json" and found["status"] == "ok"
    assert found["parts"] == ["m2-split-test-p1", "m2-split-test-p2"]
    assert host.states == [HOLD, measure.ES_CONTINUOUS]  # one request over both launches
    assert found["groups"] == [["forest_noon", "nether_crimson"], ["end_dragon"]]
    assert [a for a in announced if "part 1 of 2 of m2-split-test" in a]
    assert all("no warm-up pass" in a for a in announced if a.startswith("launch (announced)"))
    assert launches(fake) == 2 and reloads(fake) == (12 - 1) + (7 - 1)  # selftest's apart
    parts = [record.read_record(root, name) for name in found["parts"]]
    assert [p["split"] for p in parts] == [
        {
            "session": "m2-split-test",
            "part": 1,
            "parts": 2,
            "views": ["forest_noon", "nether_crimson"],
        },
        {"session": "m2-split-test", "part": 2, "parts": 2, "views": ["end_dragon"]},
    ]
    assert all(p["status"] == "ok" and "verdicts" not in p for p in parts)
    assert all(p["session"]["displays"]["acTimeoutS"] == 600 for p in parts)
    assert all(c["pass"] == 2 for p in parts for c in p["captures"])  # no warm-up pass
    assert [len(p["captures"]) for p in parts] == [10, 5]
    assert found["identity"] == parts[0]["identity"] == parts[1]["identity"]
    judged = found["verdicts"]
    assert judged["calibration"] == cid and judged["twin"]["inside"] is True
    assert [r["view"] for r in judged["candidates"][0]["views"]] == [
        "forest_noon",
        "nether_crimson",
        "end_dragon",
    ]
    assert "captures" not in found and found["variants"][0]["id"] == "baseline"
    again = compare_verb.compare(root, "m2-split-test", None)
    assert again["sameAsRecord"] is True
    with pytest.raises(compare_verb.CompareError, match="is part 1 of session m2-split-test"):
        compare_verb.compare(root, "m2-split-test-p1", None)
    with pytest.raises(record.RecordError, match="run m2-split-test exists"):
        run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)


def test_only_a_measured_run_holds_the_displays_on(fake_run, monkeypatch) -> None:
    root, _, _, host = fake_run
    seen: list[dict | None] = []

    def perform(*args: object, displays: dict | None = None, **kwargs: object) -> dict:
        seen.append(displays)
        return {"status": "ok"}

    monkeypatch.setattr(run_verb, "perform", perform)
    monkeypatch.setattr(run_verb, "write_launch", lambda root, found, say: root / "x.json")
    acceptance = {
        "name": "m2-acc-test",
        "kind": "acceptance",
        "views": "bench_263",
        "world": "bench_263",
        "variants": [{"pack": PACK, "profile": None}],
        "tier": "bench",
        "resourcePacks": "standard",
        "items": ["A3"],
    }
    run_verb.run_session(root, acceptance, host, FakeMachine(), print, print)
    assert seen == [None] and host.states == []
    run_verb.run_session(root, measured(name="m2-held-test"), host, FakeMachine(), print, print)
    assert seen[1] is not None and seen[1]["request"] == measure.DISPLAY_REQUEST
    assert host.states == [HOLD, measure.ES_CONTINUOUS]


def test_a_split_session_resumes_at_its_first_part_not_ok(fake_run, monkeypatch, capsys) -> None:
    root, spec_path, fake, host = fake_run
    set_suite(root, capture__reloadCap=8)  # the baseline and its twin, 3 reloads a view: 8, 5
    fresh_games(monkeypatch, fake, host)
    spec_path.write_text(json.dumps(measured(name="m2-resume-test")), encoding="utf-8")
    lose_focus_at(monkeypatch, fake, 6 + 2)  # part 2's second window
    assert cli.main(["run", str(spec_path)]) == 1
    err = capsys.readouterr().err
    assert "invalid; results/records/m2-resume-test-p2.json" in err
    assert "rerun to resume m2-resume-test at this part" in err
    assert not (root / record.RECORDS / "m2-resume-test.json").exists()
    monkeypatch.setattr(fake, "_window", fake.__class__._window.__get__(fake))
    before = launches(fake)
    said: list[str] = []
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), said.append, print)
    assert found["status"] == "ok" and launches(fake) == before + 1  # part 1 kept
    assert found["parts"] == ["m2-resume-test-p1", "m2-resume-test-p2b"]
    assert any("m2-resume-test: part 1 of 2 is m2-resume-test-p1, ok" in s for s in said)
    assert record.read_record(root, "m2-resume-test-p2")["status"] == "invalid"
    assert "verdicts" not in found  # calibration null (D40)


def test_a_part_of_another_identity_ends_its_session_invalid(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    set_suite(root, capture__reloadCap=8)
    fresh_games(monkeypatch, fake, host)
    spec_path.write_text(json.dumps(measured(name="m2-moved-test")), encoding="utf-8")
    lose_focus_at(monkeypatch, fake, 6 + 1)
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert (found["name"], found["status"]) == ("m2-moved-test-p2", "invalid")
    set_suite(root, validity__minFrames=99)  # the suite's hash moves: another identity
    found, path = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert path.name == "m2-moved-test.json" and found["status"] == "invalid"
    assert "part 2's identity differs from m2-moved-test-p1's: suite.sha256" in found["reason"]
    assert found["parts"] == ["m2-moved-test-p1"] and "verdicts" not in found
    with pytest.raises(record.RecordError, match="run m2-moved-test exists"):  # never resumed
        run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)


def test_a8_in_a_split_session_waits_in_its_parts_and_is_judged_in_its_record(
    fake_run, monkeypatch
) -> None:
    root, spec_path, fake, host = fake_run
    small_full(root)
    set_suite(root, capture__reloadCap=12)
    fresh_games(monkeypatch, fake, host)
    cid = fake_calibration(root, spec_path, mode="full")
    spec = measured(
        name="m2-a8-split",
        mode="full",
        kind="acceptance",
        items=["A8"],
        variants=[BASE, TIMED],
        calibration=cid,
    )
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "ok" and found["acceptance"][0]["pass"] is True
    part = record.read_record(root, found["parts"][0])
    entry = part["acceptance"][0]
    assert entry["pass"] is None and entry["evidence"]["pending"] == (
        "judged in session m2-a8-split's record"
    )
    assert part["status"] == "ok"


def test_calibrate_resumes_a_split_session_at_its_first_part_not_ok(fake_run, monkeypatch):
    """Quick calibration sessions over a cap of 12 (2 twins: 5 reloads a view) take 2 launches;
    the first calibrate stops at session 1's second part, the next counts 3 launches left."""
    root, _, fake, host = fake_run
    small_calibration(root, 2)
    set_suite(root, capture__reloadCap=12)
    fresh_games(monkeypatch, fake, host)
    lose_focus_at(monkeypatch, fake, 10 + 2)
    announced: list[str] = []
    outcome = calibrate_verb.calibrate(root, "quick", host, FakeMachine(), print, announced.append)
    assert "0 whole, 2 to run, 4 launch(es)" in announced[0]
    assert outcome["stopped"] is not None and outcome["ran"] == [outcome["ran"][0]]
    monkeypatch.setattr(fake, "_window", fake.__class__._window.__get__(fake))
    announced.clear()
    outcome = calibrate_verb.calibrate(root, "quick", host, FakeMachine(), print, announced.append)
    assert "0 whole, 2 to run, 3 launch(es)" in announced[0]
    assert outcome["stopped"] is None
    cal = record.load_calibration(root, outcome["calibration"])
    first = record.read_record(root, cal["sessions"][0])
    assert first["parts"][1].endswith("-p2b") and len(cal["nulls"]) == 4


# The review's fixes (M2.P07 step 4).


def judged_record(root: Path, name: str, cid: str, beyond: bool, at: str) -> None:
    """A record the twin monitor reads: ok, judged by `cid`, its twin inside or beyond."""
    found = {
        "name": name,
        "status": "ok",
        "startedAt": at,
        "verdicts": {"calibration": cid, "twin": {"inside": not beyond}},
    }
    (root / record.RECORDS).mkdir(parents=True, exist_ok=True)
    (root / record.RECORDS / f"{name}.json").write_text(json.dumps(found), encoding="utf-8")


def test_a_judged_run_keeps_its_calibrations_launch_its_newest_and_its_monitor(fake_run) -> None:
    """measurement.md#calibration: a run whose Ci is not the calibration's twins a session would
    launch otherwise (D43); a superseded generation, or one whose twin monitor asks for
    recalibrating (more than 2 of the last 20 twins beyond), judges no new run."""
    root, spec_path, _, _ = fake_run
    cid = fake_calibration(root, spec_path)
    spec_path.write_text(json.dumps(measured(calibration=cid)), encoding="utf-8")
    with pytest.raises(
        record.RecordError, match=r"measured 2 candidates \(its twins\) a round, this"
    ):
        run_verb.prepare(root, spec_path, FakeMachine())
    pair = measured(calibration=cid, variants=[BASE, SHADOWS])
    spec_path.write_text(json.dumps(pair), encoding="utf-8")
    run_verb.prepare(root, spec_path, FakeMachine())  # holds
    for n, at in enumerate(("2026-10-13T01", "2026-10-13T02", "2026-10-13T03")):
        judged_record(root, f"m2-noisy-{n}", cid, True, at)
    with pytest.raises(record.RecordError, match="twin monitor asks for recalibrating: 3 of the"):
        run_verb.prepare(root, spec_path, FakeMachine())
    spec_path.write_text(json.dumps(measured()), encoding="utf-8")
    again = fake_calibration(root, spec_path, generation=2)
    assert again == f"{cid}-r2" and record.calibration_ids(root, "quick", cid[6:]) == [cid, again]
    spec_path.write_text(json.dumps(pair), encoding="utf-8")
    with pytest.raises(record.RecordError, match=f"is superseded; fix: name {again}"):
        run_verb.prepare(root, spec_path, FakeMachine())
    spec_path.write_text(json.dumps({**pair, "calibration": again}), encoding="utf-8")
    assert run_verb.prepare(root, spec_path, FakeMachine()).spec.calibration == again


def test_a_run_that_did_not_end_ok_holds_no_verdicts_and_its_items_wait(
    fake_run, monkeypatch
) -> None:
    root, spec_path, fake, host = fake_run
    small_full(root)
    fresh_games(monkeypatch, fake, host)
    quick = fake_calibration(root, spec_path)
    full = fake_calibration(root, spec_path, mode="full")
    quit_mod = launch.quit_mod

    def bad_quit(*args: Any) -> dict:
        return {**quit_mod(*args), "exitCode": 1}

    monkeypatch.setattr(launch, "quit_mod", bad_quit)
    pair = measured(name="m2-badquit-1", calibration=quick, variants=[BASE, SHADOWS])
    spec_path.write_text(json.dumps(pair), encoding="utf-8")
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert found["status"] == "failed" and "exited 1" in found["reason"]
    assert "verdicts" not in found and found["captures"]
    a8 = measured(
        name="m2-badquit-2",
        mode="full",
        kind="acceptance",
        items=["A8"],
        variants=[BASE, TIMED],
        calibration=full,
    )
    spec_path.write_text(json.dumps(a8), encoding="utf-8")
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    entry = found["acceptance"][0]
    assert found["status"] == "failed" and entry["pass"] is None
    assert entry["evidence"]["pending"] == "the session ended failed"


def test_a_judged_split_session_whose_identity_moved_ends_invalid(fake_run, monkeypatch) -> None:
    """run-record.md#split-sessions: the part's identity is held against the first ok part's
    before the calibration's, so the session ends invalid rather than refused."""
    root, spec_path, fake, host = fake_run
    set_suite(root, capture__reloadCap=12)
    fresh_games(monkeypatch, fake, host)
    cid = fake_calibration(root, spec_path)
    spec = measured(name="m2-judged-moved", calibration=cid, variants=[BASE, SHADOWS])
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    lose_focus_at(monkeypatch, fake, 10 + 1)
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert (found["name"], found["status"]) == ("m2-judged-moved-p2", "invalid")
    set_suite(root, validity__minFrames=99)
    found, path = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert path.name == "m2-judged-moved.json" and found["status"] == "invalid"
    assert "part 2's identity differs" in found["reason"] and "verdicts" not in found


def test_a_session_record_checks_its_parts_identity_and_groups() -> None:
    one = {"name": "s-p1", "identity": {"a": 1}, "split": {"part": 1, "views": ["v1"]}}
    two = {"name": "s-p2", "identity": {"a": 1}, "split": {"part": 2, "views": ["v2"]}}
    assert run_verb.session_mismatch([one, two], (("v1",), ("v2",))) is None
    moved = {**two, "identity": {"a": 2}}
    assert "s-p2's identity differs from s-p1's: a" in str(
        run_verb.session_mismatch([one, moved], (("v1",), ("v2",)))
    )
    assert "measured ['v2'] as part 2, not group 2" in str(
        run_verb.session_mismatch([one, two], (("v1",), ("v3",)))
    )
    assert run_verb.session_mismatch([one], (("v1",), ("v2",))) == "1 parts for 2 groups"


def test_a_split_sessions_parts_must_share_their_variants() -> None:
    """The critique's finding 1: a profile edited between launches leaves the spec and the
    identity as they were, so the parts' variants (options written, read back) are compared."""
    variant = {
        "id": "shadows-off",
        "role": "candidate",
        "pack": "pack.zip",
        "sha512": "a",
        "profile": "played",
        "options": {"SHADOW_QUALITY": "-1", "CLOUD_QUALITY": "2"},
        "timers": False,
        "effective": {"sha256": "e1"},
    }
    one = {"name": "s-p1", "identity": {}, "split": {"part": 1, "views": ["v1"]}}
    two = {"name": "s-p2", "identity": {}, "split": {"part": 2, "views": ["v2"]}}
    groups = (("v1",), ("v2",))
    parts = [{**one, "variants": [variant]}, {**two, "variants": [variant]}]
    assert run_verb.session_mismatch(parts, groups) is None
    edited = {**variant, "options": {**variant["options"], "CLOUD_QUALITY": "3"}}
    parts[1] = {**two, "variants": [edited]}
    assert run_verb.session_mismatch(parts, groups) == "s-p2's variants differ from s-p1's"
    read_back = {**variant, "effective": {"sha256": "e2"}}
    parts[1] = {**two, "variants": [read_back]}
    assert run_verb.session_mismatch(parts, groups) == "s-p2's variants differ from s-p1's"


def test_a_part_keeps_its_split_when_its_analysis_breaks(fake_run, monkeypatch) -> None:
    root, spec_path, fake, host = fake_run
    set_suite(root, capture__reloadCap=8)
    fresh_games(monkeypatch, fake, host)
    spec_path.write_text(json.dumps(measured(name="m2-broken-split")), encoding="utf-8")

    def broken(run: Any) -> dict:
        raise RuntimeError("the cut met a wall")

    monkeypatch.setattr(run_verb, "measured_fields", broken)
    found, _ = run_verb.run_session(root, spec_path, host, FakeMachine(), print, print)
    assert found["name"] == "m2-broken-split-p1" and found["status"] == "failed"
    assert found["split"]["session"] == "m2-broken-split" and "met a wall" in found["reason"]


def test_an_orphaned_parts_items_wait_on_their_session_record(tmp_path: Path) -> None:
    raw = tmp_path / record.RAW / "m2-a8-x-p1"
    raw.mkdir(parents=True)
    spec = {"kind": "acceptance", "mode": "full", "items": ["A8", "A11"]}
    split = {"session": "m2-a8-x", "part": 1, "parts": 2, "views": ["v1"]}
    journal = {"name": "m2-a8-x-p1", "spec": spec, "split": split}
    found = measure.orphan_record(tmp_path, raw, journal, {"at": "now"}, False)
    assert found["split"] == split
    assert [(e["item"], e["pass"]) for e in found["acceptance"]] == [("A8", None), ("A11", None)]
    assert found["acceptance"][0]["evidence"]["pending"] == "judged in session m2-a8-x's record"
    record.check_acceptance(found["acceptance"])


def test_the_twin_monitor_counts_a8_and_a11_twins_and_only_ok_records(tmp_path: Path) -> None:
    folder = tmp_path / record.RECORDS
    folder.mkdir(parents=True)
    cid = "full-" + "c" * 64
    entry = {"item": "A8", "pass": True, "evidence": {"calibration": cid, "twin": False}}
    for name, changes in (
        ("m2-a8-1", {}),
        ("m2-a8-2", {"status": "failed"}),
        ("m2-a8-3", {"split": {"session": "m2-a8-x"}}),
    ):
        found = {"name": name, "status": "ok", "startedAt": name, "acceptance": [entry], **changes}
        (folder / f"{name}.json").write_text(json.dumps(found), encoding="utf-8")
    assert record.judged_twins(tmp_path, cid) == [True]


def test_calibrate_recalibrates_its_identity_as_a_new_generation(fake_run, monkeypatch) -> None:
    """measurement.md#calibration: the monitor's recalibration under the same identity; the
    sessions cal-<mode>-<hash>-r2-<n>, the file <mode>-<sha256>-r2 superseding the first; a
    session whose spec calibrate did not write is passed over."""
    root, _, fake, host = fake_run
    small_calibration(root, 2)
    fresh_games(monkeypatch, fake, host)
    first = calibrate_verb.calibrate(root, "quick", host, FakeMachine(), print, print)
    assert first["stopped"] is None and "-r" not in first["calibration"]
    with pytest.raises(record.RecordError, match="no full calibration of this identity"):
        calibrate_verb.calibrate(root, "full", host, FakeMachine(), print, print, True)
    digest = first["identityHash"]
    stray = calibrate_verb.session_spec(
        calibrate_verb.session_name("quick", digest, 1, 2), "quick", PACK
    )
    run_verb.run_session(root, {**stray, "notes": "by hand"}, host, FakeMachine(), print, print)
    said: list[str] = []
    announced: list[str] = []
    again = calibrate_verb.calibrate(
        root, "quick", host, FakeMachine(), said.append, announced.append, True
    )
    assert again["calibration"] == f"{first['calibration']}-r2" and again["stopped"] is None
    assert "(generation 2, after quick-" in announced[0] and "0 whole, 2 to run" in announced[0]
    assert any("a spec calibrate did not write" in s for s in said)
    cal = record.load_calibration(root, again["calibration"])
    assert (cal["generation"], cal["supersedes"]) == (2, first["calibration"])
    assert all("-r2-" in name for name in cal["sessions"]) and cal["twinMonitor"]["window"] == 20
    said.clear()
    calibrate_verb.calibrate(root, "quick", host, FakeMachine(), said.append, print)
    assert f"{again['calibration']}.json exists for this identity" in said[0]
