"""Pre-launch files, the launch gate and the direct launch (platform.md#install-and-launch).

Every later phase starts the game through `launch`, so the options, the mods folder and the
started command line must be exactly what the run's identity says (docs/run-record.md#identity).
Before every launch: the gate refuses a running game and a leftover optilux-* ETW session and
records AMD's PresentMon (F2); the classpath jars, the asset index and the version JSON are hashed
against the launch spec and the packs against the platform file; game/mods/ is made to hold
exactly the tier's jars (P39); options.txt, sodium-options.json and config/iris.properties are
written from config/suite.json display (F3). The command is built from the spec and
config/java/bench.json, started, and its real command line read back with psutil and compared
(D17); the join is awaited in this session's latest.log (F11). With a token and the helper in
the store, the mod session follows the join (0.01.05): the pipe opened and its server pid,
DACL and single instance checked, `hello` answering the launched pid, frames.index advancing,
every request in a JSONL log under results/raw/ with the token redacted; the game then quits
through the mod's `quit`, and by WM_CLOSE without one (A1). Every side effect on the machine
goes through Host, which the tests replace.
"""

import ctypes
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import psutil

from optilux import modclient, platform
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, STORE, Say, shown

# The game folder under runtime/<platform>/ and what launch reads and writes in it.
GAME = "game"
MODS = "mods"
SAVES = "saves"
LEVEL = "level.dat"
PLAYERS = "players/data"
# The server names a player file by the player's UUID (spike L1: players/data/51ff11bb-....dat).
UUID_NAME = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OPTIONS = "options.txt"
SODIUM = "config/sodium-options.json"
IRIS = "config/iris.properties"
RESOURCE_PACKS = "resourcepacks"
SHADER_PACKS = "shaderpacks"
LOG = "logs/latest.log"
# The game's stdout and stderr: a JVM that fails before log4j starts leaves its reason only there.
STDOUT = "logs/stdout.log"

# The gate (F2, docs/roadmap.md#findings-assigned). The harness names its PresentMon sessions
# optilux-<run> (measurement.md#tools): one left by a killed run would record the next session.
OWN_SESSION = "optilux-"
# AMD Software starts its own PresentMon with every game (platform.md#mc-263-verified, AMD
# PresentMon): recorded, never stopped or waited on.
AMD_PROCESS = "presentmon-x64.exe"
AMD_SESSION = "RSXTraceSession"
# JVMs beside the game: a Gradle build's client (the wrapper, or the gradle command) blocks the
# gate; a daemon idles between builds (VS Code's Gradle extension keeps one) and is recorded with
# every other java process (VS Code's language server), as AMD's PresentMon is.
JAVA_NAMES = ("java.exe", "javaw.exe")
GRADLE_BUILD = ("org.gradle.wrapper.GradleWrapperMain", "org.gradle.launcher.GradleMain")
GRADLE_DAEMON = "org.gradle.launcher.daemon.bootstrap.GradleDaemon"
LOGMAN = ("logman", "query", "-ets")
# logman answered in under a second in the spike; a hung one must not hang the launch.
LOGMAN_TIMEOUT = 30
# A logman session row: the name (it may hold spaces, and a long one runs into the Type column
# with one space), then the one-word Type and Status columns.
SESSION_ROW = re.compile(r"^(?P<name>.+?)\s+\S+\s+\S+$")

# Fabric Loader 0.19.5 loads the regular, non-hidden files of mods/ whose name ends in `.jar` and
# does not start with a dot, one level deep (DirectoryModCandidateFinder in the pinned jar, walked
# with depth 1); launch removes every top-level jar but the tier's, whatever its case.
JAR = ".jar"
# Mods Fabric Loader provides itself: the log lists them beside the jars' mods (spike L1).
BUILTIN_MODS = ("fabricloader", "java", "minecraft")
# The helper's jar, copied into the store by `mod build` (0.01.04); absent until then.
HELPER_GLOB = "optilux-helper*.jar"

# The command (docs/platform.md#install-and-launch).
TOKEN_PROPERTY = "-Doptilux.token="  # noqa: S105 the property name, not a secret
# 32 random bytes as URL-safe base64: 43 characters of [A-Za-z0-9_-], inside the mod's token rule
# (32-128 characters of that alphabet, docs/plans/m1.md 0.01.04).
TOKEN_BYTES = 32
# The offline session (platform.md#mc-263-verified R9): --accessToken is required and any value
# passes; --offlineDeveloperMode takes no value.
ACCESS_TOKEN = "0"  # noqa: S105 a placeholder the offline session ignores
OFFLINE = "--offlineDeveloperMode"
# --clientId and --xuid name a Microsoft account. Main declares both with an optional argument and
# an empty default (the 26.3 client jar, read with javap), so the offline launch drops each pair
# instead of passing the unfilled placeholder the spike's L1 command carried.
DROPPED = ("clientid", "auth_xuid")
# The launcher properties are informational (crash reports); the harness version goes to the run
# record, so the command line stays a function of the spec and the profile.
LAUNCHER_NAME = "optilux"
LAUNCHER_VERSION = "0"
QUICK_PLAY = "is_quick_play_singleplayer"
# The bench machine is Windows (AGENTS.md): Java's classpath separator there.
CLASSPATH_SEPARATOR = ";"
PLACEHOLDER = re.compile(r"\$\{(\w+)\}")
# The JVM reads these before main and they never show on the command line, so they are dropped
# from the game's environment: the checked command line is then the whole of what the JVM got.
JAVA_ENV = ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")
# The game gets no console of its own and ignores the harness's Ctrl+C (Windows only; 0 elsewhere).
CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
    subprocess, "CREATE_NO_WINDOW", 0
)

# The join (F11): the spike joined in 18.4 s; 120 s is over 6x that, and only the modal Iris
# dialog ran longer (167 s, platform.md#mc-263-verified L2).
JOIN_TIMEOUT = 120.0
# The integrated server's line for the join (26.3, spike L1 and L2): "[03:28:01] [Server
# thread/INFO]: optilux[local:E:9375a0e8] logged in with entity id 11 at (-518.5, 75.0, -361.5)".
JOINED = re.compile(r"\]: (?P<name>[^\s\[]+)\[local:[^\]]*\] logged in with entity id \d+ at \(")
# Fabric Loader's list (spike L1): "Loading 54 mods:", then "\t- <id> <version>" per mod and an
# indented "|--" or "\--" line per mod nested in a jar.
MODS_HEADER = re.compile(r"\]: Loading \d+ mods:$")
TOP_MOD = re.compile(r"^\t- (\S+) \S+")
# WM_CLOSE ended the bench game in 1.9 s (L1) and the dev game in 17 s (L2's watchdog).
QUIT_TIMEOUT = 60.0
# The window exists seconds after the start, long before the join.
WINDOW_TIMEOUT = 10.0
WM_CLOSE = 0x0010
# latest.log, the window and the hold are polled; a quarter second bounds the join time's error.
POLL = 0.25

