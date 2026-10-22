"""The measured session (docs/measurement.md#session and #validity; docs/plans/m2.md M2.P05): what
`run` does for a measurement, calibration or A8 and A11 acceptance run between the launch and the
quit, the captures it records after it, the machine check before it (D42), the displays held on
through it and the orphans the next run finishes (D41).

- Variants: the spec's (record.check_variants) and the twins the runner adds, a measurement run's
  one A/A twin, a calibration run's statistics.calibration.twinsPerSession, each a byte copy of the
  baseline's zip under shaderpacks/ with the baseline's settings (D35); a measurement run's
  passthrough candidate, a zip built here and written beside them (D46). Before every reload the
  variant's files are written: iris.properties naming its pack and the pack's settings file
  shaderpacks/<pack>.txt with its option values (Iris re-reads both at a reload, spike R4). After
  the reload its pack and every written option's effective value are checked, and the variant's
  whole option map may not move between its captures.
- The session: PresentMon started on the game (one ETW session per run, P5); the session start,
  the baseline's files written before the start-of-run reload; the warm-up pass, one baseline
  window per view; the measured pass, per view the schedule A, then (Ci, A) for each candidate, R
  rounds (the mode's, or a budget run's own: record.BUDGET). Each pass is a lap over the mode's
  views, ordered for the fewest weather and dimension changes (D48). At a view: its function
  (time, weather), camera.place, the GUI and game mode (D49: entities alone shows the GUI, in
  creative with prep's torch), then the stepped ticks when the overworld's weather changed, with
  the camera at the view. Per capture: the variant's files,
  shaders.reload and the options read back, timers.start for a timers-on variant,
  window.measure {after: reload} with the largest settle that applies, timers.stop; the heap read
  every record.RELOAD_EVERY reloads when the spec asks (M2.P06), and then after every reload the
  game's and the adapter's GPU memory (typeperf, only read). A budget run may reload the baseline
  in every slot (`alone`) or leave out the windows (`windows` false: M2.P06's diagnosis).
  PresentMon stops once a row past the last window is written.
- After the session: each window cut from the complete CSV between its HEAD stamps
  (presentmon.cut_window), its summaries and measurement.md#validity's flags, the invalidating
  events inside it among them; a capture without them is never passed.
"""

import contextlib
import csv
import hashlib
import io
import json
import re
import shutil
import statistics
import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from optilux import launch, modclient, platform, presentmon, record, world
from optilux.acceptance import F4_MIN_AVAILABLE, memory_row
from optilux.session import (
    CLOSED,
    COMMAND_TIMEOUT,
    GPU_COUNTER,
    INVALIDATING,
    OVERWORLD,
    PARTIAL,
    PLACE_TIMEOUT,
    READY_TIMEOUT,
    RELOAD_TIMEOUT,
    STABLE_FRAMES,
    Journal,
    RunError,
    RunHost,
    Session,
    now,
    session_start,
    view_pose,
    visual_settle,
)
from optilux.verbs.install import RUNTIME, Say, shown

# The present mode every row of a valid window shows (measurement.md#validity).
INDEPENDENT_FLIP = "Hardware: Independent Flip"
# A twin's file under shaderpacks/: optilux-twin<n>-<the baseline's zip>.
TWIN_PREFIX = "optilux-twin"
# The passthrough pack (plans/m2.md D46), record.PASSTHROUGH under shaderpacks/: a `shaders`
# directory, which Iris looks for in a zip, and an empty shaders.properties. The pinned Iris jar
# (P17, read with javap in M2.P08) draws every program the pack lacks with its fallback into
# colortex0, makes no shadow targets and so no shadow pass (the pack neither enables shadows nor
# samples them), and with no final program copies colortex0 to the screen.
PASSTHROUGH_ENTRIES = ("shaders/", "shaders/shaders.properties")
# As `pack build` writes its zip (plans/m0.md D14): the zip format's epoch and Unix attributes,
# so every machine writes the same bytes; a directory drwxr-xr-x with the MS-DOS directory bit,
# a file rw-r--r--.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
ZIP_SYSTEM = 3
ZIP_FOLDER = (0o40755 << 16) | 0x10
ZIP_FILE = 0o100644 << 16
# The pack's settings file Iris reads at a reload, beside the pack in shaderpacks/.
SETTINGS = "{pack}.txt"
# The view functions world prep writes (world.py: optilux:view/<id>, ending in `return 1`).
FUNCTION = "/function optilux:view/{id}"
# The only view that shows the GUI, in creative with prep's torch in the main hand (D49).
ENTITIES = "entities"
TICKS_TIMEOUT = 60.0
# The timers on a timers-on variant (mod-protocol.md#commands): every pass, read 3 frames late,
# and room for every frame from the start to the stop (a 4 s settle and a 2.5 s window at 400 fps
# are 2,600 frames), so none drops `full`.
TIMERS = {"perPass": True, "maxPending": 3, "maxFrames": 10000}
# PresentMon: its first rows before the first window; a row past the last window before its stop.
FIRST_ROWS_TIMEOUT = presentmon.FIRST_ROW_TIMEOUT
COVER_TIMEOUT = 30.0
CSV = "presentmon.csv"
# The flags that invalidate a capture (measurement.md#validity); leftGpuBound marks a candidate's
# rows indicative, timersDropped its timer rows, neither its GPUBusy.
INVALIDATING_FLAGS = (
    "cut",
    "fewFrames",
    "notNumbers",
    "halves",
    "presentMode",
    "cpuLimited",
    "event",
    "noWindow",
)
# The events that end a measured session (D42).
ENDING = ("focus.lost", "screen.opened")
# The screens the harness's own steps open: a camera.place into another dimension shows the
# loading screen (every M1 and M2.P04 log); the quit's saving screens come after the last step.
HARNESS_SCREENS = ("net.minecraft.client.gui.screens.LevelLoadingScreen",)
# A visual run's captures (plans/m3.md D63): at each view and variant a pair of frames PAIR_MS
# apart, the first ready-triggered, both aligned, written under raw/<run>/frames/<view>/<variant>/;
# the mod's own wait for the predicate (at most READY_TIMEOUT) and both PNGs inside the timeout.
# A pair is flagged `moving` when its PNGs differ: the game's one PNG writer writes equal pixels
# as equal bytes, and a pack drawing the same frame every frame never moves (record.VISUAL_FLAGS).
PAIR = record.VISUAL_PAIR
PAIR_MS = 2000
FRAMES = "frames"
VISUAL_CAPTURE_TIMEOUT = READY_TIMEOUT + 30.0


def ends(event: dict) -> bool:
    """An event that ends a measured session (D42): focus lost, or a screen the harness did not
    open."""
    if event["event"] == "screen.opened":
        return (event.get("data") or {}).get("screen") not in HARNESS_SCREENS
    return event["event"] in ENDING


# D42: the machine to itself before a measured launch.
IDLE_SECONDS = 30.0
GPU_MAX_PCT = 2.0
GPU_SAMPLES = 3
MACHINE_WAIT = 600.0
MACHINE_POLL = 10.0
# The displays held on through a measured run (user, 2026-10-14): off on the idle timeout, nothing
# presents and PresentMon writes no row (m2-survey-1-p1 and -p1b). winbase.h's flags.
ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002
DISPLAY_REQUEST = "ES_CONTINUOUS | ES_DISPLAY_REQUIRED"
# GUID_CONSOLE_DISPLAY_STATE's values (winnt.h); a dimmed display still presents.
DISPLAY_STATES = {0: "off", 1: "on", 2: "dimmed"}
ENGINE = re.compile(
    r"GPU Engine\(pid_(?P<pid>\d+)_luid_0x(?P<high>[0-9A-Fa-f]+)_0x(?P<low>[0-9A-Fa-f]+)_phys_\d+"
    r"_eng_\d+_engtype_3D\)"
)
PDH_HEADER = "(PDH-CSV 4.0)"
# M2.P06's diagnosis: the game's and the display adapter's GPU memory, in bytes (typeperf).
PROCESS_MEMORY = re.compile(
    r"GPU Process Memory\(pid_(?P<pid>\d+)_luid_0x(?P<high>[0-9A-Fa-f]+)_0x(?P<low>[0-9A-Fa-f]+)"
    r"_phys_\d+\)\\(?P<kind>Dedicated|Shared) Usage$"
)
ADAPTER_MEMORY = re.compile(
    r"GPU Adapter Memory\(luid_0x(?P<high>[0-9A-Fa-f]+)_0x(?P<low>[0-9A-Fa-f]+)_phys_\d+\)"
    r"\\(?P<kind>Dedicated|Shared) Usage$"
)

