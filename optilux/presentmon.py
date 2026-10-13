"""PresentMon, minimal (docs/measurement.md#tools, docs/plans/m1.md 0.01.09; roadmap.md F1).

The console build from runtime/tools/ (config/tools.json) records one process's presents into a
CSV: started with measurement.md#tools' flags in its own console process group
(CREATE_NEW_PROCESS_GROUP), stopped with CTRL_BREAK_EVENT through GenerateConsoleCtrlEvent, the
one stop that leaves no ETW session behind (Windows disables Ctrl+C in such a child; spike L1).
A PresentMon that exits before the stop, or outlasts it and is killed, fails the run: its session
may still be running. The CSV grows during the run and completes at exit; its first row arrives
about 4 s after the start, so the caller waits for rows, never sleeps, and reads only what grew
since its last read (cr10). `--qpc_time_ms` writes CPUStartQPCTime as absolute QPC milliseconds,
the mod's clock (docs/mod.md#6-time-and-determinism). A9's row match lives here too: the rows of a
capture's span against the capture's stamps; and the measured session's window cut
(measurement.md#tools): a window's rows between its two HEAD stamps, each edge held against the
row its swap stamp maps to, and the summaries of those rows.
"""

import bisect
import contextlib
import csv
import io
import itertools
import signal
import statistics
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

FLAGS = ("--qpc_time_ms", "--v2_metrics")
SESSION_PREFIX = "optilux-"
QPC = "CPUStartQPCTime"
PROCESS_ID = "ProcessID"
SWAP_CHAIN = "SwapChainAddress"
# The v2 metrics the summaries read (measurement.md#tools): FrameTime runs from this frame's CPU
# start to the next's, GPUBusy is the time at least one GPU engine worked for the process,
# GPULatency the time from the frame's CPU start until the GPU started on it.
FRAME_TIME = "FrameTime"
GPU_BUSY = "GPUBusy"
GPU_LATENCY = "GPULatency"
PRESENT_MODE = "PresentMode"
UTF8_BOM = b"\xef\xbb\xbf"
# CTRL_BREAK_EVENT (wincon.h); the child gets a process group of its own, no console of its own.
CTRL_BREAK_EVENT = 1
CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
# The spike's PresentMon stopped at once on CTRL_BREAK_EVENT (exit 0) and wrote its first row
# 4.0 s after the start (platform.md#mc-263-verified L1).
STOP_TIMEOUT = 30.0
FIRST_ROW_TIMEOUT = 30.0
POLL = 0.1
# A9 (docs/mod.md#12-acceptance, plans/m1.md D26): the offset limit at the median and the maximum.
A9_LIMIT_MS = 1.0


class PresentMonError(RuntimeError):
    """PresentMon did not start, stop or record as it must; the message names the problem."""