# The mod session (0.01.05). The request log of a launch goes beside the run records' raw
# artifacts (results/raw/ is ignored by git), one folder per launch.
RAW = "results/raw"
REQUESTS = "requests.jsonl"
# frames.index is asked every FRAMES_GAP until it advances, for at most FRAMES_TIMEOUT: right
# after the join Iris creates the pack's pipeline on the render thread and no frame renders
# (0.01.05's first launch: "Creating pipeline" at the join, the next frame 3 s later).
FRAMES_GAP = 0.5
FRAMES_TIMEOUT = 30.0
# An SDDL ACE: type;flags;rights;object guid;inherited guid;sid (and resource attributes).
SDDL_ACE = re.compile(r"\(([^)]*)\)")

# The two Sodium flags F3 writes (docs/roadmap.md#findings-assigned F3).
SODIUM_FLAGS = (
    ("notifications", "has_edited_fullscreen_option", True),
    ("performance", "use_no_error_g_l_context", False),
)


class LaunchError(RuntimeError):
    """A launch that cannot proceed or failed a check; the message names the problem and the fix."""


def quiet(text: str) -> None:
    pass


# The side effects.


@dataclass(frozen=True)
class ProcessInfo:
    """One running process as the gate sees it; a field psutil may not read is None."""

    pid: int
    name: str
    exe: str | None
    cwd: str | None
    cmdline: list[str]


class Process(Protocol):
    """What launch needs of a started game: subprocess.Popen's interface."""

    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


def processes() -> list[ProcessInfo]:
    """Every process psutil lists, fields it may not read (another user's, a protected one) None."""
    found = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cwd", "cmdline"]):
        info = proc.info
        found.append(
            ProcessInfo(
                info["pid"], info["name"] or "", info["exe"], info["cwd"], info["cmdline"] or []
            )
        )
    return found


def logman() -> str:
    """`logman query -ets`: the running ETW sessions; unelevated is enough (spike S6)."""
    try:
        done = subprocess.run(LOGMAN, capture_output=True, text=True, timeout=LOGMAN_TIMEOUT)  # noqa: S603 constant argv
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LaunchError(f"`{' '.join(LOGMAN)}` failed: {error}; fix: run it by hand") from None
    if done.returncode != 0:
        raise LaunchError(
            f"`{' '.join(LOGMAN)}` exited {done.returncode}: {done.stdout.strip()[-200:]}; fix: "
            "run it by hand"
        )
    return done.stdout


def windows_of(pid: int) -> list[int]:
    """The visible top-level windows of a process (user32 EnumWindows through ctypes)."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    visit_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [visit_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    found: list[int] = []

    def visit(hwnd: int, _: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(visit_type(visit), 0)
    return found


def post_close(hwnd: int) -> bool:
    """WM_CLOSE posted to a window, as its close button does: the game saves and exits."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


