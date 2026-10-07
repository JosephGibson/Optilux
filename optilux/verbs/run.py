"""`optilux run <spec.json> [--json]` (docs/run-record.md#run-spec, docs/plans/m1.md 0.01.08).

An acceptance run: the spec checked (optilux/record.py, every refusal naming its fix), the live
world hash-checked against its snapshot and the display against the suite, then two announced
launches. The session launch runs the session start of docs/mod-protocol.md#choreography (A10
is its selftest), then per view A2 (a capture with F2 pressed inside it through SendInput; the
new screenshot must equal one captured frame byte for byte; a miss is kept and retaken once) and
A3 (`/tp` through `command` against camera.place with tpSemantics, both read back), then
`input.block off` and `quit`. A1's launch starts without the token and never connects: the
pipe list holds no optilux- pipe, latest.log no applied mixin and no active line, the JVM's
thread dump no optilux- thread; WM_CLOSE ends it. The record goes to results/records/<name>.json,
the request log and the raw artifacts to results/raw/<name>/. Exit 0 when every item passed.
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
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, launch, modclient, platform, record, repo, sendinput
from optilux.verbs import Verb
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, Say, shown

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


class RunError(RuntimeError):
    """A run that cannot go on; the message names the problem."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# The machine, beyond launch's.


class RunHost(launch.Host):
    """launch's Host plus what the items read and inject; the tests replace it."""

    def pipes(self) -> list[str]:
        return sorted(os.listdir(PIPES))

    def thread_dump(self, jcmd: Path, pid: int) -> str:
        done = subprocess.run(
            [str(jcmd), str(pid), "Thread.print"],
            capture_output=True,
            text=True,
            timeout=JCMD_TIMEOUT,
        )
        if done.returncode != 0:
            raise RunError(
                f"jcmd {pid} Thread.print exited {done.returncode}: {done.stderr[-300:]}"
            )
        return done.stdout

    def key_press(self, vk: int, scan: int) -> int:
        return sendinput.key_press(vk, scan=scan)

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


def a2_attempt(s: Session, view: dict, attempt: int, resolution: str) -> dict:
    """One A2 attempt at the placed view: input.block off, a capture of A2_FRAMES frames, F2
    through SendInput A2_LEAD frames into it, input.block on; the new screenshot against every
    captured frame; the pose and the events checked after."""
    c = s.client
    folder = s.raw / "a2" / view["id"]
    shots = s.launched.game / SCREENSHOTS
    s.label = f"{view['id']}: A2 attempt {attempt}"
    evidence: dict[str, Any] = {"attempt": attempt}
    state = c.state()
    if not state["focused"]:
        # input.block is on here: the fallback's click activates the window and does nothing
        # in game.
        fallback = [s.host.focus(s.launched.pid)]
        time.sleep(1.0)
        state = c.state()
        if not state["focused"]:
            fallback.append(s.host.click_focus(s.launched.pid))
            time.sleep(1.0)
            state = c.state()
        evidence["focusFallback"] = fallback
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
            f"unmodified {pack.file}: session start, A10, A2 and A3 on {len(views['views'])} views"
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
            # Each view's evidence lands in its item as it is taken, so a later failure keeps it.
            if "A2" in spec.items:
                items["A2"] = {"pass": False, "complete": False, "views": a2_views}
            if "A3" in spec.items:
                items["A3"] = {"pass": False, "complete": False, "views": a3_views}
            session_facts["views"] = settled
            for view in views["views"]:
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
    return {
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
        "session": session_facts,
        "raw": shown(raw, root),
    }


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
