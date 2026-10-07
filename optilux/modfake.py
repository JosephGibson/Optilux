"""A protocol fake of the helper mod, generated from commands.json (docs/mod-protocol.md#client-
rules: "a protocol fake generated from the command table, covering every command").

Fake.serve answers one connection on any byte stream as the mod's protocol core does: strict
JSON lines, the envelope, `hello` with the token first, every command's arguments checked
against commands.json, coded errors, `cancel`, events only after hello, and for every command a
result typed from its commands.json fields plus frameIndex, sinceReload and qpcNs. hello answers
this process's pid, frames.index advances, quit answers then ends the connection. The game
adapter's commands answer from a small game model (`game`): camera.place sets the pose camera.get
and state read back, a dimension change pushes dimension.changed, input.block and hud.set keep
their flags, `/tick freeze` freezes (ticks.step fails without it; an unknown dimension and,
without tpSemantics, a pitch outside -90..90 are refused, as the mod does); the fake applies no
`/tp` semantics (the mod alone does, docs/lessons.md#game-control), so tpSemantics places the
pose as given. `ready` answers at once; shaders.reload restarts sinceReload at the current frame,
answers framesAfter + 1 frames later and pushes reload.done; shaders.options reads the model's
options; frames.capture writes `count` small PNGs and capture.json into a new attempt folder under
an absolute directory, as the mod does; selftest passes. Like the mod
it answers busy for the exclusive resources and the running cap, a request's own timeoutSeconds
with `timeout`, an unbuilt command with unsupported, and keeps one resume per connection. Tests
steer it: `delays` holds a command's answer back (answers out of order, timeouts), `refusals`
makes a command answer an error code, `built` limits the commands it answers. PipeService serves
a real named pipe with the mod's flags and DACL (Windows only).
"""

import contextlib
import hashlib
import itertools
import json
import os
import struct
import threading
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from optilux import modclient

PROTOCOL = 1
# A fake value per result type; `|null` types answer null.
SAMPLES = {
    "string": "fake",
    "integer": 0,
    "number": 0.0,
    "boolean": False,
    "object": {},
    "array": [],
    "id": 0,
}
# The fake's frame clock: frames.index advances by this much per call.
FRAMES_PER_CALL = 3
# Requests running at once, as the mod's Protocol.MAX_RUNNING.
MAX_RUNNING = 32
# The fake player's eye height above its feet (the game's standing player).
EYE_HEIGHT = 1.62
OVERWORLD = "minecraft:overworld"
# The spike world's dimensions; camera.place refuses others, as the mod does.
DIMENSIONS = (OVERWORLD, "minecraft:the_nether", "minecraft:the_end")


class Refusal(Exception):
    """A game-model answer the mod gives as an error: its code and message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def initial_game() -> dict:
    """The fake's game: a spectator at spawn, ticks running, focused, no screen, a pack loaded."""
    return {
        "pack": "fake-pack.zip",
        "options": {"FAKE_BOOL": True, "FAKE_VALUE": "2"},
        "reloadFrame": 0,
        "pose": {"dimension": OVERWORLD, "x": 0.5, "y": 70.0, "z": 0.5, "yaw": 0.0, "pitch": 0.0},
        "gamemode": "spectator",
        "time": 6000,
        "tick": 0,
        "frozen": False,
        "focused": True,
        "inputBlocked": False,
        "hideGui": False,
        "debugOverlay": False,
    }


# The game adapter's commands, answered from the fake's game model.
GAME_COMMANDS = (
    "state",
    "world.wait",
    "command",
    "ticks.step",
    "camera.place",
    "camera.get",
    "input.block",
    "hud.set",
)
# The renderer and shader-loader commands, capture and selftest, answered from the model.
RENDER_COMMANDS = ("ready", "shaders.reload", "shaders.options", "frames.capture", "selftest")
SELFTEST_CHECKS = ("frameClock", "renderer", "reload", "capture", "input")
# The fake's captured frames: tiny RGBA PNGs.
FRAME_SIZE = 2