class Host:
    """The machine as launch uses it; the tests replace it."""

    def processes(self) -> list[ProcessInfo]:
        return processes()

    def logman(self) -> str:
        return logman()

    def start(self, command: list[str], cwd: Path, stdout: Path, env: dict[str, str]) -> Process:
        stdout.parent.mkdir(parents=True, exist_ok=True)
        with stdout.open("wb") as out:  # the child holds its own handle
            return subprocess.Popen(  # noqa: S603 argv list from the committed spec, no shell
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=CREATION_FLAGS,
            )

    def cmdline(self, pid: int) -> list[str]:
        return psutil.Process(pid).cmdline()

    def windows(self, pid: int) -> list[int]:
        return windows_of(pid)

    def close(self, hwnd: int) -> bool:
        return post_close(hwnd)

    def connect(self, token: str, pid: int, log: Path) -> modclient.Client:
        return modclient.connect(token, pid, log)

    def second_instance(self, name: str) -> int:
        from optilux import winpipe

        return winpipe.second_instance(name)

    def user_sid(self) -> str:
        from optilux import winpipe

        return winpipe.current_user_sid()

    def canonical_sid(self, text: str) -> str:
        from optilux import winpipe

        return winpipe.canonical_sid(text)

    def clock(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


# The gate.


def norm(path: str) -> str:
    """A Windows path for comparison: forward slashes, lower case, no trailing slash."""
    return path.replace("\\", "/").lower().rstrip("/")


def mentions(text: str, base: str) -> bool:
    """`text` names `base` (normed) or a path under it: the match ends at a path boundary, so
    runtime/mc-26.3 is not found in runtime/mc-26.30."""
    start = 0
    while (index := text.find(base, start)) >= 0:
        end = index + len(base)
        if end == len(text) or text[end] in '/;" ':
            return True
        start = index + 1
    return False


def etw_sessions(text: str) -> list[str]:
    """The session names of `logman query -ets`: the rows after the dashed rule, up to the first
    blank line."""
    lines = [line.rstrip() for line in text.splitlines()]
    rule = next((i for i, line in enumerate(lines) if line.startswith("---")), None)
    if rule is None:
        raise LaunchError(
            f"`{' '.join(LOGMAN)}` printed no session table; fix: run it by hand and check the "
            "gate's parser against its output"
        )
    names = []
    for line in lines[rule + 1 :]:
        if not line.strip():
            break
        match = SESSION_ROW.match(line.strip())
        if match:
            names.append(match.group("name"))
    return names


@dataclass
class Gate:
    """What the gate found: blocking games, sessions and Gradle builds; AMD's PresentMon and
    the other JVMs (recorded only)."""

    games: list[dict]
    sessions: list[str]
    amd: dict
    builds: list[dict] = field(default_factory=list)
    java: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.games and not self.sessions and not self.builds


def amd_facts(procs: Iterable[ProcessInfo], sessions: list[str]) -> dict:
    """AMD Software's PresentMon processes and its RSXTraceSession (F2): recorded, never stopped."""
    found = [
        {"pid": p.pid, "exe": p.exe, "cmdline": " ".join(p.cmdline)}
        for p in procs
        if p.name.lower() == AMD_PROCESS
    ]
    return {"presentMon": found, "rsxTraceSession": AMD_SESSION in sessions}


def gate(base: Path, procs: list[ProcessInfo], logman_text: str, own_pid: int) -> Gate:
    """No process may run from runtime/<platform>/ (its executable, working folder or any
    argument there) and no optilux-* ETW session may be running (F2)."""
    needle = norm(str(base))
    games = []
    for proc in procs:
        if proc.pid == own_pid:
            continue
        where = [
            ("exe", proc.exe and mentions(norm(proc.exe), needle)),
            ("cwd", proc.cwd and mentions(norm(proc.cwd), needle)),
            ("cmdline", any(mentions(norm(arg), needle) for arg in proc.cmdline)),
        ]
        hits = [name for name, hit in where if hit]
        if hits:
            games.append({"pid": proc.pid, "name": proc.name, "via": hits})
    sessions = etw_sessions(logman_text)
    own = [name for name in sessions if name.lower().startswith(OWN_SESSION)]
    blocking = {game["pid"] for game in games}
    java = [
        {"pid": proc.pid, "name": proc.name, "exe": proc.exe, "role": java_role(proc.cmdline)}
        for proc in procs
        if proc.name.lower() in JAVA_NAMES and proc.pid not in blocking and proc.pid != own_pid
    ]
    builds = [{"pid": j["pid"], "name": j["name"]} for j in java if j["role"] == "gradle build"]
    return Gate(games, own, amd_facts(procs, sessions), builds, java)


def java_role(cmdline: list[str]) -> str:
    """A JVM's role as the gate reads it from its main class."""
    if any(arg in GRADLE_BUILD for arg in cmdline):
        return "gradle build"
    if GRADLE_DAEMON in cmdline:
        return "gradle daemon"
    return "other"


# Hashes against the spec and the platform file.


def check_hash(path: Path, algorithm: str, pin: str, what: str, root: Path) -> None:
    """A file's digest against its pin; LaunchError naming the file, missing or different."""
    if not path.is_file():
        raise LaunchError(f"{what} {shown(path, root)} is missing; fix: run `optilux install`")
    actual = platform.digest(path, algorithm)
    if actual != pin:
        raise LaunchError(
            f"{what} {shown(path, root)}: {algorithm} {actual} differs from {pin}; fix: run "
            "`optilux install`, which names the pin it breaks"
        )


def check_spec_files(root: Path, base: Path, plat: platform.Platform, spec: dict) -> str:
    """Every classpath jar, the asset index and Mojang's version JSON against the spec; the
    version's type (`--versionType`), read from that JSON."""
    for entry in spec["classpath"]:
        check_hash(base / entry["path"], "sha1", entry["sha1"], "classpath jar", root)
    index = spec["assetIndex"]
    path = base / "assets" / "indexes" / f"{index['id']}.json"
    check_hash(path, "sha1", index["sha1"], "asset index", root)
    path = base / "versions" / plat.minecraft / f"{plat.minecraft}.json"
    check_hash(path, "sha1", spec["sources"]["versionJson"]["sha1"], "version JSON", root)
    return json.loads(path.read_text(encoding="utf-8"))["type"]


def reference_pack(plat: platform.Platform) -> platform.Pinned:
    """The one reference pack: the shader pack every M1 launch runs, unmodified."""
    packs = [p for p in plat.tier_files("bench") if p.kind == "referencePack"]
    if len(packs) != 1:
        raise LaunchError(
            f"{plat.path.name} lists {len(packs)} reference packs; fix: launch knows one"
        )
    return packs[0]


def check_packs(root: Path, base: Path, plat: platform.Platform, tier: str) -> list[dict]:
    """The tier's resource packs and the reference pack in their game folders, by sha512."""
    found = []
    for pinned in plat.tier_files(tier):
        if pinned.game_folder is None:
            continue
        check_hash(
            base / pinned.game_folder / pinned.file, "sha512", pinned.sha512, pinned.kind, root
        )
        found.append({"file": pinned.file, "kind": pinned.kind, "sha512": pinned.sha512})
    return found


# game/mods/.


@dataclass
class Mods:
    """game/mods/ after placement: the jars by name with their sha512 and state (kept, copied),
    the jars removed, and the sorted sha512 list (docs/run-record.md#identity)."""

    placed: list[dict]
    removed: list[str]
    helper: str | None
    sha512: list[str] = field(default_factory=list)


def store_helper(store: Path) -> Path | None:
    """The helper's jar in the store; None before `mod build` copies one there (0.01.04)."""
    found = sorted(store.glob(HELPER_GLOB))
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise LaunchError(f"the store holds {len(found)} helper jars ({names}); fix: keep one")
    return found[0] if found else None


def place_mods(root: Path, base: Path, plat: platform.Platform, tier: str) -> Mods:
    """Make game/mods/ hold exactly the tier's jars plus the helper, copied from the store: every
    other top-level jar is removed (the folder is harness-owned, P39), a jar whose sha512 is off
    its pin replaced; every placed jar is re-hashed after."""
    store = base / STORE
    want = {p.file: p.sha512 for p in plat.tier_files(tier) if p.kind == "mod"}
    helper = store_helper(store)
    if helper is not None:
        want[helper.name] = platform.sha512(helper)  # pinned at build, not in the platform file
    folder = base / GAME / MODS
    folder.mkdir(parents=True, exist_ok=True)
    removed = []
    for entry in sorted(folder.iterdir()):
        if entry.is_file() and entry.name.lower().endswith(JAR) and entry.name not in want:
            entry.unlink()
            removed.append(entry.name)
    placed = []
    for name, pin in want.items():
        target = folder / name
        if target.is_file() and platform.sha512(target) == pin:
            placed.append({"file": name, "sha512": pin, "state": "kept"})
            continue
        source = store / name
        check_hash(source, "sha512", pin, "store jar", root)
        part = target.with_name(target.name + ".part")  # never a half jar under its name
        shutil.copyfile(source, part)
        os.replace(part, target)
        placed.append({"file": name, "sha512": pin, "state": "copied"})
    present = sorted(e.name for e in folder.iterdir() if e.is_file() and e.name.endswith(JAR))
    if present != sorted(want):
        raise LaunchError(
            f"game/mods/ holds {', '.join(present)} after placement, not "
            f"{', '.join(sorted(want))}; fix: close whatever writes there"
        )
    for name, pin in want.items():
        check_hash(folder / name, "sha512", pin, "placed jar", root)
    return Mods(placed, removed, helper.name if helper else None, sorted(want.values()))


def jar_mod_id(path: Path) -> str:
    """The Fabric mod id a jar declares in its fabric.mod.json."""
    try:
        with zipfile.ZipFile(path) as jar:
            return json.loads(jar.read("fabric.mod.json"))["id"]
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        raise LaunchError(
            f"{path.name} declares no Fabric mod id ({error}); fix: re-pin it"
        ) from None


# The pre-launch files.


def written_options(display: dict, overrides: dict[str, str]) -> dict[str, str]:
    """The options.txt keys launch writes: suite.json display.optionsTxt with the `--set`
    overrides applied; an override of a key the suite does not write is refused, and so is a
    value that is not one printable line (a line break would write another key)."""
    written = dict(display["optionsTxt"])
    unknown = [key for key in overrides if key not in written]
    if unknown:
        raise LaunchError(
            f"--set {', '.join(unknown)}: not an option the suite writes; fix: one of "
            f"{', '.join(written)}"
        )
    for key, value in overrides.items():
        if not value.isprintable():
            raise LaunchError(f"--set {key}={value!r} is not one printable line; fix: retype it")
    written.update(overrides)
    return written


def options_text(existing: str | None, written: dict[str, str]) -> str:
    """options.txt with every written key at its value: a key the game wrote keeps its line's
    place (a later duplicate, which the game would read last, is dropped), a missing key is
    appended in the written order, every other line stays as the game wrote it; LF."""
    lines: list[str] = []
    seen: set[str] = set()
    for line in (existing or "").splitlines():
        key = line.split(":", 1)[0]
        if ":" in line and key in written:
            if key not in seen:
                lines.append(f"{key}:{written[key]}")
                seen.add(key)
            continue
        lines.append(line)
    lines += [f"{key}:{value}" for key, value in written.items() if key not in seen]
    return "\n".join(lines) + "\n"


def options_values(text: str) -> dict[str, str]:
    """options.txt as Minecraft reads it: lines split at their first colon, the last one wins."""
    found = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            found[key] = value
    return found


def sodium_text(options: dict) -> str:
    """sodium-options.json as Sodium 0.9.2 writes it (Gson pretty printing: a two-space indent,
    LF, no final newline; the spike's file is this text byte for byte)."""
    return json.dumps(options, indent=2)


def sodium_file(display: dict) -> tuple[str, str]:
    """The Sodium file launch writes and its sha256, refused unless that hash is the suite's
    display.sodiumOptions and both F3 flags are set."""
    options = display["sodiumOptionsFile"]
    for section, key, value in SODIUM_FLAGS:
        if options.get(section, {}).get(key) is not value:
            raise LaunchError(
                f"suite.json display.sodiumOptionsFile {section}.{key} is not {json.dumps(value)} "
                "(F3); fix: set it"
            )
    text = sodium_text(options)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != display["sodiumOptions"]:
        raise LaunchError(
            f"sodium-options.json as written hashes {digest}, suite.json display.sodiumOptions "
            f"says {display['sodiumOptions']}; fix: after a deliberate change, record the new hash "
            "(it is identity)"
        )
    return text, digest


def iris_properties(display: dict, tier: str, pack: str) -> dict[str, str]:
    """config/iris.properties' keys: the pack, then suite.json display.irisProperties with the
    tier's overrides (display.irisTiers)."""
    found = {"shaderPack": pack, **display["irisProperties"]}
    found.update(display.get("irisTiers", {}).get(tier, {}))
    for key, value in found.items():
        if not (value.isascii() and value.isprintable() and value == value.strip()):
            raise LaunchError(f"iris.properties {key}={value!r} would need escaping; fix: rename")
        if "\\" in value:
            raise LaunchError(f"iris.properties {key}={value!r} holds a backslash; fix: rename")
    return found


def iris_text(properties: dict[str, str]) -> str:
    """config/iris.properties as launch writes it: one key=value line per key, LF. Iris adds its
    other keys at their defaults and a dated comment when it rewrites the file (spike R4)."""
    return "".join(f"{key}={value}\n" for key, value in properties.items())


def properties_values(text: str) -> dict[str, str]:
    """A properties file as Iris writes it: key=value lines, # comments."""
    found = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith(("#", "!")) and "=" in line:
            key, value = line.split("=", 1)
            found[key.strip()] = value.strip()
    return found


@dataclass
class Prelaunch:
    """The three files as written: every options.txt key (overrides included) and the
    overrides alone, the Sodium file and its sha256, the iris.properties keys."""

    options: dict[str, str]
    overrides: dict[str, str]
    sodium: str
    sodium_sha256: str
    iris: dict[str, str]


def prelaunch(display: dict, tier: str, pack: str, overrides: dict[str, str]) -> Prelaunch:
    """The three files' contents, checked before anything is written: the options with the
    overrides, the Sodium file against its hash, the Iris keys."""
    sodium, digest = sodium_file(display)
    return Prelaunch(
        written_options(display, overrides),
        dict(overrides),
        sodium,
        digest,
        iris_properties(display, tier, pack),
    )


def write_prelaunch(game: Path, pre: Prelaunch) -> dict:
    """options.txt (over the game's own lines), sodium-options.json and config/iris.properties
    written before the launch; the options file as the game will read it: its sha256 and every
    key the harness does not write, with its value (run-record.md#identity, `recorded`)."""
    path = game / OPTIONS
    existing = path.read_text(encoding="utf-8") if path.is_file() else None
    (game / SODIUM).parent.mkdir(parents=True, exist_ok=True)
    text = options_text(existing, pre.options)
    path.write_bytes(text.encode("utf-8"))
    (game / SODIUM).write_bytes(pre.sodium.encode("utf-8"))
    (game / IRIS).write_bytes(iris_text(pre.iris).encode("utf-8"))
    unwritten = {k: v for k, v in options_values(text).items() if k not in pre.options}
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "unwritten": unwritten}


