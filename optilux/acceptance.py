"""M1's acceptance items on a running session (docs/mod.md#12-acceptance, docs/plans/m1.md
0.01.08 and 0.01.09): A1 (a launch without the token: no pipe, no applied mixin, no mod thread),
A2 (F2 pressed inside a capture; the screenshot equals one captured frame), A3 (`/tp` against
camera.place), A4 (a broken copy of the reference pack answers iris-compile-error), A7 (input
with input.block off and on), A9 (captured frames matched to PresentMon's rows) and F4's reload
table. Each item writes its evidence into the dict it is handed; optilux/verbs/run.py runs them
and writes the record."""

import contextlib
import hashlib
import math
import re
import shutil
import statistics
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from optilux import launch, modclient, presentmon, record, sendinput
from optilux.session import (
    COMMAND_TIMEOUT,
    INVALIDATING,
    OVERWORLD,
    PLACE_TIMEOUT,
    READY_TIMEOUT,
    RELOAD_TIMEOUT,
    STABLE_FRAMES,
    RunError,
    RunHost,
    Session,
    ensure_focus,
    in_front,
    trim,
    view_pose,
)
from optilux.verbs.install import Say, shown

SCREENSHOTS = "screenshots"


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
# A capture answered `timeout` holds its resource until its pending frames are written (at most
# 16 4K PNGs on 4 writers): input.block waits that long for it instead of ending the session.
A2_FREE_TIMEOUT = 30.0


# A PNG ends with its IEND chunk: the screenshot is complete once its bytes end so.
PNG_END = b"IEND\xaeB`\x82"


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
# The mod's warnings the run reads from the session's latest.log: a hook's first failure
# (Hooks.report; hook.error goes out only after hello, so one before it reaches only the log) and
# an Iris load failing outside shaders.reload (IrisAdapter.failed: no event, no answer).
HOOK_FAILED = re.compile(r"optilux-helper: \S+(?: \S+)* failed at frame \d+")
IRIS_OUTSIDE = "optilux-helper: Iris failed to load a pack outside shaders.reload"


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


def thread_names(dump: str) -> list[str]:
    """The thread names of a `jcmd <pid> Thread.print` dump."""
    return [m.group("name") for line in dump.splitlines() if (m := THREAD_LINE.match(line))]


