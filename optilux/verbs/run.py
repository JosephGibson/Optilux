"""`optilux run <spec.json> [--json]` (docs/run-record.md#run-spec, docs/plans/m1.md 0.01.08 and
0.01.09).

An acceptance run: the spec checked (optilux/record.py, every refusal naming its fix), the live
world hash-checked against its snapshot and the display against the suite, then the announced
launches. The session launch runs the session start of docs/mod-protocol.md#choreography (A10
is its selftest). At the first view: A4 (a copy of the reference zip with one program broken,
selected for one reload that must answer iris-compile-error; the pack restored, reloaded, ready,
one frame), A7 (SendInput's key and mouse motion with input.block off open a screen and turn the
camera; blocked, they change nothing; unblocked again, the motion turns it), A9 (120 frames
captured inside one PresentMon run, their stamps matched to its rows by order). Then per view A2
(a capture with F2 pressed inside it through SendInput; the new screenshot must equal one
captured frame byte for byte; a miss is kept and retaken once) and A3 (`/tp` through `command`
against camera.place with tpSemantics, both read back), F4's reload table (`reloads` in the
spec: heap after GC and private bytes every 10 reloads), then `input.block off` and `quit`. A1's
launch starts without the token and never connects: the pipe list holds no optilux- pipe,
latest.log no applied mixin and no active line, the JVM's thread dump no optilux- thread;
WM_CLOSE ends it. The record goes to results/records/<name>.json, the request log and the raw
artifacts to results/raw/<name>/. Exit 0 when every item passed.
"""

import argparse
import contextlib
import hashlib
import json
import math
import os
import queue
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from optilux import REPO_ROOT, launch, modclient, platform, presentmon, record, repo, sendinput
from optilux.verbs import Verb
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, TOOLS, TOOLS_DIR, Say, shown

PREFIX = "optilux run"
REQUESTS = "requests.jsonl"
SCREENSHOTS = "screenshots"
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

# A2 (docs/mod.md#12-acceptance): unmodified Unbound never renders two equal frames (TAA and its
# wall-clock animation: 0.01.07's frames 975-977 and 0.01.08's 24-frame rehearsals all differed),
# so F2 is pressed inside one capture of A2_FRAMES frames, A2_LEAD frames after it began, and the
# screenshot F2 writes must equal one captured frame. The rehearsal's match came 7 frames in; the
# mod stalls the render thread at 16 pending frames, so the later frames leave F2 time to land.
A2_FRAMES = 24
A2_LEAD = 6
A2_LEAD_TIMEOUT = 10.0
A2_CAPTURE_TIMEOUT = 120.0
A2_ATTEMPTS = 2
SCREENSHOT_TIMEOUT = 15.0
# A PNG ends with its IEND chunk: the screenshot is complete once its bytes end so.
PNG_END = b"IEND\xaeB`\x82"
# Events that invalidate a capture (docs/mod-protocol.md#client-rules).
INVALIDATING = ("hook.error", "focus.lost", "screen.opened", "reload.done", "dimension.changed")
# A3: after `/tp` the client holds the new pose a frame or two later; two equal reads in a row
# end the wait.
TP_TIMEOUT = 10.0
TP_POLL = 0.05

# A1: the helper's own log lines (mod/src/main/java/optilux/helper/HelperClient.java and
# MixinGate.java) and its thread names (Session.java: optilux-pipe, -worker-N, -timer-N, -writer-N).
INERT = "optilux-helper: inert ("
ACTIVE = "optilux-helper: active:"
APPLIED = re.compile(r"optilux-helper: mixin \S+ applied to ")
DECLINED = re.compile(r"optilux-helper: mixin \S+ not applied to \S+: inert")
MOD_THREAD = "optilux-"
JCMD_TIMEOUT = 60
THREAD_LINE = re.compile(r'^"(?P<name>[^"]*)"')

# A4 (docs/mod.md#12-acceptance, plans/m1.md D25): a copy of the reference zip under
# shaderpacks/ with one program made invalid, selected through iris.properties for one reload and
# deleted after the session; the reference zip itself is never touched.
A4_PREFIX = "optilux-a4-broken-"
# The overworld's final pass: Unbound's shaders/dimension.properties maps every dimension but the
# Nether and the End to world0, and A4 runs at the first view, an overworld one.
A4_PROGRAM = "shaders/world0/final.fsh"
A4_IDENTIFIER = "optiluxA4Undeclared"
A4_BODY = (
    "#version 130\n\n"
    "// optilux A4 (docs/plans/m1.md D25): broken on purpose; the compiler must refuse it.\n"
    f"void main() {{\n    gl_FragData[0] = vec4({A4_IDENTIFIER});\n}}\n"
).encode("ascii")
A4_CAPTURE_TIMEOUT = 60.0

# A7 (docs/mod.md#12-acceptance, plans/m1.md D24): one SendInput mouse motion (0.01.06's 300
# counts turned the yaw 45 degrees) and the chat key; an effect shows within frames, so a check
# polls for A7_WAIT; the blocked arm holds at least A7_HOLD_FRAMES and A7_HOLD_SECONDS for an
# effect that must not come.
A7_DX = 200
A7_DY = 100
A7_WAIT = 3.0
A7_POLL = 0.05
A7_HOLD_FRAMES = 60
A7_HOLD_SECONDS = 1.5
# MouseHandler.grabMouse sets ignoreFirstMove and onMove drops the first motion after it (read in
# the 26.3 jar, 0.01.09: m1-acceptance-4's control motion right after the grab moved nothing, the
# same motion later turned the camera), so the control primes the grab with one motion first.
A7_PRIME_WAIT = 1.0
CHAT_SCREEN = "net.minecraft.client.gui.screens.ChatScreen"
# The state fields A7's blocked arm compares: commands.json's state result without the server tick
# (every answer also carries frameIndex, sinceReload and qpcNs, which move with each frame).
STATE_KEYS = ("inWorld", "dimension", "gamemode", "screen", "paused", "focused")

# A9 (docs/mod.md#12-acceptance, plans/m1.md D26): 120 frames, every one, inside one PresentMon
# run; the PNGs are deleted after the manifest is verified (2 GB at 4K; the record keeps the
# stamps and capture.json keeps the hashes).
A9_FRAMES = 120
A9_CAPTURE_TIMEOUT = 120.0
# After the capture: the CSV must reach a row past the last stamp (rows arrive in ETW's buffers).
A9_COVER_TIMEOUT = 30.0