class Process(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


class Host:
    """The machine as PresentMon's start and stop use it; the tests replace it."""

    def start(self, command: list[str], log: Path) -> Process:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("wb") as out:  # the child holds its own handle
            return subprocess.Popen(  # noqa: S603 argv list from tools.json's pinned exe
                command,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                creationflags=CREATION_FLAGS,
            )

    def ctrl_break(self, pid: int) -> int:
        """CTRL_BREAK_EVENT to the process group `pid` leads (GenerateConsoleCtrlEvent): 0 when
        sent, else the Windows error (87 from a process on another console). The harness ignores
        CTRL_BREAK itself first: should the group be gone by the call, the console hands the
        event to every process on it."""
        import ctypes

        if hasattr(signal, "SIGBREAK"):
            # Off the main thread signal() raises ValueError: the handler stays as it is.
            with contextlib.suppress(ValueError):
                signal.signal(signal.SIGBREAK, signal.SIG_IGN)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.GenerateConsoleCtrlEvent.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        kernel32.GenerateConsoleCtrlEvent.restype = ctypes.c_int
        if kernel32.GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid):
            return 0
        return ctypes.get_last_error() or -1

    def clock(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def arguments(pid: str, output: str, session: str) -> list[str]:
    """measurement.md#tools' arguments, in its order; with placeholders for the three run values
    they are the harness identity's PresentMon flags (plans/m2.md D36)."""
    return [
        "--process_id",
        pid,
        "--output_file",
        output,
        *FLAGS,
        "--session_name",
        session,
        "--stop_existing_session",
        "--no_console_stats",
    ]


def command(exe: Path, pid: int, output: Path, session: str) -> list[str]:
    """measurement.md#tools' command line."""
    return [str(exe), *arguments(str(pid), str(output), session)]


class RowsTail:
    """The CSV read as it grows (cr10): each read takes only the bytes past the last one and keeps
    a partial last line for the next, so a session's long file is never read again whole; the
    rows counted, the last row's CPU start. PermissionError passes up (PresentMon holds the file
    unshared while it runs, P5); PresentMonError as read_rows refuses."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.header: list[str] | None = None
        self.rows = 0
        self.last_ns: int | None = None
        self._partial = b""

    def read(self) -> None:
        try:
            with self.path.open("rb") as handle:
                handle.seek(self.offset)
                data = handle.read()
        except FileNotFoundError:  # PresentMon creates it with the first present it sees
            return
        if not self.offset and data.startswith(UTF8_BOM):
            data = data[len(UTF8_BOM) :]
            self.offset = len(UTF8_BOM)
        self.offset += len(data)
        data = self._partial + data
        end = data.rfind(b"\n") + 1
        self._partial = data[end:]
        lines = list(csv.reader(io.StringIO(data[:end].decode("utf-8", "replace"))))
        if lines and self.header is None:
            self.header = lines.pop(0)
            if QPC not in self.header:
                raise PresentMonError(f"{self.path.name} has no {QPC} column")
        for values in lines:
            if self.header is None or len(values) != len(self.header):
                raise PresentMonError(
                    f"{self.path.name} row {self.rows + 1}: {len(values)} fields, the header "
                    f"has {len(self.header or [])}"
                )
            self.rows += 1
            self.last_ns = round(float(values[self.header.index(QPC)]) * 1e6)


@dataclass
class Recording:
    """A started PresentMon: its process, the CSV it writes, its session and its console log; the
    CSV's tail as the waits have read it."""

    process: Process
    output: Path
    session: str
    log: Path
    command: list[str]
    started: float
    tail: RowsTail = field(init=False)

    def __post_init__(self) -> None:
        self.tail = RowsTail(self.output)


def tail(path: Path, size: int = 400) -> str:
    """The end of PresentMon's console log, which it writes in UTF-16 (0.01.09's run)."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16", "replace")[-size:].strip()
    return data[-size:].decode("utf-8", "replace").strip()


def start(exe: Path, pid: int, output: Path, session: str, host: Host) -> Recording:
    """PresentMon recording `pid`'s presents into `output` (which must not exist yet) under ETW
    session `session` (optilux-<run>); PresentMonError when it is missing or exits at once."""
    if not session.startswith(SESSION_PREFIX):
        raise PresentMonError(
            f"session {session!r} lacks the {SESSION_PREFIX} prefix the gate reads"
        )
    if not exe.is_file():
        raise PresentMonError(f"no {exe}; fix: run `optilux install`")
    if output.exists():
        raise PresentMonError(f"{output} exists; fix: a new run name (raw folders are single-use)")
    log = output.with_suffix(".log")
    line = command(exe, pid, output, session)
    try:
        process = host.start(line, log)
    except OSError as error:
        raise PresentMonError(f"PresentMon did not start: {error}") from None
    found = Recording(process, output, session, log, line, host.clock())
    if process.poll() is not None:
        raise PresentMonError(
            f"PresentMon exited with code {process.returncode} at its start: {tail(log)}"
        )
    return found


def stop(found: Recording, host: Host) -> dict:
    """CTRL_BREAK_EVENT to PresentMon's group and its exit awaited: the code and the seconds.
    PresentMonError when it had already exited (killed or failed: its session may run on), or the
    event could not be sent or it outlasted STOP_TIMEOUT (it is killed then, its session left)."""
    process = found.process
    if process.poll() is not None:
        raise PresentMonError(
            f"PresentMon exited with code {process.returncode} before the stop (killed or failed; "
            f"ETW session {found.session} may still run): {tail(found.log)}"
        )
    began = host.clock()
    error = host.ctrl_break(process.pid)
    try:
        code = process.wait(STOP_TIMEOUT if error == 0 else 0)
    except subprocess.TimeoutExpired:
        process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):  # the error below says it all
            process.wait(STOP_TIMEOUT)
        why = (
            f"outlasted CTRL_BREAK_EVENT by {STOP_TIMEOUT:.0f} s"
            if error == 0
            else f"could not be sent CTRL_BREAK_EVENT (Windows error {error})"
        )
        raise PresentMonError(
            f"PresentMon {why} and was killed; ETW session {found.session} may still run (fix: "
            f"`logman stop {found.session} -ets`)"
        ) from None
    facts = {
        "how": "CTRL_BREAK_EVENT",
        "sent": error == 0,
        "exitCode": code,
        "seconds": round(host.clock() - began, 3),
        "recordedSeconds": round(host.clock() - found.started, 3),
    }
    if code != 0:
        raise PresentMonError(f"PresentMon exited with code {code} on CTRL_BREAK_EVENT: {facts}")
    return facts


# The CSV.


def read_rows(path: Path, complete: bool = False) -> tuple[list[str], list[dict]]:
    """The CSV's header and rows. While PresentMon writes, the last line may be partial: only
    lines ending in a newline count unless `complete`. PresentMon 2.6 writes a UTF-8 byte-order
    mark and CRLF lines (0.01.09's run); no file yet reads as no rows (PresentMon
    creates it with the first present it sees); PermissionError passes up (a file PresentMon holds
    unshared). PresentMonError for a row whose field count differs from the header's, or a file
    with no CPUStartQPCTime column."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return [], []
    text = data.decode("utf-8-sig", "replace")
    if not complete:
        text = text[: text.rfind("\n") + 1]
    lines = list(csv.reader(io.StringIO(text)))
    if not lines:
        return [], []
    header = lines[0]
    if QPC not in header:
        raise PresentMonError(f"{path.name} has no {QPC} column (header {header[:12]}...)")
    rows = []
    for number, values in enumerate(lines[1:], start=2):
        if len(values) != len(header):
            raise PresentMonError(
                f"{path.name} line {number}: {len(values)} fields, the header has {len(header)}"
            )
        rows.append(dict(zip(header, values, strict=True)))
    return header, rows


def qpc_ns(row: dict) -> int:
    """A row's CPUStartQPCTime (absolute QPC milliseconds) in the mod's qpcNs."""
    return round(float(row[QPC]) * 1e6)


def wait_rows(found: Recording, host: Host, after_ns: int | None, timeout: float) -> int:
    """Wait until the CSV holds a row (with `after_ns`, one whose CPUStartQPCTime lies after it);
    the rows then. Each poll reads only what the file gained (found.tail, cr10). While PresentMon
    holds the file unshared, its size stands in: any bytes for a first row, two growths since the
    wait began for a row after `after_ns` (-1 is returned then; the complete CSV is checked after
    the stop). PresentMonError when PresentMon exits meanwhile or the timeout passes."""
    deadline = host.clock() + timeout
    sizes: list[int] = []
    rows = found.tail
    while True:
        try:
            rows.read()
        except PermissionError:
            size = found.output.stat().st_size
            if not sizes or size != sizes[-1]:
                sizes.append(size)
            if (after_ns is None and size > 0) or (after_ns is not None and len(sizes) >= 3):
                return -1
        else:
            last = rows.last_ns
            if rows.rows and (after_ns is None or (last is not None and last > after_ns)):
                return rows.rows
        if found.process.poll() is not None:
            raise PresentMonError(
                f"PresentMon exited with code {found.process.returncode} while recording: "
                f"{tail(found.log)}"
            )
        if host.clock() >= deadline:
            wanted = "a row" if after_ns is None else f"a row after qpcNs {after_ns}"
            raise PresentMonError(
                f"{found.output.name} held {rows.rows} rows and no {wanted} after {timeout:g} s"
            )
        host.sleep(POLL)


# The measured session's window cut (measurement.md#tools, plans/m2.md M2.P05).


@dataclass(frozen=True)
class Timeline:
    """One process's rows of a complete CSV in CPU-start order, with each row's qpcNs: what every
    window of the session is cut from."""

    rows: list[dict]
    qpcs: list[int]


def timeline(rows: list[dict], pid: int) -> Timeline:
    mine = sorted((row for row in rows if row.get(PROCESS_ID) == str(pid)), key=qpc_ns)
    return Timeline(mine, [qpc_ns(row) for row in mine])


def nearest(line: Timeline, stamp: int, within: float) -> int | None:
    """The index of the row whose CPU start lies nearest `stamp`, None when none lies within
    `within` ns of it."""
    at = bisect.bisect_left(line.qpcs, stamp)
    near = [i for i in (at - 1, at) if 0 <= i < len(line.qpcs)]
    if not near:
        return None
    best = min(near, key=lambda i: abs(line.qpcs[i] - stamp))
    return best if abs(line.qpcs[best] - stamp) <= within else None


def cut_window(line: Timeline, start: dict, end: dict, frames: int) -> dict:
    """A window's rows (measurement.md#tools): those whose CPUStartQPCTime x 1e6 lies between its
    start and end HEAD stamps, both included. Each edge is held against the row its swap stamp maps
    to (A9's mapping: frame k's row starts 0.1-0.4 ms after frame k's swap stamp, plans/m1.md D26):
    `edges` gives, at the start, the cut's first row less frame start's row, and at the end, its
    last row less frame end - 1's; a frame's row and HEAD stamp lie within a fraction of a
    millisecond of each other, so each edge reads 0 or 1 (M2.P02's windows read 1 at both: the
    constant one-frame shift D26 keeps). Problems, each invalidating the capture: no row after
    the end (the CSV ends inside), an edge whose swap stamp maps to no row within half a frame, an
    edge more than one row off, rows between the edges' frames that are not one per frame, more
    than one swap chain."""
    lo = bisect.bisect_left(line.qpcs, start["qpcNs"])
    hi = bisect.bisect_right(line.qpcs, end["qpcNs"])
    rows = line.rows[lo:hi]
    found: dict = {"rows": rows, "edges": None, "frameRow": None, "problems": []}
    problems = found["problems"]
    if frames <= 0:
        problems.append(f"the window holds {frames} frames")
        return found
    if hi >= len(line.rows):
        problems.append("the CSV ends inside the window: no row after its end")
    half = (end["qpcNs"] - start["qpcNs"]) / frames / 2
    first = nearest(line, start["swapQpcNs"], half)
    last = nearest(line, end["swapQpcNs"], half)
    for name, index in (("start", first), ("end", last)):
        if index is None:
            problems.append(f"no row within half a frame of the {name} mark's swap stamp")
    found["frameRow"] = first  # frame start's row: frame start + k's is row frameRow + k
    if first is not None and last is not None:
        found["edges"] = [lo - first, hi - last]
        if last - first != frames:
            problems.append(
                f"{last - first} rows from frame start's row to frame end's, {frames} frames"
            )
        for name, off in zip(("start", "end"), found["edges"], strict=True):
            if abs(off) > 1:
                problems.append(f"the {name} edge is {off} rows off the window's frames")
    chains = sorted({row.get(SWAP_CHAIN, "") for row in rows})
    if len(chains) > 1:
        problems.append(f"{len(chains)} swap chains in the window")
    return found


def number(value: str | None) -> float | None:
    """A CSV metric as a float; None for PresentMon's NA or an empty field."""
    try:
        found = float(value) if value is not None else None
    except ValueError:
        return None
    return found


def p95(values: list[float]) -> float | None:
    """The 95th percentile, linear between the order statistics; None below two values."""
    if len(values) < 2:
        return None
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def summary(rows: list[dict]) -> dict:
    """A window's summaries (measurement.md#validity, run-record.md#fields), in ms: median GPUBusy,
    median and p95 FrameTime, median GPULatency, median GPUBusy over median FrameTime, the median
    GPUBusy of each half (the rows split in order) and their difference in % of their mean, the
    present modes counted, and the rows whose metrics were not numbers (PresentMon's NA)."""
    busy = [v for r in rows if (v := number(r.get(GPU_BUSY))) is not None]
    frame = [v for r in rows if (v := number(r.get(FRAME_TIME))) is not None]
    latency = [v for r in rows if (v := number(r.get(GPU_LATENCY))) is not None]
    middle = len(rows) // 2
    halves = [
        [v for r in part if (v := number(r.get(GPU_BUSY))) is not None]
        for part in (rows[:middle], rows[middle:])
    ]
    found: dict = {
        "frames": len(rows),
        "gpuBusyMs": round(statistics.median(busy), 4) if busy else None,
        "frameTimeMs": round(statistics.median(frame), 4) if frame else None,
        "frameTimeP95Ms": None if (tail95 := p95(frame)) is None else round(tail95, 4),
        "gpuLatencyMs": round(statistics.median(latency), 4) if latency else None,
        "gpuBusyOverFrameTime": None,
        "halvesGpuBusyMs": None,
        "halvesPct": None,
        "presentModes": dict(Counter(r.get(PRESENT_MODE, "") for r in rows)),
        "notNumbers": len(rows) - min(len(busy), len(frame)),
    }
    if busy and frame and found["frameTimeMs"]:
        found["gpuBusyOverFrameTime"] = round(statistics.median(busy) / statistics.median(frame), 4)
    if all(halves):
        first, second = (statistics.median(part) for part in halves)
        found["halvesGpuBusyMs"] = [round(first, 4), round(second, 4)]
        if first + second > 0:
            found["halvesPct"] = round(100 * abs(second - first) / ((first + second) / 2), 3)
    return found


# A9.


def span_rows(rows: list[dict], first_ns: int, last_ns: int, half_ns: int) -> list[dict]:
    """The rows of a capture's span: CPUStartQPCTime within `half_ns` (half the shortest frame)
    of the first and the last swap stamp. A frame's CPU start is its previous Present's return
    (plans/m1.md P38), the moment the swap stamp marks: in 0.01.09's runs the row lagged it by
    0.10-0.38 ms, while the HEAD stamp of a frame without readback work came only 0.10-0.12 ms
    after the swap, so an edge on the HEAD stamps put the first row on either side of it
    (m1-acceptance-5 paired every frame one present off). Half a frame from the swap stamps keeps
    each edge half a frame from the nearest row (user, 2026-10-07)."""
    ordered = sorted(rows, key=qpc_ns)
    return [row for row in ordered if first_ns - half_ns <= qpc_ns(row) <= last_ns + half_ns]


def offsets_summary(values: list[float]) -> dict:
    """Signed offsets (ms): min, median, max, and the median and maximum of their sizes."""
    sizes = [abs(v) for v in values]
    return {
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
        "absMedian": round(statistics.median(sizes), 4),
        "absMax": round(max(sizes), 4),
    }


def a9_match(rows: list[dict], frames: list[dict], limit_ms: float = A9_LIMIT_MS) -> dict:
    """A9's match (plans/m1.md 0.01.09, D26): the captured frames by frameIndex, consecutive, each
    with its swap stamp; the rows of their span (span_rows, half the shortest frame around the
    swap stamps) must count the same as the stamps; then frame k pairs with row k. Both offsets,
    stamp minus CPUStartQPCTime x 1e6 in ms, are reported: the frame-hook HEAD stamp's and the
    swap-return stamp's; A9 passes on the swap stamp, its median and maximum size under `limit_ms`
    and under half the shortest frame (docs/mod.md#12-acceptance). One frame has no shortest
    frame: its span is `limit_ms` wide on each side."""
    stamps = sorted(frames, key=lambda f: f["frameIndex"])
    if not stamps:
        return {"pass": False, "problem": "no captured frame"}
    if any(not f.get("swapQpcNs") for f in stamps):
        return {"pass": False, "problem": "a frame carries no swap stamp (swapQpcNs 0)"}
    indexes = [f["frameIndex"] for f in stamps]
    gaps = [b - a for a, b in itertools.pairwise(indexes) if b - a != 1]
    swaps = [f["swapQpcNs"] for f in stamps]
    shortest = min(b - a for a, b in itertools.pairwise(swaps)) / 1e6 if len(swaps) > 1 else None
    half_ns = round((limit_ms if shortest is None else shortest / 2) * 1e6)
    first, last = swaps[0], swaps[-1]
    span = span_rows(rows, first, last, half_ns)
    found: dict = {
        "frames": len(stamps),
        "frameIndexes": [indexes[0], indexes[-1]],
        "consecutive": not gaps,
        "rows": len(rows),
        "spanRows": len(span),
        "rowsAfter": sum(1 for row in rows if qpc_ns(row) > last + half_ns),
        "spanNs": [first - half_ns, last + half_ns],
    }
    processes = sorted({row.get(PROCESS_ID, "") for row in span})
    chains = sorted({row.get(SWAP_CHAIN, "") for row in span})
    found.update(processes=processes, swapChains=chains)
    if len(processes) > 1 or len(chains) > 1:
        # A second process or swap chain could put a foreign row into the span and pass.
        return {**found, "pass": False, "problem": "the span holds more than one swap chain"}
    if gaps:
        return {**found, "pass": False, "problem": f"the frames are not consecutive: {gaps}"}
    if not found["rowsAfter"]:
        return {**found, "pass": False, "problem": "the CSV ends inside the capture's span"}
    if len(span) != len(stamps):
        return {
            **found,
            "pass": False,
            "problem": f"{len(span)} rows in the span against {len(stamps)} stamps",
        }
    head = [(f["qpcNs"] - qpc_ns(r)) / 1e6 for f, r in zip(stamps, span, strict=True)]
    swap = [(f["swapQpcNs"] - qpc_ns(r)) / 1e6 for f, r in zip(stamps, span, strict=True)]
    bound = limit_ms if shortest is None else min(limit_ms, shortest / 2)
    on_swap = offsets_summary(swap)
    found.update(
        headOffsetMs=offsets_summary(head),
        swapOffsetMs=on_swap,
        shortestFrameMs=None if shortest is None else round(shortest, 4),
        limitMs=round(bound, 4),
        pairs=[
            {
                "frameIndex": f["frameIndex"],
                "cpuStartQpcMs": r[QPC],
                "headMs": round(h, 4),
                "swapMs": round(s, 4),
            }
            for f, r, h, s in zip(stamps, span, head, swap, strict=True)
        ],
    )
    passed = on_swap["absMedian"] < bound and on_swap["absMax"] < bound
    return {**found, "pass": passed}