def helper_lines(log: str) -> dict:
    """The helper's inert, active and mixin lines in a latest.log, and its failure lines: a hook
    that threw (Hooks.report) and an Iris load that failed outside shaders.reload
    (IrisAdapter.failed)."""
    lines = [line for line in log.splitlines() if "optilux-helper" in line]
    return {
        "inert": [line for line in lines if INERT in line],
        "active": [line for line in lines if ACTIVE in line],
        "applied": [line for line in lines if APPLIED.search(line)],
        "declined": [line for line in lines if DECLINED.search(line)],
        "hookFailures": [line for line in lines if HOOK_FAILED.search(line)],
        "irisOutsideReload": [line for line in lines if IRIS_OUTSIDE in line],
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
    state = ensure_focus(s, evidence)
    evidence.update(focused=state["focused"], screen=state["screen"])
    if not in_front(s, state) or state["screen"] is not None:
        evidence["problem"] = (
            "the game is not focused, its window is not in the foreground or a screen is open"
        )
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
        # SendInput goes to whatever window is in front: F2 only while the game's is (inject).
        pressed = inject(s, "F2", lambda: s.host.key_press(sendinput.VK_F2, sendinput.SCAN_F2))
        ours = pressed["focused"] is True and pressed["foregroundPid"] == s.launched.pid
        sent = pressed["inserted"]
        after = c.request("frames.index")["frameIndex"]
        worker.join(A2_CAPTURE_TIMEOUT + 2 * modclient.MARGIN)
    except BaseException:
        # The capture holds its resource until it ends, and input.block answers busy until then:
        # the cleanup waits for it and never replaces the error that ended the attempt.
        with contextlib.suppress(Exception):
            if worker.is_alive():
                worker.join(A2_CAPTURE_TIMEOUT + 2 * modclient.MARGIN)
            c.input_block_when_free(True, A2_FREE_TIMEOUT)
        raise
    c.input_block_when_free(True, A2_FREE_TIMEOUT)
    evidence.update(
        frameBefore=first,
        frameAtPress=reached,
        frameAfterPress=after,
        focusedAtPress=pressed["focused"],
        foregroundPidAtPress=pressed["foregroundPid"],
        sendInput={"sent": 2 if ours else 0, "inserted": sent},
    )
    if not ours:
        evidence["problem"] = "the game lost focus or the foreground before the press; no F2"
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
    passed = a2_pass(
        sent,
        ours,
        matches,
        bad,
        evidence["poseDifferences"],
        evidence["screenshot"]["size"],
        resolution,
    )
    return {**evidence, "pass": passed}


def a2_pass(
    sent: int,
    ours: bool,
    matches: list[int],
    bad: list[dict],
    differences: list[str],
    size: str | None,
    resolution: str,
) -> bool:
    """A2's verdict on one attempt: F2's two key events inserted into the game's own window,
    the screenshot equal to a captured frame and at the display's resolution, no invalidating
    event and the pose unmoved."""
    return (
        sent == 2 and ours and bool(matches) and not bad and not differences and size == resolution
    )


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
            f"{differences or 'equal'}"
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


def a4_names(message: str) -> dict:
    """Whether the refusal names the broken program and its undeclared identifier."""
    program = PurePosixPath(A4_PROGRAM).name  # Iris names the file: "final.fsh: ERROR: ..."
    return {"namesProgram": program in message, "namesIdentifier": A4_IDENTIFIER in message}


def a4_clean(events: list[dict]) -> bool:
    """No event across A4's window invalidates its capture (docs/mod-protocol.md#client-rules)
    but its own reloads: the broken one's reload.failed and the good one's reload.done."""
    return not any(e["event"] in INVALIDATING and e["event"] != "reload.done" for e in events)


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
        **a4_names(message),
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
    events = [e for e in s.events[mark:] if e["event"] in ("reload.failed", *INVALIDATING)]
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
        and a4_clean(events)
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

    control_ok, blocked_ok, after_ok = a7_verdicts(control, blocked, after)
    evidence.update(controlPassed=control_ok, blockedPassed=blocked_ok, afterPassed=after_ok)
    evidence["pass"] = control_ok and blocked_ok and after_ok and not bad
    s.say(
        f"A7: {'pass' if evidence['pass'] else 'fail'} (control {control_ok}, blocked "
        f"{blocked_ok}, after {after_ok}, invalidating events {len(bad)})"
    )


def sent(entry: dict | None, count: int) -> bool:
    """An injection that went out: the game in front and SendInput's count as sent."""
    return bool(entry) and entry["focused"] is True and entry["inserted"] == count


def a7_verdicts(control: dict, blocked: dict, after: dict) -> tuple[bool, bool, bool]:
    """A7's three arms: the control (T opened chat, Escape closed it, the primed motion turned
    the camera), blocked (both injections inserted and nothing moved, opened or changed over
    A7_HOLD_FRAMES), after (the motion turned the camera again)."""
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
    return control_ok, blocked_ok, after_ok


def delete_pngs(folder: Path) -> int:
    """The captured frames under `folder` deleted; how many."""
    pngs = sorted(folder.rglob("frame-*.png")) if folder.is_dir() else []
    for png in pngs:
        png.unlink(missing_ok=True)
    return len(pngs)


def a9_pass(match: dict, complete: bool, stop_exit: int, left: list, bad: list) -> bool:
    """A9's verdict: the stamps matched, the capture complete, PresentMon stopped with exit 0 and
    its ETW session gone, and no event that invalidates a capture during it
    (docs/mod-protocol.md#client-rules)."""
    return match["pass"] is True and complete is True and stop_exit == 0 and not left and not bad


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
            s.drain()
            mark = len(s.events)
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
    s.drain()
    bad = [e for e in s.events[mark:] if e["event"] in INVALIDATING]
    evidence["invalidatingEvents"] = bad
    evidence["pass"] = a9_pass(
        match, shot["verified"]["complete"], evidence["stop"]["exitCode"], left, bad
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
            **per_reload(first, last, count),
        },
        "reloadSeconds": {
            "min": min(seconds),
            "median": round(statistics.median(seconds), 4),
            "max": max(seconds),
        },
        "each": each,
        "raw": shown(folder, s.root),
    }


def per_reload(first: dict, last: dict, count: int) -> dict:
    """F4's growth per reload from its first memory row to its last."""
    return {
        "heapMiB": round((last["heapUsedMiB"] - first["heapUsedMiB"]) / count, 2),
        "privateMiB": round((last["privateMiB"] - first["privateMiB"]) / count, 1),
    }


def pipe_names(host: RunHost) -> list[str]:
    return [name for name in host.pipes() if name.startswith(MOD_THREAD)]


# A1.


def a1_seen(control: dict) -> bool:
    """A1's positive control: in the session launch the three detectors saw the mod (its pipe
    listed, mixins applied, optilux- threads in the dump). A detector that could not be read
    holds "unread: ..." and counts as blind."""
    threads = control.get("sessionThreads")
    return (
        control.get("sessionPipeListed") is True
        and control.get("sessionMixinsApplied", 0) > 0
        and isinstance(threads, list)
        and len(threads) > 0
    )


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
    passed = (
        a1_seen(control)
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