# D41: an orphan's game and PresentMon ended within these.
ORPHAN_STOP_TIMEOUT = presentmon.STOP_TIMEOUT


# Variants and their files.


@dataclass(frozen=True)
class Variant:
    """One variant of a measured run: its id, role (baseline, candidate, twin), the file Iris loads
    from shaderpacks/, the pinned zip it is (a twin's source), the profile, the option values its
    settings file holds, and whether the per-pass timers run in its windows."""

    id: str
    role: str
    pack: str
    source: str
    profile: str | None
    options: dict
    timers: bool


def variants(spec: record.Spec, suite: dict) -> list[Variant]:
    """The spec's variants, the baseline first, then the twins the runner adds after its
    candidates: one A/A twin (`twin`) for a measurement or A8 and A11 run, twinsPerSession
    (`twin-1`...) for a calibration run; each twin the baseline's settings on a copy of its zip."""
    base, *others = spec.variants
    found = [
        Variant(
            base["id"],
            "baseline",
            base["pack"],
            base["pack"],
            base["profile"],
            dict(base["options"]),
            base["timers"],
        )
    ]
    found += [
        Variant(
            v["id"],
            "candidate",
            v["pack"],
            v["pack"],
            v["profile"],
            dict(v["options"]),
            v["timers"],
        )
        for v in others
    ]
    if spec.alone:  # a budget run's baseline in every slot: no twin (record.BUDGET)
        return found
    twins = record.candidates(spec.kind, spec.variants, suite) - len(others)
    for n in range(1, twins + 1):
        found.append(
            Variant(
                record.TWIN if twins == 1 else f"{record.TWIN}-{n}",
                "twin",
                f"{TWIN_PREFIX}{n}-{base['pack']}",
                base["pack"],
                base["profile"],
                dict(base["options"]),
                base["timers"],
            )
        )
    return found


def settings_text(options: dict) -> bytes:
    """The pack's settings file as the harness writes it before a reload: one name=value line per
    option in name order, a boolean as true or false, LF; Iris reads it as a Java properties file
    and writes it back with the effective values."""
    lines = [
        f"{name}={'true' if value is True else 'false' if value is False else value}\n"
        for name, value in sorted(options.items())
    ]
    return "".join(lines).encode("ascii")


def variant_files(game: Path, display: dict, tier: str, variant: Variant) -> dict[Path, bytes]:
    """The two files a variant's reload reads, by path: the pack's settings file and
    config/iris.properties as launch writes it, naming the variant's pack."""
    iris = launch.iris_text(launch.iris_properties(display, tier, variant.pack))
    return {
        game / launch.SHADER_PACKS / SETTINGS.format(pack=variant.pack): settings_text(
            variant.options
        ),
        game / launch.IRIS: iris.encode("utf-8"),
    }


def make_twins(
    game: Path, found: list[Variant], source: Path, sha512: str, own: Callable[[Path], None]
) -> list[dict]:
    """Each twin's zip, a byte copy of the baseline's (D35), written through a part name and
    checked by sha512 against the pin; RunError for a copy already there (an orphan's: `run`
    finishes orphans first) or one that differs. `own` takes each file before it is written, so
    the run deletes what it wrote and nothing else."""
    made = []
    for twin in (v for v in found if v.role == "twin"):
        target = game / launch.SHADER_PACKS / twin.pack
        if target.exists():
            raise RunError(f"{target.name} exists in shaderpacks/; fix: delete it, then rerun")
        own(target)
        part = target.with_name(target.name + ".part")
        shutil.copyfile(source, part)
        part.replace(target)
        digest = platform.sha512(target)
        if digest != sha512:
            raise RunError(f"{target.name} hashes {digest[:12]}..., its source {sha512[:12]}...")
        made.append({"file": twin.pack, "sha512": digest})
    return made


def passthrough_zip() -> bytes:
    """The passthrough pack's bytes (D46): PASSTHROUGH_ENTRIES in order, each empty and stored."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name in PASSTHROUGH_ENTRIES:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.create_system = ZIP_SYSTEM
            info.external_attr = ZIP_FOLDER if name.endswith("/") else ZIP_FILE
            archive.writestr(info, b"")
    return buffer.getvalue()


def variant_sha512(variant: Variant, reference: str) -> str:
    """The sha512 of the zip a variant loads: the passthrough's own, else the pinned reference
    pack's `reference` (a twin's is its source's)."""
    if variant.source == record.PASSTHROUGH:
        return hashlib.sha512(passthrough_zip()).hexdigest()
    return reference


def make_passthrough(game: Path, found: list[Variant], own: Callable[[Path], None]) -> dict | None:
    """The passthrough pack under shaderpacks/ when a variant runs it (D46), written through a
    part name and checked by sha512; RunError for a file already there (an orphan's: `run`
    finishes orphans first). `own` takes it before it is written, as make_twins does."""
    if not any(v.source == record.PASSTHROUGH for v in found):
        return None
    target = game / launch.SHADER_PACKS / record.PASSTHROUGH
    if target.exists():
        raise RunError(f"{target.name} exists in shaderpacks/; fix: delete it, then rerun")
    own(target)
    data = passthrough_zip()
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    part.replace(target)
    digest, wanted = platform.sha512(target), hashlib.sha512(data).hexdigest()
    if digest != wanted:
        raise RunError(f"{target.name} hashes {digest[:12]}..., written {wanted[:12]}...")
    return {"file": record.PASSTHROUGH, "sha512": digest}


def remove_files(paths: list[Path]) -> dict:
    """The run's files deleted (the game has exited): those removed, and those that would not go."""
    removed, kept = [], []
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                removed.append(path.name)
        except OSError as error:
            kept.append(f"{path.name}: {error}")
    return {"removed": removed, "kept": kept}


def effective_problems(variant: Variant, values: dict) -> list[str]:
    """Each written option whose effective value after the reload is not the written one: Iris
    ignores a value its option does not list and keeps the default."""
    problems = []
    for name, value in sorted(variant.options.items()):
        if name not in values:
            problems.append(f"{name} is no option of the pack")
        elif values[name] != value:
            problems.append(f"{name} reads {values[name]!r}, written {value!r}")
    return problems


def values_sha256(values: dict) -> str:
    return record.sha256_of(values)


# The schedule and the laps.


def schedule(found: list[Variant], rounds: int, alone: bool = False) -> list[tuple[Variant, int]]:
    """One view's captures (measurement.md#session, suite.json statistics.schedule): A, then
    (Ci, A) for each candidate in order, R rounds; each with its round. `alone`: the baseline
    takes the twin's slot too (a budget run's, record.BUDGET)."""
    base, others = found[0], ([found[0]] if alone else found[1:])
    order = [(base, 1)]
    for r in range(1, rounds + 1):
        for variant in others:
            order += [(variant, r), (base, r)]
    return order


def settle_for(capture: dict, view_switch: bool, dimension_change: bool) -> float:
    """The window's skip (measurement.md#session step 6): the largest suite.json settle that
    applies to anything since the last window: a reload always, a view switch, a dimension
    change."""
    settles = capture["settleS"]
    found = settles["afterReload"]
    if view_switch:
        found = max(found, settles["afterViewSwitch"])
    if dimension_change:
        found = max(found, settles["afterDimensionChange"])
    return found


# The window's numbers.


