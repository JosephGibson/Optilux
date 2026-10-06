"""The harness's client of the helper mod (docs/mod-protocol.md#client-rules).

`connect` opens the mod's pipe, named from the launch token, retrying until it exists, and refuses
a pipe served by any process but the launched game (GetNamedPipeServerProcessId, the client's
half of "both ends check each other", docs/mod.md#5-safety). A Client writes requests from any
thread and a reader thread matches the answers by id, so requests run concurrently and answers
may come in any order; events go to a queue. Timeouts nest: a request's wait exceeds the mod's
own timeoutSeconds and fits inside any outer wait; a wait that expires sends `cancel` and ends
the request, not the session. Every request, answer and event goes to a JSONL log with the
token redacted: the token is never written to a file. The checks of a request's arguments read
commands.json, the same table the mod and the fake read.
"""

import contextlib
import hashlib
import itertools
import json
import math
import queue
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from optilux import REPO_ROOT

# The command table (docs/mod.md#11-build-and-test), shipped in the mod's jar.
COMMANDS = Path("mod/src/main/resources/commands.json")
# The pipe's name (docs/mod-protocol.md#transport); the mod's PipeName derives the same.
PIPE_PREFIX = "\\\\.\\pipe\\optilux-"
PIPE_SALT = "optilux-pipe:"
PIPE_HEX = 32
REDACTED = "<redacted>"
# The pipe exists from the mod's entrypoint on, seconds before the join; 30 s covers a slow start.
CONNECT_TIMEOUT = 30.0
# A command without timeoutSeconds is answered from the mod's memory or the next frame (hello,
# frames.index, quit): 10 s is far past any of them and short of a hung session.
DEFAULT_WAIT = 10.0
# The client waits this much longer than the mod's own timeoutSeconds, so the mod's `timeout`
# answer arrives before the client gives up (docs/mod-protocol.md#client-rules).
MARGIN = 5.0
# One read takes at most this many bytes from the pipe.
READ_BYTES = 64 * 1024
# The mod refuses a longer line with id null (docs/mod-protocol.md#transport); the client refuses
# it before sending, so the refusal cannot turn into a timeout.
MAX_LINE = 1 << 20
# An id is an integer the mod reads as a Java long, or a string of 1 to 64 characters.
ID_RANGE = (-(2**63), 2**63 - 1)


class ModError(RuntimeError):
    """A session with the mod that cannot go on as asked; the message names the fix."""


class ModRefused(ModError):
    """The mod answered ok false: its error code and message."""

    def __init__(self, command: str, code: str, message: str) -> None:
        super().__init__(f"{command}: {code}: {message}")
        self.code = code
        self.message = message


class ModTimeout(ModError):
    """No answer within the client's wait; `cancel` was sent."""


class ModGone(ModError):
    """The pipe closed before the answer."""


class Stream(Protocol):
    """A byte stream: winpipe.Pipe on Windows, a socket pair in tests."""

    def read(self, size: int) -> bytes: ...
    def write(self, data: bytes) -> None: ...
    def close(self) -> None: ...


def pipe_name(token: str) -> str:
    """\\\\.\\pipe\\optilux- and the first 32 hex digits of SHA-256("optilux-pipe:" + token)."""
    digest = hashlib.sha256((PIPE_SALT + token).encode("utf-8")).hexdigest()
    return PIPE_PREFIX + digest[:PIPE_HEX]


def load_commands(root: Path = REPO_ROOT) -> dict:
    """commands.json as a dict, its commands keyed by name in the table's order."""
    data = json.loads((root / COMMANDS).read_text(encoding="utf-8"))
    data["byName"] = {command["name"]: command for command in data["commands"]}
    return data


def strict_json(text: str) -> Any:
    """One JSON value as the protocol allows it: no NaN or Infinity, no duplicate key."""

    def pairs(items: list[tuple[str, Any]]) -> dict:
        found: dict = {}
        for key, value in items:
            if key in found:
                raise ValueError(f"duplicate key {key!r}")
            found[key] = value
        return found

    def constant(name: str) -> Any:
        raise ValueError(f"{name} is not JSON")

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    check_text(value)
    return value


