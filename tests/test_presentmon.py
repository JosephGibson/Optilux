"""PresentMon, minimal (docs/plans/m1.md 0.01.09): the start and the CTRL_BREAK_EVENT stop on a
fake process (and, on Windows, on a real child that handles the break the way PresentMon does),
the CSV read while it grows, and A9's cut and match on a fixture CSV and stamps."""

import csv
import ctypes
import io
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from optilux import presentmon

FIXTURES = Path(__file__).parent / "fixtures" / "run"
EXE = Path("PresentMon-2.6.0-x64.exe")


class FakeProcess:
    """A PresentMon that exits 0 on CTRL_BREAK_EVENT, or ignores it (`deaf`), or has exited."""

    def __init__(self, pid: int = 4242, deaf: bool = False, exited: int | None = None) -> None:
        self.pid = pid
        self.returncode = exited
        self.deaf = deaf
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            raise subprocess.TimeoutExpired("PresentMon", timeout or 0)
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


class FakeHost(presentmon.Host):
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.started: list[list[str]] = []
        self.breaks: list[int] = []
        self.error = 0
        self.now = 100.0

    def start(self, command: list[str], log: Path) -> FakeProcess:
        self.started.append(command)
        return self.process

    def ctrl_break(self, pid: int) -> int:
        self.breaks.append(pid)
        if self.error:
            return self.error
        if not self.process.deaf:
            self.process.returncode = 0
        return 0

    def clock(self) -> float:
        self.now += 0.5
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def started(tmp_path: Path, process: FakeProcess) -> tuple[presentmon.Recording, FakeHost]:
    (tmp_path / EXE).write_bytes(b"MZ")
    host = FakeHost(process)
    found = presentmon.start(tmp_path / EXE, 777, tmp_path / "pm.csv", "optilux-run-1", host)
    return found, host


def test_the_start_runs_the_measurement_command_line(tmp_path: Path) -> None:
    found, host = started(tmp_path, FakeProcess())
    assert host.started == [
        [
            str(tmp_path / EXE),
            "--process_id",
            "777",
            "--output_file",
            str(tmp_path / "pm.csv"),
            "--qpc_time_ms",
            "--v2_metrics",
            "--session_name",
            "optilux-run-1",
            "--stop_existing_session",
            "--no_console_stats",
        ]
    ]
    assert found.session == "optilux-run-1" and found.log == tmp_path / "pm.log"


def test_the_stop_is_ctrl_break_to_presentmons_group(tmp_path: Path) -> None:
    found, host = started(tmp_path, FakeProcess(pid=4242))
    facts = presentmon.stop(found, host)
    assert host.breaks == [4242]
    assert (facts["how"], facts["sent"], facts["exitCode"]) == ("CTRL_BREAK_EVENT", True, 0)


def test_a_presentmon_gone_before_the_stop_fails(tmp_path: Path) -> None:
    found, host = started(tmp_path, FakeProcess())
    found.process.returncode = 1  # killed from outside
    with pytest.raises(presentmon.PresentMonError, match="before the stop"):
        presentmon.stop(found, host)
    assert host.breaks == []


def test_a_presentmon_deaf_to_the_break_is_killed_and_fails(tmp_path: Path) -> None:
    found, host = started(tmp_path, FakeProcess(deaf=True))
    with pytest.raises(presentmon.PresentMonError, match="was killed"):
        presentmon.stop(found, host)
    assert found.process.killed


def test_a_break_that_cannot_be_sent_kills_at_once_and_fails(tmp_path: Path) -> None:
    found, host = started(tmp_path, FakeProcess(deaf=True))
    host.error = 87  # ERROR_INVALID_PARAMETER: PresentMon's group is on another console
    began = host.now
    with pytest.raises(presentmon.PresentMonError, match="Windows error 87"):
        presentmon.stop(found, host)
    assert found.process.killed and host.now - began < presentmon.STOP_TIMEOUT


def test_a_presentmon_that_exits_at_once_fails_the_start(tmp_path: Path) -> None:
    with pytest.raises(presentmon.PresentMonError, match="at its start"):
        started(tmp_path, FakeProcess(exited=2))


