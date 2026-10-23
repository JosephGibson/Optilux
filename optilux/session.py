"""One game session as `run` drives it (docs/mod-protocol.md#choreography), and what M2's verbs
reuse: RunHost (the machine beyond launch's: pipes, jcmd, memory, SendInput, focus, PresentMon,
idle time and the 3D engine's users, the display timeout and request, other processes' facts, the
game's connections), the Session
(the client, the step log, the events, the events that end it), the run's journal (plans/m2.md
D41), the session start, a view's time, weather and pose, the focus checks before any injected
input, the spec loader and the PresentMon pin check. The acceptance items live in
optilux/acceptance.py, the measured session in optilux/measure.py, the verb in
optilux/verbs/run.py."""

import contextlib
import json
import os
import queue
import subprocess
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from optilux import launch, modclient, presentmon, record, sendinput
from optilux.verbs.install import TOOLS, TOOLS_DIR, Say, shown

REQUESTS = launch.REQUESTS


PIPES = "\\\\.\\pipe\\"


# The run's journal (plans/m2.md D41): raw/<name>/partial.json while the run goes, renamed
# journal.json once its record is written.
PARTIAL = "partial.json"
CLOSED = "journal.json"
# A rename over a file a scanner holds open can fail for a moment on Windows.
REPLACE_TRIES = 20
REPLACE_GAP = 0.05


# The 3D engine's users (plans/m2.md D42, P16): typeperf's per-process GPU Engine counters.
GPU_COUNTER = r"\GPU Engine(*engtype_3D)\Utilization Percentage"
# plans/m2.md M2.P06's diagnosis: every process's and adapter's GPU memory (only read).
GPU_MEMORY = tuple(
    rf"\GPU {who} Memory(*)\{kind} Usage"
    for who in ("Process", "Adapter")
    for kind in ("Dedicated", "Shared")
)
TYPEPERF_TIMEOUT = 30
LOGMAN_STOP_TIMEOUT = 30
# The displays as a measured run takes its display request (winnt.h, winuser.h; only read): the
# power scheme's "Turn off display after" (GUID_VIDEO_SUBGROUP, GUID_VIDEO_POWERDOWN_TIMEOUT) and
# the console display's state (GUID_CONSOLE_DISPLAY_STATE), reported to a callback subscriber.
DISPLAY_IDLE = ("7516b95f-f776-4464-8c53-06167f40cc99", "3c0bc021-c8a8-4e07-a973-6b14cbcb2b7e")
CONSOLE_DISPLAY = "6fe69556-704a-47a0-8f24-c28d936fda47"
DEVICE_NOTIFY_CALLBACK = 2
PBT_POWERSETTINGCHANGE = 0x8013
DISPLAY_STATE_WAIT = 2.0


# The session start's waits (seconds): world.wait and selftest after a 14 s join (0.01.07's
# selftest took 3.2 s), ready over 10 stable frames, a reload (0.4-0.6 s so far).
WORLD_TIMEOUT = 60.0


SELFTEST_TIMEOUT = 120.0


STABLE_FRAMES = 10


READY_TIMEOUT = 120.0


RELOAD_TIMEOUT = 60.0


# A dimension's first entry creates Iris's pipeline for it: 15.5 s for the Nether (0.01.06),
# 14.4 s for the End (0.01.08's first launch).
PLACE_TIMEOUT = 90.0


COMMAND_TIMEOUT = 10.0


# The time a view names is the overworld clock's (handoff 0.01.06: 26.x has no day time).
OVERWORLD = "minecraft:overworld"


# The only perf view with entities in sight and the GUI shown (shows_hand).
ENTITIES = "entities"


# Events that invalidate a capture (docs/mod-protocol.md#client-rules).
INVALIDATING = ("hook.error", "focus.lost", "screen.opened", "reload.done", "dimension.changed")


JCMD_TIMEOUT = 60


class RunError(RuntimeError):
    """A run that cannot go on; the message names the problem."""