def png(width: int, height: int, rgba: bytes) -> bytes:
    """A PNG of 8-bit RGBA rows, no filter."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride : (y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        modclient.PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def attempt_folder(directory: Path) -> Path:
    """The first free attempt-NNN under `directory`, created (the mod's Capture.attemptFolder)."""
    directory.mkdir(parents=True, exist_ok=True)
    for n in itertools.count(1):
        folder = directory / f"attempt-{n:03d}"
        with contextlib.suppress(FileExistsError):
            folder.mkdir()
            return folder
    raise AssertionError("unreachable")


def sample(kind: str) -> Any:
    return None if kind.endswith("|null") else SAMPLES[kind]


def result_fields(commands: dict, name: str) -> dict:
    """A command's result as the fake answers it: each field a sample of its type."""
    return {key: sample(kind) for key, kind in commands["byName"][name]["result"].items()}


class Fake:
    """One fake mod; serve() runs one connection at a time. `built` names the commands it
    answers (default: every command of commands.json); the others answer unsupported, as the
    mod's unbuilt ones do."""

    def __init__(
        self,
        token: str,
        commands: dict | None = None,
        pid: int | None = None,
        built: list[str] | None = None,
    ) -> None:
        self.token = token
        self.commands = commands or modclient.load_commands()
        self.pid = os.getpid() if pid is None else pid
        names = list(self.commands["byName"])
        # hello and cancel are the protocol core's own, in every build.
        self.built = [
            name for name in names if built is None or name in built or name in ("hello", "cancel")
        ]
        self.delays: dict[str, float] = {}
        self.refusals: dict[str, tuple[str, str]] = {}
        self.received: list[dict] = []
        self.cancelled: list[Any] = []
        self._frames = itertools.count(100, FRAMES_PER_CALL)
        self._frame = 100
        self._lock = threading.Lock()
        self._write = None
        self._authenticated = False
        self._resume: tuple[bool, list] | None = None
        self._said_hello = False
        self._last_cancelled: list = []
        self._running: dict[Any, threading.Event] = {}
        self._held: dict[str, Any] = {}
        self.quit = threading.Event()
        self.game = initial_game()

    # The wire.

    def serve(self, stream: modclient.Stream) -> None:
        """Answer lines from `stream` until it ends or a quit was answered."""
        write_lock = threading.Lock()

        def write(message: dict) -> None:
            line = json.dumps(message, separators=(",", ":")) + "\n"
            with write_lock, contextlib.suppress(OSError):
                stream.write(line.encode("utf-8"))

        with self._lock:
            self._write = write
            self._authenticated = False
            self._resume = None
        buffer = b""
        skipping = False
        try:
            while not self.quit.is_set() and (chunk := stream.read(modclient.READ_BYTES)):
                buffer += chunk
                while b"\n" in buffer and not self.quit.is_set():
                    line, buffer = buffer.split(b"\n", 1)
                    if skipping:
                        skipping = False
                    else:
                        self._line(line.removesuffix(b"\r"), write)
                if not skipping and len(buffer) > modclient.MAX_LINE:
                    write(self._error(None, "line-too-long", "the line passed 1 MiB"))
                    buffer, skipping = b"", True
                elif skipping:
                    buffer = b""
        finally:
            with self._lock:
                self._write = None
                cancelled = list(self._running)
                for stop in self._running.values():
                    stop.set()
                self._running.clear()
                self._held = {
                    resource: owner
                    for resource, owner in self._held.items()
                    if not self._until(resource)
                }
                if self._authenticated:
                    self._last_cancelled = cancelled
            stream.close()

    def emit(self, event: str, data: dict) -> bool:
        """Push an event; sent only after hello, as the mod does. Whether it was sent."""
        with self._lock:
            write = self._write if self._authenticated else None
        if write is None:
            return False
        write({"event": event, "data": data, **self._stamps()})
        return True

    def _until(self, resource: str) -> bool:
        """Whether a resource is held past its request (timers until timers.stop)."""
        return any(
            c.get("exclusive") == resource and c.get("exclusiveUntil")
            for c in self.commands["commands"]
        )

    def _stamps(self) -> dict:
        return {
            "frameIndex": self._frame,
            "sinceReload": self._frame - self.game["reloadFrame"],
            "qpcNs": time.perf_counter_ns(),
        }

    def _error(self, request_id: Any, code: str, message: str) -> dict:
        return {"id": request_id, "ok": False, "error": {"code": code, "message": message}}

    def _line(self, raw: bytes, write: Callable[[dict], None]) -> None:
        try:
            message = modclient.strict_json(raw.decode("utf-8"))
        except UnicodeDecodeError:
            write(self._error(None, "bad-encoding", "the line is not UTF-8"))
            return
        except ValueError as error:
            write(self._error(None, "bad-json", str(error)))
            return
        if not isinstance(message, dict):
            write(self._error(None, "bad-request", "a request is a JSON object"))
            return
        try:
            if "id" not in message:
                raise ValueError("the request has no id")
            request_id = modclient.check_id("id", message["id"])
        except ValueError as error:
            write(self._error(None, "bad-request", str(error)))
            return
        self.received.append(message)
        answer = self._judge(request_id, message)
        if answer is not None:
            write(answer)

    def _judge(self, request_id: Any, message: dict) -> dict | None:
        """The immediate answer, or None when the request runs on (delayed). The checks run in
        the mod's order (Protocol.line, then dispatch)."""
        unknown = [key for key in message if key not in ("id", "cmd", "args")]
        if unknown:
            return self._error(request_id, "bad-request", f"unknown top-level field {unknown[0]}")
        name = message.get("cmd")
        if not isinstance(name, str):
            return self._error(request_id, "bad-request", "cmd must be a string")
        if not self._authenticated and name != "hello":
            return self._error(request_id, "unauthenticated", "say hello with the token first")
        command = self.commands["byName"].get(name)
        if command is None:
            return self._error(request_id, "unknown-command", f"no command {name}")
        try:
            args = modclient.check_args(command, message.get("args", {}))
        except ValueError as error:
            return self._error(request_id, "bad-request", str(error))
        if name == "hello":
            if args["token"] != self.token:
                return self._error(request_id, "unauthenticated", "the token does not match")
            with self._lock:
                self._authenticated = True
        if name not in self.built:
            return self._error(request_id, "unsupported", f"{name} is not built in this fake")
        if name == "cancel":
            return self._ok(request_id, {"cancelled": self._cancel(args["id"])})
        with self._lock:
            if request_id in self._running:
                return self._error(request_id, "bad-request", f"id {request_id} is in use")
            if len(self._running) >= MAX_RUNNING:
                return self._error(request_id, "busy", f"{MAX_RUNNING} requests are running")
            if command.get("mutating") and self._held:
                return self._error(request_id, "busy", f"{', '.join(self._held)} active")
            resource = command.get("exclusive")
            if resource is not None:
                if resource in self._held:
                    return self._error(request_id, "busy", f"{resource} is in use")
                self._held[resource] = request_id
        if name in self.refusals:
            self._free(name, request_id, ok=False)
            code, text = self.refusals[name]
            return self._error(request_id, code, text)
        delay = self.delays.get(name)
        if delay is None:
            answer = self._answer(request_id, name, args)
            self._free(name, request_id, ok=True)
            return answer
        stop = threading.Event()
        with self._lock:
            self._running[request_id] = stop
        threading.Thread(
            target=self._later, args=(request_id, name, args, delay, stop), daemon=True
        ).start()
        return None

    def _free(self, name: str, request_id: Any, ok: bool) -> None:
        """Release what the request held; a successful command frees what it ends."""
        command = self.commands["byName"][name]
        with self._lock:
            resource = command.get("exclusive")
            if (
                resource is not None
                and self._held.get(resource) == request_id
                and not (ok and command.get("exclusiveUntil"))
            ):
                del self._held[resource]
            if ok:
                for other in self.commands["commands"]:
                    if other.get("exclusiveUntil") == name:
                        self._held.pop(other["exclusive"], None)

    def _later(self, request_id: Any, name: str, args: dict, delay: float, stop: threading.Event):
        """A delayed answer; the request's own timeoutSeconds answers `timeout` first, as the
        mod's timer does."""
        own = args.get("timeoutSeconds")
        timed_out = own is not None and own < delay
        if stop.wait(own if timed_out else delay):
            self._free(name, request_id, ok=False)
            return  # cancelled or disconnected: its answer was given or nobody listens
        with self._lock:
            if self._running.pop(request_id, None) is None:
                return
            write = self._write
        if timed_out and own is not None:
            # The mod's order (Protocol.stop): `timeout` goes out first, and the resource stays
            # held until the stopped handler returns.
            if write is not None:
                write(self._error(request_id, "timeout", f"timeoutSeconds {own} expired"))
            stop.wait(delay - own)
            self._free(name, request_id, ok=False)
            return
        answer = self._answer(request_id, name, args)
        self._free(name, request_id, ok=True)
        if write is not None:
            write(answer)

    def _cancel(self, target: Any) -> bool:
        with self._lock:
            stop = self._running.pop(target, None)
            write = self._write
        if stop is None:
            return False
        stop.set()
        self.cancelled.append(target)
        if write is not None:
            write(self._error(target, "cancelled", "cancelled by request"))
        return True

    def _ok(self, request_id: Any, fields: dict) -> dict:
        return {"id": request_id, "ok": True, "result": {**fields, **self._stamps()}}

    def _answer(self, request_id: Any, name: str, args: dict) -> dict:
        fields = result_fields(self.commands, name)
        if name == "hello":
            with self._lock:
                if self._resume is None:  # one resume per connection, as the mod keeps
                    self._resume = (self._said_hello, list(self._last_cancelled))
                    self._said_hello = True
                resumed, cancelled = self._resume
            fields.update(
                protocol=PROTOCOL,
                mod={"id": "optilux-helper", "version": "fake"},
                platform="fake",
                versions={},
                capabilities=list(self.built),
                pid=self.pid,
                resumed=resumed,
                cancelled=cancelled,
            )
        elif name == "frames.index":
            self._frame = next(self._frames)
        elif name == "quit":
            self.quit.set()
        elif name in GAME_COMMANDS or name in RENDER_COMMANDS:
            try:
                fields = (
                    self._game(name, args) if name in GAME_COMMANDS else self._render(name, args)
                )
            except Refusal as refusal:
                return self._error(request_id, refusal.code, str(refusal))
        return self._ok(request_id, fields)

    def _render(self, name: str, args: dict) -> dict:
        """The renderer and shader-loader answers, capture and selftest, from the model."""
        game = self.game
        if name == "ready":
            check = {"name": "fake", "holds": True, "seconds": 0.0, "gapFrames": 0}
            return {
                "seconds": args["minSeconds"],
                "predicateSeconds": 0.0,
                "limitedBy": "stableFrames",
                "rendererCheck": check,
                "frames": args["stableFrames"],
            }
        if name == "shaders.reload":
            # Answered once the new pipeline rendered framesAfter frames, as the mod does.
            game["reloadFrame"] = self._frame
            self._frame += args["framesAfter"] + 1
            self._frames = itertools.count(self._frame + FRAMES_PER_CALL, FRAMES_PER_CALL)
            self.emit("reload.done", {"pack": game["pack"], "pipeline": "Fake", "seconds": 0.0})
            return {
                "pack": game["pack"],
                "pipeline": "Fake",
                "seconds": 0.0,
                "framesAfter": args["framesAfter"],
                "reloadFrame": game["reloadFrame"],
            }
        if name == "shaders.options":
            return {"pack": game["pack"], "values": dict(game["options"])}
        if name == "selftest":
            return {"pass": True, "checks": {check: {"pass": True} for check in SELFTEST_CHECKS}}
        return self._capture(args)

    def _capture(self, args: dict) -> dict:
        """frames.capture as the mod writes it: PNGs and capture.json in a new attempt folder."""
        for later in ("align", "flush", "after"):
            if args.get(later) not in (None, False):
                raise Refusal(
                    "unsupported",
                    f"frames.capture.{later} is not built in this mod (align M3, flush M5)",
                )
        directory = Path(args["directory"])
        if not directory.is_absolute():
            raise Refusal("bad-request", f"frames.capture.directory {directory} is not absolute")
        if "every" in args and "intervalMs" in args:
            raise Refusal("bad-request", "frames.capture takes every or intervalMs, not both")
        folder = attempt_folder(directory)
        frames = []
        for n in range(1, args["count"] + 1):
            name = f"frame-{n:05d}.png"
            data = png(FRAME_SIZE, FRAME_SIZE, bytes([n % 256, 0, 0, 255]) * FRAME_SIZE**2)
            (folder / name).write_bytes(data)
            index = self._frame + (n - 1) * args.get("every", 1)
            frames.append(
                {
                    "name": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "frameIndex": index,
                    "sinceReload": index - self.game["reloadFrame"],
                    "qpcNs": index * 7_000_000,
                    "swapQpcNs": index * 7_000_000 - 1_000_000,
                }
            )
        manifest = {
            "schema": 1,
            "complete": True,
            "stopped": None,
            "count": args["count"],
            **(
                {"intervalMs": args["intervalMs"]}
                if "intervalMs" in args
                else {"every": args.get("every", 1)}
            ),
            "frames": frames,
            "dropped": [],
        }
        path = folder / modclient.MANIFEST
        path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        return {"frames": frames, "dropped": [], "manifest": str(path)}

    def _game(self, name: str, args: dict) -> dict:
        """The game adapter's answers from the model."""
        game = self.game
        pose = game["pose"]
        if name == "state":
            return {
                "inWorld": True,
                "dimension": pose["dimension"],
                "gamemode": game["gamemode"],
                "screen": None,
                "paused": False,
                "focused": game["focused"],
                "tick": game["tick"],
            }
        if name == "world.wait":
            return {"pose": dict(pose), "time": game["time"], "joinedQpcNs": 0}
        if name == "command":
            text = args["text"].removeprefix("/")
            if text == "tick freeze":
                game["frozen"] = True
            return {"succeeded": True, "messages": [f"fake: {text}"], "failures": []}
        if name == "ticks.step":
            if not game["frozen"]:
                raise Refusal("failed", "ticks are not frozen; fix: command /tick freeze first")
            game["tick"] += args["n"]
            return {"ticks": args["n"]}
        if name == "camera.place":
            target = args.get("dimension", pose["dimension"])
            if target not in DIMENSIONS:
                raise Refusal("bad-request", f"camera.place.dimension {target} is no dimension")
            if not args["tpSemantics"] and not -90 <= args["pitch"] <= 90:
                raise Refusal("bad-request", f"camera.place.pitch {args['pitch']} lies outside")
            if target != pose["dimension"]:
                self.emit("dimension.changed", {"from": pose["dimension"], "to": target})
            game["pose"] = {"dimension": target, **{k: args[k] for k in modclient.POSE_KEYS}}
            return {"pose": dict(game["pose"]), "arrivedSeconds": 0.0}
        if name == "camera.get":
            eye = {"x": pose["x"], "y": pose["y"] + EYE_HEIGHT, "z": pose["z"]}
            return {"pose": dict(pose), "eye": eye}
        if name == "input.block":
            game["inputBlocked"] = args["on"]
            return {"on": args["on"]}
        for key in ("hideGui", "debugOverlay"):  # hud.set
            if key in args:
                game[key] = args[key]
        return {"hideGui": game["hideGui"], "debugOverlay": game["debugOverlay"]}


def socket_streams() -> tuple[modclient.Stream, modclient.Stream]:
    """Two connected in-memory streams (a socket pair): the client's end and the fake's."""
    import socket

    class SocketStream:
        def __init__(self, sock: socket.socket) -> None:
            self._sock = sock

        def read(self, size: int) -> bytes:
            try:
                return self._sock.recv(size)
            except OSError:
                return b""

        def write(self, data: bytes) -> None:
            self._sock.sendall(data)

        def close(self) -> None:
            with contextlib.suppress(OSError):
                self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()

    left, right = socket.socketpair()
    return SocketStream(left), SocketStream(right)


def serve_streams(fake: Fake) -> tuple[modclient.Stream, threading.Thread]:
    """The fake serving one end of a socket pair on a thread; the other end for a Client."""
    client, server = socket_streams()
    thread = threading.Thread(target=fake.serve, args=(server,), daemon=True)
    thread.start()
    return client, thread


class PipeService:
    """The fake on a real named pipe (Windows): the mod's flags and DACL, one client at a time,
    served again after each disconnect until stop()."""

    def __init__(self, fake: Fake, name: str) -> None:
        from optilux import winpipe

        self._winpipe = winpipe
        self.fake = fake
        self.name = name
        self.handle = winpipe.create_server(name)
        self._stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self._stopping.is_set():
            pipe = self._winpipe.accept(self.handle)
            if pipe is None:
                continue
            self.fake.quit.clear()
            self.fake.serve(pipe)

    def stop(self) -> None:
        self._stopping.set()
        api = self._winpipe.api()
        deadline = time.monotonic() + 5
        while self.thread.is_alive() and time.monotonic() < deadline:
            api.k32.CancelIoEx(self.handle, None)  # repeated: a connect may start after one
            self.thread.join(timeout=0.05)
        api.k32.CloseHandle(self.handle)


def log_lines(path: Path) -> list[dict]:
    """A request log's records."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