@pytest.mark.parametrize(
    ("session", "exists", "says"),
    [("run-1", False, "prefix"), ("optilux-run-1", True, "exists")],
)
def test_the_start_refuses_a_foreign_session_or_a_used_file(
    tmp_path: Path, session: str, exists: bool, says: str
) -> None:
    (tmp_path / EXE).write_bytes(b"MZ")
    if exists:
        (tmp_path / "pm.csv").write_text("x", encoding="utf-8")
    with pytest.raises(presentmon.PresentMonError, match=says):
        presentmon.start(tmp_path / EXE, 1, tmp_path / "pm.csv", session, FakeHost(FakeProcess()))


# A real child in its own process group, stopped by CTRL_BREAK_EVENT: PresentMon's mechanism.

CHILD = textwrap.dedent(
    """
    import signal, sys, time
    out = sys.argv[1]
    def stop(signum, frame):
        with open(out, "a", encoding="utf-8") as f:
            f.write("stopped\\n")
        sys.exit(0)
    signal.signal(signal.SIGBREAK, stop)
    with open(out, "w", encoding="utf-8") as f:
        f.write("ready\\n")
    while True:
        time.sleep(0.05)
    """
)


def has_console() -> bool:
    if sys.platform != "win32":
        return False
    processes = (ctypes.c_uint32 * 4)()
    return ctypes.windll.kernel32.GetConsoleProcessList(processes, 4) > 0  # type: ignore[attr-defined]


@pytest.mark.windows
@pytest.mark.skipif(not has_console(), reason="CTRL_BREAK_EVENT reaches a group on one's console")
def test_a_real_child_stops_on_ctrl_break(tmp_path: Path) -> None:
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    out = tmp_path / "out.txt"
    host = presentmon.Host()
    process = host.start([sys.executable, str(script), str(out)], tmp_path / "child.log")
    found = presentmon.Recording(process, out, "optilux-test", tmp_path / "child.log", [], 0.0)
    deadline = host.clock() + 30
    while not (out.is_file() and out.read_text(encoding="utf-8")) and host.clock() < deadline:
        host.sleep(0.05)
    facts = presentmon.stop(found, host)
    assert (facts["sent"], facts["exitCode"]) == (True, 0)
    assert out.read_text(encoding="utf-8") == "ready\nstopped\n"


# The CSV.

# The first 12 rows of m1-acceptance-4's CSV as PresentMon 2.6 wrote them (byte-order mark, the
# v2 columns; CRLF made LF by git).
HEADER = (FIXTURES / "presentmon.csv").read_text(encoding="utf-8-sig").splitlines()[0]


def csv_text(starts_ms: list[float], pid: int = 777) -> str:
    """A CSV in the fixture's columns with one row per CPU start (ms)."""
    columns = HEADER.split(",")
    lines = [HEADER]
    for start in starts_ms:
        row = {name: "0" for name in columns}
        row.update(
            Application="javaw.exe",
            ProcessID=str(pid),
            SwapChainAddress="0x0000000000ABCDEF",
            PresentMode="Hardware: Independent Flip",
            CPUStartQPCTime=f"{start:.6f}",
        )
        lines.append(",".join(row[name] for name in columns))
    return "\n".join(lines) + "\n"


def test_the_fixture_csv_reads_with_its_qpc_column() -> None:
    header, rows = presentmon.read_rows(FIXTURES / "presentmon.csv", complete=True)
    assert header[0] == "Application"  # the byte-order mark is dropped
    assert presentmon.QPC in header and presentmon.PROCESS_ID in header
    assert len(rows) == 12 and rows[0]["ProcessID"] == "23672"
    assert presentmon.qpc_ns(rows[0]) == round(float(rows[0][presentmon.QPC]) * 1e6)