def timers_summary(answer: dict, start: int, end: int) -> dict:
    """A timers-on window's timer rows (run-record.md#fields): its frames start to end - 1 among
    the timers' frames, those missing (dropped), each pass's median in ms (same-named groups of a
    frame summed), the median top-level sum, the dropped counts since the start."""
    frames = [f for f in answer["frames"] if start <= f["frameIndex"] < end]
    passes: dict[str, list[float]] = {}
    depths: dict[str, int] = {}
    for frame in frames:
        sums: dict[str, int] = {}
        for item in frame["passes"]:
            sums[item["name"]] = sums.get(item["name"], 0) + item["gpuNanos"]
            depths.setdefault(item["name"], item["depth"])
        for name, nanos in sums.items():
            passes.setdefault(name, []).append(nanos / 1e6)
    tops = [modclient.top_level_nanos(f) / 1e6 for f in frames]
    return {
        "frames": len(frames),
        "missing": (end - start) - len(frames),
        "topLevelMs": round(statistics.median(tops), 4) if tops else None,
        "passes": {
            name: {"depth": depths[name], "ms": round(statistics.median(ms), 4)}
            for name, ms in passes.items()
        },
        "dropped": answer["dropped"],
        "unmatchedPops": answer["unmatchedPops"],
        "cutPasses": answer["cutPasses"],
        "byFrame": {f["frameIndex"]: modclient.top_level_nanos(f) for f in frames},
    }


def residual_ms(line: presentmon.Timeline, cut: dict, start: int, by_frame: dict) -> float | None:
    """A11's residual on one window (mod.md#12-acceptance): the median over its frames of the
    frame's GPUBusy less its top-level pass sum, frame k's row found by the swap mapping
    (cut_window's frameRow + k - start). None when a timer frame has no row or no GPUBusy there
    (the cut's edge can leave frame start's row outside the rows `notNumbers` reads): the residual
    is unjudged, never a median of fewer frames."""
    first = cut.get("frameRow")
    if first is None:
        return None
    found = []
    for index, nanos in by_frame.items():
        at = first + (int(index) - start)
        row = line.rows[at] if 0 <= at < len(line.rows) else {}
        busy = presentmon.number(row.get(presentmon.GPU_BUSY))
        if busy is None:
            return None
        found.append(busy - nanos / 1e6)
    return round(statistics.median(found), 4) if found else None


def window_events(events: list[dict], start: int, end: int) -> list[dict]:
    """The events that invalidate a capture (mod-protocol.md#client-rules) stamped in one of its
    frames, start to end - 1: an event carries the frame current when it was sent, and frame end
    begins at the end mark, after the window."""
    return [
        e
        for e in events
        if e["event"] in INVALIDATING
        and isinstance(e.get("frameIndex"), int)
        and start <= e["frameIndex"] < end
    ]


def flags_of(role: str, summary: dict, cut: dict, events: list[dict], validity: dict) -> list[str]:
    """measurement.md#validity's flags of one capture: the cut (a problem at an edge or between
    them), fewer than minFrames rows, metrics that are no numbers, halves apart by more than
    halvesWithinPct, a row in any present mode but Independent Flip, GPUBusy over FrameTime under
    gpuBoundMin (the baseline's capture invalid, a candidate's or twin's left GPU-bound), an
    invalidating event inside the window."""
    found = []
    if cut["problems"]:
        found.append("cut")
    if summary["frames"] < validity["minFrames"]:
        found.append("fewFrames")
    if summary["notNumbers"]:
        found.append("notNumbers")
    halves = summary["halvesPct"]
    if halves is None or halves > validity["halvesWithinPct"]:
        found.append("halves")
    if set(summary["presentModes"]) != {INDEPENDENT_FLIP}:
        found.append("presentMode")
    ratio = summary["gpuBusyOverFrameTime"]
    if ratio is None or ratio < validity["gpuBoundMin"]:
        found.append("cpuLimited" if role == "baseline" else "leftGpuBound")
    if events:
        found.append("event")
    return found


def captured(entry: dict, line: presentmon.Timeline, events: list[dict], validity: dict) -> dict:
    """A journaled capture as the record holds it: its place in the session, the cut's rows and
    edges, the summaries, the flags and whether it is valid; with timers, its timer rows and A11's
    residual. The window's marks and the cut's problems stay in raw/. A budget run's capture
    without a window (record.BUDGET) keeps its place, reload and GPU memory, no numbers, never
    valid."""
    window = entry["window"]
    place = {k: entry[k] for k in ("index", "pass", "view", "variant", "role", "round", "settleS")}
    if window is None:
        return {
            **place,
            "reloadS": entry["reload"]["seconds"],
            "gpuMemory": entry.get("gpuMemory"),
            "flags": ["noWindow"],
            "valid": False,
            "problems": [],
        }
    start, end = window["start"], window["end"]
    cut = presentmon.cut_window(line, start, end, window["frames"])
    summary = presentmon.summary(cut["rows"])
    inside = window_events(events, start["frameIndex"], end["frameIndex"])
    flags = flags_of(entry["role"], summary, cut, inside, validity)
    modes = summary["presentModes"]
    found: dict[str, Any] = dict(place)
    found.update(
        frames=window["frames"],
        rows=summary["frames"],
        edges=cut["edges"],
        gpuBusyMs=summary["gpuBusyMs"],
        frameTimeMs=summary["frameTimeMs"],
        frameTimeP95Ms=summary["frameTimeP95Ms"],
        gpuLatencyMs=summary["gpuLatencyMs"],
        gpuBusyOverFrameTime=summary["gpuBusyOverFrameTime"],
        halvesGpuBusyMs=summary["halvesGpuBusyMs"],
        halvesPct=summary["halvesPct"],
        presentMode=next(iter(modes)) if len(modes) == 1 else modes,
    )
    timers = entry.get("timers")
    if timers is not None:
        if timers["missing"]:
            flags.append("timersDropped")
        found["timers"] = {
            **{k: v for k, v in timers.items() if k != "byFrame"},
            "residualMs": residual_ms(line, cut, start["frameIndex"], timers["byFrame"]),
        }
    if "gpuMemory" in entry:
        found["gpuMemory"] = entry["gpuMemory"]
    found["flags"] = flags
    found["valid"] = not any(flag in INVALIDATING_FLAGS for flag in flags)
    found["problems"] = cut["problems"] + [
        f"{e['event']} at frame {e['frameIndex']}" for e in inside
    ]
    return found


def stale_functions(root: Path, views: dict) -> list[str]:
    """The views whose function in the snapshot's data pack is not the one the views file gives
    (world.view_function): the session calls the snapshot's, the record states the views file's
    time and weather, so the two must agree (`world prep` writes both)."""
    folder = root / record.SNAPSHOTS / views["id"] / "datapacks" / world.PACK / world.FUNCTIONS
    stale = []
    for view in views["views"]:
        path = folder / f"{view['id']}.mcfunction"
        if not path.is_file() or path.read_bytes() != world.view_function(view, views["id"]):
            stale.append(view["id"])
    return stale