def check_text(value: Any) -> None:
    """No lone surrogate in any string or key (an escape such as \\ud800 is no Unicode text)."""
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("a lone surrogate in a string") from None
    elif isinstance(value, dict):
        for key, item in value.items():
            check_text(key)
            check_text(item)
    elif isinstance(value, list):
        for item in value:
            check_text(item)


def check_args(command: dict, args: Any) -> dict:
    """A request's arguments against commands.json, as the mod checks them: an object, no
    unknown name, the required present, each of its type and in range; the defaults filled.
    ValueError names the problem (the mod answers bad-request)."""
    name = command["name"]
    if not isinstance(args, dict):
        raise ValueError(f"{name}: args must be an object")
    unknown = [key for key in args if key not in command["args"]]
    if unknown:
        takes = ", ".join(command["args"]) or "none"
        raise ValueError(f"{name}: unknown argument {', '.join(unknown)}; it takes {takes}")
    checked = {}
    for arg, spec in command["args"].items():
        if arg not in args:
            if spec.get("required"):
                raise ValueError(f"{name}: missing argument {arg}")
            if "default" in spec:
                checked[arg] = spec["default"]
            continue
        checked[arg] = check_value(f"{name}.{arg}", spec, args[arg])
    return checked


def check_value(where: str, spec: dict, value: Any) -> Any:
    kind = spec["type"]
    if kind == "string":
        if not isinstance(value, str):
            raise ValueError(f"{where} must be a string")
        if not spec.get("minLength", 0) <= len(value) <= spec.get("maxLength", len(value)):
            raise ValueError(f"{where} is {len(value)} characters, out of its range")
        if "values" in spec and value not in spec["values"]:
            raise ValueError(f"{where} must be one of {', '.join(spec['values'])}")
    elif kind in ("integer", "number"):
        ok = isinstance(value, int) or kind == "number" and isinstance(value, float)
        if isinstance(value, bool) or not ok:
            raise ValueError(f"{where} must be {'an integer' if kind == 'integer' else 'a number'}")
        if kind == "integer" and not ID_RANGE[0] <= value <= ID_RANGE[1]:
            raise ValueError(f"{where} is outside the 64-bit range")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{where} is out of the double range")
        if "gt" in spec and not value > spec["gt"]:
            raise ValueError(f"{where} must be greater than {spec['gt']}")
        if not spec.get("min", value) <= value <= spec.get("max", value):
            raise ValueError(f"{where} is out of its range")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{where} must be true or false")
    elif kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{where} must be an object")
    elif kind == "array":
        if not isinstance(value, list):
            raise ValueError(f"{where} must be an array")
    elif kind == "id":
        check_id(where, value)
    else:
        raise ValueError(f"{where}: unknown type {kind}")
    return value


def check_id(where: str, value: Any) -> Any:
    """An id: an integer, or a string of 1 to 64 characters (docs/mod-protocol.md#envelope)."""
    if isinstance(value, str) and 1 <= len(value) <= 64:
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if not ID_RANGE[0] <= value <= ID_RANGE[1]:
            raise ValueError(f"{where} is outside the 64-bit range")
        return value
    raise ValueError(f"{where} must be an integer or a string of 1-64 characters")


def redacted(value: Any, token: str | None) -> Any:
    """`value` with every string equal to the token, and hello's token argument, replaced."""
    if isinstance(value, dict):
        found = {key: redacted(item, token) for key, item in value.items()}
        if found.get("cmd") == "hello" and isinstance(found.get("args"), dict):
            if "token" in found["args"]:
                found["args"] = {**found["args"], "token": REDACTED}
        return found
    if isinstance(value, list):
        return [redacted(item, token) for item in value]
    if token and isinstance(value, str) and token in value:
        return value.replace(token, REDACTED)
    return value