def read_back(game: Path, pre: Prelaunch) -> dict:
    """The files after the quit against what was written: every options.txt key (each one is
    identity, F3's two included), the iris.properties keys, the two Sodium flags, and Sodium's
    file still the written text (its hash is identity)."""
    read = options_values((game / OPTIONS).read_text(encoding="utf-8"))
    moved = {
        key: {"written": value, "read": read.get(key)}
        for key, value in pre.options.items()
        if read.get(key) != value
    }
    iris = properties_values((game / IRIS).read_text(encoding="utf-8"))
    iris_moved = {
        key: {"written": value, "read": iris.get(key)}
        for key, value in pre.iris.items()
        if iris.get(key) != value
    }
    sodium_bytes = (game / SODIUM).read_bytes()
    sodium = json.loads(sodium_bytes)
    flags = {
        f"{section}.{key}": sodium.get(section, {}).get(key)
        for section, key, value in SODIUM_FLAGS
        if sodium.get(section, {}).get(key) is not value
    }
    same = sodium_bytes == pre.sodium.encode("utf-8")
    return {
        "ok": not moved and not iris_moved and not flags and same,
        "options": {"keys": len(pre.options), "moved": moved},
        "iris": {"keys": len(pre.iris), "moved": iris_moved},
        "sodium": {"flagsMoved": flags, "sameText": same},
    }