def test_a_partial_last_line_waits_while_presentmon_writes(tmp_path: Path) -> None:
    path = tmp_path / "pm.csv"
    path.write_text(csv_text([1000.0, 1007.0])[:-12], encoding="utf-8")
    assert len(presentmon.read_rows(path)[1]) == 1
    with pytest.raises(presentmon.PresentMonError, match="fields"):
        presentmon.read_rows(path, complete=True)
    # As PresentMon 2.6 writes it: a byte-order mark and CRLF lines.
    crlf = "\ufeff" + csv_text([1000.0, 1007.0]).replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))
    assert [r[presentmon.QPC] for r in presentmon.read_rows(path)[1]] == [
        "1000.000000",
        "1007.000000",
    ]


def test_no_file_yet_reads_as_no_rows_and_a_foreign_csv_is_refused(tmp_path: Path) -> None:
    assert presentmon.read_rows(tmp_path / "absent.csv") == ([], [])
    other = tmp_path / "other.csv"
    other.write_text("Application,ProcessID\nx,1\n", encoding="utf-8")
    with pytest.raises(presentmon.PresentMonError, match="no CPUStartQPCTime"):
        presentmon.read_rows(other)


def test_the_wait_ends_on_a_row_past_the_stamp(tmp_path: Path) -> None:
    found, host = started(tmp_path, FakeProcess())
    found.output.write_text(csv_text([1000.0, 1007.0]), encoding="utf-8")
    assert presentmon.wait_rows(found, host, None, 5) == 2
    assert presentmon.wait_rows(found, host, 1_006_000_000, 5) == 2
    with pytest.raises(presentmon.PresentMonError, match="no a row after"):
        presentmon.wait_rows(found, host, 1_007_000_000, 5)
    found.process.returncode = 1
    with pytest.raises(presentmon.PresentMonError, match="while recording"):
        presentmon.wait_rows(found, host, 1_007_000_000, 5)


# A9: frames k = 0..n-1 whose previous Present returned at row k's CPU start (+ swap ms) and whose
# head came `head` ms after it.


def stamps(starts_ms: list[float], first: int, count: int, swap: float, head: float) -> list[dict]:
    return [
        {
            "frameIndex": 500 + k,
            "qpcNs": round((starts_ms[first + k] + head) * 1e6),
            "swapQpcNs": round((starts_ms[first + k] + swap) * 1e6),
        }
        for k in range(count)
    ]


STARTS = [1000.0 + 7.0 * k for k in range(12)]


def _rows(starts_ms: list[float]) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_text(starts_ms))))


def test_a9_pairs_the_span_by_order_and_passes_on_the_swap_stamp() -> None:
    frames = stamps(STARTS, 3, 5, swap=0.04, head=2.5)
    found = presentmon.a9_match(_rows(STARTS), frames)
    assert found["pass"] is True
    assert (found["spanRows"], found["frames"], found["rowsAfter"]) == (5, 5, 4)
    assert [p["cpuStartQpcMs"] for p in found["pairs"]] == [f"{s:.6f}" for s in STARTS[3:8]]
    assert found["swapOffsetMs"]["median"] == pytest.approx(0.04)
    assert found["headOffsetMs"]["absMax"] == pytest.approx(2.5)
    assert found["shortestFrameMs"] == pytest.approx(7.0)


def test_a9_fails_on_a_swap_offset_of_a_millisecond_or_more() -> None:
    found = presentmon.a9_match(_rows(STARTS), stamps(STARTS, 3, 5, swap=1.2, head=2.5))
    assert found["pass"] is False and found["swapOffsetMs"]["absMedian"] == pytest.approx(1.2)


def test_a9_fails_when_the_rows_do_not_count_the_same_as_the_stamps() -> None:
    frames = stamps(STARTS, 3, 5, swap=0.04, head=2.5)
    missing = [row for k, row in enumerate(_rows(STARTS)) if k != 5]
    found = presentmon.a9_match(missing, frames)
    assert found["pass"] is False and "4 rows in the span against 5 stamps" in found["problem"]
    other = _rows(STARTS)
    other[5]["SwapChainAddress"] = "0x0000000000FEDCBA"
    assert "more than one swap chain" in presentmon.a9_match(other, frames)["problem"]
    extra = _rows(sorted([*STARTS, STARTS[5] + 3.0]))
    assert presentmon.a9_match(extra, frames)["problem"].startswith("6 rows")