class RequestLog:
    """The run's JSONL request log (docs/mod-protocol.md#client-rules): one line per request,
    answer, event or note, the token redacted, and the written text checked for it as well."""

    def __init__(self, path: Path | None, token: str | None) -> None:
        self.path = path
        self._token = token
        self._lock = threading.Lock()
        self.lines = 0
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")

    def write(self, direction: str, message: Any) -> None:
        if self.path is None:
            return
        record = {
            "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "dir": direction,
            "message": redacted(message, self._token),
        }
        text = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        if self._token and self._token in text:  # never reached: redacted() replaced it
            text = text.replace(self._token, REDACTED)
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as out:
            out.write(text + "\n")
            self.lines += 1


class _Waiter:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.answer: dict | None = None


class Client:
    """A session with the mod over a stream: requests from any thread, answers matched by id,
    events queued. `expected_pid` is the launched game's: hello must answer with it."""

    def __init__(
        self,
        stream: Stream,
        token: str,
        log: Path | None = None,
        expected_pid: int | None = None,
        commands: dict | None = None,
    ) -> None:
        self._stream = stream
        self._token = token
        self.expected_pid = expected_pid
        self.commands = commands or load_commands()
        self.log = RequestLog(log, token)
        self.events: queue.Queue[dict] = queue.Queue()
        self.stray: list[dict] = []
        self._pending: dict[int, _Waiter] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._outer = threading.local()  # each thread's outer deadline (within())
        self._gone: str | None = None
        self._closing = False
        # Set by connect(): the pipe's server pid and its DACL as SDDL.
        self.server_pid: int | None = None
        self.dacl: str | None = None
        self._reader = threading.Thread(target=self._read, name="optilux-modclient", daemon=True)
        self._reader.start()

    @property
    def gone(self) -> str | None:
        """Why the stream ended, or None while it is open."""
        return self._gone

    def note(self, message: dict) -> None:
        """A harness fact for the request log (the connect, a check)."""
        self.log.write("note", message)

    @contextlib.contextmanager
    def within(self, seconds: float) -> Iterator[None]:
        """An outer wait: every request inside must be able to end within it."""
        previous = getattr(self._outer, "deadline", None)
        deadline = time.monotonic() + seconds
        self._outer.deadline = deadline if previous is None else min(previous, deadline)
        try:
            yield
        finally:
            self._outer.deadline = previous

    def request(self, command: str, args: dict | None = None, wait: float | None = None) -> dict:
        """Send one request and wait for its answer: the result, or ModRefused, ModTimeout (after
        sending `cancel`) or ModGone. ValueError before sending for a request commands.json
        refuses or a wait that does not nest."""
        spec = self.commands["byName"].get(command)
        if spec is None:
            raise ValueError(f"no command {command} in {COMMANDS.as_posix()}")
        args = dict(args or {})
        check_args(spec, args)
        own = args.get("timeoutSeconds")
        if wait is None:
            wait = own + MARGIN if own is not None else DEFAULT_WAIT
        if own is not None and wait <= own:
            raise ValueError(
                f"{command}: the client wait {wait:g} s must exceed timeoutSeconds {own:g} s"
            )
        outer = getattr(self._outer, "deadline", None)
        if outer is not None and wait >= outer - time.monotonic():
            raise ValueError(
                f"{command}: the client wait {wait:g} s does not fit the outer wait's "
                f"{max(outer - time.monotonic(), 0):.1f} s"
            )
        request_id = next(self._ids)
        message = {"id": request_id, "cmd": command, "args": args}
        line = encode(message)
        waiter = _Waiter()
        with self._lock:
            if self._gone is not None:
                raise ModGone(f"{command}: the pipe is closed ({self._gone})")
            self._pending[request_id] = waiter
        try:
            self._send(message, line)
        except OSError as error:
            with self._lock:
                self._pending.pop(request_id, None)
            raise ModGone(f"{command} {request_id}: the request was not sent ({error})") from None
        if not waiter.done.wait(wait):
            with self._lock:
                late = self._pending.pop(request_id, None) is None and waiter.done.is_set()
            if not late:
                cancel = {"id": next(self._ids), "cmd": "cancel", "args": {"id": request_id}}
                with contextlib.suppress(OSError):
                    self._send(cancel, encode(cancel))
                raise ModTimeout(
                    f"{command} {request_id}: no answer within {wait:g} s; cancel sent"
                )
        answer = waiter.answer
        if answer is None:
            raise ModGone(f"{command} {request_id}: the pipe closed first ({self._gone})")
        if answer.get("ok") is True:
            return answer["result"]
        error = answer.get("error") or {}
        raise ModRefused(command, str(error.get("code")), str(error.get("message")))

    def hello(self) -> dict:
        """`hello` with the token; ModError when it answers with another pid than the launched."""
        result = self.request("hello", {"token": self._token})
        if self.expected_pid is not None and result.get("pid") != self.expected_pid:
            raise ModError(
                f"hello answered pid {result.get('pid')}, not the launched {self.expected_pid}"
            )
        return result

    def next_event(self, timeout: float) -> dict | None:
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._closing = True
        self._stream.close()
        self._reader.join(timeout=5)

    def _send(self, message: dict, line: bytes) -> None:
        self.log.write("sent", message)
        with self._write_lock:
            self._stream.write(line)

    def _read(self) -> None:
        buffer = b""
        reason = "the mod closed the pipe"
        try:
            while chunk := self._stream.read(READ_BYTES):
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._dispatch(line)
        except OSError as error:
            reason = f"read failed: {error}"
        if self._closing:
            reason = "the client closed the pipe"
        with self._lock:
            self._gone = reason
            pending = list(self._pending.values())
            self._pending.clear()
        self.log.write("note", {"closed": reason})
        for waiter in pending:
            waiter.done.set()

    def _dispatch(self, line: bytes) -> None:
        try:
            message = strict_json(line.decode("utf-8"))
        except ValueError as error:  # UnicodeDecodeError is one
            self.log.write("received", {"unreadable": line.decode("utf-8", "replace")})
            self.stray.append({"unreadable": str(error)})
            return
        self.log.write("received", message)
        if not isinstance(message, dict):
            self.stray.append({"unreadable": message})
            return
        if "event" in message and "id" not in message:
            self.events.put(message)
            return
        with self._lock:
            waiter = self._pending.pop(message.get("id"), None)
        if waiter is None:
            self.stray.append(message)
            return
        waiter.answer = message
        waiter.done.set()