# The command.


def substitute(argument: str, values: dict[str, str]) -> str:
    """A template argument with its ${name} placeholders filled; LaunchError for one launch does
    not know (a new spec fact)."""

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise LaunchError(
                f"the launch spec's argument {argument!r} needs ${{{name}}}, which launch does not "
                "fill; fix: teach optilux/launch.py the placeholder (a platform change)"
            )
        return values[name]

    return PLACEHOLDER.sub(fill, argument)


def game_arguments(template: list[str], values: dict[str, str]) -> list[str]:
    """The spec's game-argument template filled, each DROPPED placeholder removed with its flag."""
    found: list[str] = []
    for argument in template:
        if any(name in DROPPED for name in PLACEHOLDER.findall(argument)):
            if found and found[-1].startswith("--"):
                found.pop()
            continue
        found.append(substitute(argument, values))
    return found


def heap_arguments(java_profile: dict) -> list[str]:
    """-Xms and -Xmx from config/java/bench.json (equal, in MiB), then its flags."""
    heap = java_profile["heap"]
    if heap.get("unit") != "MiB" or not heap.get("xmsEqualsXmx"):
        raise LaunchError("bench.json's heap is not Xms = Xmx in MiB; fix: launch writes only that")
    return [f"-Xms{heap['size']}m", f"-Xmx{heap['size']}m", *java_profile.get("flags", [])]


def build_command(
    spec: dict,
    java_profile: dict,
    java: Path,
    base: Path,
    world: str,
    username: str,
    uuid: str,
    token: str | None,
    version_type: str,
) -> list[str]:
    """The game's command: Temurin's java, bench.json's heap and flags, the token, the spec's
    JVM options, the main class (KnotClient), the game-argument template, quickPlay, offline."""
    profile_id = spec["sources"]["fabricProfile"]["id"]
    values = {
        "natives_directory": str(base / "versions" / profile_id / "natives"),
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": LAUNCHER_VERSION,
        "classpath": CLASSPATH_SEPARATOR.join(str(base / e["path"]) for e in spec["classpath"]),
        "auth_player_name": username,
        "version_name": profile_id,
        "game_directory": str(base / GAME),
        "assets_root": str(base / "assets"),
        "assets_index_name": spec["assetIndex"]["id"],
        "auth_uuid": uuid,
        "auth_access_token": ACCESS_TOKEN,
        "version_type": version_type,
        "quickPlaySingleplayer": world,
    }
    command = [str(java), *heap_arguments(java_profile)]
    if token is not None:
        command.append(TOKEN_PROPERTY + token)
    command += [substitute(argument, values) for argument in spec["jvmOptions"]]
    command.append(spec["mainClass"])
    command += game_arguments(spec["gameArguments"], values)
    command += [substitute(argument, values) for argument in spec["featureArguments"][QUICK_PLAY]]
    command.append(OFFLINE)
    return command


def redact(command: list[str]) -> list[str]:
    """The command with the token's value hidden: it is fresh per launch and never identity."""
    return [
        TOKEN_PROPERTY + "<redacted>" if argument.startswith(TOKEN_PROPERTY) else argument
        for argument in command
    ]


def check_command(started: list[str], built: list[str]) -> list[str]:
    """Every difference between the started command line and the built one, the token's value
    excepted (only its presence must agree); empty when equal."""
    found = []
    if len(started) != len(built):
        found.append(f"{len(started)} arguments started, {len(built)} built")
    for index, (got, want) in enumerate(zip(redact(started), redact(built), strict=False)):
        if got != want:
            found.append(f"argument {index}: started {got!r}, built {want!r}")
    return found


def command_facts(
    started: list[str], spec: dict, java_profile: dict, java: Path, base: Path
) -> list[str]:
    """The started command line against the profile and the spec directly, so a builder bug
    cannot pass by agreeing with itself: the java, the heap and flags, the main class once, the
    classpath in the spec's order."""
    found = []
    if not started or norm(started[0]) != norm(str(java)):
        found.append(f"java is {started[0] if started else None!r}, not {str(java)!r}")
    found += [
        f"{argument} appears {started.count(argument)} times, not once"
        for argument in heap_arguments(java_profile)
        if started.count(argument) != 1
    ]
    heap = [a for a in started if a.startswith(("-Xms", "-Xmx"))]
    if len(heap) != 2:
        found.append(f"heap arguments {heap}, not bench.json's two")
    if started.count(spec["mainClass"]) != 1:
        found.append(f"main class {spec['mainClass']} appears {started.count(spec['mainClass'])}x")
    paths = [norm(str(base / entry["path"])) for entry in spec["classpath"]]
    if "-cp" not in started or started.index("-cp") + 1 >= len(started):
        found.append("no -cp argument")
    else:
        got = [norm(p) for p in started[started.index("-cp") + 1].split(CLASSPATH_SEPARATOR)]
        if len(got) != len(paths):
            found.append(f"the classpath holds {len(got)} entries, not the spec's {len(paths)}")
        elif got != paths:
            index = next(i for i, (a, b) in enumerate(zip(got, paths, strict=True)) if a != b)
            found.append(f"classpath entry {index} is {got[index]}, not the spec's {paths[index]}")
    return found


# The log.


@dataclass(frozen=True)
class LogMark:
    """latest.log before the start. log4j rolls a non-empty one over at startup and writes a new
    file (OnStartupTriggeringPolicy); should it append instead, this session's lines start at the
    marked size, and a rewrite in place shows as another head."""

    identity: tuple[int, int]
    size: int
    head: bytes


# The head a mark keeps: the first line's timestamp alone tells two sessions apart.
HEAD = 256


def log_mark(path: Path) -> LogMark | None:
    try:
        stat = path.stat()
        with path.open("rb") as handle:  # the game is not running yet: no rollover to block
            head = handle.read(HEAD)
    except FileNotFoundError:
        return None
    return LogMark((stat.st_dev, stat.st_ino), stat.st_size, head)