# F4 stops (and fails) before a reload when the machine's available memory is under this: the
# spike's dev tier grew 320 MiB of private bytes per reload, and this machine has 32 GiB.
F4_MIN_AVAILABLE = 2 * 1024**3
# F4 (roadmap.md#findings-assigned): `jcmd <pid> GC.run`, then GC.heap_info's heap line, e.g.
# "garbage-first heap   total reserved 6291456K, committed 6291456K, used 23182K [0x..."
# (Temurin 25, tests/fixtures/run/gc-heap-info.txt).
HEAP_LINE = re.compile(
    r"^\s*(?P<heap>[\w-]+(?: [\w-]+)* heap)\s+total (?:reserved )?(?P<reserved>\d+)K, "
    r"(?:committed (?P<committed>\d+)K, )?used (?P<used>\d+)K"
)
METASPACE_LINE = re.compile(r"^\s*Metaspace\s+used (?P<used>\d+)K, committed (?P<committed>\d+)K")
MIB = 1024 * 1024


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
        done = subprocess.run(
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


def thread_names(dump: str) -> list[str]:
    """The thread names of a `jcmd <pid> Thread.print` dump."""
    return [m.group("name") for line in dump.splitlines() if (m := THREAD_LINE.match(line))]


def helper_lines(log: str) -> dict:
    """The helper's inert, active and mixin lines in a latest.log."""
    lines = [line for line in log.splitlines() if "optilux-helper" in line]
    return {
        "inert": [line for line in lines if INERT in line],
        "active": [line for line in lines if ACTIVE in line],
        "applied": [line for line in lines if APPLIED.search(line)],
        "declined": [line for line in lines if DECLINED.search(line)],
    }


def png_size(data: bytes) -> tuple[int, int] | None:
    """A PNG's width and height from its IHDR."""
    if not data.startswith(modclient.PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def literal(value: float | int) -> str:
    """A number as `/tp` reads it: an int without a decimal point (the block-centre rule), a
    float with one."""
    return str(value) if isinstance(value, int) else repr(float(value))


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
    the visual settle: suite.json's default, plus its addition after a dimension change (from the
    joined dimension for the first view). capture.ticksAfterWeatherChange ticks are stepped after
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
    settle = capture["visualSettleS"]["default"]
    if previous != view["dim"]:
        settle += capture["visualSettleS"]["addAfterDimensionChange"]
    ready = s.step(
        f"{view['id']}: ready",
        lambda: c.ready(STABLE_FRAMES, settle, READY_TIMEOUT),
        lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
    )
    return {"placed": placed, "settleSeconds": settle, "ready": ready}


def listing(folder: Path) -> set[str]:
    return {p.name for p in folder.glob("*.png")} if folder.is_dir() else set()


def new_screenshot(folder: Path, before: set[str]) -> Path | None:
    """The newest screenshot written since `before`, once its PNG is complete."""
    deadline = time.monotonic() + SCREENSHOT_TIMEOUT
    while time.monotonic() < deadline:
        fresh = [folder / name for name in listing(folder) - before]
        if fresh:
            path = max(fresh, key=lambda p: (p.stat().st_mtime_ns, p.name))
            with contextlib.suppress(OSError):
                if path.read_bytes().endswith(PNG_END):
                    return path
        time.sleep(0.2)
    return None


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


def a2_attempt(s: Session, view: dict, attempt: int, resolution: str) -> dict:
    """One A2 attempt at the placed view: input.block off, a capture of A2_FRAMES frames, F2
    through SendInput A2_LEAD frames into it, input.block on; the new screenshot against every
    captured frame; the pose and the events checked after."""
    c = s.client
    folder = s.raw / "a2" / view["id"]
    shots = s.launched.game / SCREENSHOTS
    s.label = f"{view['id']}: A2 attempt {attempt}"
    evidence: dict[str, Any] = {"attempt": attempt}
    state = ensure_focus(s, evidence)
    evidence.update(focused=state["focused"], screen=state["screen"])
    if not state["focused"] or state["screen"] is not None:
        evidence["problem"] = "the game is not focused or a screen is open"
        return {**evidence, "pass": False}
    s.drain()
    mark = len(s.events)
    before = listing(shots)
    box: dict[str, Any] = {}

    def capture() -> None:
        try:
            box["result"] = c.frames_capture(folder, A2_FRAMES, A2_CAPTURE_TIMEOUT, every=1)
        except (modclient.ModError, ValueError, OSError) as error:
            box["error"] = str(error)

    worker = threading.Thread(target=capture, name="optilux-a2-capture")
    c.input_block(False)
    try:
        first = c.request("frames.index")["frameIndex"]
        worker.start()
        deadline = time.monotonic() + A2_LEAD_TIMEOUT
        reached = first
        while reached < first + A2_LEAD and time.monotonic() < deadline:
            time.sleep(0.002)
            reached = c.request("frames.index")["frameIndex"]
        pressed = c.state()
        # SendInput goes to whatever window is in front: F2 only while the game holds focus.
        sent = s.host.key_press(sendinput.VK_F2, sendinput.SCAN_F2) if pressed["focused"] else 0
        after = c.request("frames.index")["frameIndex"]
        worker.join(A2_CAPTURE_TIMEOUT + 2 * modclient.MARGIN)
    except BaseException:
        # The capture holds its resource until it ends, and input.block answers busy until then:
        # the cleanup waits for it and never replaces the error that ended the attempt.
        with contextlib.suppress(Exception):
            if worker.is_alive():
                worker.join(A2_CAPTURE_TIMEOUT + 2 * modclient.MARGIN)
            c.input_block(True)
        raise
    c.input_block(True)
    evidence.update(
        frameBefore=first,
        frameAtPress=reached,
        frameAfterPress=after,
        focusedAtPress=pressed["focused"],
        sendInput={"sent": 2 if pressed["focused"] else 0, "inserted": sent},
    )
    if not pressed["focused"]:
        evidence["problem"] = "the game lost focus before the press; F2 was not sent"
    if "result" not in box:
        evidence["problem"] = f"the capture failed: {box.get('error', 'no answer')}"
        return {**evidence, "pass": False}
    result = box["result"]
    frames = result["frames"]
    evidence["capture"] = {
        "folder": shown(Path(result["verified"]["folder"]), s.root),
        "frames": [{"frameIndex": f["frameIndex"], "sha256": f["sha256"]} for f in frames],
        "distinct": len({f["sha256"] for f in frames}),
        "dropped": result["dropped"],
        "complete": result["verified"]["complete"],
    }
    shot = new_screenshot(shots, before)
    pose = c.camera_get()["pose"]
    s.drain()
    bad = [e for e in s.events[mark:] if e["event"] in INVALIDATING]
    evidence["poseAfter"] = pose
    evidence["poseDifferences"] = modclient.pose_differences(view_pose(view), pose)
    evidence["invalidatingEvents"] = bad
    if shot is None:
        evidence["problem"] = f"no new screenshot in {SCREENSHOT_TIMEOUT:g} s"
        return {**evidence, "pass": False}
    data = shot.read_bytes()
    kept = folder / "f2" / f"attempt-{attempt}-{shot.name}"
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(shot, kept)
    digest = hashlib.sha256(data).hexdigest()
    size = png_size(data)
    matches = [f["frameIndex"] for f in frames if f["sha256"] == digest]
    evidence["screenshot"] = {
        "file": f"{SCREENSHOTS}/{shot.name}",
        "kept": shown(kept, s.root),
        "sha256": digest,
        "bytes": len(data),
        "size": f"{size[0]}x{size[1]}" if size else None,
    }
    evidence["matches"] = matches
    passed = (
        sent == 2
        and pressed["focused"] is True
        and bool(matches)
        and not bad
        and not evidence["poseDifferences"]
        and evidence["screenshot"]["size"] == resolution
    )
    return {**evidence, "pass": passed}


def a2(s: Session, view: dict, resolution: str, settle: float) -> dict:
    """A2 at one view: an attempt, and on a miss one retake from the view placed and settled
    again, the missed files kept (lessons.md#determinism)."""
    attempts = []
    pose = view_pose(view)
    for attempt in range(1, A2_ATTEMPTS + 1):
        if attempt > 1:
            s.step(
                f"{view['id']}: A2 retake camera.place",
                lambda: s.client.camera_place(pose, PLACE_TIMEOUT),
            )
            s.step(
                f"{view['id']}: A2 retake ready",
                lambda: s.client.ready(STABLE_FRAMES, settle, READY_TIMEOUT),
            )
        found = a2_attempt(s, view, attempt, resolution)
        attempts.append(found)
        shot = found.get("screenshot", {}).get("file")
        s.say(
            f"{view['id']}: A2 attempt {attempt}: {'pass' if found['pass'] else 'miss'}; F2 "
            f"{shot or 'wrote nothing'}; matches frame {found.get('matches') or 'none'} of "
            f"{found.get('capture', {}).get('distinct', 0)} distinct"
        )
        if found["pass"]:
            break
    return {"view": view["id"], "pass": attempts[-1]["pass"], "attempts": attempts}


def wait_moved(c: modclient.Client, away: dict) -> dict:
    """The client's pose once it left `away` and two reads in a row agree (the /tp has landed)."""
    deadline = time.monotonic() + TP_TIMEOUT
    last = None
    while time.monotonic() < deadline:
        pose = c.camera_get()["pose"]
        if pose == last and modclient.pose_differences(away, pose):
            return pose
        last = pose
        time.sleep(TP_POLL)
    raise RunError(f"/tp: the client still held {last} after {TP_TIMEOUT:g} s")


def a3(s: Session, view: dict) -> dict:
    """A3 at one view: two probes (integer x and z with yaw 180: the centre correction and the
    wrap; the view's own pose with yaw + 360: the wrap alone), each sent once as `/tp` through
    `command` and once as camera.place with tpSemantics from the same spot, both read back with
    camera.get; the poses must be equal (yaw and pitch at float precision)."""
    c = s.client
    dim = view["dim"]
    away = {**view_pose(view), "y": view["y"] + 3.0}
    probes = {
        "centre": {
            "x": math.floor(view["x"]) + 1,
            "y": view["y"] + 1.0,
            "z": math.floor(view["z"]) + 1,
            "yaw": 180,
            "pitch": view["pitch"],
        },
        "wrap": {
            "x": view["x"],
            "y": view["y"],
            "z": view["z"],
            "yaw": view["yaw"] + 360.0,
            "pitch": view["pitch"],
        },
    }
    found = []
    for name, probe in probes.items():
        s.label = f"{view['id']}: A3 {name}"
        args = " ".join(literal(probe[key]) for key in ("x", "y", "z", "yaw", "pitch"))
        text = f"/execute in {dim} run tp @s {args}"
        try:
            c.camera_place(away, PLACE_TIMEOUT)
            feedback = c.command(text, COMMAND_TIMEOUT)
            by_tp = wait_moved(c, away)
            c.camera_place(away, PLACE_TIMEOUT)
            placed = c.camera_place({"dimension": dim, **probe}, PLACE_TIMEOUT, tp_semantics=True)
            read = c.camera_get()["pose"]
        except (modclient.ModError, RunError) as error:
            found.append(
                {"probe": name, "sent": probe, "command": text, "error": str(error), "pass": False}
            )
            s.say(f"{view['id']}: A3 {name}: failed: {error}")
            continue
        differences = modclient.pose_differences(by_tp, placed["pose"])
        differences += modclient.pose_differences(placed["pose"], read)
        found.append(
            {
                "probe": name,
                "sent": probe,
                "command": text,
                "feedback": feedback["messages"],
                "tp": by_tp,
                "placed": placed["pose"],
                "read": read,
                "differences": differences,
                "pass": not differences,
            }
        )
        s.say(
            f"{view['id']}: A3 {name}: /tp gave {by_tp}, camera.place {read}: "
            f"{'equal' if not differences else differences}"
        )
    s.drain()
    return {"view": view["id"], "pass": all(p["pass"] for p in found), "probes": found}


# A4.


def write_broken_pack(source: Path, target: Path, program: str, body: bytes) -> dict:
    """A copy of the zip `source` at `target` (new) with entry `program`'s bytes replaced by
    `body`, every other entry copied as it was (name, order, date, compression, bytes); the facts:
    the program, the sha256 of its old and new bytes, the entry count, the copy's sha256 and size.
    RunError when the target exists or the program is no entry of the zip."""
    if target.exists():
        raise RunError(f"{target} exists; fix: delete it (a copy an earlier A4 left behind)")
    with zipfile.ZipFile(source) as packed:
        names = packed.namelist()
        if program not in names:
            raise RunError(f"{source.name} holds no {program}; fix: name a program it has")
        original = packed.read(program)
        with zipfile.ZipFile(target, "x") as out:
            for info in packed.infolist():
                entry = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                entry.compress_type = info.compress_type
                entry.external_attr = info.external_attr
                entry.create_system = info.create_system
                out.writestr(entry, body if info.filename == program else packed.read(info))
    return {
        "file": target.name,
        "program": program,
        "originalSha256": hashlib.sha256(original).hexdigest(),
        "brokenSha256": hashlib.sha256(body).hexdigest(),
        "entries": len(names),
        "sha256": record.file_sha256(target),
        "bytes": target.stat().st_size,
    }


def broken_copies(game: Path) -> list[Path]:
    return sorted((game / launch.SHADER_PACKS).glob(f"{A4_PREFIX}*"))


def remove_broken(game: Path) -> dict:
    """A4's copies (and a settings file Iris may have written beside one) deleted after the game
    exited: the names removed, and those that could not be."""
    removed, kept = [], []
    for path in broken_copies(game):
        try:
            path.unlink()
            removed.append(path.name)
        except OSError as error:
            kept.append(f"{path.name}: {error}")
    return {"removed": removed, "kept": kept}


def a4(s: Session, evidence: dict) -> None:
    """A4 at the placed overworld view, its evidence filled as it goes and `pass` set last: the
    broken copy written beside the reference zip; iris.properties names it and shaders.reload must
    answer iris-compile-error with a message; iris.properties is then written back as launch
    wrote it, and the recovery must hold: shaders.reload loads the reference pack's pipeline,
    `ready` holds, one frame is captured."""
    c = s.client
    game = s.launched.game
    good = dict(s.launched.prelaunch.iris)
    pack = good["shaderPack"]
    packs = game / launch.SHADER_PACKS
    s.label = "A4"
    state = c.state()
    evidence["dimension"] = state["dimension"]
    if state["dimension"] != OVERWORLD:
        evidence["problem"] = (
            f"{A4_PROGRAM} is the overworld's; the game is in {state['dimension']}"
        )
        return
    target = packs / f"{A4_PREFIX}{pack}"
    evidence["brokenPack"] = write_broken_pack(packs / pack, target, A4_PROGRAM, A4_BODY)
    s.say(
        f"A4: wrote shaderpacks/{target.name}: {A4_PROGRAM} replaced by {len(A4_BODY)} bytes "
        f"using the undeclared {A4_IDENTIFIER}"
    )
    iris = game / launch.IRIS
    s.drain()
    mark = len(s.events)
    s.label = "A4 broken reload"
    began = time.monotonic()
    iris.write_bytes(launch.iris_text({**good, "shaderPack": target.name}).encode("utf-8"))
    try:
        broken: dict[str, Any] = {"answer": c.shaders_reload(RELOAD_TIMEOUT, 2)}
    except modclient.ModRefused as error:
        broken = {"code": error.code, "message": error.message}
    finally:
        iris.write_bytes(launch.iris_text(good).encode("utf-8"))
    broken["seconds"] = round(time.monotonic() - began, 3)
    s.steps.append({"step": "A4 broken reload", **broken})
    s.drain()
    message = broken.get("message") or ""
    s.say(
        f"A4 broken reload: {broken.get('code', 'answered ok')} in {broken['seconds']:.2f} s: "
        f"{message[:160]!r}"
    )
    evidence.update(
        brokenReload=broken,
        namesProgram="final" in message,
        namesIdentifier=A4_IDENTIFIER in message,
        irisRestored=launch.properties_values(iris.read_text(encoding="utf-8")) == good,
    )
    recovery = s.step(
        "A4 recovery shaders.reload",
        lambda: c.shaders_reload(RELOAD_TIMEOUT, 2, pack=pack),
        lambda a: f"{a['pack']} ({a['pipeline']}) in {a['seconds']:.3f} s",
    )
    ready = s.step(
        "A4 ready",
        lambda: c.ready(STABLE_FRAMES, 0.0, READY_TIMEOUT),
        lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
    )
    shot = s.step(
        "A4 one frame",
        lambda: c.frames_capture(s.raw / "a4", 1, A4_CAPTURE_TIMEOUT, every=1),
        lambda a: f"frame {a['frames'][0]['frameIndex'] if a['frames'] else 'none'}",
    )
    s.drain()
    kinds = ("reload.failed", "reload.done", "screen.opened", "hook.error")
    events = [e for e in s.events[mark:] if e["event"] in kinds]
    frames = shot["frames"]
    evidence.update(
        recovery=recovery,
        ready={key: ready[key] for key in ("seconds", "limitedBy") if key in ready},
        frame={
            "folder": shown(Path(shot["verified"]["folder"]), s.root),
            "complete": shot["verified"]["complete"],
            "frames": [
                {key: f[key] for key in ("frameIndex", "sinceReload", "sha256")} for f in frames
            ],
        },
        events=events,
    )
    evidence["pass"] = (
        broken.get("code") == "iris-compile-error"
        and (evidence["namesProgram"] or evidence["namesIdentifier"])
        and evidence["irisRestored"] is True
        and recovery["pack"] == pack
        and recovery["pipeline"] not in (None, "VanillaRenderingPipeline")
        and shot["verified"]["complete"] is True
        and len(frames) == 1
        and any(e["event"] == "reload.failed" for e in events)
        and not any(e["event"] in ("screen.opened", "hook.error") for e in events)
    )
    s.say(f"A4: {'pass' if evidence['pass'] else 'fail'}")


# A7.


def wait_for(check, timeout: float = A7_WAIT) -> Any:
    """`check()` polled until it returns a truthy value or `timeout` passes; its last value."""
    deadline = time.monotonic() + timeout
    while True:
        found = check()
        if found or time.monotonic() >= deadline:
            return found
        time.sleep(A7_POLL)


def turned(c: modclient.Client, before: dict, timeout: float = A7_WAIT) -> dict | None:
    """The camera's pose once it left `before` and two reads in a row agree; None if it stayed."""
    last = None

    def check() -> dict | None:
        nonlocal last
        pose = c.camera_get()["pose"]
        moved = pose == last and bool(modclient.pose_differences(before, pose))
        last = pose
        return pose if moved else None

    return wait_for(check, timeout)


def inject(s: Session, what: str, send) -> dict:
    """One injection, sent only while `state.focused` holds and the foreground window is the
    game's (SendInput reaches whatever window is in front; in m1-acceptance-6 a T sent with
    `focused` true opened nothing): focused, the foreground window's pid, then the count SendInput
    inserted."""
    focused = s.client.state()["focused"]
    foreground = s.host.foreground_pid()
    ours = focused is True and foreground == s.launched.pid
    return {
        "what": what,
        "focused": focused,
        "foregroundPid": foreground,
        "inserted": send() if ours else 0,
    }


def close_screen(s: Session, escape) -> dict | None:
    """A screen still open after A7 (a failed path: T opened chat and no Escape followed) closed
    with Escape while input.block is off for it, so later items start without it; None when no
    screen was open."""
    c = s.client
    screen = c.state()["screen"]
    if screen is None:
        return None
    try:
        c.input_block(False)
        sent = inject(s, "Escape", escape)
        closed = wait_for(lambda: c.state()["screen"] is None)
    finally:
        c.input_block(True)
    return {"screen": screen, "escape": sent, "closed": closed}


def a7(s: Session, view: dict, evidence: dict) -> None:
    """A7 at the placed view, its evidence filled as it goes and `pass` set last (plans/m1.md
    0.01.09, D24: one session, one input path). The positive control with input.block off: T opens
    the chat screen, Escape closes it (which grabs the mouse), one motion primes the grab (the game
    drops the first motion after a grab; whether it turned is recorded), the next turns the camera.
    Blocked: the same motion and key change neither camera.get nor state, and open no screen
    over A7_HOLD_FRAMES. Unblocked again, the same motion turns the camera: the grab held through
    the blocked arm. Every injection needs state.focused true before it and SendInput's count
    equal to the events sent; the pose is restored after."""
    c = s.client
    host = s.host
    s.label = "A7"
    state = ensure_focus(s, evidence)  # input.block is on: a fallback click does nothing in game
    evidence["start"] = state
    if not in_front(s, state) or state["screen"] is not None:
        evidence["problem"] = "the game is not in front or a screen is open"
        return
    s.drain()
    mark = len(s.events)

    def key() -> int:
        return host.key_press(sendinput.VK_T, sendinput.SCAN_T)

    def escape() -> int:
        return host.key_press(sendinput.VK_ESCAPE, sendinput.SCAN_ESCAPE)

    def move() -> int:
        return host.mouse_move(A7_DX, A7_DY)

    motion = f"mouse ({A7_DX}, {A7_DY})"
    control: dict[str, Any] = {}
    blocked: dict[str, Any] = {}
    after: dict[str, Any] = {}
    evidence.update(control=control, blocked=blocked, afterControl=after)
    try:
        s.label = "A7 control"
        c.input_block(False)
        control["key"] = inject(s, "T", key)
        control["screen"] = wait_for(lambda: c.state()["screen"])
        if control["screen"]:
            control["escape"] = inject(s, "Escape", escape)
            control["closed"] = wait_for(lambda: c.state()["screen"] is None)
        # The closing screen grabbed the mouse, and the game drops the first motion after a grab.
        primed = c.camera_get()["pose"]
        control["prime"] = inject(s, motion, move)
        control["primeTurned"] = turned(c, primed, A7_PRIME_WAIT)
        before = c.camera_get()["pose"]
        control["mouse"] = inject(s, motion, move)
        control.update(poseBefore=before, poseAfter=turned(c, before))
        s.say(
            f"A7 control: T opened {control['screen']}; {motion} turned the camera to "
            f"{control['poseAfter']}"
        )
        s.label = "A7 blocked"
        c.input_block(True)
        s.drain()
        held = len(s.events)
        state_before = c.state()
        pose_before = c.camera_get()["pose"]
        first = c.request("frames.index")["frameIndex"]
        blocked["mouse"] = inject(s, motion, move)
        blocked["key"] = inject(s, "T", key)
        began = time.monotonic()
        frame = first
        while time.monotonic() - began < max(A7_HOLD_SECONDS, 30.0):
            frame = c.request("frames.index")["frameIndex"]
            if frame - first >= A7_HOLD_FRAMES and time.monotonic() - began >= A7_HOLD_SECONDS:
                break
            time.sleep(A7_POLL)
        state_after = c.state()
        pose_after = c.camera_get()["pose"]
        s.drain()
        blocked.update(
            stateBefore=state_before,
            stateAfter=state_after,
            stateChanged={
                key: [state_before[key], state_after[key]]
                for key in STATE_KEYS
                if state_before[key] != state_after[key]
            },
            poseBefore=pose_before,
            poseAfter=pose_after,
            poseChanged=pose_after != pose_before,
            framesHeld=frame - first,
            secondsHeld=round(time.monotonic() - began, 3),
            screensOpened=[e for e in s.events[held:] if e["event"] == "screen.opened"],
        )
        s.say(
            f"A7 blocked: {blocked['framesHeld']} frames held; pose changed "
            f"{blocked['poseChanged']}, state changed {blocked['stateChanged'] or 'nothing'}, "
            f"screens {len(blocked['screensOpened'])}"
        )
        s.label = "A7 after"
        c.input_block(False)
        before = c.camera_get()["pose"]
        after["mouse"] = inject(s, motion, move)
        after.update(poseBefore=before, poseAfter=turned(c, before))
    except BaseException:
        with contextlib.suppress(Exception):
            c.input_block(True)
        raise
    c.input_block(True)
    s.say(f"A7 after: {motion} turned the camera to {after['poseAfter']}")
    evidence["closedAtEnd"] = close_screen(s, escape)
    s.step(
        f"{view['id']}: A7 camera.place back",
        lambda: c.camera_place(view_pose(view), PLACE_TIMEOUT),
    )
    s.drain()
    bad = [e for e in s.events[mark:] if e["event"] in ("focus.lost", "hook.error")]
    evidence["invalidatingEvents"] = bad

    def sent(entry: dict | None, count: int) -> bool:
        return bool(entry) and entry["focused"] is True and entry["inserted"] == count

    control_ok = (
        sent(control.get("key"), 2)
        and control["screen"] == CHAT_SCREEN
        and sent(control.get("escape"), 2)
        and control.get("closed") is True
        and sent(control.get("prime"), 1)
        and sent(control.get("mouse"), 1)
        and control.get("poseAfter") is not None
    )
    blocked_ok = (
        sent(blocked.get("mouse"), 1)
        and sent(blocked.get("key"), 2)
        and blocked["poseChanged"] is False
        and not blocked["stateChanged"]
        and not blocked["screensOpened"]
        and blocked["framesHeld"] >= A7_HOLD_FRAMES
    )
    after_ok = sent(after.get("mouse"), 1) and after.get("poseAfter") is not None
    evidence.update(controlPassed=control_ok, blockedPassed=blocked_ok, afterPassed=after_ok)
    evidence["pass"] = control_ok and blocked_ok and after_ok and not bad
    s.say(
        f"A7: {'pass' if evidence['pass'] else 'fail'} (control {control_ok}, blocked "
        f"{blocked_ok}, after {after_ok}, invalidating events {len(bad)})"
    )


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


def delete_pngs(folder: Path) -> int:
    """The captured frames under `folder` deleted; how many."""
    pngs = sorted(folder.rglob("frame-*.png")) if folder.is_dir() else []
    for png in pngs:
        png.unlink(missing_ok=True)
    return len(pngs)


def a9(s: Session, exe: Path, session: str, evidence: dict) -> None:
    """A9 at the placed view, its evidence filled as it goes and `pass` set last: PresentMon
    started on the game; once its CSV holds rows, A9_FRAMES frames captured with every 1; once a
    row lies past the last stamp, PresentMon stopped (CTRL_BREAK_EVENT) and its ETW session gone;
    the game's rows matched to the stamps (presentmon.a9_match: both offsets, the pass on the swap
    stamp). A PresentMon that dies or must be killed fails the run (RunError). The PNGs are
    deleted after the match; capture.json and the CSV stay under raw/a9/."""
    c = s.client
    pm = s.host.presentmon()
    pid = s.launched.pid
    folder = s.raw / "a9"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / "presentmon.csv"
    s.label = "A9"
    try:
        found = presentmon.start(exe, pid, output, session, pm)
    except presentmon.PresentMonError as error:
        evidence["problem"] = str(error)
        raise RunError(f"A9: {error}") from None
    try:
        try:
            arguments = found.command[1:]
            evidence["presentmon"] = {
                "exe": exe.name,
                "arguments": [shown(output, s.root) if a == str(output) else a for a in arguments],
                "session": session,
            }
            s.say(f"A9: PresentMon recording pid {pid} as {session} into {shown(output, s.root)}")
            rows = presentmon.wait_rows(found, pm, None, presentmon.FIRST_ROW_TIMEOUT)
            evidence["firstRows"] = {"rows": rows, "seconds": round(pm.clock() - found.started, 2)}
            s.say(f"A9: first rows after {evidence['firstRows']['seconds']:.1f} s")
            shot = s.step(
                "A9 frames.capture",
                lambda: c.frames_capture(folder / "frames", A9_FRAMES, A9_CAPTURE_TIMEOUT, every=1),
                lambda a: f"{len(a['frames'])} frames, {len(a['dropped'])} dropped",
            )
            last = max(f["qpcNs"] for f in shot["frames"]) if shot["frames"] else 0
            evidence["cover"] = presentmon.wait_rows(found, pm, last, A9_COVER_TIMEOUT)
        except BaseException as error:
            try:
                evidence["stop"] = presentmon.stop(found, pm)
            except presentmon.PresentMonError as stopped:
                evidence["stopProblem"] = str(stopped)
            if isinstance(error, presentmon.PresentMonError) or (
                isinstance(error, Exception) and "stopProblem" in evidence
            ):
                evidence["problem"] = str(error)
                more = f"; the stop: {evidence['stopProblem']}" if "stopProblem" in evidence else ""
                raise RunError(f"A9: {error}{more}") from None
            raise
        try:
            evidence["stop"] = presentmon.stop(found, pm)
        except presentmon.PresentMonError as error:
            evidence["problem"] = str(error)
            raise RunError(f"A9: {error}") from None
    finally:
        # A9_FRAMES 4K PNGs (about 2 GB); capture.json keeps their hashes.
        evidence["pngsDeleted"] = delete_pngs(folder / "frames")
    left = [name for name in launch.etw_sessions(s.host.logman()) if name == session]
    header, rows_all = presentmon.read_rows(output, complete=True)
    mine = [row for row in rows_all if row.get(presentmon.PROCESS_ID) == str(pid)]
    match = presentmon.a9_match(mine, shot["frames"])
    evidence.update(
        sessionLeft=left,
        csv={
            "file": shown(output, s.root),
            "columns": len(header),
            "rows": len(rows_all),
            "gameRows": len(mine),
            "sha256": record.file_sha256(output),
        },
        capture={
            "manifest": shown(Path(shot["manifest"]), s.root),
            "complete": shot["verified"]["complete"],
            "dropped": shot["dropped"],
        },
        match=match,
    )
    evidence["pass"] = (
        match["pass"] is True
        and shot["verified"]["complete"] is True
        and evidence["stop"]["exitCode"] == 0
        and not left
    )
    head, swap = match.get("headOffsetMs", {}), match.get("swapOffsetMs", {})
    s.say(
        f"A9: {'pass' if evidence['pass'] else 'fail'}: {match['spanRows']} rows in the span for "
        f"{match['frames']} stamps; swap offset median {swap.get('median')} ms, max size "
        f"{swap.get('absMax')} ms; head offset median {head.get('median')} ms, max size "
        f"{head.get('absMax')} ms; {match.get('problem') or 'matched'}"
    )


# F4.


def heap_info(text: str) -> dict:
    """GC.heap_info's heap line (and Metaspace's, when printed) in KiB; RunError without one."""
    found: dict[str, Any] = {}
    for line in text.splitlines():
        if "heap" not in found and (m := HEAP_LINE.match(line)):
            found.update(
                heap=m.group("heap"),
                reservedKiB=int(m.group("reserved")),
                committedKiB=int(m.group("committed")) if m.group("committed") else None,
                usedKiB=int(m.group("used")),
            )
        elif m := METASPACE_LINE.match(line):
            found["metaspaceUsedKiB"] = int(m.group("used"))
    if "heap" not in found:
        raise RunError(f"GC.heap_info printed no heap line: {text.strip()[:200]!r}")
    return found


def memory_row(s: Session, jcmd: Path, reloads: int, folder: Path) -> dict:
    """One row of F4's table: GC.run, then GC.heap_info's heap after it, and the private bytes."""
    pid = s.launched.pid
    s.host.jcmd(jcmd, pid, "GC.run")
    text = s.host.jcmd(jcmd, pid, "GC.heap_info")
    (folder / f"heap-{reloads:03d}.txt").write_text(text, encoding="utf-8", newline="\n")
    heap = heap_info(text)
    private = s.host.private_bytes(pid)
    committed = heap["committedKiB"]
    return {
        "reloads": reloads,
        "heapUsedMiB": round(heap["usedKiB"] / 1024, 1),
        "heapCommittedMiB": None if committed is None else round(committed / 1024, 1),
        "privateMiB": round(private / MIB, 1),
        "availableMiB": round(s.host.available_memory() / MIB),
        "heapUsedKiB": heap["usedKiB"],
        "privateBytes": private,
    }


def reload_table(s: Session, jcmd: Path, pack: str, count: int) -> dict:
    """F4: `count` shaders.reload of the reference pack back to back, a memory row before the
    first and after every record.RELOAD_EVERY; the growth per reload from the first row to the
    last, and the reloads' own seconds."""
    c = s.client
    folder = s.raw / "f4"
    folder.mkdir(parents=True, exist_ok=True)
    s.label = "F4"
    rows = [memory_row(s, jcmd, 0, folder)]
    row = rows[0]
    s.say(f"F4: before: heap after GC {row['heapUsedMiB']} MiB, private {row['privateMiB']} MiB")
    each = []
    for n in range(1, count + 1):
        s.label = f"F4 reload {n}"
        available = s.host.available_memory()
        if available < F4_MIN_AVAILABLE:
            raise RunError(
                f"F4 stopped before reload {n}: {available / 1024**3:.1f} GiB available, under "
                f"{F4_MIN_AVAILABLE / 1024**3:.0f} GiB; the rows so far: {rows}"
            )
        began = time.monotonic()
        try:
            answer = c.shaders_reload(RELOAD_TIMEOUT, 2, pack=pack)
        except modclient.ModError as error:
            raise RunError(f"F4 reload {n}: {error}") from None
        each.append(
            {
                "n": n,
                "seconds": round(answer["seconds"], 4),
                "requestSeconds": round(time.monotonic() - began, 3),
                "reloadFrame": answer["reloadFrame"],
            }
        )
        if n % record.RELOAD_EVERY == 0:
            rows.append(memory_row(s, jcmd, n, folder))
            row = rows[-1]
            s.say(
                f"F4: after {n}: heap after GC {row['heapUsedMiB']} MiB, private "
                f"{row['privateMiB']} MiB"
            )
        s.drain()
    first, last = rows[0], rows[-1]
    seconds = [entry["seconds"] for entry in each]
    return {
        "tier": "bench",
        "pack": pack,
        "reloads": count,
        "every": record.RELOAD_EVERY,
        "rows": rows,
        "perReload": {
            "heapMiB": round((last["heapUsedMiB"] - first["heapUsedMiB"]) / count, 2),
            "privateMiB": round((last["privateMiB"] - first["privateMiB"]) / count, 1),
        },
        "reloadSeconds": {
            "min": min(seconds),
            "median": round(statistics.median(seconds), 4),
            "max": max(seconds),
        },
        "each": each,
        "raw": shown(folder, s.root),
    }


def pipe_names(host: RunHost) -> list[str]:
    return [name for name in host.pipes() if name.startswith(MOD_THREAD)]


# A1.


def a1(
    root: Path,
    raw: Path,
    world: str,
    tier: str,
    host: RunHost,
    say: Say,
    announce: Say,
    jcmd: Path,
    control: dict,
) -> dict:
    """A1 inert: a launch without the token, never connected; after the join no optilux- pipe,
    the helper's inert line and no applied mixin or active line in latest.log, no optilux- thread
    in the JVM's thread dump; WM_CLOSE ends it with exit 0. The same three detectors must have
    seen the mod in the session launch (`control`: its pipe listed, mixins applied, optilux-
    threads), else a detector that went blind would pass A1."""
    announce(
        f"launch (announced): A1, tier {tier}, world {world}, unmodified reference pack, no "
        "token: the mod must stay inert; no connection is attempted"
    )
    launched = launch.launch(root, world, tier, False, {}, say, host)
    folder = raw / "a1"
    folder.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {"launch": trim(launched.facts), "connectionAttempted": False}
    try:
        pipes = pipe_names(host)
        dump = host.thread_dump(jcmd, launched.pid)
        (folder / "threads.txt").write_text(dump, encoding="utf-8", newline="\n")
        names = thread_names(dump)
    except BaseException as error:
        how = launch.end(launched.process, host)
        if isinstance(error, KeyboardInterrupt):
            raise
        raise RunError(f"A1: {error}; the game was ended ({how})") from None
    quit_facts = launch.quit_game(launched.process, host)
    log = launched.log.read_text(encoding="utf-8", errors="replace")
    shutil.copyfile(launched.log, folder / "latest.log")
    lines = helper_lines(log)
    threads = [name for name in names if name.startswith(MOD_THREAD)]
    evidence.update(
        pipes={"optilux": pipes},
        log={
            "file": shown(folder / "latest.log", root),
            "inert": lines["inert"],
            "declinedMixins": len(lines["declined"]),
            "applied": lines["applied"],
            "active": lines["active"],
        },
        threads={
            "file": shown(folder / "threads.txt", root),
            "count": len(names),
            "optilux": threads,
        },
        quit=quit_facts,
        control=control,
    )
    seen = (
        control.get("sessionPipeListed") is True
        and control.get("sessionMixinsApplied", 0) > 0
        and bool(control.get("sessionThreads"))
    )
    passed = (
        seen
        and not pipes
        and bool(lines["inert"])
        and not lines["applied"]
        and not lines["active"]
        and len(names) > 0
        and not threads
        and quit_facts["exitCode"] == 0
    )
    say(
        f"A1: {'pass' if passed else 'fail'}: optilux pipes {pipes or 'none'}; "
        f"{len(lines['inert'])} inert line, {len(lines['declined'])} mixins declined, "
        f"{len(lines['applied'])} applied; {len(names)} threads, optilux {threads or 'none'}; "
        f"WM_CLOSE exit {quit_facts['exitCode']}"
    )
    return {**evidence, "pass": passed}


def session_plan(spec: record.Spec, views: dict) -> str:
    """What the session launch will do, for its announcement."""
    parts = ["session start (A10)"]
    singles = [item for item in ("A4", "A7", "A9") if item in spec.items]
    if singles:
        parts.append(f"{', '.join(singles)} at {views['views'][0]['id']}")
    per_view = [item for item in ("A2", "A3") if item in spec.items]
    if per_view:
        parts.append(f"{' and '.join(per_view)} on {len(views['views'])} views")
    if spec.reloads:
        parts.append(f"F4's {spec.reloads} reloads")
    return ", ".join(parts)


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


def perform(
    root: Path, spec_path: Path, host: RunHost, machine: record.Machine, say: Say, announce: Say
) -> dict:
    """The run: checks, the session launch, A1's launch, the record. Returns the record."""
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    java_profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    base = root / RUNTIME / plat.id
    saves = base / launch.GAME / launch.SAVES
    pack = launch.reference_pack(plat)
    spec = record.check_spec(root, load_spec(spec_path), plat, suite, saves, pack.file)
    views, views_path = record.load_views(root, spec.views)
    snapshot = root / record.SNAPSHOTS / spec.views
    snap_hash, snap_files = record.tree_hash(snapshot)
    live_hash, live_files = record.tree_hash(saves / spec.world)
    if live_hash != snap_hash:
        raise record.RecordError(
            f"saves/{spec.world} hashes {live_hash[:12]}... ({live_files} files), its snapshot "
            f"{record.SNAPSHOTS}/{spec.views}/ {snap_hash[:12]}... ({snap_files}); fix: retake the "
            "snapshot from the world, or restore it (M2's `world restore`)"
        )
    say(
        f"world: saves/{spec.world} equals {record.SNAPSHOTS}/{spec.views}/: {snap_hash} "
        f"({snap_files} files)"
    )
    options = launch.written_options(suite["display"], {})
    system, system_recorded = record.system_facts(machine, options, suite["display"])
    say(
        f"system: {system['gpu']}, {system['resolution']} {system['windowMode']}, HAGS "
        f"{'on' if system['hags'] else 'off'}, Windows build {system['windowsBuild']}"
    )
    java_home = root / JAVA_DIR / java_profile["runtime"]["build"]
    jcmd = java_home / "bin" / "jcmd.exe"
    pm_exe = check_presentmon(root) if "A9" in spec.items else None
    leftover = broken_copies(base / launch.GAME)
    if leftover:
        raise record.RecordError(
            f"shaderpacks/ holds {', '.join(p.name for p in leftover)} from an earlier A4; fix: "
            "delete it (A4 writes its copy fresh)"
        )
    raw = root / record.RAW / spec.name
    raw.mkdir(parents=True)
    (raw / "world-manifest.txt").write_text(
        record.tree_text(record.tree_files(snapshot)), encoding="utf-8", newline="\n"
    )
    started = now()
    head = repo.head(root)
    dirty = bool(repo.changes(root))
    items: dict[str, dict] = {}
    session_facts: dict[str, Any] = {}
    problems: list[str] = []
    ident = None
    table = None
    variants: list[dict] = []
    recorded: dict[str, Any] = {
        "platformFile": record.file_sha256(plat.path),
        **system_recorded,
        "harness": {"commit": head, "dirty": dirty},
    }
    status = "ok"
    try:
        announce(
            f"launch (announced): the session, tier {spec.tier}, world {spec.world}, "
            f"unmodified {pack.file}: {session_plan(spec, views)}; hands off the mouse and "
            "keyboard until the quit"
        )
        launched = launch.launch(root, spec.world, spec.tier, True, {}, say, host)
        session_facts["launch"] = trim(launched.facts)
        recorded["amd"] = launched.facts["gate"]["amd"]
        try:
            client, mod = launch.open_mod(launched, root, host, say, raw / REQUESTS)
        except BaseException as error:
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise RunError(f"{error}; the game was ended ({how})") from None
        session_facts["mod"] = mod
        s = Session(root, raw, launched, client, host, say)
        try:
            # A1's positive controls: the detectors A1 relies on, seeing the mod active here.
            expected = modclient.pipe_name(launched.token).removeprefix(PIPES)
            try:
                session_facts["pipeListed"] = expected in host.pipes()
            except OSError as error:
                session_facts["pipeListed"] = f"unread: {error}"
            try:
                dump = host.thread_dump(jcmd, launched.pid)
                (raw / "session-threads.txt").write_text(dump, encoding="utf-8", newline="\n")
                session_facts["threads"] = [
                    name for name in thread_names(dump) if name.startswith(MOD_THREAD)
                ]
            except (OSError, RunError, subprocess.SubprocessError) as error:
                session_facts["threads"] = f"unread: {error}"
            start = session_start(s, pack.file, suite["capture"]["gpuWarmupS"])
            items["A10"] = {
                "pass": start["selftest"]["pass"] is True,
                "selftest": start["selftest"],
                "after": {"worldWait": start["joined"]},
            }
            variants.append(
                {
                    "pack": pack.file,
                    "sha512": pack.sha512,
                    "profile": None,
                    "options": {
                        "count": len(start["options"]["values"]),
                        "values": start["options"]["values"],
                    },
                }
            )
            session_facts["reload"] = start["reload"]
            previous = start["joined"]["pose"]["dimension"]
            weather = None
            a2_views, a3_views, settled = [], [], []
            session_facts["views"] = settled
            # Each item's evidence lands in the record as it is taken, so a later failure keeps it.
            first = views["views"][0]
            singles = [item for item in ("A4", "A7", "A9") if item in spec.items]
            if singles or spec.reloads:
                done = settle_view(s, first, weather, suite, previous)
                settled.append({"view": first["id"], **done})
                previous, weather = first["dim"], first["weather"]
                if "A4" in spec.items:
                    items["A4"] = {"pass": False, "view": first["id"]}
                    a4(s, items["A4"])
                if "A7" in spec.items:
                    items["A7"] = {"pass": False, "view": first["id"]}
                    a7(s, first, items["A7"])
                if "A9" in spec.items:
                    s.step(
                        f"{first['id']}: A9 ready",
                        lambda: client.ready(STABLE_FRAMES, done["settleSeconds"], READY_TIMEOUT),
                        lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
                    )
                    items["A9"] = {"pass": False, "view": first["id"]}
                    a9(s, pm_exe, f"{presentmon.SESSION_PREFIX}{spec.name}", items["A9"])
            if "A2" in spec.items:
                items["A2"] = {"pass": False, "complete": False, "views": a2_views}
            if "A3" in spec.items:
                items["A3"] = {"pass": False, "complete": False, "views": a3_views}
            for view in views["views"] if "A2" in spec.items or "A3" in spec.items else []:
                done = settle_view(s, view, weather, suite, previous)
                settled.append({"view": view["id"], **done})
                previous, weather = view["dim"], view["weather"]
                if "A2" in spec.items:
                    a2_views.append(a2(s, view, system["resolution"], done["settleSeconds"]))
                if "A3" in spec.items:
                    a3_views.append(a3(s, view))
            for item, done_views in (("A2", a2_views), ("A3", a3_views)):
                if item in spec.items:
                    items[item]["pass"] = all(v["pass"] for v in done_views)
                    items[item]["complete"] = True
            if spec.reloads:
                table = reload_table(s, jcmd, pack.file, spec.reloads)
            home = view_pose(views["views"][0])
            s.step("camera.place home", lambda: client.camera_place(home, PLACE_TIMEOUT))
            s.step("input.block off", lambda: client.input_block(False))
            s.label = "quit"
            session_facts["quit"] = launch.quit_mod(client, launched.process, host)
            say(
                f"quit: exit code {session_facts['quit']['exitCode']} in "
                f"{session_facts['quit']['seconds']:.1f} s"
            )
        except BaseException as error:
            client.close()
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise RunError(f"the session: {error}; the game was ended ({how})") from None
        finally:
            s.drain()
            session_facts["steps"] = s.steps
            session_facts["events"] = s.events
            if "A4" in spec.items:  # the game has exited here: its pack copy can go
                session_facts["a4Cleanup"] = remove_broken(launched.game)
        session_facts["logCheck"] = launch.check_log(raw / REQUESTS, launched.token)
        session_facts["readBack"] = launch.read_back(launched.game, launched.prelaunch)
        shutil.copyfile(launched.log, raw / "session-latest.log")
        options_txt = launched.game / launch.OPTIONS
        recorded["optionsTxt"] = {"sha256": record.file_sha256(options_txt)}
        mods_log = helper_lines(launched.log.read_text(encoding="utf-8", errors="replace"))
        session_facts["helperLog"] = {
            "applied": len(mods_log["applied"]),
            "active": len(mods_log["active"]),
        }
        packs = [p for p in launched.facts["hashes"]["packs"] if p["kind"] == "resourcePack"]
        settings = dict(launched.facts["settings"])
        ident = record.identity(
            plat=plat,
            tier=spec.tier,
            spec_path=platform.spec_path(root, plat.id),
            mods=launched.facts["mods"]["sha512"],
            world={
                "snapshot": f"{record.SNAPSHOTS}/{spec.views}",
                "treeSha256": snap_hash,
                "files": snap_files,
                "live": spec.world,
            },
            views_path=views_path,
            packs=[{"file": p["file"], "sha512": p["sha512"]} for p in packs],
            settings=settings,
            suite=suite,
            java=record.java_identity(java_home, java_profile, mod["hello"]["versions"]["java"]),
            system=system,
        )
        if "A1" in spec.items:
            control = {
                "sessionPipeListed": session_facts["pipeListed"],
                "sessionMixinsApplied": session_facts["helperLog"]["applied"],
                "sessionThreads": session_facts["threads"],
            }
            items["A1"] = a1(root, raw, spec.world, spec.tier, host, say, announce, jcmd, control)
    except KeyboardInterrupt:
        status = "aborted"
        problems.append("stopped by the user")
    except (RunError, launch.LaunchError, modclient.ModError, record.RecordError) as error:
        problems.append(str(error))
    except Exception as error:  # a session ran: its record is written whatever broke
        problems.append(f"{type(error).__name__}: {error}")
    if any(e["event"] == "hook.error" for e in session_facts.get("events", [])):
        status = "invalid" if status == "ok" else status
        problems.append("hook.error in the session")
    quit_facts = session_facts.get("quit")
    if quit_facts is not None and quit_facts["exitCode"] != 0:
        problems.append(f"the session's quit exited {quit_facts['exitCode']}")
    if "readBack" in session_facts and not session_facts["readBack"]["ok"]:
        problems.append("the option files did not read back as written")
    if "A10" in items and not items["A10"]["pass"] and "A10" not in spec.items:
        problems.append("selftest failed at the session start")  # A10 holds at every start
    if session_facts.get("a4Cleanup", {}).get("kept"):
        problems.append(f"A4's copy was not deleted: {session_facts['a4Cleanup']['kept']}")
    if spec.reloads and table is None:
        problems.append(f"F4's table of {spec.reloads} reloads was not completed")
    acceptance = []
    for item in spec.items:
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
    found = {
        "schema": record.SCHEMA,
        "name": spec.name,
        "kind": spec.kind,
        "spec": spec.data,
        "status": status,
        "reason": "; ".join(problems) or None,
        "startedAt": started,
        "endedAt": now(),
        "identity": ident,
        "recorded": recorded,
        "variants": variants,
        "acceptance": acceptance,
    }
    if spec.reloads:
        found["reloadTable"] = table
    return {**found, "session": session_facts, "raw": shown(raw, root)}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("spec", help="the run spec, a JSON file (docs/run-record.md#run-spec)")


def run(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)

    def announce(text: str) -> None:  # every launch is announced, --json or not
        print(text, file=sys.stderr if args.json else sys.stdout, flush=True)

    try:
        found = perform(root, Path(args.spec), RunHost(), record.Machine(), say, announce)
    except (record.RecordError, platform.PlatformError, launch.LaunchError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    try:
        path = record.write_record(root, found, say)
    except record.RecordError as error:
        dump = root / found["raw"] / "record-unwritten.json"
        dump.write_text(json.dumps(found, indent=1, default=str) + "\n", encoding="utf-8")
        message = f"{error}; the record's content is in {shown(dump, root)}"
        print(f"{PREFIX}: {message}", file=sys.stderr)
        return 1
    passed = {entry["item"]: entry["pass"] for entry in found["acceptance"]}
    if args.json:
        print(
            json.dumps(
                {
                    "ok": found["status"] == "ok",
                    "record": shown(path, root),
                    "status": found["status"],
                    "reason": found["reason"],
                    "items": passed,
                }
            )
        )
    else:
        items = ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in passed.items())
        line = f"{PREFIX}: {found['status']}; {shown(path, root)}: {items}"
        if found["reason"]:
            line += f"; {found['reason']}"
        print(line, file=sys.stdout if found["status"] == "ok" else sys.stderr)
    return 0 if found["status"] == "ok" else 1


VERB = Verb(
    name="run",
    help="run an acceptance spec: the session, the items, the record",
    run=run,
    configure=configure,
    structured=True,
)