class SessionEnded(RunError):
    """A measured session ended by an event (plans/m2.md D42: focus.lost or screen.opened):
    its record is invalid."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Attached:
    """A running process this harness did not start (an orphan's game or PresentMon), as launch's
    end and PresentMon's stop use a started one: poll, wait (subprocess.TimeoutExpired), kill.
    Windows gives no exit code of another process's child: an exit reads as code 0."""

    def __init__(self, proc: psutil.Process) -> None:
        self._proc = proc
        self.pid = proc.pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is None and not self._proc.is_running():
            self.returncode = 0
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        try:
            code = self._proc.wait(timeout)
        except psutil.TimeoutExpired:
            raise subprocess.TimeoutExpired(f"pid {self.pid}", timeout or 0) from None
        self.returncode = code if isinstance(code, int) else 0
        return self.returncode

    def kill(self) -> None:
        with contextlib.suppress(psutil.NoSuchProcess):
            self._proc.kill()  # psutil refuses a pid reused since this handle was made

    def same(self, kept: dict) -> bool:
        """This handle's process is the journal's: the same creation time and executable, read
        through the handle the end will use (D41: Windows reuses pids)."""
        try:
            exe = self._proc.exe()
            created = self._proc.create_time()
        except psutil.Error:
            return False
        same_exe = launch.norm(exe) == launch.norm(str(kept.get("exe") or ""))
        return created == kept.get("createTime") and same_exe


# The machine, beyond launch's.


def guid(text: str) -> Any:
    """A GUID's 16 bytes as Windows lays them out, for a ctypes call to take by reference."""
    import ctypes
    import uuid

    return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)


