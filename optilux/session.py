"""One game session as `run` drives it (docs/mod-protocol.md#choreography), and what M2's verbs
reuse: RunHost (the machine beyond launch's: pipes, jcmd, memory, SendInput, focus, PresentMon),
the Session (the client, the step log, the events), the session start, a view's time, weather and
pose, the focus checks before any injected input, the spec loader and the PresentMon pin check.
The acceptance items live in optilux/acceptance.py, the verb in optilux/verbs/run.py."""

import json
import os
import queue
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from optilux import launch, modclient, presentmon, record, sendinput
from optilux.verbs.install import TOOLS, TOOLS_DIR, Say, shown

REQUESTS = launch.REQUESTS


PIPES = "\\\\.\\pipe\\"


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


# Events that invalidate a capture (docs/mod-protocol.md#client-rules).
INVALIDATING = ("hook.error", "focus.lost", "screen.opened", "reload.done", "dimension.changed")


JCMD_TIMEOUT = 60


class RunError(RuntimeError):
    """A run that cannot go on; the message names the problem."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# The machine, beyond launch's.


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


# The session.


class Session:
    """One launched game with the mod connected: its steps, events and facts as they happen."""

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

    def step(self, name: str, call, show=None) -> Any:
        """Run one request, record its answer (or error) and the seconds, say it."""
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
        self.steps.append({"step": name, "answer": answer, "seconds": seconds})
        self.drain()
        self.say(f"{name}: {show(answer) if show else 'ok'} ({seconds:.2f} s)")
        return answer


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
    if "readBack" in facts and not facts["readBack"]["ok"]:
        problems.append("the option files did not read back as written")
    if "A10" in items and not items["A10"]["pass"] and "A10" not in asked:
        problems.append("selftest failed at the session start")  # A10 holds at every start
    if facts.get("a4Cleanup", {}).get("kept"):
        problems.append(f"A4's copy was not deleted: {facts['a4Cleanup']['kept']}")
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
    failed = [entry["item"] for entry in acceptance if not entry["pass"]]
    if failed and status == "ok":
        status = "failed"
        problems.append(f"items failed: {', '.join(failed)}")
    elif problems and status == "ok":
        status = "failed"
    return status, acceptance


def session_start(s: Session, pack: str, warmup: float) -> dict:
    """mod-protocol.md#choreography's session start after hello: world.wait, state, selftest
    (A10), input.block on, hideGui, /tick freeze, ready, the start-of-run reload, the GPU warm-up,
    then the pack's effective options (the variant fields)."""
    c = s.client
    joined = s.step(
        "world.wait",
        lambda: c.world_wait(WORLD_TIMEOUT),
        lambda a: f"{a['pose']['dimension']} at frame {a['frameIndex']}",
    )
    s.step("state", c.state, lambda a: f"{a['dimension']}, {a['gamemode']}, focused {a['focused']}")
    selftest = s.step(
        "selftest", lambda: c.selftest(SELFTEST_TIMEOUT), lambda a: f"pass {a['pass']}"
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
    reload = s.step(
        "shaders.reload",
        lambda: c.shaders_reload(RELOAD_TIMEOUT, 2, pack=pack),
        lambda a: f"{a['pack']} in {a['seconds']:.3f} s, reloadFrame {a['reloadFrame']}",
    )
    s.label = "warm-up"
    launch.hold(s.launched.process, s.host, warmup)
    s.drain()
    s.say(f"GPU warm-up: held {warmup:g} s (suite.json capture.gpuWarmupS)")
    options = s.step(
        "shaders.options", c.shaders_options, lambda a: f"{len(a['values'])} values of {a['pack']}"
    )
    return {"joined": joined, "selftest": selftest, "reload": reload, "options": options}


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
    visual = capture["visualSettleS"]
    settle = visual.get(view["id"], visual["default"])  # a role's own settle (underwater 2.0)
    if previous != view["dim"]:
        settle += capture["visualSettleS"]["addAfterDimensionChange"]
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