def session_text(path: Path, mark: LogMark | None) -> str | None:
    """This session's text of latest.log: a new file whole, the same file past the marked size
    (an append) or whole (rewritten in place); None while the marked file is untouched, which
    launch never opens then, so log4j's rename at startup cannot meet an open handle."""
    try:
        stat = path.stat()
        same = mark if mark is not None and (stat.st_dev, stat.st_ino) == mark.identity else None
        if same and stat.st_size == same.size:
            return None
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if same and len(data) >= same.size and data[: len(same.head)] == same.head:
        data = data[same.size :]
    return data.decode("utf-8", errors="replace")


def joined_line(text: str, username: str) -> str | None:
    """The server's line for the player's join, None before it."""
    for line in text.splitlines():
        match = JOINED.search(line)
        if match and match.group("name") == username:
            return line
    return None


def logged_mods(text: str) -> list[str] | None:
    """The top-level mod ids of Fabric Loader's list (nested mods left out); None before it."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if MODS_HEADER.search(line):
            found = []
            for item in lines[index + 1 :]:
                if not item.startswith("\t"):
                    break
                if match := TOP_MOD.match(item):
                    found.append(match.group(1))
            return found
    return None


def wait_join(
    process: Process,
    path: Path,
    mark: LogMark | None,
    username: str,
    host: Host,
    started: float,
    timeout: float = JOIN_TIMEOUT,
) -> tuple[float, str, list[str] | None]:
    """Wait for the join in this session's latest.log: (seconds since the start, the line,
    Fabric Loader's mod list). The list comes from the latest read that shows it, so one read
    mid-write is corrected by the next, and a midnight rollover (log4j's TimeBasedTriggeringPolicy)
    keeps the list read before it. LaunchError when the game exits first or the timeout passes
    (F11)."""
    mods = None
    while True:
        text = session_text(path, mark)
        if text is not None and (found := logged_mods(text)):
            mods = found
        line = joined_line(text, username) if text is not None else None
        if line is not None:
            return host.clock() - started, line, mods
        if process.poll() is not None:
            raise LaunchError(f"the game exited with code {process.returncode} before the join")
        if host.clock() - started >= timeout:
            raise LaunchError(f"no join in latest.log within {timeout:.0f} s (F11)")
        host.sleep(POLL)


# Ending the game.


def end(process: Process, host: Host) -> str:
    """End a started game that failed a check: WM_CLOSE when it has a window (the world is then
    saved), a kill when it has none or outlasts QUIT_TIMEOUT; how it ended."""
    if process.poll() is not None:
        return f"it had exited with code {process.returncode}"
    windows = host.windows(process.pid)
    for hwnd in windows:
        host.close(hwnd)
    if windows:
        try:
            return f"WM_CLOSE, exit code {process.wait(QUIT_TIMEOUT)}"
        except subprocess.TimeoutExpired:
            pass
    process.kill()
    try:
        process.wait(QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:  # said, never raised over the error that called end()
        return f"killed, still running after {QUIT_TIMEOUT:g} s"
    return "killed"


def quit_game(process: Process, host: Host) -> dict:
    """Quit by WM_CLOSE to the game's visible windows and wait for the exit: the code, the
    seconds from the post to the exit, the windows closed. LaunchError (the game killed) when it
    has no window or outlasts QUIT_TIMEOUT."""
    deadline = host.clock() + WINDOW_TIMEOUT
    while not (windows := host.windows(process.pid)):
        if process.poll() is not None:
            raise LaunchError(f"the game exited with code {process.returncode} before the quit")
        if host.clock() >= deadline:
            process.kill()
            raise LaunchError(f"the game shows no window in {WINDOW_TIMEOUT:.0f} s; it was killed")
        host.sleep(POLL)
    posted = host.clock()
    closed = sum(1 for hwnd in windows if host.close(hwnd))
    try:
        code = process.wait(QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        raise LaunchError(
            f"the game outlasted WM_CLOSE by {QUIT_TIMEOUT:.0f} s; it was killed"
        ) from None
    return {
        "how": "WM_CLOSE",
        "windows": closed,
        "exitCode": code,
        "seconds": host.clock() - posted,
    }


def hold(process: Process, host: Host, seconds: float) -> None:
    """Stay in the world for `seconds`, watching for an exit (a crash is a stop condition)."""
    until = host.clock() + seconds
    while host.clock() < until:
        if process.poll() is not None:
            raise LaunchError(f"the game exited with code {process.returncode} while held")
        host.sleep(min(POLL, max(until - host.clock(), 0)))


# The mod session.


def request_log(root: Path, now: datetime) -> Path:
    """This launch's request log: results/raw/launch-<UTC time>/requests.jsonl."""
    return root / RAW / f"launch-{now:%Y%m%d-%H%M%S}" / REQUESTS


def dacl_aces(sddl: str) -> list[dict]:
    """A DACL's ACEs from SDDL: type (A allow, D deny, ...), rights and SID each."""
    found = []
    for ace in SDDL_ACE.findall(sddl.split("S:", 1)[0]):
        fields = ace.split(";")
        found.append({"type": fields[0], "rights": fields[2], "sid": fields[5]})
    return found


def open_mod(
    launched: "Launched", root: Path, host: Host, say: Say, log: Path | None = None
) -> tuple[modclient.Client, dict]:
    """The mod's pipe after the join, checked from both sides: served by the launched pid, a
    DACL of one allow ACE for this user (D21), a second server instance refused; then `hello`
    answering the launched pid and frames.index advancing within FRAMES_TIMEOUT. Each check is
    said as it passes. The request log goes to `log` (a run's folder), else to this launch's
    folder. The open client and the facts; LaunchError (the client closed) when a check fails."""
    log = log or request_log(root, datetime.now(UTC))
    try:
        client = host.connect(launched.mod_token(), launched.pid, log)
    except modclient.ModError as error:
        raise LaunchError(str(error)) from None
    try:
        user = host.user_sid()
        aces = dacl_aces(client.dacl or "")
        found = [(a["type"], host.canonical_sid(a["sid"])) for a in aces]
        if found != [("A", user)]:
            raise LaunchError(f"the pipe's DACL is {client.dacl}, not one allow ACE for {user}")
        refused = host.second_instance(modclient.pipe_name(launched.mod_token()))
        if refused == 0:
            raise LaunchError("a second server instance of the mod's pipe was created")
        say(
            f"mod: pipe served by pid {client.server_pid} (the launched game); DACL "
            f"{client.dacl} (one allow ACE, this user); a second server instance refused "
            f"(Windows error {refused})"
        )
        hello = client.hello()
        versions = ", ".join(f"{k} {v}" for k, v in hello["versions"].items())
        say(
            f"mod: hello: protocol {hello['protocol']}, {hello['mod']['id']} "
            f"{hello['mod']['version']} on {hello['platform']} ({versions}), pid {hello['pid']}, "
            f"capabilities {', '.join(hello['capabilities'])}"
        )
        first = client.request("frames.index")
        asked = host.clock()
        while True:
            host.sleep(FRAMES_GAP)
            second = client.request("frames.index")
            if second["frameIndex"] > first["frameIndex"]:
                break
            if host.clock() - asked >= FRAMES_TIMEOUT:
                raise LaunchError(
                    f"frames.index stayed at {first['frameIndex']} for {FRAMES_TIMEOUT:g} s: no "
                    "frame was rendered"
                )
        waited = host.clock() - asked
        say(
            f"mod: frames.index {first['frameIndex']} -> {second['frameIndex']} after "
            f"{waited:.1f} s (qpcNs {first['qpcNs']} -> {second['qpcNs']})"
        )
    except (LaunchError, modclient.ModError, OSError, KeyError, TypeError) as error:
        client.close()
        malformed = isinstance(error, KeyError | TypeError)
        detail = f"a malformed answer ({error!r})" if malformed else str(error)
        raise LaunchError(f"the mod session: {detail}") from None
    except BaseException:
        client.close()
        raise
    facts = {
        "pipe": {
            "serverPid": client.server_pid,
            "dacl": client.dacl,
            "secondInstanceError": refused,
        },
        "hello": hello,
        "frames": {"first": first, "advanced": second, "seconds": round(waited, 2)},
        "requestLog": shown(log, root),
    }
    return client, facts


def quit_mod(client: modclient.Client, process: Process, host: Host) -> dict:
    """Quit through the mod: `quit` is answered, then the game stops as its close button makes
    it; the exit code and the seconds from the request to the exit. LaunchError (the game killed)
    when it outlasts QUIT_TIMEOUT."""
    asked = host.clock()
    try:
        client.request("quit")
    except modclient.ModError as error:
        raise LaunchError(f"quit: {error}") from None
    try:
        code = process.wait(QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        raise LaunchError(
            f"the game outlasted quit by {QUIT_TIMEOUT:.0f} s; it was killed"
        ) from None
    finally:
        client.close()
    return {"how": "quit", "exitCode": code, "seconds": host.clock() - asked}


def check_log(path: Path, token: str) -> dict:
    """The request log after the session: its lines, and the token absent from its bytes
    (docs/mod-protocol.md#client-rules); LaunchError when it is there."""
    data = path.read_bytes()
    if token.encode("utf-8") in data:
        raise LaunchError(
            f"{path.name} holds the token; fix: the redaction in optilux/modclient.py"
        )
    return {"lines": data.count(b"\n"), "bytes": len(data), "tokenAbsent": True}


# The launch.


def player_uuid(world: Path, fallback: str) -> tuple[str, str]:
    """`--uuid` (F8): the world's players/data/<uuid>.dat name when it holds one, else the
    platform file's offline UUID; (uuid, where it came from)."""
    folder = world / PLAYERS
    found = folder.glob("*.dat") if folder.is_dir() else []
    names = sorted(p.stem for p in found if UUID_NAME.fullmatch(p.stem))
    if len(names) > 1:
        raise LaunchError(
            f"{folder.name}/ in {world.name} holds {len(names)} player files; fix: keep the bench "
            "player's"
        )
    if names:
        return names[0], f"{PLAYERS}/{names[0]}.dat"
    return fallback, "offlinePlayer"


@dataclass
class Launched:
    """A started, joined game: its process, pid, token and latest.log, and the facts for the
    report and the run record (`settings` holds what the record needs of --no-token and --set)."""

    process: Process
    pid: int
    token: str | None
    log: Path
    game: Path
    prelaunch: Prelaunch
    facts: dict

    def mod_token(self) -> str:
        """The token the mod's pipe is named from; LaunchError for a --no-token launch, whose
        mod is inert."""
        if self.token is None:
            raise LaunchError("this launch ran with --no-token: the mod is inert, no pipe to open")
        return self.token


def launch(
    root: Path,
    world: str,
    tier: str = "bench",
    token: bool = True,
    overrides: dict[str, str] | None = None,
    say: Say = quiet,
    host: Host | None = None,
) -> Launched:
    """Start the current platform's game for `tier` in `world` after the gate, the hashes, the
    mods and the pre-launch files; check the started command line; wait for the join. A check
    that fails after the start ends the game and raises LaunchError."""
    host = host or Host()
    overrides = overrides or {}
    plat = platform.load(root)
    if tier not in plat.tiers:
        raise LaunchError(
            f"no tier {tier!r} in {plat.path.name}; fix: one of {', '.join(plat.tiers)}"
        )
    if pending := plat.pending(tier):
        raise LaunchError(f"tier {tier} lacks {'; '.join(pending)}; fix: launch another tier")
    spec = platform.load_spec(root, plat.id)
    if spec is None:
        raise LaunchError(f"no launch spec for {plat.id}; fix: run `optilux install`")
    base = root / RUNTIME / plat.id
    game = base / GAME
    if (
        Path(world).name != world
        or world in (".", "..")
        or not (game / SAVES / world / LEVEL).is_file()
    ):
        raise LaunchError(
            f"no world {world!r} under {shown(game / SAVES, root)}/ (quickPlay joins an existing "
            "world only); fix: name one, or create it in game (docs/plans/m1.md D23)"
        )
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    java_profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    java = root / JAVA_DIR / java_profile["runtime"]["build"] / "bin" / "java.exe"
    if not java.is_file():
        raise LaunchError(f"no {shown(java, root)}; fix: run `optilux install`")
    username = plat.data["offlinePlayer"]["name"]
    uuid, uuid_from = player_uuid(game / SAVES / world, plat.data["offlinePlayer"]["uuid"])
    pack = reference_pack(plat)
    pre = prelaunch(suite["display"], tier, pack.file, overrides)  # refused before any write
    # Iris.loadExternalShaderpack reads a pack's saved options from shaderpacks/<pack>.txt (the
    # 1.11.7 jar's bytecode): M1 runs the reference pack at its defaults (profile null).
    saved = base / GAME / SHADER_PACKS / f"{pack.file}.txt"
    if saved.exists():
        raise LaunchError(
            f"{shown(saved, root)} holds saved settings for {pack.file}, so it would not run at "
            "its defaults (profile null); fix: delete it (M2's profiles write the file themselves)"
        )
    began = host.clock()

    found = gate(base, host.processes(), host.logman(), os.getpid())
    if not found.ok:
        blocking = [f"pid {g['pid']} {g['name']} ({', '.join(g['via'])})" for g in found.games]
        blocking += [f"ETW session {name}" for name in found.sessions]
        blocking += [f"pid {b['pid']} {b['name']}: a Gradle build" for b in found.builds]
        raise LaunchError(
            f"the gate is closed: {'; '.join(blocking)} (F2); fix: quit that game, stop that "
            "session (never AMD's) or let the build finish"
        )
    say(gate_line(found, shown(base, root)))
    version_type = check_spec_files(root, base, plat, spec)
    packs = check_packs(root, base, plat, tier)
    say(
        f"hashes: {len(spec['classpath'])} classpath jars, asset index {spec['assetIndex']['id']} "
        f"and the version JSON sha1-equal to the spec; {len(packs)} packs sha512-equal"
    )
    mods = place_mods(root, base, plat, tier)
    say(mods_line(mods, tier))
    options_file = write_prelaunch(game, pre)
    say(
        f"pre-launch: options.txt ({len(pre.options)} keys"
        + (f", --set {', '.join(f'{k}={v}' for k, v in overrides.items())}" if overrides else "")
        + f"), sodium-options.json (sha256 {pre.sodium_sha256[:12]}...), iris.properties "
        f"({', '.join(f'{k}={v}' for k, v in pre.iris.items())})"
    )
    secret = secrets.token_urlsafe(TOKEN_BYTES) if token else None
    command = build_command(
        spec, java_profile, java, base, world, username, uuid, secret, version_type
    )
    log = game / LOG
    mark = log_mark(log)
    env = {key: value for key, value in os.environ.items() if key.upper() not in JAVA_ENV}
    prepared = host.clock() - began
    started_at = host.clock()
    try:
        process = host.start(command, game, game / STDOUT, env)
    except OSError as error:
        raise LaunchError(f"java did not start: {error}; fix: run `optilux install`") from None
    try:
        try:
            started = host.cmdline(process.pid)
        except psutil.Error as error:
            raise LaunchError(f"the started command line is unreadable ({error})") from None
        problems = check_command(started, command)
        problems += command_facts(started, spec, java_profile, java, base)
        if problems:
            raise LaunchError(f"the started command line differs: {'; '.join(problems)}")
        say(
            f"started pid {process.pid}: {len(started)} arguments, KnotClient, "
            f"{len(spec['classpath'])} jars, --quickPlaySingleplayer {world}, token "
            f"{'passed' if secret else 'absent (--no-token)'}; the command line read back equals "
            "the spec and bench.json"
        )
        seconds, line, logged = wait_join(process, log, mark, username, host, started_at)
        expected = sorted(
            {*BUILTIN_MODS, *(jar_mod_id(game / MODS / p["file"]) for p in mods.placed)}
        )
        if logged is None or sorted(logged) != expected:
            raise LaunchError(f"the log lists mods {logged}, not the {tier} set {expected}")
        try:
            amd_after = amd_facts(host.processes(), etw_sessions(host.logman()))
        except LaunchError as error:  # a record, never a reason to end a good session
            amd_after = {"problem": str(error)}
    except BaseException as error:
        how = end(process, host)
        if isinstance(error, LaunchError):
            raise LaunchError(f"{error}; the game was ended ({how})") from None
        raise
    say(f"joined in {seconds:.1f} s: {line.strip()}")
    say(f"log: the mods are the {tier} set ({', '.join(sorted(logged))})")
    say(f"AMD after the join (recorded, never stopped): {amd_text(amd_after)}")
    facts = {
        "platform": plat.id,
        "tier": tier,
        "world": world,
        "pid": process.pid,
        "log": shown(log, root),
        "stdout": shown(game / STDOUT, root),
        "uuid": {"value": uuid, "from": uuid_from},
        "gate": {
            "games": found.games,
            "sessions": found.sessions,
            "amd": found.amd,
            "java": found.java,
        },
        "amdAfterJoin": amd_after,
        "hashes": {
            "classpathJars": len(spec["classpath"]),
            "assetIndex": spec["assetIndex"]["id"],
            "versionJson": spec["sources"]["versionJson"]["sha1"],
            "packs": packs,
        },
        "mods": {
            "placed": mods.placed,
            "removed": mods.removed,
            "helper": mods.helper,
            "sha512": mods.sha512,
        },
        "logMods": sorted(logged),
        "settings": {
            "options": pre.options,
            "overrides": pre.overrides,
            "token": secret is not None,
            "sodiumOptions": pre.sodium_sha256,
            "iris": pre.iris,
        },
        "optionsFile": options_file,
        "command": {"arguments": redact(command), "check": "equal"},
        "join": {"seconds": round(seconds, 2), "line": line.strip()},
        "timings": {"prepareSeconds": round(prepared, 2), "joinSeconds": round(seconds, 2)},
    }
    return Launched(process, process.pid, secret, log, game, pre, facts)


def amd_text(amd: dict) -> str:
    """AMD Software's PresentMon as the report prints it (F2: recorded, never stopped)."""
    if "problem" in amd:
        return f"unread ({amd['problem']})"
    pm = ", ".join(f"PresentMon-x64.exe pid {p['pid']}" for p in amd["presentMon"])
    rsx = "RSXTraceSession running" if amd["rsxTraceSession"] else "no RSXTraceSession"
    return f"{pm or 'no PresentMon-x64.exe'}, {rsx}"


def gate_line(found: Gate, base: str) -> str:
    return (
        f"gate: open: no process from {base}/, no {OWN_SESSION}* ETW session; AMD (recorded, "
        f"never stopped): {amd_text(found.amd)}"
    )


def mods_line(mods: Mods, tier: str) -> str:
    states = ", ".join(f"{p['file']} ({p['state']})" for p in mods.placed)
    removed = f"; removed {', '.join(mods.removed)}" if mods.removed else "; nothing removed"
    helper = "" if mods.helper else "; optilux-helper not in the store yet (mod build, 0.01.04)"
    return f"mods: game/mods/ holds the {tier} set: {states}{removed}{helper}"