def encode(message: dict) -> bytes:
    """A request's line; ValueError for one the mod would refuse as too long."""
    text = json.dumps(message, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    data = text.encode("utf-8")
    if len(data) > MAX_LINE:
        raise ValueError(f"{message.get('cmd')}: the line is {len(data)} bytes, over {MAX_LINE}")
    return data + b"\n"


def connect(
    token: str,
    expected_pid: int | None,
    log: Path | None,
    timeout: float = CONNECT_TIMEOUT,
) -> Client:
    """The launched game's pipe: opened with retries until it exists, its server pid checked
    against the launched one before anything is sent (Windows only)."""
    from optilux import winpipe

    name = pipe_name(token)
    try:
        pipe = winpipe.open_client(name, timeout)
    except winpipe.PipeError as error:
        raise ModError(
            f"no connection to the mod: {error}; fix: read latest.log's optilux-helper lines"
        ) from None
    try:
        server = winpipe.server_pid(pipe)
        if expected_pid is not None and server != expected_pid:
            raise ModError(
                f"the pipe is served by pid {server}, not the launched {expected_pid}: another "
                "process holds the name; fix: find and end that process"
            )
        dacl = winpipe.dacl_sddl(pipe)
    except winpipe.PipeError as error:
        pipe.close()
        raise ModError(f"the mod's pipe: {error}") from None
    except BaseException:
        pipe.close()
        raise
    client = Client(pipe, token, log, expected_pid)
    client.server_pid = server
    client.dacl = dacl
    client.note({"connected": {"serverPid": server, "dacl": dacl}})
    return client