def read_timeline(path: Path, pid: int) -> tuple[presentmon.Timeline, dict]:
    """The complete CSV's rows of the game's process as a Timeline, keeping only the columns the
    cut and the summaries read (a full-mode session writes some 200,000 rows); and the file's
    facts. PresentMonError for a file that is not complete."""
    keep = (
        presentmon.QPC,
        presentmon.PROCESS_ID,
        presentmon.SWAP_CHAIN,
        presentmon.FRAME_TIME,
        presentmon.GPU_BUSY,
        presentmon.GPU_LATENCY,
        presentmon.PRESENT_MODE,
    )
    data = path.read_bytes()
    if not data.endswith(b"\n"):
        raise presentmon.PresentMonError(f"{path.name} ends inside a line: it is not complete")
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig")))
    header = next(reader, None)
    if header is None or presentmon.QPC not in header:
        raise presentmon.PresentMonError(f"{path.name} has no {presentmon.QPC} column")
    at = {name: header.index(name) for name in keep if name in header}
    rows, total = [], 0
    for number, values in enumerate(reader, start=2):
        if len(values) != len(header):
            raise presentmon.PresentMonError(
                f"{path.name} line {number}: {len(values)} fields, the header has {len(header)}"
            )
        total += 1
        if values[at[presentmon.PROCESS_ID]] == str(pid):
            rows.append({name: values[index] for name, index in at.items()})
    line = presentmon.timeline(rows, pid)
    facts = {
        "rows": total,
        "gameRows": len(line.rows),
        "columns": len(header),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    return line, facts


# D42: the machine to itself.


def gpu_users(text: str, luid: str) -> dict[int, float]:
    """Each process's share of the 3D engine on the adapter `luid` (0x...) from typeperf's CSV:
    per engine instance the mean of its samples, summed per pid. RecordError when the text holds
    no counter table."""
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    try:
        top = next(i for i, row in enumerate(rows) if row[0] == PDH_HEADER)
    except StopIteration:
        raise record.RecordError(
            f"typeperf printed no counter table: {text.strip()[-200:]!r}; fix: run `typeperf "
            f'"{GPU_COUNTER}" -sc 3` by hand (D42)'
        ) from None
    header = rows[top]
    samples = [row for row in rows[top + 1 :] if len(row) == len(header)]
    found: dict[int, float] = {}
    for column, path in enumerate(header[1:], start=1):
        match = ENGINE.search(path)
        if not match:
            continue
        adapter = (int(match["high"], 16) << 32) | int(match["low"], 16)
        if f"0x{adapter:x}" != luid.lower():
            continue
        values = []
        for row in samples:
            try:
                values.append(float(row[column]))
            except ValueError:
                continue
        if values:
            pid = int(match["pid"])
            found[pid] = found.get(pid, 0.0) + sum(values) / len(values)
    if not found:  # the compositor always draws there: no reading is no pass
        raise record.RecordError(
            f"typeperf read no 3D engine of the display's adapter {luid} (D3DKMT's LUID); fix: "
            f'run `typeperf "{GPU_COUNTER}" -sc 3` and compare its luid_ names (D42)'
        )
    return found


def machine_to_itself(host: RunHost, luid: str, say: Say) -> dict:
    """D42 before a measured launch: IDLE_SECONDS without input (GetLastInputInfo) and no process
    above GPU_MAX_PCT of the 3D engine over GPU_SAMPLES s (typeperf, only read), waited for up to
    MACHINE_WAIT; RecordError naming the input and the processes then. The last check's facts."""
    began = host.clock()
    checks = 0
    names = {}
    while True:
        checks += 1
        idle = host.idle_seconds()
        users = gpu_users(host.gpu_engine(GPU_SAMPLES), luid)
        busy = {pid: pct for pid, pct in users.items() if pct > GPU_MAX_PCT}
        if busy:
            names = {p.pid: p.name for p in host.processes() if p.pid in busy}
        waited = host.clock() - began
        top = sorted(users.items(), key=lambda item: -item[1])[:3]
        facts = {
            "idleSeconds": round(idle, 1),
            "highestGpuPct": [{"pid": pid, "pct": round(pct, 2)} for pid, pct in top],
            "checks": checks,
            "waitedSeconds": round(waited, 1),
        }
        if idle >= IDLE_SECONDS and not busy:
            return facts
        reasons = []
        if idle < IDLE_SECONDS:
            reasons.append(f"input {idle:.0f} s ago (needs {IDLE_SECONDS:g} s without)")
        reasons += [
            f"{names.get(pid, '?')} (pid {pid}) at {pct:.1f} % of the 3D engine"
            for pid, pct in sorted(busy.items(), key=lambda item: -item[1])
        ]
        if waited >= MACHINE_WAIT:
            raise record.RecordError(
                f"the machine was not the run's for {MACHINE_WAIT / 60:g} min (D42): "
                f"{'; '.join(reasons)}; fix: leave the machine alone and close those, then rerun"
            )
        say(f"machine (D42): waiting: {'; '.join(reasons)}")
        host.sleep(max(IDLE_SECONDS - idle, MACHINE_POLL) if idle < IDLE_SECONDS else MACHINE_POLL)


@contextlib.contextmanager
def displays_on(host: RunHost, say: Say, refuse_off: bool = True) -> Iterator[dict]:
    """The displays held on through a measured run, from before its first step to its end: a
    display-required power request on this thread (SetThreadExecutionState, DISPLAY_REQUEST; no
    setting changed), released at the end whatever happened. RecordError when the displays read
    off as it is taken (GUID_CONSOLE_DISPLAY_STATE, read after it: the request is not known to
    wake them) or unread, unless `refuse_off` is False (a visual run's: its frames are read back,
    off or on), or when a call fails. The AC display timeout and the input's seconds are recorded
    beside the state, never judged: the request holds the displays' own idle timer, so input
    older than the timeout does not mean them off (a process after a measured one). The
    request's facts."""
    try:
        timeout = host.display_timeout()
        idle = host.idle_seconds()
        host.execution_state(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)
    except OSError as error:
        raise record.RecordError(
            f"the display request: {error}; fix: rerun, and if it fails again read the calls in "
            "optilux/session.py (RunHost.display_timeout, idle_seconds, execution_state)"
        ) from None
    try:
        try:
            state = host.display_state()  # after the request, which holds them from here on
        except OSError as error:
            state = None
            say(f"displays: their state was not read: {error}")
        shown_state = DISPLAY_STATES.get(state, "unread") if state is not None else "unread"
        if shown_state in ("off", "unread") and refuse_off:
            raise record.RecordError(
                f"the displays read {shown_state} (input {idle:.0f} s ago, the display timeout "
                f"{timeout} s on AC), and with them off PresentMon records no frame; fix: wake "
                "them, then rerun at once (the run holds them on)"
            )
        say(
            f"displays: {shown_state}, held on through the run (the AC display timeout "
            f"{timeout} s, input {idle:.0f} s ago)"
        )
        yield {
            "request": DISPLAY_REQUEST,
            "state": shown_state,
            "acTimeoutS": timeout,
            "idleSeconds": round(idle, 1),
        }
    finally:
        try:
            host.execution_state(ES_CONTINUOUS)
        except OSError as error:  # the request ends with the thread: never fail a written record
            say(f"displays: the request's release failed ({error}); it ends with the process")


# The session.


@dataclass
class Measured:
    """One measured session's state and facts, kept as it goes so a session that breaks leaves
    them for its record."""

    s: Session
    spec: record.Spec
    suite: dict
    views: list[dict]
    found: list[Variant]
    journal: Journal
    pm_exe: Path
    jcmd: Path
    display_mode: str
    own: Callable[[Path], None]
    luid: str = ""
    facts: dict = field(default_factory=dict)
    entries: list[dict] = field(default_factory=list)
    effective: dict = field(default_factory=dict)
    heap: list[dict] = field(default_factory=list)
    marks: dict = field(default_factory=dict)
    recording: presentmon.Recording | None = None
    index: int = 0
    reloads: int = 0
    ramped: str | None = None
    previous: str | None = None
    gui: bool = False
    last_end: int | None = None
    last_written: Variant | None = None
    cycle: int = 1  # a visual run's align: the Optilux pack's cycle (config/pipeline.json)

    @property
    def c(self) -> modclient.Client:
        return self.s.client

    @property
    def game(self) -> Path:
        return self.s.launched.game

    def mark(self, phase: str) -> None:
        self.marks[phase] = time.monotonic()

    def write_files(self, variant: Variant) -> None:
        for path, data in variant_files(
            self.game, self.suite["display"], self.spec.tier, variant
        ).items():
            if path.parent.name == launch.SHADER_PACKS:
                self.own(path)  # the settings file is the run's; iris.properties is launch's
            path.write_bytes(data)
        self.last_written = variant

    def check_options(self, variant: Variant, answer: dict) -> None:
        """The reload's options against the variant's (RunError naming each one that differs);
        the variant's first map kept, a later one that moved refused."""
        values = answer["values"]
        problems = effective_problems(variant, values)
        if problems:
            raise RunError(
                f"{variant.id}: the options after the reload differ from the variant's: "
                f"{'; '.join(problems)}; fix: write each value as the pack lists it"
            )
        digest = values_sha256(values)
        first = self.effective.get(variant.id)
        if first is None:
            self.effective[variant.id] = {"sha256": digest, "values": values}
            kept = {"sha256": digest, "count": len(values)}
            if variant.role == "baseline" or self.spec.kind == record.VISUAL:  # D63: each in full
                kept["values"] = values
            self.journal.set(
                "effective", {**self.journal.data.get("effective", {}), variant.id: kept}
            )
        elif first["sha256"] != digest:
            moved = sorted(k for k in values if first["values"].get(k) != values[k])
            raise RunError(f"{variant.id}: its effective options moved between captures: {moved}")


def body(m: Measured) -> None:
    """The measured session after hello: PresentMon, the session start, the warm-up pass (while
    suite.json's capture.warmupPass keeps it, or the survey's spec does: D47), the measured pass,
    PresentMon's stop, input.block off."""
    s, c = m.s, m.c
    s.stop_on = ends
    output = s.raw / CSV
    session = f"{presentmon.SESSION_PREFIX}{m.spec.name}"
    pm = s.host.presentmon()
    m.mark("presentmon")
    pm_facts: dict[str, Any] = {"session": session, "csv": shown(output, s.root)}
    m.facts["presentmon"] = pm_facts
    m.recording = presentmon.start(m.pm_exe, s.launched.pid, output, session, pm)
    try:
        pid = m.recording.process.pid
        m.journal.set("presentmon", {**(s.host.process_facts(pid) or {"pid": pid}), **pm_facts})
        s.say(f"PresentMon: recording pid {s.launched.pid} as {session} into {pm_facts['csv']}")
        m.mark("start")
        base = m.found[0]
        start: dict = {}
        m.facts["start"] = start
        session_start(
            s,
            base.pack,
            m.suite["capture"]["gpuWarmupS"],
            m.display_mode,
            m.suite["display"]["resolution"],
            start,
            lambda: m.write_files(base),
        )
        m.reloads = record.ACCEPTANCE_RELOADS
        m.check_options(base, start["options"])
        m.previous = start["joined"]["pose"]["dimension"]
        heap_row(m)
        rows = presentmon.wait_rows(m.recording, pm, None, FIRST_ROWS_TIMEOUT)
        pm_facts["firstRows"] = rows
        laps = []
        if m.spec.warmup:  # suite.json capture.warmupPass (D47), or the survey's spec
            m.mark("warmupPass")
            order = record.lap(m.views, m.ramped)
            laps.append([v["id"] for v in order])
            for view in order:
                switch = arrive(m, view)
                capture(m, view, base, 0, 1, settle_for(m.suite["capture"], True, switch))
        m.mark("measuredPass")
        order = record.lap(m.views, m.ramped)
        laps.append([v["id"] for v in order])
        m.facts["laps"] = laps
        for view in order:
            switch = arrive(m, view)
            for slot, (variant, r) in enumerate(schedule(m.found, m.spec.rounds, m.spec.alone)):
                settle = settle_for(m.suite["capture"], slot == 0, switch and slot == 0)
                capture(m, view, variant, r, 2, settle)
        if m.gui:
            leave_gui(m, "end")
        m.mark("presentmonStop")
        if m.last_end is not None:
            pm_facts["cover"] = presentmon.wait_rows(m.recording, pm, m.last_end, COVER_TIMEOUT)
    except BaseException:
        with contextlib.suppress(RunError):  # the session's own error is the one to report
            stop_presentmon(m, pm)
        raise
    stop_presentmon(m, pm)
    s.step("input.block off", lambda: c.input_block(False))


def stop_presentmon(m: Measured, pm: presentmon.Host) -> None:
    """PresentMon stopped by CTRL_BREAK_EVENT whatever ended the session; its facts or its
    problem kept. A PresentMon that died or had to be killed fails the run (F1)."""
    facts = m.facts["presentmon"]
    if m.recording is None or "stop" in facts or "stopProblem" in facts:
        return
    try:
        facts["stop"] = presentmon.stop(m.recording, pm)
        m.journal.set("presentmonStop", facts["stop"])  # its CSV complete: an orphan's is cut
    except presentmon.PresentMonError as error:
        facts["stopProblem"] = str(error)
        session = m.recording.session
        try:  # a dead or killed PresentMon may leave its ETW session, which closes the gate
            if session in launch.etw_sessions(m.s.host.logman()):
                facts["sessionStopped"] = m.s.host.stop_session(session)
        except (launch.LaunchError, RunError) as stopped:
            facts["sessionStopProblem"] = str(stopped)
        raise RunError(f"PresentMon: {error}") from None


def leave_gui(m: Measured, where: str) -> None:
    """D49 after the entities view: the GUI hidden again and spectator back, before the next pose
    (camera.place needs a spectator or a flying player)."""
    s, c = m.s, m.c
    s.step(f"{where}: hud.set hideGui", lambda: c.hud_set(hide_gui=True))
    s.step(
        f"{where}: spectator",
        lambda: c.command("/gamemode spectator", COMMAND_TIMEOUT),
        lambda a: "; ".join(a["messages"]),
    )
    m.gui = False


def arrive(m: Measured, view: dict) -> bool:
    """A view reached (measurement.md#session step 5): its function, camera.place, D49's GUI and
    game mode, the overworld weather's ticks with the camera there when it changed. Whether the
    dimension changed on the way."""
    s, c = m.s, m.c
    vid = view["id"]
    if m.gui:
        leave_gui(m, vid)
    text = FUNCTION.format(id=vid)
    called = s.step(
        f"{vid}: function",
        lambda: c.command(text, COMMAND_TIMEOUT, check=False),
        lambda a: "; ".join(a["messages"] + a["failures"]) or f"succeeded {a['succeeded']}",
    )
    if called["succeeded"] is not True:
        raise RunError(
            f"{vid}: {text} did not succeed ({called['failures']}); a view function failing stops "
            "the run (plans/m2.md section 7: the views are the user's)"
        )
    pose = view_pose(view)
    placed = s.step(
        f"{vid}: camera.place",
        lambda: c.camera_place(pose, PLACE_TIMEOUT),
        lambda a: f"arrived in {a['arrivedSeconds']:.2f} s",
    )
    problems = modclient.pose_differences(pose, placed["pose"])
    if problems:
        raise RunError(f"{vid}: camera.place answered {placed['pose']}: {problems}")
    if m.previous != view["dim"]:
        # Another dimension shows a loading screen first: no reload or window starts over it.
        s.step(
            f"{vid}: ready",
            lambda: c.ready(STABLE_FRAMES, 0.0, READY_TIMEOUT),
            lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
        )
    if vid == ENTITIES:
        s.step(
            f"{vid}: creative",
            lambda: c.command("/gamemode creative", COMMAND_TIMEOUT),
            lambda a: "; ".join(a["messages"]),
        )
        s.step(f"{vid}: hud.set hideGui false", lambda: c.hud_set(hide_gui=False))
        m.gui = True
    if view["dim"] == OVERWORLD and m.ramped != view["weather"]:
        n = m.suite["capture"]["ticksAfterWeatherChange"]
        s.step(f"{vid}: ticks.step {n}", lambda: c.ticks_step(n, TICKS_TIMEOUT))
        m.ramped = view["weather"]
        m.facts.setdefault("weatherTicks", []).append({"view": vid, "ticks": n})
    changed = m.previous != view["dim"]
    m.previous = view["dim"]
    return changed


def capture(m: Measured, view: dict, variant: Variant, rnd: int, pass_no: int, settle: float):
    """One capture (measurement.md#session steps 6 and 8): the variant's files, shaders.reload
    and its pack, the options read back, the timers on a timers-on variant, window.measure
    {after: reload} with `settle` as its skip, then the journal and the heap row when due. A
    budget run stops before a reload with less than F4's 2 GiB of physical memory available, reads
    the GPU memory after each capture, and without windows keeps the reload and its options."""
    s, c = m.s, m.c
    m.index += 1
    label = f"{m.index:03d} {view['id']} {variant.id}"
    if m.spec.heap:
        available = s.host.available_memory()
        if available < F4_MIN_AVAILABLE:
            raise RunError(
                f"{label}: {available / 1024**3:.1f} GiB of physical memory available, under "
                f"{F4_MIN_AVAILABLE / 1024**3:.0f} GiB: the budget run stops before the machine "
                "pages (F4's guard)"
            )
    m.write_files(variant)
    m.reloads += 1
    reload = s.step(
        f"{label}: shaders.reload",
        lambda: c.shaders_reload(RELOAD_TIMEOUT, 2, pack=variant.pack),
        lambda a: f"{a['seconds']:.3f} s, reloadFrame {a['reloadFrame']}",
    )
    options = s.step(
        f"{label}: shaders.options",
        c.shaders_options,
        keep=lambda a: {"pack": a["pack"], "values": len(a["values"])},
    )
    m.check_options(variant, options)
    if not m.spec.windows:
        bare(m, view, variant, rnd, pass_no, settle, label, reload)
        return
    if variant.timers:
        s.step(f"{label}: timers.start", lambda: c.timers_start(**timer_args()))
    window = s.step(
        f"{label}: window.measure",
        lambda: c.window_measure("reload", settle, m.suite["capture"]["windowS"]),
        lambda a: f"{a['frames']} frames from {a['start']['frameIndex']}",
    )
    entry: dict[str, Any] = {
        "index": m.index,
        "pass": pass_no,
        "view": view["id"],
        "variant": variant.id,
        "role": variant.role,
        "round": rnd,
        "settleS": settle,
        "reload": {k: reload[k] for k in ("seconds", "reloadFrame", "pack")},
        "window": {k: window[k] for k in ("start", "end", "frames", "seconds", "skippedSeconds")},
    }
    first, last = window["start"]["frameIndex"], window["end"]["frameIndex"]
    if variant.timers:
        stopped = s.step(
            f"{label}: timers.stop",
            c.timers_stop,
            keep=lambda a: {**a, "frames": len(a["frames"])},  # the frames: captures.json
        )
        entry["timers"] = timers_summary(stopped, first, last)
    # The pose held through the window (D49's creative mode flies; nothing else moves it).
    held = s.step(f"{label}: camera.get", c.camera_get)
    moved = modclient.pose_differences(view_pose(view), held["pose"])
    if moved:
        raise RunError(f"{label}: the camera left the view during the capture: {moved}")
    entry["events"] = window_events(s.events, first, last)
    m.last_end = window["end"]["qpcNs"]
    if m.spec.heap:
        entry["gpuMemory"] = gpu_memory_of(m)
    m.entries.append(entry)
    m.journal.append("captures", entry)
    heap_row(m)


def bare(
    m: Measured,
    view: dict,
    variant: Variant,
    rnd: int,
    pass_no: int,
    settle: float,
    label: str,
    reload: dict,
) -> None:
    """A budget run's capture without its window (record.BUDGET `windows` false): the reload,
    its 2 frames and its options alone, the pose checked, the GPU memory read, no frames
    measured and no settle waited."""
    held = m.s.step(f"{label}: camera.get", m.c.camera_get)
    moved = modclient.pose_differences(view_pose(view), held["pose"])
    if moved:
        raise RunError(f"{label}: the camera left the view: {moved}")
    entry: dict[str, Any] = {
        "index": m.index,
        "pass": pass_no,
        "view": view["id"],
        "variant": variant.id,
        "role": variant.role,
        "round": rnd,
        "settleS": None,  # no window, so no settle waited
        "reload": {k: reload[k] for k in ("seconds", "reloadFrame", "pack")},
        "window": None,
        "events": [],
        "gpuMemory": gpu_memory_of(m),
    }
    m.entries.append(entry)
    m.journal.append("captures", entry)
    heap_row(m)


def visual_body(m: Measured) -> None:
    """A visual session after hello (plans/m3.md D63): the session start, the first variant's files
    written before the start-of-run reload; one lap over the mode's views (D48), each reached as a
    measured pass reaches it (arrive: its function, camera.place, D49's GUI, the overworld
    weather's ticks), then per variant its pair (visual_capture), the settle's dimension-change
    addition only for the first after a dimension change; input.block off. No PresentMon."""
    s, c = m.s, m.c
    s.stop_on = ends
    m.mark("start")
    base = m.found[0]
    start: dict = {}
    m.facts["start"] = start
    session_start(
        s,
        base.pack,
        m.suite["capture"]["gpuWarmupS"],
        m.display_mode,
        m.suite["display"]["resolution"],
        start,
        lambda: m.write_files(base),
    )
    m.reloads = record.ACCEPTANCE_RELOADS
    m.check_options(base, start["options"])
    m.previous = start["joined"]["pose"]["dimension"]
    m.mark("views")
    order = record.lap(m.views, m.ramped)
    m.facts["laps"] = [[v["id"] for v in order]]
    for view in order:
        changed = arrive(m, view)
        for slot, variant in enumerate(m.found):
            settle = visual_settle(m.suite["capture"], view, changed and slot == 0)
            visual_capture(m, view, variant, settle)
    if m.gui:
        leave_gui(m, "end")
    s.step("input.block off", lambda: c.input_block(False))


def visual_capture(m: Measured, view: dict, variant: Variant, settle: float) -> None:
    """One variant's frames at one view (plans/m3.md D63): its files, shaders.reload and its pack,
    the options read back; frames.capture's pair: ready (STABLE_FRAMES and the view's visual
    settle as minSeconds: measurement.md#readiness), aligned on the Optilux pack's cycle (phase 0),
    PAIR frames PAIR_MS apart, PNGs under raw/frames/<view>/<variant>/, judged by their files
    (modclient.verify_manifest); the pose held. Its entry: each frame's path under raw/, sha256 and
    stamps, ready's report, the flags (record.VISUAL_FLAGS)."""
    s, c = m.s, m.c
    m.index += 1
    label = f"{m.index:03d} {view['id']} {variant.id}"
    m.write_files(variant)
    m.reloads += 1
    reload = s.step(
        f"{label}: shaders.reload",
        lambda: c.shaders_reload(RELOAD_TIMEOUT, 2, pack=variant.pack),
        lambda a: f"{a['seconds']:.3f} s, reloadFrame {a['reloadFrame']}",
    )
    options = s.step(
        f"{label}: shaders.options",
        c.shaders_options,
        keep=lambda a: {"pack": a["pack"], "values": len(a["values"])},
    )
    m.check_options(variant, options)
    folder = s.raw / FRAMES / view["id"] / variant.id
    align = (m.cycle, 0)
    taken = s.step(
        f"{label}: frames.capture",
        lambda: c.frames_capture(
            folder,
            PAIR,
            VISUAL_CAPTURE_TIMEOUT,
            interval_ms=PAIR_MS,
            align=align,
            ready=(STABLE_FRAMES, settle),
        ),
        lambda a: (
            f"frames {', '.join(str(f['frameIndex']) for f in a['frames'])} after "
            f"{a['ready']['seconds']:.2f} s ready"
        ),
    )
    held = s.step(f"{label}: camera.get", c.camera_get)
    moved = modclient.pose_differences(view_pose(view), held["pose"])
    if moved:
        raise RunError(f"{label}: the camera left the view during the capture: {moved}")
    # The attempt folder by its name under the folder asked for, whatever form the mod's path took.
    attempt = folder.relative_to(s.raw) / Path(taken["manifest"]).parent.name
    frames = [
        {
            "path": (attempt / frame["name"]).as_posix(),
            "sha256": frame["sha256"],
            **{key: frame[key] for key in modclient.MARK_KEYS},
        }
        for frame in taken["frames"]
    ]
    ready = taken["ready"]
    last = frames[-1]["frameIndex"] if frames else ready["frameIndex"]
    events = window_events(s.events, ready["frameIndex"], last + 1)
    whole = len(frames) == PAIR and not taken["dropped"] and taken["verified"]["complete"] is True
    apart = (frames[-1]["qpcNs"] - frames[0]["qpcNs"]) / 1e9 if whole else None
    flags = [] if whole else ["incomplete"]
    if whole and frames[0]["sha256"] != frames[1]["sha256"]:
        flags.append("moving")
    if events:
        flags.append("event")
    entry = {
        "index": m.index,
        "view": view["id"],
        "variant": variant.id,
        "settleS": settle,
        "reload": {k: reload[k] for k in ("seconds", "reloadFrame", "pack")},
        "align": {"cycle": align[0], "phase": align[1]},
        "ready": ready,
        "frames": frames,
        "pairSeconds": None if apart is None else round(apart, 4),
        "dropped": taken["dropped"],
        "flags": flags,
        "valid": not any(flag in record.VISUAL_INVALIDATING for flag in flags),
        "problems": [f"{e['event']} at frame {e['frameIndex']}" for e in events],
    }
    m.entries.append(entry)
    m.journal.append("captures", entry)


def visual_problems(entries: list[dict], planned: int, laps_done: bool) -> list[str]:
    """What fails a visual record beside its session: a pair planned but never taken, or one
    missing a frame (missing = fail)."""
    problems = []
    missing = planned - len(entries)
    if missing > 0 and laps_done:
        problems.append(f"{missing} planned captures were not taken")
    short = [str(e["index"]) for e in entries if "incomplete" in e["flags"]]
    if short:
        problems.append(f"captures {', '.join(short)} miss a frame")
    return problems


def gpu_memory(text: str, pid: int, luid: str) -> dict:
    """The game's dedicated and shared GPU memory and the adapter's, in MiB, on the adapter
    `luid` (0x...) from typeperf's one-sample CSV (M2.P06's diagnosis). RecordError when the
    text holds no counter table or no column of the game or the adapter."""
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    try:
        top = next(i for i, row in enumerate(rows) if row[0] == PDH_HEADER)
    except StopIteration:
        raise record.RecordError(
            f"typeperf printed no counter table: {text.strip()[-200:]!r}"
        ) from None
    header = rows[top]
    sample = next((row for row in rows[top + 1 :] if len(row) == len(header)), None)
    if sample is None:
        raise record.RecordError("typeperf printed no sample")
    found: dict[str, float] = {}
    for column, path in enumerate(header[1:], start=1):
        process = PROCESS_MEMORY.search(path)
        match = process or ADAPTER_MEMORY.search(path)
        if not match or (process and int(process["pid"]) != pid):
            continue
        adapter = (int(match["high"], 16) << 32) | int(match["low"], 16)
        if f"0x{adapter:x}" != luid.lower():
            continue
        try:
            value = float(sample[column])
        except ValueError:  # one unread instance would make the sum silently low
            raise record.RecordError(
                f"typeperf's {path} reads {sample[column]!r}, no number"
            ) from None
        key = f"{'process' if process else 'adapter'}{match['kind']}MiB"
        found[key] = found.get(key, 0.0) + value
    keys = [f"{who}{kind}MiB" for who in ("process", "adapter") for kind in ("Dedicated", "Shared")]
    missing = [key for key in keys if key not in found]
    if missing:
        raise record.RecordError(
            f"typeperf read no {', '.join(missing)} for pid {pid} on the adapter {luid}"
        )
    return {key: round(found[key] / 1024**2, 1) for key in keys}


def gpu_memory_of(m: Measured) -> dict:
    """The GPU memory now (gpu_memory), or the problem that left it unread: never a number."""
    try:
        return gpu_memory(m.s.host.gpu_memory(), m.s.launched.pid, m.luid)
    except (OSError, record.RecordError) as error:
        return {"problem": str(error)}


def timer_args() -> dict:
    return {
        "per_pass": TIMERS["perPass"],
        "max_pending": TIMERS["maxPending"],
        "max_frames": TIMERS["maxFrames"],
    }


def heap_row(m: Measured) -> None:
    """The heap after GC and the private bytes (F4's row, M2.P06) at the session's start and then
    whenever the reloads reach the next multiple of record.RELOAD_EVERY, when the spec asks."""
    if not m.spec.heap:
        return
    last = m.heap[-1]["reloads"] if m.heap else None
    if last is not None and m.reloads // record.RELOAD_EVERY == last // record.RELOAD_EVERY:
        return
    folder = m.s.raw / "heap"
    folder.mkdir(exist_ok=True)
    row = memory_row(m.s, m.jcmd, m.reloads, folder)
    row["gpu"] = gpu_memory_of(m)
    m.heap.append(row)
    m.s.say(
        f"heap: after {m.reloads} reloads {row['heapUsedMiB']} MiB, private {row['privateMiB']} MiB"
    )


def heap_table(rows: list[dict], physical: int) -> dict | None:
    """The heap rows with the growth per reload from the first to the last and the machine's
    physical memory in bytes (plans/m2.md D43's rule reads them); the game's GPU memory,
    dedicated and shared (dedicated alone stops at the card's size), likewise when both rows read
    it."""
    if not rows:
        return None
    first, last = rows[0], rows[-1]
    count = last["reloads"] - first["reloads"]
    per = {
        "heapMiB": round((last["heapUsedMiB"] - first["heapUsedMiB"]) / count, 2)
        if count
        else None,
        "privateMiB": round((last["privateMiB"] - first["privateMiB"]) / count, 1)
        if count
        else None,
    }
    gpu = [game_gpu(row.get("gpu") or {}) for row in (first, last)]
    if count and gpu[0] is not None and gpu[1] is not None:
        per["gpuMiB"] = round((gpu[1] - gpu[0]) / count, 1)
    return {
        "every": record.RELOAD_EVERY,
        "physicalMiB": round(physical / 1024**2),
        "rows": rows,
        "perReload": per,
    }


def game_gpu(reading: dict) -> float | None:
    """The game's dedicated plus shared GPU memory of one reading, None when it was not read."""
    dedicated, shared = reading.get("processDedicatedMiB"), reading.get("processSharedMiB")
    return None if dedicated is None or shared is None else dedicated + shared


# After the session.


def summarize(m: Measured, pid: int) -> tuple[list[dict], list[str]]:
    """Every journaled capture cut from the complete CSV and judged; the problems that leave a
    capture without its numbers (the CSV unread), each failing the run."""
    output = m.s.raw / CSV
    if not m.entries:
        return [], []
    try:
        line, facts = read_timeline(output, pid)
    except (OSError, ValueError, presentmon.PresentMonError) as error:
        return [unsummarized(e, str(error)) for e in m.entries], [
            f"the captures were not cut: {error}"
        ]
    m.facts.setdefault("presentmon", {})["file"] = facts
    validity = m.suite["validity"]
    return [captured(e, line, m.s.events, validity) for e in m.entries], []


def unsummarized(entry: dict, why: str) -> dict:
    """A capture whose rows could not be read: its place and the reason, never a number."""
    found = {k: entry[k] for k in ("index", "pass", "view", "variant", "role", "round", "settleS")}
    frames = entry["window"]["frames"] if entry["window"] else None
    return {**found, "frames": frames, "valid": False, "unsummarized": why}


def variant_records(m: Measured, sha512: str) -> list[dict]:
    """The record's variants (run-record.md#fields): id, role, pack and the zip's sha512 (the
    reference pack's `sha512`, the passthrough's own), profile, the written options, timers, and
    the effective options read back after the reload: the whole map of the baseline and of a
    variant of another pack (the passthrough's), each other variant's sha256 and the values that
    differ from the baseline's."""
    base = m.effective.get(m.found[0].id)
    found = []
    for v in m.found:
        entry: dict[str, Any] = {
            "id": v.id,
            "role": v.role,
            "pack": v.pack,
            "sha512": variant_sha512(v, sha512),
            "profile": v.profile,
            "options": v.options,
            "timers": v.timers,
        }
        mine = m.effective.get(v.id)
        if mine is None:
            entry["effective"] = None
        elif v.role == "baseline" or base is None or v.source != m.found[0].source:
            entry["effective"] = {
                "sha256": mine["sha256"],
                "count": len(mine["values"]),
                "values": mine["values"],
            }
        else:  # a key the baseline holds and this map lacks reads None
            names = sorted({*mine["values"], *base["values"]})
            differ = {
                k: mine["values"].get(k)
                for k in names
                if base["values"].get(k) != mine["values"].get(k)
            }
            entry["effective"] = {
                "sha256": mine["sha256"],
                "count": len(mine["values"]),
                "fromBaseline": differ,
            }
        found.append(entry)
    return found


def measured_problems(found: list[dict], planned: int, laps_done: bool) -> list[str]:
    """What fails a measured record beside its session: a capture planned but never measured, or
    one without its numbers (missing = fail, measurement.md#verdicts-and-cost-rows)."""
    problems = []
    missing = planned - len(found)
    if missing > 0 and laps_done:
        problems.append(f"{missing} planned captures were not measured")
    bare = [str(c["index"]) for c in found if "unsummarized" in c]
    if bare:
        problems.append(f"captures {', '.join(bare)} have no numbers")
    return problems


def time_split(marks: dict, ended: float) -> dict:
    """Seconds per phase from the marks' monotonic times, in their order, the last to `ended`."""
    order = sorted(marks.items(), key=lambda item: item[1])
    return {
        name: round((order[i + 1][1] if i + 1 < len(order) else ended) - at, 1)
        for i, (name, at) in enumerate(order)
    }


# D41: orphans.


def finish_orphans(root: Path, host: RunHost, say: Say) -> list[dict]:
    """Every run whose journal is still partial and whose runner is gone (D41): its game and its
    PresentMon ended, each only after its pid's creation time and executable match the journal's
    (the game's under runtime/, as the launch gate tells it), its PresentMon's ETW session
    stopped, its files under shaderpacks/ deleted, its record written aborted (summarized only
    from a complete CSV) and its journal closed. A journal whose record exists is closed. The
    records written; RecordError for a run still going or a process that would not end."""
    raws = root / record.RAW
    finished = []
    for partial in sorted(raws.glob(f"*/{PARTIAL}")) if raws.is_dir() else []:
        raw = partial.parent
        if (root / record.RECORDS / f"{raw.name}.json").exists():
            partial.replace(raw / CLOSED)
            continue
        finished.append(finish(root, raw, host, say))
    return finished


def same_process(host: RunHost, kept: dict | None) -> dict | None:
    """The running process a journal's pid entry names, when its creation time and executable
    match the journal's (Windows reuses pids); None when it is gone or another."""
    if not kept or not isinstance(kept.get("pid"), int):
        return None
    now_facts = host.process_facts(kept["pid"])
    if now_facts is None:
        return None
    same = now_facts.get("createTime") == kept.get("createTime") and launch.norm(
        str(now_facts.get("exe") or "")
    ) == launch.norm(str(kept.get("exe") or ""))
    return now_facts if same else None


def attached(host: RunHost, pid: int, kept: dict) -> Any:
    """The running process `pid` to end, checked again through the handle that ends it; None
    when it exited since it was checked or is no longer the journal's."""
    try:
        process = host.attach(pid)
    except psutil.NoSuchProcess:
        return None
    return process if process.same(kept) else None


def finish(root: Path, raw: Path, host: RunHost, say: Say) -> dict:
    """One orphan finished (finish_orphans)."""
    name = raw.name
    try:
        journal = json.loads((raw / PARTIAL).read_text(encoding="utf-8"))
    except ValueError as error:
        raise record.RecordError(
            f"{shown(raw / PARTIAL, root)} is no JSON ({error}); fix: read it, end what it names "
            "yourself, then rename it journal.json"
        ) from None
    runner = same_process(host, journal.get("runner"))
    if runner is not None:
        raise record.RecordError(
            f"run {name} is still going (its runner, pid {runner['pid']}, runs); fix: let it end"
        )
    plat = platform.load(root)
    base = root / RUNTIME / plat.id
    done: dict[str, Any] = {"at": now()}
    game = same_process(host, journal.get("game"))
    if game is not None:
        info = launch.ProcessInfo(
            game["pid"],
            game.get("name", ""),
            game.get("exe"),
            game.get("cwd"),
            game.get("cmdline") or [],
        )
        if not launch.games(base, [info], -1):
            raise record.RecordError(
                f"run {name}'s game pid {game['pid']} runs from outside {shown(base, root)}/; "
                "fix: end it yourself"
            )
        process = attached(host, game["pid"], journal["game"])
        done["game"] = "gone" if process is None else launch.end(process, host)
        if process is not None and process.poll() is None:
            raise record.RecordError(
                f"run {name}'s game pid {game['pid']} outlived WM_CLOSE and a kill; fix: end it"
            )
    else:
        done["game"] = "gone"
    kept = journal.get("presentmon") or {}
    pm = same_process(host, kept)
    session = kept.get("session")
    process = attached(host, pm["pid"], kept) if pm is not None else None
    stopped = (journal.get("presentmonStop") or {}).get("exitCode") == 0
    complete = False
    try:
        if process is not None:
            done["presentmonSession"] = host.stop_session(session) if session else None
            try:
                process.wait(ORPHAN_STOP_TIMEOUT)
                done["presentmon"] = "exited after its ETW session stopped"
                complete = True
            except Exception:  # noqa: BLE001 subprocess.TimeoutExpired or a wait that failed
                process.kill()
                done["presentmon"] = "killed after its ETW session stopped"
        else:
            done["presentmon"] = (
                "stopped by its run" if stopped else "gone" if kept else "never started"
            )
            if session and session in launch.etw_sessions(host.logman()):
                done["presentmonSession"] = host.stop_session(session)
            complete = stopped  # a PresentMon found gone may have died with its CSV short
    except RunError as error:  # logman's own failure: the session may run on
        raise record.RecordError(
            f"run {name}'s ETW session {session}: {error}; fix: `logman stop {session} -ets`"
        ) from None
    paths = [root / p for p in journal.get("files", [])]
    shaderpacks = base / launch.GAME / launch.SHADER_PACKS
    done["files"] = remove_files([p for p in paths if p.parent == shaderpacks])
    found = orphan_record(root, raw, journal, done, complete)
    path = record.write_record(root, found, say)
    (raw / PARTIAL).replace(raw / CLOSED)
    say(f"orphan {name}: game {done['game']}, PresentMon {done['presentmon']}; {shown(path, root)}")
    return found


def orphan_record(root: Path, raw: Path, journal: dict, done: dict, complete: bool) -> dict:
    """An orphan's record, aborted: the journal's spec, identity and captures, the captures
    summarized only when PresentMon ended by its session's stop and the CSV is complete."""
    spec = journal["spec"]
    entries = journal.get("captures", [])
    validity = journal.get("validity")  # the run's own suite: its identity hashed it
    pid = (journal.get("game") or {}).get("pid")
    visual = spec.get("kind") == record.VISUAL
    captures: list[dict] = []
    why = "PresentMon did not end by its session's stop: its CSV may lack its last rows"
    if visual:  # each journaled pair as taken (whole or flagged), its frames under raw/: no CSV
        captures = [{k: v for k, v in e.items() if k != "problems"} for e in entries]
        why = ""
    elif entries and complete and isinstance(pid, int) and validity is not None:
        try:
            line, facts = read_timeline(raw / CSV, pid)
            done["csv"] = facts
            captures = [captured(e, line, e.get("events", []), validity) for e in entries]
            why = ""
        except (OSError, ValueError, presentmon.PresentMonError) as error:
            why = f"the CSV: {error}"
    if why:
        captures = [unsummarized(e, why) for e in entries]
    found: dict[str, Any] = {
        "schema": record.SCHEMA,
        "name": journal["name"],
        "kind": spec["kind"],
        "spec": spec,
        "notes": spec.get("notes"),
        "status": "aborted",
        "reason": (
            "the run ended without writing its record (killed or crashed); the next run "
            f"finished it at {done['at']}"
        ),
        "startedAt": journal.get("startedAt"),
        "endedAt": journal.get("journaledAt"),
        "identity": journal.get("identity"),
        "recorded": journal.get("recorded", {}),
    }
    if journal.get("split"):  # a split session's part (run-record.md#split-sessions)
        found["split"] = journal["split"]
    if spec.get("mode") is not None:
        effective = journal.get("effective", {})
        found.update(
            mode=spec["mode"],
            **({} if visual else {"calibration": spec.get("calibration")}),
            variants=[
                {**v, "effective": effective.get(v["id"])} for v in journal.get("variants", [])
            ],
            captures=captures,
        )
    if spec["kind"] == "acceptance":
        part = journal.get("split")
        entry = (
            {"pass": None, "evidence": {"pending": f"judged in session {part['session']}'s record"}}
            if part
            else {"pass": False, "evidence": {"notRun": "the run was killed"}}
        )
        found["acceptance"] = [{"item": item, **entry} for item in spec.get("items") or []]
    found["session"] = {"orphan": done, "journal": shown(raw / CLOSED, root)}
    found["raw"] = shown(raw, root)
    return found