class RunHost(launch.Host):
    """launch's Host plus what the items read and inject; the tests replace it."""

    def pipes(self) -> list[str]:
        return sorted(os.listdir(PIPES))

    def jcmd(self, jcmd: Path, pid: int, command: str) -> str:
        """`jcmd <pid> <command>`'s output; RunError when it fails."""
        done = subprocess.run(  # noqa: S603 argv list: the Temurin jcmd, a pid, a constant
            [str(jcmd), str(pid), command],
            capture_output=True,
            text=True,
            timeout=JCMD_TIMEOUT,
        )
        if done.returncode != 0:
            raise RunError(f"jcmd {pid} {command} exited {done.returncode}: {done.stderr[-300:]}")
        return done.stdout

    def thread_dump(self, jcmd: Path, pid: int) -> str:
        return self.jcmd(jcmd, pid, "Thread.print")

    def private_bytes(self, pid: int) -> int:
        """The process's private bytes (psutil, plans/m1.md D17)."""
        return psutil.Process(pid).memory_info().private

    def available_memory(self) -> int:
        return psutil.virtual_memory().available

    def physical_memory(self) -> int:
        """The machine's physical memory in bytes (plans/m2.md D43's private-bytes limit)."""
        return psutil.virtual_memory().total

    def key_press(self, vk: int, scan: int) -> int:
        return sendinput.key_press(vk, scan=scan)

    def mouse_move(self, dx: int, dy: int) -> int:
        return sendinput.mouse_move(dx, dy)

    def foreground_pid(self) -> int:
        """The pid owning the foreground window (0 when none)."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        owner = wintypes.DWORD()
        window = user32.GetForegroundWindow()
        if window:
            user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        return owner.value

    def presentmon(self) -> presentmon.Host:
        return presentmon.Host()

    def idle_seconds(self) -> float:
        """Seconds since the last input on this session's desktop (GetLastInputInfo; the
        harness's own SendInput counts too, lessons.md#windows). OSError when the call fails."""
        import ctypes
        from ctypes import wintypes

        class LastInputInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LastInputInfo()
        info.cbSize = ctypes.sizeof(info)
        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32 = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined]
        kernel32.GetTickCount.restype = wintypes.DWORD
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            raise OSError(ctypes.get_last_error(), "GetLastInputInfo failed")
        return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0

    def display_timeout(self) -> int:
        """The active power scheme's "Turn off display after" on AC in seconds, 0 for never
        (PowerGetActiveScheme, PowerReadACValueIndex: only read). OSError when a call fails."""
        import ctypes
        from ctypes import wintypes

        powrprof = ctypes.WinDLL("powrprof")  # type: ignore[attr-defined]
        kernel32 = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined]
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        scheme = ctypes.c_void_p()  # a GUID the call allocates, freed with LocalFree
        failed = powrprof.PowerGetActiveScheme(None, ctypes.byref(scheme))
        if failed:
            raise OSError(f"PowerGetActiveScheme returned {failed}")
        subgroup, setting = (guid(g) for g in DISPLAY_IDLE)
        value = wintypes.DWORD()
        try:
            failed = powrprof.PowerReadACValueIndex(
                None, scheme, ctypes.byref(subgroup), ctypes.byref(setting), ctypes.byref(value)
            )
        finally:
            kernel32.LocalFree(scheme)
        if failed:
            raise OSError(f"PowerReadACValueIndex returned {failed}")
        return value.value

    def display_state(self) -> int | None:
        """The console display's state, which Windows reports at once to a new subscriber of
        GUID_CONSOLE_DISPLAY_STATE (PowerSettingRegisterNotification with a callback; only read):
        0 off, 1 on, 2 dimmed; None when no report came within DISPLAY_STATE_WAIT. OSError when
        the subscription fails."""
        import ctypes
        import threading
        from ctypes import wintypes

        reported: list[int] = []
        came = threading.Event()

        @ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p)
        def report(context: object, kind: int, setting: int) -> int:
            # POWERBROADCAST_SETTING: the setting's GUID, its data's length, then the data.
            raw = ctypes.string_at(setting, 24)
            if kind == PBT_POWERSETTINGCHANGE and raw[:16] == bytes(guid(CONSOLE_DISPLAY)):
                reported.append(int.from_bytes(raw[20:24], "little"))
                came.set()
            return 0

        powrprof = ctypes.WinDLL("powrprof")  # type: ignore[attr-defined]
        # DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS: the callback and its context.
        subscribe = (ctypes.c_void_p * 2)(ctypes.cast(report, ctypes.c_void_p), None)
        console = guid(CONSOLE_DISPLAY)
        handle = ctypes.c_void_p()
        failed = powrprof.PowerSettingRegisterNotification(
            ctypes.byref(console),
            DEVICE_NOTIFY_CALLBACK,
            ctypes.byref(subscribe),
            ctypes.byref(handle),
        )
        if failed:
            raise OSError(f"PowerSettingRegisterNotification returned {failed}")
        try:
            came.wait(DISPLAY_STATE_WAIT)
        finally:
            powrprof.PowerSettingUnregisterNotification(handle)
        return reported[0] if reported else None

    def execution_state(self, flags: int) -> None:
        """SetThreadExecutionState(flags): a power request held by the calling thread until it
        sets another or ends, no setting changed. OSError when it fails (it returns 0)."""
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined]
        kernel32.SetThreadExecutionState.restype = ctypes.c_uint32
        kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
        if not kernel32.SetThreadExecutionState(flags):
            raise OSError(f"SetThreadExecutionState({flags:#x}) returned 0")

    def gpu_engine(self, samples: int) -> str:
        """typeperf's CSV of every process's 3D engine use, one sample a second (only read,
        plans/m2.md P16). OSError naming the exit when typeperf fails."""
        try:
            done = subprocess.run(  # noqa: S603 a constant counter path and two integers
                ["typeperf", GPU_COUNTER, "-si", "1", "-sc", str(samples)],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=TYPEPERF_TIMEOUT + samples,
            )
        except subprocess.TimeoutExpired as error:
            raise OSError(f"typeperf ran past {error.timeout:g} s") from None
        if done.returncode != 0:
            raise OSError(f"typeperf exited {done.returncode}: {done.stdout.strip()[-200:]}")
        return done.stdout

    def gpu_memory(self) -> str:
        """typeperf's one-sample CSV of every process's and adapter's dedicated and shared GPU
        memory (only read, M2.P06). OSError naming the exit when typeperf fails."""
        try:
            done = subprocess.run(  # noqa: S603 constant counter paths
                ["typeperf", *GPU_MEMORY, "-sc", "1"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=TYPEPERF_TIMEOUT,
            )
        except subprocess.TimeoutExpired as error:
            raise OSError(f"typeperf ran past {error.timeout:g} s") from None
        if done.returncode != 0:
            raise OSError(f"typeperf exited {done.returncode}: {done.stdout.strip()[-200:]}")
        return done.stdout

    def process_facts(self, pid: int) -> dict | None:
        """A running process's facts as a journal keeps them (D41: Windows reuses pids, so a pid
        names the same process only with the same creation time and executable); None when no
        process has the pid. A field Windows will not read (another user's or a protected
        process: never this harness's game or PresentMon) is None, so it never matches."""
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return None
        found: dict[str, Any] = {"pid": pid}
        reads = {
            "createTime": proc.create_time,
            "exe": proc.exe,
            "name": proc.name,
            "cwd": proc.cwd,
            "cmdline": proc.cmdline,
        }
        for key, read in reads.items():
            try:
                found[key] = read()
            except psutil.NoSuchProcess:
                return None
            except psutil.Error:  # AccessDenied: not a process of this user's
                found[key] = None
        return found

    def attach(self, pid: int) -> Attached:
        return Attached(psutil.Process(pid))

    def connections(self, pid: int) -> list[dict]:
        """The process's internet connections with a remote end (F10: offline mode still calls
        api.minecraftservices.com at startup), recorded, never blocked."""
        found = psutil.Process(pid).net_connections(kind="inet")
        return [
            {"remote": f"{c.raddr.ip}:{c.raddr.port}", "status": c.status} for c in found if c.raddr
        ]

    def stop_session(self, name: str) -> str:
        """`logman stop <name> -ets`: an orphan's own ETW session stopped, the fix PresentMon's
        error names (D41). RunError when it fails."""
        try:
            done = subprocess.run(  # noqa: S603 logman and an optilux- session name
                ["logman", "stop", name, "-ets"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=LOGMAN_STOP_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RunError(f"logman stop {name} -ets failed: {error}") from None
        if done.returncode != 0:
            raise RunError(
                f"logman stop {name} -ets exited {done.returncode}: {done.stdout.strip()[-200:]}"
            )
        return done.stdout.strip()

    def focus(self, pid: int) -> str:
        """The game's window brought to the foreground (attached thread input), when it is not."""
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        windows = launch.windows_of(pid)
        if not windows:
            return "no window"
        theirs = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        mine = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(mine, theirs, True)
        done = user32.SetForegroundWindow(windows[0])
        user32.AttachThreadInput(mine, theirs, False)
        return f"SetForegroundWindow -> {done}"

    def click_focus(self, pid: int) -> str:
        """One click at the centre of the game's window, which activates it, and only when the
        window under that point is the game's: a click never lands on another program."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        windows = launch.windows_of(pid)
        if not windows:
            return "no window"
        rect = wintypes.RECT()
        user32.GetWindowRect(windows[0], ctypes.byref(rect))
        point = wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        under = user32.GetAncestor(user32.WindowFromPoint(point), 2)  # GA_ROOT
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(under, ctypes.byref(owner))
        if owner.value != pid:
            return f"the window at ({point.x}, {point.y}) is pid {owner.value}'s: no click"
        user32.SetCursorPos(point.x, point.y)
        return f"clicked ({point.x}, {point.y}) in the game's window: {sendinput.left_click()}"


def view_pose(view: dict) -> dict:
    keys = ("x", "y", "z", "yaw", "pitch")
    return {"dimension": view["dim"], **{key: view[key] for key in keys}}


def shows_hand(view: dict) -> bool:
    """plans/m2.md D49: of the perf views entities alone shows the GUI, in creative with prep's
    torch in the main hand; a coverage view with `hand` does too (plans/m3.md D64)."""
    return view["id"] == ENTITIES or view.get("hand") is True


# The session.


class Session:
    """One launched game with the mod connected: its steps, events and facts as they happen.
    `stop_on` tells the events that end the session at the step that drains them
    (SessionEnded)."""

    def __init__(
        self, root: Path, raw: Path, launched: launch.Launched, client, host: RunHost, say: Say
    ) -> None:
        self.root = root
        self.raw = raw
        self.launched = launched
        self.client: modclient.Client = client
        self.host = host
        self.say = say
        self.steps: list[dict] = []
        self.events: list[dict] = []
        self.label = "start"
        self.stop_on: Callable[[dict], bool] | None = None

    def drain(self) -> list[dict]:
        found = []
        while True:
            try:
                event = self.client.events.get_nowait()
            except queue.Empty:
                break
            found.append(
                {
                    "step": self.label,
                    "event": event.get("event"),
                    "data": event.get("data"),
                    "frameIndex": event.get("frameIndex"),
                    "sinceReload": event.get("sinceReload"),
                }
            )
        self.events += found
        return found

    def stop_check(self, events: list[dict], name: str) -> None:
        """SessionEnded at the first of `events` that `stop_on` tells."""
        ending = [e for e in events if self.stop_on is not None and self.stop_on(e)]
        if ending:
            first = ending[0]
            raise SessionEnded(
                f"{name}: {first['event']} {first.get('data') or ''} at frame "
                f"{first['frameIndex']} ends the session (plans/m2.md D42: a measured session "
                "needs the machine to itself)"
            )

    def step(self, name: str, call, show=None, keep=None) -> Any:
        """Run one request, record its answer (or error, or what `keep` keeps of a long one) and
        the seconds, say it."""
        self.label = name
        began = time.monotonic()
        try:
            answer = call()
        except (modclient.ModError, ValueError, OSError) as error:
            self.steps.append(
                {"step": name, "error": str(error), "seconds": round(time.monotonic() - began, 3)}
            )
            self.drain()
            raise RunError(f"{name}: {error}") from None
        seconds = round(time.monotonic() - began, 3)
        kept = keep(answer) if keep is not None else answer
        self.steps.append({"step": name, "answer": kept, "seconds": seconds})
        drained = self.drain()
        self.say(f"{name}: {show(answer) if show else 'ok'} ({seconds:.2f} s)")
        self.stop_check(drained, name)
        return answer


class Journal:
    """The run's journal (plans/m2.md D41), raw/<name>/partial.json: the spec, the identity, the
    pids of the runner, the game and PresentMon, the files the run wrote under runtime/ and each
    capture's stamps, written whole as they change (a temporary file renamed over it, so a run
    killed at any moment leaves the last whole one). The next `run` finishes a run whose journal
    is still partial (measure.finish_orphans); `close` renames it once the record is written."""

    def __init__(self, raw: Path, data: dict) -> None:
        self.path = raw / PARTIAL
        self.data = data
        self.write()

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.write()

    def append(self, key: str, value: Any) -> None:
        self.data.setdefault(key, []).append(value)
        self.write()

    def write(self) -> None:
        self.data["journaledAt"] = now()  # an orphan's record ends at its journal's last write
        part = self.path.with_name(self.path.name + ".tmp")
        text = json.dumps(self.data, indent=1, default=str, allow_nan=False) + "\n"
        part.write_bytes(text.encode("utf-8"))
        replace(part, self.path)

    def close(self) -> None:
        replace(self.path, self.path.with_name(CLOSED))


def replace(source: Path, target: Path) -> None:
    """os.replace, retried for a moment while another process (a scanner) holds the target."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_GAP)


def record_status(
    status: str,
    problems: list[str],
    facts: dict,
    items: dict[str, dict],
    asked: Sequence[str],
    reloads: int,
    table: dict | None,
) -> tuple[str, list[dict]]:
    """The record's status and acceptance list from a session's facts and items
    (docs/run-record.md#record): invalid on a hook failure, failed on any problem or failed item,
    aborted kept; an item never reached is recorded as not run with the last problem. `problems`
    gains each reason; each item's `pass` moves from its evidence to its entry."""
    if any(e["event"] == "hook.error" for e in facts.get("events", [])):
        status = "invalid" if status == "ok" else status
        problems.append("hook.error in the session")
    check = facts.get("logCheck")
    if check is not None and check.get("tokenAbsent") is not True:
        problems.append(f"the request log holds the token: {check.get('problem', 'redaction')}")
    elif check is None and "mod" in facts:
        problems.append("the request log was not checked for the token")
    stray = [s for s in facts.get("stray", []) if s.get("ok") is False]
    if stray:
        codes = ", ".join(sorted({str((s.get("error") or {}).get("code")) for s in stray}))
        problems.append(
            f"the mod sent {len(stray)} answer(s) to no request of ours ({codes}): a line it "
            "could not read"
        )
    logged = facts.get("helperLog", {})
    if logged.get("hookFailures"):
        status = "invalid" if status == "ok" else status
        problems.append(f"the mod logged {logged['hookFailures']} hook failure(s) in latest.log")
    if logged.get("irisOutsideReload"):
        status = "invalid" if status == "ok" else status
        problems.append(
            f"Iris failed to load a pack outside shaders.reload ({logged['irisOutsideReload']} "
            "time(s) in latest.log): a view may have rendered without the pack"
        )
    quit_facts = facts.get("quit")
    if quit_facts is not None and quit_facts["exitCode"] != 0:
        problems.append(f"the session's quit exited {quit_facts['exitCode']}")
    if quit_facts is not None and quit_facts.get("pipeEnded") is False:
        problems.append(launch.UNREAD_END)
    if "readBack" in facts and not facts["readBack"]["ok"]:
        problems.append("the option files did not read back as written")
    if "A10" in items and not items["A10"]["pass"] and "A10" not in asked:
        problems.append("selftest failed at the session start")  # A10 holds at every start
    if facts.get("a4Cleanup", {}).get("kept"):
        problems.append(f"A4's copy was not deleted: {facts['a4Cleanup']['kept']}")
    if facts.get("filesCleanup", {}).get("kept"):  # an Optilux variant's zip and settings file
        problems.append(f"the run's files were not deleted: {facts['filesCleanup']['kept']}")
    if reloads and table is None:
        problems.append(f"F4's table of {reloads} reloads was not completed")
    acceptance = []
    for item in asked:
        found = items.get(item)
        if found is None:
            acceptance.append(
                {
                    "item": item,
                    "pass": False,
                    "evidence": {"notRun": problems[-1] if problems else "not run"},
                }
            )
            continue
        passed = found.pop("pass")
        acceptance.append({"item": item, "pass": passed, "evidence": found})
    # An item whose verdict waits (pass null: A5's first launch) has not failed.
    failed = [entry["item"] for entry in acceptance if entry["pass"] is False]
    if failed and status == "ok":
        status = "failed"
        problems.append(f"items failed: {', '.join(failed)}")
    elif problems and status == "ok":
        status = "failed"
    return status, acceptance


def framebuffer_size(state: dict) -> str:
    """`state`'s framebuffer, the main render target, as WIDTHxHEIGHT."""
    size = state.get("framebuffer")
    if not isinstance(size, dict):
        return repr(size)
    return f"{size.get('width')}x{size.get('height')}"


def framebuffer_refusal(state: dict, mode: str, resolution: str) -> str | None:
    """The render target against the display (plans/m2.md D38): `state`'s framebuffer, the size
    the game renders at, must equal the display mode the identity holds and suite.json's
    display.resolution; the refusal naming its fix, None when the three agree."""
    found = framebuffer_size(state)
    if found == mode == resolution:
        return None
    return (
        f"the game renders {found}, the display mode is {mode} and suite.json display.resolution "
        f"{resolution}; fix: the game exclusive fullscreen at the display's own mode (suite.json "
        "display.optionsTxt, no fullscreenResolution), the display set by you"
    )


def session_start(
    s: Session,
    pack: str,
    warmup: float,
    mode: str,
    resolution: str,
    facts: dict | None = None,
    before_reload: Callable[[], None] | None = None,
) -> dict:
    """mod-protocol.md#choreography's session start after hello: world.wait, state (its
    framebuffer refused unless equal to the display mode and suite.json's display.resolution,
    D38), selftest (A10; a failed one ends the session, c5), input.block on, hideGui, /tick
    freeze, ready, the start-of-run reload (after `before_reload`, which writes a measured run's
    baseline files), the GPU warm-up, then the pack's effective options (the variant fields).
    Each answer goes into `facts` as it comes, so a session that ends inside keeps them."""
    c = s.client
    facts = {} if facts is None else facts
    facts["joined"] = s.step(
        "world.wait",
        lambda: c.world_wait(WORLD_TIMEOUT),
        lambda a: f"{a['pose']['dimension']} at frame {a['frameIndex']}",
    )
    state = s.step(
        "state",
        c.state,
        lambda a: (
            f"{a['dimension']}, {a['gamemode']}, focused {a['focused']}, framebuffer "
            f"{framebuffer_size(a)}"
        ),
    )
    problem = framebuffer_refusal(state, mode, resolution)
    if problem is not None:
        raise RunError(f"state: {problem}")
    selftest = s.step(
        "selftest", lambda: c.selftest(SELFTEST_TIMEOUT), lambda a: f"pass {a['pass']}"
    )
    facts["selftest"] = selftest
    if selftest.get("pass") is not True:
        failed = [k for k, v in (selftest.get("checks") or {}).items() if v.get("pass") is not True]
        raise RunError(
            f"selftest failed at the session start ({', '.join(failed) or 'no check named'}): "
            "the session ends there (c5); fix: read the checks in the record"
        )
    s.step("input.block on", lambda: c.input_block(True))
    s.step("hud.set hideGui", lambda: c.hud_set(hide_gui=True))
    s.step(
        "command /tick freeze",
        lambda: c.command("/tick freeze", COMMAND_TIMEOUT),
        lambda a: "; ".join(a["messages"]),
    )
    s.step(
        "ready",
        lambda: c.ready(STABLE_FRAMES, 0.0, READY_TIMEOUT),
        lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
    )
    if before_reload is not None:
        before_reload()
    facts["reload"] = s.step(
        "shaders.reload",
        lambda: c.shaders_reload(RELOAD_TIMEOUT, 2, pack=pack),
        lambda a: f"{a['pack']} in {a['seconds']:.3f} s, reloadFrame {a['reloadFrame']}",
    )
    s.label = "warm-up"
    launch.hold(s.launched.process, s.host, warmup)
    s.stop_check(s.drain(), "warm-up")
    s.say(f"GPU warm-up: held {warmup:g} s (suite.json capture.gpuWarmupS)")
    facts["options"] = s.step(
        "shaders.options", c.shaders_options, lambda a: f"{len(a['values'])} values of {a['pack']}"
    )
    return facts


def set_time(c: modclient.Client, ticks: int) -> dict:
    """`/time set` at the overworld clock, run in the overworld: 26.3 sets the clock of the
    sender's dimension and the Nether has none ("There is no default clock in dimension
    minecraft:the_nether", 0.01.08's second run). 26.3 answers a failure when the clock already
    reads that value ("Clock minecraft:overworld is already set to 6000 tick(s)", the first run):
    the clock then holds the view's time, so that answer counts as done; any other is refused."""
    text = f"/execute in {OVERWORLD} run time set {ticks}"
    result = c.command(text, COMMAND_TIMEOUT, check=False)
    already = [f for f in result["failures"] if f"already set to {ticks} tick" in f]
    if result["succeeded"] is not True and not (
        already and len(already) == len(result["failures"])
    ):
        raise modclient.ModError(f"command {text}: {result['failures']}")
    return result


def visual_settle(capture: dict, view: dict, dimension_changed: bool) -> float:
    """A view's visual settle (measurement.md#readiness, suite.json capture.visualSettleS): its
    role's own (underwater's 2.0), else the default, plus the addition after a dimension change."""
    visual = capture["visualSettleS"]
    settle = visual.get(view["id"], visual["default"])
    return settle + (visual["addAfterDimensionChange"] if dimension_changed else 0.0)


def settle_view(
    s: Session, view: dict, weather: str | None, suite: dict, previous: str | None
) -> dict:
    """A view's time and weather (M2 writes them as a function), the exact pose, then ready with
    the visual settle: suite.json's for the view's role, else its default, plus its addition after
    a dimension change (from the joined dimension for the first view).
    capture.ticksAfterWeatherChange ticks are stepped after
    the weather when it changes (weather ramps only while ticking), and on the first view, where
    the world's weather is unknown (`weather` None); the time is set after them."""
    c = s.client
    capture = suite["capture"]
    s.step(
        f"{view['id']}: weather",
        lambda: c.command(f"/weather {view['weather']}"),
        lambda a: "; ".join(a["messages"]),
    )
    if weather != view["weather"]:
        n = capture["ticksAfterWeatherChange"]
        s.step(f"{view['id']}: ticks.step {n}", lambda: c.ticks_step(n, 60.0))
    s.step(
        f"{view['id']}: time",
        lambda: set_time(c, view["time"]),
        lambda a: "; ".join(a["messages"] + a["failures"]),
    )
    pose = view_pose(view)
    placed = s.step(
        f"{view['id']}: camera.place",
        lambda: c.camera_place(pose, PLACE_TIMEOUT),
        lambda a: f"arrived in {a['arrivedSeconds']:.2f} s",
    )
    problems = modclient.pose_differences(pose, placed["pose"])
    if problems:
        raise RunError(f"{view['id']}: camera.place answered {placed['pose']}: {problems}")
    settle = visual_settle(capture, view, previous != view["dim"])
    ready = s.step(
        f"{view['id']}: ready",
        lambda: c.ready(STABLE_FRAMES, settle, READY_TIMEOUT),
        lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
    )
    return {"placed": placed, "settleSeconds": settle, "ready": ready}


def in_front(s: Session, state: dict) -> bool:
    """The game reports focus and owns the foreground window."""
    return state["focused"] is True and s.host.foreground_pid() == s.launched.pid


def ensure_focus(s: Session, evidence: dict) -> dict:
    """The game's state, after bringing its window to the front when it is not (unfocused, or
    another process owns the foreground window): SetForegroundWindow, then one click at its centre
    (call it with input.block on: the click then activates the window and does nothing in game).
    The fallback's steps and the foreground window's pid go into `evidence`."""
    c = s.client
    state = c.state()
    if not in_front(s, state):
        fallback = [f"foreground pid {s.host.foreground_pid()}", s.host.focus(s.launched.pid)]
        time.sleep(1.0)
        state = c.state()
        if not in_front(s, state):
            fallback.append(s.host.click_focus(s.launched.pid))
            time.sleep(1.0)
            state = c.state()
        evidence["focusFallback"] = fallback
    evidence["foregroundPid"] = s.host.foreground_pid()
    return state


# A9.


def check_presentmon(root: Path) -> Path:
    """The pinned PresentMon under runtime/tools/, sha256-equal to config/tools.json's pin."""
    pin = json.loads((root / TOOLS).read_text(encoding="utf-8"))["presentmon"]
    exe = root / TOOLS_DIR / pin["file"]
    if not exe.is_file():
        raise record.RecordError(f"no {shown(exe, root)}; fix: run `optilux install`")
    digest = record.file_sha256(exe)
    if digest != pin["sha256"]:
        raise record.RecordError(
            f"{pin['file']} hashes {digest[:12]}..., its pin {pin['sha256'][:12]}...; fix: run "
            "`optilux install`"
        )
    return exe


def trim(facts: dict) -> dict:
    """A launch's facts for the record: the command's arguments counted, not listed (the spec
    and bench.json give them; the check is recorded)."""
    found = {key: value for key, value in facts.items() if key != "command"}
    found["command"] = {
        "check": facts["command"]["check"],
        "arguments": len(facts["command"]["arguments"]),
    }
    return found


# The run.


def load_spec(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise record.RecordError(f"cannot read {path}: {error}; fix: give a spec file") from None
    except ValueError as error:
        raise record.RecordError(f"{path.name} is not JSON ({error}); fix: repair it") from None