def test_a9_fails_on_gaps_and_on_a_csv_that_ends_inside_the_span() -> None:
    frames = stamps(STARTS, 3, 5, swap=0.04, head=2.5)
    gapped = [frames[0], *frames[2:]]
    assert "not consecutive" in presentmon.a9_match(_rows(STARTS), gapped)["problem"]
    short = _rows(STARTS[:8])
    assert "ends inside" in presentmon.a9_match(short, frames)["problem"]
    assert presentmon.a9_match(_rows(STARTS), [])["pass"] is False


REAL = [
    # run, pid, swap offset (min, median, max, |median|, |max|), head offset (median, |max|)
    ("4", "23672", (-0.3346, -0.1635, -0.1069, 0.1635, 0.3346), (13.5664, 34.4641)),
    ("5", "24608", (-0.379, -0.1585, -0.1011, 0.1585, 0.379), (13.1963, 32.571)),
]


@pytest.mark.parametrize(("run", "pid", "swap", "head"), REAL)
def test_a9_on_the_real_spans_and_stamps(run: str, pid: str, swap: tuple, head: tuple) -> None:
    """The real match: m1-acceptance-<run>'s 120 stamps (capture.json) against its CSV's rows from
    two before the span to three after it. -4's offsets equal its record's; -5's record failed on
    the HEAD-anchored span this rule replaced (user, 2026-10-07): its first row lies after the
    first HEAD stamp, so the old rule paired every frame one present off."""
    _, rows = presentmon.read_rows(FIXTURES / f"a9-{run}-presentmon.csv", complete=True)
    frames = json.loads((FIXTURES / f"a9-{run}-frames.json").read_text(encoding="utf-8"))
    found = presentmon.a9_match(rows, frames["frames"])
    assert found["pass"] is True
    assert (found["frames"], found["spanRows"], found["rowsAfter"]) == (120, 120, 3)
    assert (found["processes"], found["swapChains"]) == ([pid], ["0x0"])
    keys = ("min", "median", "max", "absMedian", "absMax")
    assert tuple(found["swapOffsetMs"][key] for key in keys) == swap
    assert (found["headOffsetMs"]["median"], found["headOffsetMs"]["absMax"]) == head
    first_row = presentmon.qpc_ns(sorted(rows, key=presentmon.qpc_ns)[2])
    assert (first_row > frames["frames"][0]["qpcNs"]) is (run == "5")


def test_presentmons_session_prefix_is_the_one_the_launch_gate_reads() -> None:
    """A run killed mid-A9 leaves its ETW session; the next launch's gate finds it by prefix."""
    from optilux import launch

    assert presentmon.SESSION_PREFIX == launch.OWN_SESSION


def test_a_presentmon_that_survives_its_kill_still_fails_with_the_fix(tmp_path: Path) -> None:
    """The kill's own wait timing out is said in the error, never raised over it."""

    class Undying(FakeProcess):
        def kill(self) -> None:
            self.killed = True  # still running

    found, host = started(tmp_path, Undying(deaf=True))
    with pytest.raises(presentmon.PresentMonError, match="logman stop optilux-run-1 -ets"):
        presentmon.stop(found, host)


def test_a_presentmon_that_exits_nonzero_on_the_break_fails(tmp_path: Path) -> None:
    class Failing(FakeHost):
        def ctrl_break(self, pid: int) -> int:
            self.process.returncode = 2
            return 0

    found, _ = started(tmp_path, FakeProcess())
    with pytest.raises(presentmon.PresentMonError, match="exited with code 2"):
        presentmon.stop(found, Failing(found.process))


def test_a9_refuses_a_frame_without_a_swap_stamp() -> None:
    frames = [{"frameIndex": 1, "qpcNs": 7_000_000, "swapQpcNs": 0}]
    found = presentmon.a9_match([], frames)
    assert found["pass"] is False and "swap stamp" in found["problem"]
    assert presentmon.a9_match([], [])["pass"] is False
