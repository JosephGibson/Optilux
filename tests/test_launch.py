"""optilux.launch and `optilux launch` without a game: the three pre-launch writers give exact
bytes (LF) from config/suite.json; the gate on fake processes and logman's real output; the
command built from the committed launch spec has the spike's L1 shape; the started command line's
check and the log wait on fixtures, the timeout included; game/mods/ reconciled on a fixture
folder; a whole launch, hold, quit and read-back through a fake game. The tests marked `windows`
run user32, psutil and logman for real. Nothing here reads runtime/ or starts the game
(docs/plans/m1.md D19)."""

import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from optilux import REPO_ROOT, cli, launch, modclient, modfake, platform
from optilux.verbs import launch as launch_verb

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "launch"
# A trimmed latest.log of the spike's bench-tier launch L1 and `logman query -ets` on this machine
# (2026-10-06), both with their line endings normalized to LF by .gitattributes.
LOG = (FIXTURES / "latest.log").read_text(encoding="utf-8")
LOGMAN = (FIXTURES / "logman.txt").read_text(encoding="utf-8")
DISPLAY = json.loads((REPO_ROOT / "config" / "suite.json").read_text(encoding="utf-8"))["display"]
SPEC = json.loads(
    (REPO_ROOT / "config" / "platforms" / "mc-26.3.launch.json").read_text(encoding="utf-8")
)
BENCH = json.loads((REPO_ROOT / "config" / "java" / "bench.json").read_text(encoding="utf-8"))
UUID = "51ff11bb-8719-3a7c-b3f6-cb4a2d1c5a79"
TOKEN = "T" * 43
PLATFORM = "mc-fixture"
URLSAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

# The spike's L1 command (platform.md#mc-263-verified, L1 command line; its record lives under
# runtime/spike/), 41 arguments with the paths elided. launch builds this shape without the two
# unfilled account pairs, with the token and the harness's launcher name.
L1 = [
    "<java>",
    "-Xms6144m",
    "-Xmx6144m",
    "-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump",
    "-XX:StackShadowPages=32",
    "--enable-native-access=ALL-UNNAMED",
    "--add-exports",
    "java.base/jdk.internal.misc=ALL-UNNAMED",
    "-Djava.library.path=<natives>/java",
    "-Djna.tmpdir=<natives>/jna",
    "-Dorg.lwjgl.system.SharedLibraryExtractPath=<natives>/lwjgl",
    "-Dio.netty.native.workdir=<natives>/netty",
    "-Dminecraft.launcher.brand=optilux-spike",
    "-Dminecraft.launcher.version=0",
    "-cp",
    "<82 jars>",
    "-DFabricMcEmu= net.minecraft.client.main.Main ",
    "net.fabricmc.loader.impl.launch.knot.KnotClient",
    "--username",
    "optilux",
    "--version",
    "fabric-loader-0.19.5-26.3",
    "--gameDir",
    "<game>",
    "--assetsDir",
    "<assets>",
    "--assetIndex",
    "34",
    "--uuid",
    UUID,
    "--accessToken",
    "0",
    "--clientId",
    "${clientid}",
    "--xuid",
    "${auth_xuid}",
    "--versionType",
    "release",
    "--quickPlaySingleplayer",
    "spike",
    "--offlineDeveloperMode",
]

# options.txt as the game writes it (CRLF): suite keys at other values, one the game would read
# last, and keys the suite never writes.
GAME_OPTIONS = (
    "\r\n".join(
        [
            "version:4892",
            "ao:true",
            "renderDistance:12",
            "lastServer:",
            "fov:0.0",
            "renderDistance:8",
            "key_key.attack:key.mouse.left",
        ]
    )
    + "\r\n"
)


def sha1(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()  # Mojang's file sums


def sha512(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def jar(mod_id: str) -> bytes:
    """A jar holding a fabric.mod.json for `mod_id`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": mod_id}))
    return buffer.getvalue()


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def with_sessions(*names: str) -> str:
    """LOGMAN with more session rows, as logman pads them."""
    rows = "".join(f"{name:<40}Trace                         Running \n" for name in names)
    rule = "-" * 79 + "\n"
    return LOGMAN.replace(rule, rule + rows, 1)


def proc(pid: int, name: str, exe=None, cwd=None, cmdline=()) -> launch.ProcessInfo:
    return launch.ProcessInfo(pid, name, exe, cwd, list(cmdline))


def paths(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "runtime" / "mc-26.3"
    java = tmp_path / "runtime" / "java" / "jdk-25.0.4.1+1" / "bin" / "java.exe"
    return base, java


def build(tmp_path: Path, token: str | None = TOKEN) -> list[str]:
    base, java = paths(tmp_path)
    return launch.build_command(SPEC, BENCH, java, base, "spike", "optilux", UUID, token, "release")


# The pre-launch writers.


def test_options_txt_keeps_the_games_lines_and_writes_the_suites_keys() -> None:
    written = {"version": "5023", "renderDistance": "16", "fov": "0.5", "bobView": "false"}
    text = launch.options_text(GAME_OPTIONS, written)
    assert text.encode() == (
        b"version:5023\nao:true\nrenderDistance:16\nlastServer:\nfov:0.5\n"
        b"key_key.attack:key.mouse.left\nbobView:false\n"
    )
    assert launch.options_values(text)["renderDistance"] == "16"
    assert launch.options_values(GAME_OPTIONS)["renderDistance"] == "8"  # the game reads the last
    # A fresh game folder: the suite's keys alone, in its order.
    assert launch.options_text(None, written) == (
        "version:5023\nrenderDistance:16\nfov:0.5\nbobView:false\n"
    )


def test_the_written_options_are_the_suites_with_the_overrides() -> None:
    written = launch.written_options(DISPLAY, {})
    assert written == DISPLAY["optionsTxt"] and len(written) == 24
    assert (written["version"], written["graphicsPreset"]) == ("5023", '"custom"')
    # The game's default afk caps a session without input at 30 fps (0.01.11); minimized does not.
    assert written["inactivityFpsLimit"] == '"minimized"'
    assert "rawMouseInput" not in written  # 26.3 removed it (lessons.md#windows)
    over = launch.written_options(DISPLAY, {"maxFps": "120"})
    assert over["maxFps"] == "120" and list(over) == list(written)
    with pytest.raises(launch.LaunchError, match="--set nope: not an option the suite writes; fix"):
        launch.written_options(DISPLAY, {"nope": "1"})
    # A line break in a value would write a key the suite does not write.
    with pytest.raises(launch.LaunchError, match="is not one printable line; fix: retype it"):
        launch.written_options(DISPLAY, {"maxFps": "260\nrenderClouds:false"})


def test_sodium_options_are_sodiums_own_format_with_the_suites_hash() -> None:
    text, digest = launch.sodium_file(DISPLAY)
    assert digest == DISPLAY["sodiumOptions"] == hashlib.sha256(text.encode()).hexdigest()
    assert text.startswith('{\n  "quality": {\n    "hidden_fluid_culling": true,\n')
    assert text.endswith('\n    "has_edited_fullscreen_option": true\n  }\n}')  # no final newline
    assert "\r" not in text and json.loads(text)["performance"]["use_no_error_g_l_context"] is False
    flipped = json.loads(json.dumps(DISPLAY))
    flipped["sodiumOptionsFile"]["notifications"]["has_edited_fullscreen_option"] = False
    with pytest.raises(launch.LaunchError, match=r"has_edited_fullscreen_option is not true .F3."):
        launch.sodium_file(flipped)
    moved = json.loads(json.dumps(DISPLAY))
    moved["sodiumOptionsFile"]["quality"]["hidden_fluid_culling"] = False
    with pytest.raises(launch.LaunchError, match=r"hashes [0-9a-f]{64}, suite.json display.sodium"):
        launch.sodium_file(moved)


def test_iris_properties_are_written_fresh_per_tier() -> None:
    bench = launch.iris_properties(DISPLAY, "bench", "Ref.zip")
    assert launch.iris_text(bench).encode() == (
        b"shaderPack=Ref.zip\nenableShaders=true\nenableDebugOptions=false\n"
        b"disableUpdateMessage=true\nmaxShadowRenderDistance=32\n"
    )
    dev = launch.iris_properties(DISPLAY, "dev", "Ref.zip")
    assert dev["enableDebugOptions"] == "true" and list(dev) == list(bench)
    with pytest.raises(launch.LaunchError, match="holds a backslash"):
        launch.iris_properties(DISPLAY, "bench", "a\\b.zip")
    with pytest.raises(launch.LaunchError, match="would need escaping"):
        launch.iris_properties(DISPLAY, "bench", " leading.zip")
    rewritten = "shaderPack=Ref.zip\n#Tue Oct 06 03:36:05 ADT 2026\ncolorSpace=SRGB\n"
    assert launch.properties_values(rewritten) == {"shaderPack": "Ref.zip", "colorSpace": "SRGB"}


def test_the_pre_launch_files_and_their_read_back(tmp_path: Path) -> None:
    game = tmp_path / "game"
    write(game / "options.txt", GAME_OPTIONS.encode())
    pre = launch.prelaunch(DISPLAY, "bench", "Ref.zip", {"maxFps": "120"})
    assert (game / "options.txt").read_bytes() == GAME_OPTIONS.encode()  # nothing written yet
    launch.write_prelaunch(game, pre)
    options = (game / "options.txt").read_bytes()
    assert b"\r" not in options and options.startswith(
        b"version:5023\nao:true\nrenderDistance:16\n"
    )
    assert b"key_key.attack:key.mouse.left\nfullscreen:true\n" in options  # appended in order
    assert launch.options_values(options.decode())["maxFps"] == "120"
    assert (game / "config" / "sodium-options.json").read_text(encoding="utf-8") == pre.sodium
    assert pre.sodium_sha256 == DISPLAY["sodiumOptions"] and pre.overrides == {"maxFps": "120"}
    iris = (game / "config" / "iris.properties").read_bytes()
    assert iris.startswith(b"shaderPack=Ref.zip\nenableShaders=true\n")
    # The game saves options.txt with CRLF; Iris adds its keys and a dated comment: as written.
    write(game / "options.txt", options.replace(b"\n", b"\r\n"))
    write(game / "config" / "iris.properties", b"#Tue Oct 06\n" + iris + b"colorSpace=SRGB\n")
    back = launch.read_back(game, pre)
    assert back == {
        "ok": True,
        "options": {"keys": 24, "moved": {}},
        "iris": {"keys": 5, "moved": {}},
        "sodium": {"flagsMoved": {}, "sameText": True},
    }
    # Any written key, F3's two included (both are identity), an Iris key or a Sodium flag that
    # moved fails the read-back.
    text = options.decode().replace("exclusiveFullscreen:false", "exclusiveFullscreen:true")
    write(game / "options.txt", text.encode())
    back = launch.read_back(game, pre)
    assert not back["ok"] and back["options"]["moved"] == {
        "exclusiveFullscreen": {"written": "false", "read": "true"}
    }
    text = options.decode()
    write(game / "options.txt", text.replace("maxFps:120", "maxFps:60").encode())
    back = launch.read_back(game, pre)
    assert not back["ok"] and back["options"]["moved"] == {
        "maxFps": {"written": "120", "read": "60"}
    }
    write(game / "options.txt", options)
    write(game / "config" / "iris.properties", iris.replace(b"Ref.zip", b"(internal)"))
    back = launch.read_back(game, pre)
    assert not back["ok"] and list(back["iris"]["moved"]) == ["shaderPack"]
    write(game / "config" / "iris.properties", iris)
    sodium = json.loads(pre.sodium)
    sodium["performance"]["use_no_error_g_l_context"] = True
    write(game / "config" / "sodium-options.json", json.dumps(sodium).encode())
    back = launch.read_back(game, pre)
    assert not back["ok"] and back["sodium"] == {
        "flagsMoved": {"performance.use_no_error_g_l_context": True},
        "sameText": False,
    }


# The gate.


def test_etw_sessions_from_logmans_output() -> None:
    names = launch.etw_sessions(LOGMAN)
    assert len(names) == 25 and names[:2] == ["Eventlog-Security", "CimFSUnionFS-Filter"]
    # A long name runs into the Type column with one space.
    assert "Microsoft-Windows-Rdp-Graphics-RdpIdd-Trace" in names
    assert "MpWppCoreTracing-20261005-191136-00000003-100000000" in names
    assert launch.etw_sessions(LOGMAN.replace("\n", "\r\n")) == names
    assert launch.etw_sessions(with_sessions("Circular Kernel Context Logger"))[0] == (
        "Circular Kernel Context Logger"
    )
    with pytest.raises(launch.LaunchError, match="printed no session table"):
        launch.etw_sessions("Error: Access is denied.\n")


def test_the_gate_blocks_on_a_game_and_an_own_session_and_records_amd(tmp_path: Path) -> None:
    base, java = paths(tmp_path)
    classpath = f"{base / 'libraries' / 'a.jar'};{base / 'versions' / '26.3' / '26.3.jar'}"
    amd = proc(
        5,
        "PresentMon-x64.exe",
        "C:\\Program Files\\AMD\\CNext\\CNext\\PresentMon-x64.exe",
        None,
        ["PresentMon-x64.exe", "-session_name", "RSXTraceSession"],
    )
    procs = [
        proc(1, "java.exe", str(java), str(tmp_path), ["java", "-cp", classpath, "KnotClient"]),
        proc(2, "bash.exe", "C:\\Git\\bin\\bash.exe", str(base / "game").upper()),
        proc(3, "java.exe", str(base / "runtime" / "java-runtime-epsilon" / "bin" / "java.exe")),
        proc(4, "java.exe", str(java), None, ["--gameDir", str(tmp_path / "runtime" / "mc-26.30")]),
        amd,
        proc(6, "python.exe", sys.executable, str(base), []),  # the harness itself
        proc(7, "secure.exe"),  # a process psutil may not read
    ]
    found = launch.gate(base, procs, LOGMAN, own_pid=6)
    assert not found.ok and found.sessions == []
    assert found.games == [
        {"pid": 1, "name": "java.exe", "via": ["cmdline"]},
        {"pid": 2, "name": "bash.exe", "via": ["cwd"]},
        {"pid": 3, "name": "java.exe", "via": ["exe"]},
    ]
    assert found.amd == {
        "presentMon": [
            {
                "pid": 5,
                "exe": "C:\\Program Files\\AMD\\CNext\\CNext\\PresentMon-x64.exe",
                "cmdline": "PresentMon-x64.exe -session_name RSXTraceSession",
            }
        ],
        "rsxTraceSession": False,
    }
    # An optilux-* session blocks; AMD's process and session are recorded and never block (F2).
    found = launch.gate(base, [amd], with_sessions("optilux-a1", "RSXTraceSession"), own_pid=0)
    assert not found.ok and found.sessions == ["optilux-a1"] and found.amd["rsxTraceSession"]
    found = launch.gate(base, [amd], with_sessions("RSXTraceSession"), own_pid=0)
    assert found.ok and found.games == [] and len(found.amd["presentMon"]) == 1


# The command.


def elide(command: list[str], tmp_path: Path) -> list[str]:
    base, java = paths(tmp_path)
    natives = str(base / "versions" / "fabric-loader-0.19.5-26.3" / "natives")
    found = []
    for argument in command:
        if argument.count(";") == 81:
            argument = "<82 jars>"
        argument = argument.replace(str(java), "<java>").replace(natives, "<natives>")
        found.append(
            {str(base / "game"): "<game>", str(base / "assets"): "<assets>"}.get(argument, argument)
        )
    return found


def test_the_command_has_the_spikes_l1_shape(tmp_path: Path) -> None:
    command = build(tmp_path)
    base, java = paths(tmp_path)
    assert command[:4] == [str(java), "-Xms6144m", "-Xmx6144m", "-Doptilux.token=" + TOKEN]
    jars = command[command.index("-cp") + 1].split(";")
    assert jars == [str(base / entry["path"]) for entry in SPEC["classpath"]] and len(jars) == 82
    assert not any("${" in argument for argument in command)
    ours = elide([a for a in command if not a.startswith("-Doptilux.token=")], tmp_path)
    dropped = ("--clientId", "${clientid}", "--xuid", "${auth_xuid}")
    shape = [a.replace("optilux-spike", "optilux") for a in L1 if a not in dropped]
    assert ours == shape and len(command) == len(L1) - 4 + 1
    # --no-token: the same command without the token.
    assert build(tmp_path, token=None) == [a for a in command if not a.startswith("-Doptilux.")]


def test_placeholders_are_filled_dropped_or_refused() -> None:
    template = ["--a", "${x}", "--clientId", "${clientid}", "--xuid", "${auth_xuid}", "--b"]
    assert launch.game_arguments(template, {"x": "C:\\1"}) == ["--a", "C:\\1", "--b"]
    with pytest.raises(launch.LaunchError, match=r"needs \$\{new_fact\}, which launch does not"):
        launch.substitute("-D${new_fact}", {})
    with pytest.raises(launch.LaunchError, match="Xms = Xmx in MiB"):
        launch.heap_arguments({"heap": {"size": 6, "unit": "GiB", "xmsEqualsXmx": True}})


def test_the_started_command_line_is_checked(tmp_path: Path) -> None:
    base, java = paths(tmp_path)
    built = build(tmp_path)
    assert launch.check_command(built, built) == []
    assert launch.command_facts(built, SPEC, BENCH, java, base) == []
    # The token's value is excepted, its presence is not.
    other = ["-Doptilux.token=" + "U" * 43 if a.startswith("-Doptilux.") else a for a in built]
    assert launch.check_command(other, built) == []
    absent = [a for a in built if not a.startswith("-Doptilux.")]
    assert launch.check_command(absent, built)[0] == f"{len(built) - 1} arguments started, 38 built"
    # A changed argument is named by its index, the token's value never.
    moved = list(built)
    moved[2] = "-Xmx8192m"
    assert launch.check_command(moved, built) == [
        "argument 2: started '-Xmx8192m', built '-Xmx6144m'"
    ]
    assert launch.command_facts(moved, SPEC, BENCH, java, base) == [
        "-Xmx6144m appears 0 times, not once"
    ]
    # A builder that drops a jar agrees with itself; the spec catches it.
    short = list(built)
    index = built.index("-cp") + 1
    short[index] = ";".join(built[index].split(";")[:-1])
    assert launch.check_command(short, short) == []
    assert launch.command_facts(short, SPEC, BENCH, java, base) == [
        "the classpath holds 81 entries, not the spec's 82"
    ]
    # One jar swapped for another: named by its index.
    jars = built[index].split(";")
    swapped = list(built)
    swapped[index] = ";".join([*jars[:5], str(base / "libraries" / "other.jar"), *jars[6:]])
    assert launch.command_facts(swapped, SPEC, BENCH, java, base) == [
        f"classpath entry 5 is {launch.norm(str(base / 'libraries' / 'other.jar'))}, not the "
        f"spec's {launch.norm(jars[5])}"
    ]
    wrong = ["java.exe", *built[1:], SPEC["mainClass"]]
    assert launch.command_facts(wrong, SPEC, BENCH, java, base) == [
        f"java is 'java.exe', not {str(java)!r}",
        f"main class {SPEC['mainClass']} appears 2x",
    ]
    assert TOKEN not in json.dumps(launch.redact(built))


@pytest.mark.windows
def test_a_started_command_line_reads_back_equal_on_windows() -> None:
    """psutil parses the line Popen wrote (list2cmdline, then CommandLineToArgvW): launch's
    arguments come back equal, one with spaces and a trailing space included (P21)."""
    python = getattr(sys, "_base_executable", sys.executable)  # the venv's python is a redirector
    args = [
        python,
        "-c",
        "import time; time.sleep(30)",
        "-DFabricMcEmu= net.minecraft.client.main.Main ",
        "-cp",
        "C:\\a b\\x.jar;C:\\y\\fabric-api-0.161.0+26.3.jar",
        'say "hi"',
        "C:\\trailing\\",
        "--offlineDeveloperMode",
    ]
    child = subprocess.Popen(args, creationflags=launch.CREATION_FLAGS)  # noqa: S603 fixed argv
    try:
        assert launch.Host().cmdline(child.pid) == args
    finally:
        child.kill()
        child.wait(10)


# A child that shows one off-screen window that never takes focus, and exits 0 once WM_CLOSE has
# destroyed it (the STATIC class closes on WM_CLOSE).
WINDOW_CHILD = """
import ctypes, sys, time
from ctypes import wintypes
user32 = ctypes.WinDLL("user32")
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
    wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
    wintypes.UINT, wintypes.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
hwnd = user32.CreateWindowExW(0x08000080, "STATIC", "optilux-test", 0x90000000, -32000, -32000,
    16, 16, None, None, None, None)
if not hwnd:
    sys.exit(2)
message = wintypes.MSG()
deadline = time.monotonic() + 30
while user32.IsWindow(hwnd) and time.monotonic() < deadline:
    while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
        user32.DispatchMessageW(ctypes.byref(message))
    time.sleep(0.01)
sys.exit(0 if not user32.IsWindow(hwnd) else 3)
"""


@pytest.mark.windows
def test_wm_close_quits_a_real_window_through_user32() -> None:
    """windows_of finds the child's visible window and quit_game's WM_CLOSE ends it with exit 0;
    the test process itself owns no window."""
    assert launch.windows_of(os.getpid()) == []
    python = getattr(sys, "_base_executable", sys.executable)
    child = subprocess.Popen(  # noqa: S603 this interpreter and a constant script
        [python, "-c", WINDOW_CHILD], creationflags=launch.CREATION_FLAGS
    )
    try:
        facts = launch.quit_game(child, launch.Host())
        assert facts["how"] == "WM_CLOSE" and facts["windows"] == 1 and facts["exitCode"] == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(10)


@pytest.mark.windows
def test_logman_lists_sessions_on_this_machine() -> None:
    assert launch.etw_sessions(launch.logman())


# The log.


def test_the_join_and_the_mod_list_from_the_log() -> None:
    assert launch.joined_line(LOG, "optilux") == (
        "[03:28:01] [Server thread/INFO]: optilux[local:E:9375a0e8] logged in with entity id 11 "
        "at (-518.5, 75.0, -361.5)"
    )
    assert launch.joined_line(LOG, "someone") is None
    assert launch.joined_line(LOG.split("[03:28:01]")[0], "optilux") is None  # before the join
    bench = ["fabric-api", "fabricloader", "iris", "java", "minecraft", "sodium"]
    assert launch.logged_mods(LOG) == bench  # nested mods (|-- and \--) left out
    assert launch.logged_mods(LOG.replace("\n", "\r\n")) == bench
    assert launch.logged_mods(LOG.splitlines()[0]) is None


def test_only_this_sessions_log_counts(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "latest.log"
    assert launch.log_mark(log) is None and launch.session_text(log, None) is None
    old = LOG.encode()
    write(log, old)  # the previous session's file, its join included
    mark = launch.log_mark(log)
    assert mark.size == len(old) and mark.head == old[: launch.HEAD]
    assert launch.session_text(log, mark) is None
    # log4j's rollover at startup: the old file renamed, a new one written.
    log.rename(log.with_name("2026-10-06-1.log"))
    write(log, b"[17:10:00] [main/INFO]: Loading Minecraft 26.3 with Fabric Loader 0.19.5\n")
    assert launch.session_text(log, mark).startswith("[17:10:00]")
    # An append to the same file: only what follows the mark is this session's.
    write(log, old)
    mark = launch.log_mark(log)
    with log.open("ab") as handle:
        handle.write(b"[17:10:00] [main/INFO]: Loading Minecraft 26.3\n")
    assert launch.session_text(log, mark) == "[17:10:00] [main/INFO]: Loading Minecraft 26.3\n"
    # The same file rewritten in place (another head): all of it.
    with log.open("r+b") as handle:
        handle.write(b"[17:11:11]")
    assert launch.session_text(log, mark).startswith("[17:11:11]")
    # An empty file is not rolled over: everything appended is this session's.
    empty = tmp_path / "empty.log"
    write(empty, b"")
    mark = launch.log_mark(empty)
    write(empty, LOG.encode())
    assert launch.session_text(empty, mark) == LOG


class FakeProcess:
    """A started game as launch sees it (subprocess.Popen's interface)."""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            raise subprocess.TimeoutExpired("java", timeout)
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


class FakeGame(launch.Host):
    """The machine with a game that behaves like the spike's: log4j rolls latest.log over and
    the join appears after `join_after` polls (`rolls` schedules more rollovers); its window
    shows after the first poll; WM_CLOSE saves options.txt with CRLF, `flip` applied, and exits
    with `exit_code`. The clock moves only by sleeps."""

    def __init__(self, game: Path, log: str | None, join_after: int = 4, exit_code: int = 0):
        self.game, self.exit_code = game, exit_code
        self.rolls: list[tuple[int, str]] = [] if log is None else [(join_after, log)]
        self.flip: dict[str, str] = {}
        self.process = FakeProcess()
        self.now = 0.0
        self.sleeps = 0
        self.started: dict | None = None
        self.procs: list[launch.ProcessInfo] = []
        self.logman_text = LOGMAN
        self.edit = None
        self.closed: list[int] = []

    def processes(self) -> list[launch.ProcessInfo]:
        return list(self.procs)

    def logman(self) -> str:
        return self.logman_text

    def start(self, command, cwd, stdout, env) -> FakeProcess:
        self.started = {"command": command, "cwd": cwd, "stdout": stdout, "env": env}
        return self.process

    def cmdline(self, pid: int) -> list[str]:
        command = list(self.started["command"])
        return self.edit(command) if self.edit else command

    def windows(self, pid: int) -> list[int]:
        return [77] if self.process.returncode is None and self.sleeps >= 1 else []

    def close(self, hwnd: int) -> bool:
        self.closed.append(hwnd)
        options = self.game / "options.txt"
        text = options.read_text(encoding="utf-8")
        for key, value in self.flip.items():
            text = text.replace(f"{key}:{launch.options_values(text)[key]}\n", f"{key}:{value}\n")
        options.write_bytes(text.replace("\n", "\r\n").encode())
        self.process.returncode = self.exit_code
        return True

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.sleeps += 1
        for count, text in self.rolls:
            if self.sleeps == count:
                log = self.game / "logs" / "latest.log"
                log.replace(log.with_name(f"2026-10-06-{count}.log.gz"))
                write(log, text.encode())


BENCH_MODS = ["fabric-api", "fabricloader", "iris", "java", "minecraft", "sodium"]


def test_the_join_wait_finds_the_line_or_fails(tmp_path: Path) -> None:
    game = tmp_path / "game"
    write(game / "logs" / "latest.log", LOG.encode())  # the previous session's, joined
    log = game / "logs" / "latest.log"
    host = FakeGame(game, LOG, join_after=3)
    mark = launch.log_mark(log)
    seconds, line, mods = launch.wait_join(host.process, log, mark, "optilux", host, 0.0)
    assert seconds == 0.75 and "logged in with entity id 11" in line and mods == BENCH_MODS
    # Midnight rolls latest.log again between Fabric's list and the join: the list is kept.
    write(log, LOG.encode())
    mark = launch.log_mark(log)
    host = FakeGame(game, None)
    split = LOG.index("[03:28:01]")
    host.rolls = [(2, LOG[:split]), (4, LOG[split:])]
    seconds, line, mods = launch.wait_join(host.process, log, mark, "optilux", host, 0.0)
    assert seconds == 1.0 and "entity id 11" in line and mods == BENCH_MODS
    assert launch.logged_mods(log.read_text(encoding="utf-8")) is None  # gone from the file
    # A read that caught the list mid-write is corrected by a later one.
    write(log, LOG.encode())
    mark = launch.log_mark(log)
    host = FakeGame(game, None)
    partial = "\n".join(LOG.splitlines()[:5]) + "\n"
    assert launch.logged_mods(partial) == ["fabric-api"]
    host.rolls = [(1, partial), (3, LOG)]
    seconds, line, mods = launch.wait_join(host.process, log, mark, "optilux", host, 0.0)
    assert mods == BENCH_MODS
    # The previous session's join never counts: no rollover, no join, the timeout passes (F11).
    host = FakeGame(game, None)
    mark = launch.log_mark(log)
    with pytest.raises(launch.LaunchError, match=r"no join in latest.log within 120 s \(F11\)"):
        launch.wait_join(host.process, log, mark, "optilux", host, 0.0)
    assert host.now == 120.0
    # The game exits first.
    host = FakeGame(game, None)
    host.process.returncode = 1
    with pytest.raises(launch.LaunchError, match="exited with code 1 before the join"):
        launch.wait_join(host.process, log, mark, "optilux", host, 0.0)


# game/mods/.

MOD_A, MOD_B, HELPER = jar("mod-a"), jar("mod-b"), jar("optilux-helper")
PACK, REF = b"PK resource pack", b"PK shader pack"
LIB, CLIENT = b"lib jar", b"client jar"
VERSION = json.dumps({"id": "26.3", "type": "release"}).encode()
INDEX = b'{"objects": {}}'
# A fake game's log: Fabric Loader's list for the fixture's bench tier, then L1's join.
FAKE_LOG = (
    "[17:10:00] [main/INFO]: Loading Minecraft 26.3 with Fabric Loader 0.19.5\n"
    "[17:10:00] [main/INFO]: Loading 5 mods:\n"
    "\t- fabricloader 0.19.5\n\t   \\-- mixinextras 0.5.5\n\t- java 25\n\t- minecraft 26.3\n"
    "\t- mod-a 1\n" + LOG[LOG.index("[03:27:48]") :]
)


def make_root(tmp_path: Path) -> Path:
    """A repo with config for platform mc-fixture (bench: mod-a and a resource pack; dev adds
    mod-b; lod a pending mod), a two-jar launch spec, the real suite display and bench.json, and
    runtime/ as install leaves it after the spike: viewfinder still in game/mods/, the game's own
    options.txt and the previous session's latest.log."""
    root = tmp_path / "repo"
    config = root / "config"
    suite = {"platform": PLATFORM, "display": DISPLAY}
    write(config / "suite.json", json.dumps(suite).encode())

    def pin(slug: str, name: str, data: bytes) -> dict:
        return {
            "slug": slug,
            "version": "1",
            "file": name,
            "modrinthVersionId": "X",
            "sha512": sha512(data),
        }

    plat = {
        "id": PLATFORM,
        "minecraft": "26.3",
        "loader": {"name": "fabric", "version": "0.19.5"},
        "offlinePlayer": {"name": "optilux", "uuid": UUID},
        "tiers": {
            "bench": {
                "extends": None,
                "mods": [pin("mod-a", "mod-a.jar", MOD_A)],
                "resourcePacks": [pin("pack", "Pack 1.zip", PACK)],
            },
            "dev": {"extends": "bench", "mods": [pin("mod-b", "mod-b.jar", MOD_B)]},
            "lod": {"extends": "bench", "mods": [{"slug": "voxy", "status": "pending"}]},
        },
        "referencePacks": [pin("ref", "Ref.zip", REF)],
    }
    write(config / "platforms" / f"{PLATFORM}.json", json.dumps(plat).encode())
    spec = dict(SPEC, platform=PLATFORM)
    spec["classpath"] = [
        {"path": "libraries/a/lib.jar", "sha1": sha1(LIB), "from": "mojang:a"},
        {"path": "versions/26.3/26.3.jar", "sha1": sha1(CLIENT), "from": "mojang:client"},
    ]
    spec["assetIndex"] = {"id": "34", "sha1": sha1(INDEX), "url": "u"}
    spec["sources"] = {
        "versionJson": {"id": "26.3", "url": "u", "sha1": sha1(VERSION)},
        "fabricProfile": SPEC["sources"]["fabricProfile"],
    }
    write(platform.spec_path(root, PLATFORM), platform.spec_text(spec).encode())
    write(config / "java" / "bench.json", json.dumps(BENCH).encode())
    base = root / "runtime" / PLATFORM
    for relative, data in {
        "libraries/a/lib.jar": LIB,
        "versions/26.3/26.3.jar": CLIENT,
        "versions/26.3/26.3.json": VERSION,
        "assets/indexes/34.json": INDEX,
        "files/mod-a.jar": MOD_A,
        "files/mod-b.jar": MOD_B,
        "files/Pack 1.zip": PACK,
        "files/Ref.zip": REF,
        "game/resourcepacks/Pack 1.zip": PACK,
        "game/shaderpacks/Ref.zip": REF,
        "game/saves/spike/level.dat": b"level",
        f"game/saves/spike/players/data/{UUID}.dat": b"player",
        f"game/saves/spike/players/data/{UUID}.dat_old": b"player",
        "game/options.txt": GAME_OPTIONS.encode(),
        "game/mods/viewfinder.jar": jar("viewfinder"),
        "game/logs/latest.log": LOG.encode(),
    }.items():
        write(base / relative, data)
    write(root / "runtime" / "java" / BENCH["runtime"]["build"] / "bin" / "java.exe", b"MZ")
    return root


def test_game_mods_is_made_to_hold_exactly_the_tier(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    base = root / "runtime" / PLATFORM
    plat = platform.load(root)
    mods = base / "game" / "mods"
    write(mods / "Stray.JAR", b"junk")  # any case
    write(mods / "mod-a.jar", b"edited")  # off its pin
    write(mods / "notes.txt", b"kept")  # Fabric loads only *.jar
    write(mods / "sub" / "deep.jar", b"x")  # one level deep only (DirectoryModCandidateFinder)
    placed = launch.place_mods(root, base, plat, "bench")
    assert sorted(p.name for p in mods.iterdir()) == ["mod-a.jar", "notes.txt", "sub"]
    assert (mods / "mod-a.jar").read_bytes() == MOD_A
    assert sorted(placed.removed) == ["Stray.JAR", "viewfinder.jar"]
    assert placed.placed == [{"file": "mod-a.jar", "sha512": sha512(MOD_A), "state": "copied"}]
    assert placed.sha512 == [sha512(MOD_A)] and placed.helper is None
    assert not list(mods.glob("*.part"))
    # Again: nothing to do. The dev tier adds its jar; bench again removes it.
    again = launch.place_mods(root, base, plat, "bench")
    assert again.placed[0]["state"] == "kept" and again.removed == []
    dev = launch.place_mods(root, base, plat, "dev")
    assert [p["file"] for p in dev.placed] == ["mod-a.jar", "mod-b.jar"]
    assert dev.sha512 == sorted([sha512(MOD_A), sha512(MOD_B)])
    assert launch.place_mods(root, base, plat, "bench").removed == ["mod-b.jar"]
    # The helper from the store joins every tier, pinned by its own hash (mod build, 0.01.04).
    write(base / "files" / "optilux-helper-0.1.jar", HELPER)
    placed = launch.place_mods(root, base, plat, "bench")
    assert placed.helper == "optilux-helper-0.1.jar"
    assert placed.sha512 == sorted([sha512(MOD_A), sha512(HELPER)])
    write(base / "files" / "optilux-helper-0.2.jar", HELPER)
    with pytest.raises(launch.LaunchError, match="the store holds 2 helper jars"):
        launch.place_mods(root, base, plat, "bench")
    (base / "files" / "optilux-helper-0.2.jar").unlink()
    # A store jar off its pin is refused, and nothing of it is placed.
    (mods / "mod-a.jar").unlink()
    write(base / "files" / "mod-a.jar", b"tampered")
    with pytest.raises(
        launch.LaunchError, match=r"store jar runtime/mc-fixture/files/mod-a.jar: sha"
    ):
        launch.place_mods(root, base, plat, "bench")
    assert not (mods / "mod-a.jar").exists()


def test_the_uuid_comes_from_the_worlds_player_file(tmp_path: Path) -> None:
    world = tmp_path / "w"
    assert launch.player_uuid(world, UUID) == (UUID, "offlinePlayer")
    other = "00000000-0000-3000-8000-000000000001"
    write(world / "players" / "data" / f"{other}.dat", b"")
    write(world / "players" / "data" / f"{other}.dat_old", b"")
    write(world / "players" / "data" / "notes.dat", b"")  # not a UUID: not a player file
    assert launch.player_uuid(world, UUID) == (other, f"players/data/{other}.dat")
    write(world / "players" / "data" / f"{UUID}.dat", b"")
    with pytest.raises(launch.LaunchError, match="holds 2 player files"):
        launch.player_uuid(world, UUID)


# The whole launch through a fake game.


def test_a_launch_end_to_end_through_a_fake_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_root(tmp_path)
    game = root / "runtime" / PLATFORM / "game"
    host = FakeGame(game, FAKE_LOG)
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Xmx1m")  # read by the JVM, never on its line
    said: list[str] = []
    launched = launch.launch(root, "spike", "bench", True, {"maxFps": "120"}, said.append, host)
    facts = launched.facts
    assert launched.pid == 4242 and len(launched.token) == 43 and set(launched.token) <= URLSAFE
    command = host.started["command"]
    assert command.count("-Doptilux.token=" + launched.token) == 1
    assert command[-3:] == ["--quickPlaySingleplayer", "spike", "--offlineDeveloperMode"]
    assert host.started["cwd"] == game and host.started["stdout"] == game / "logs" / "stdout.log"
    assert "JAVA_TOOL_OPTIONS" not in host.started["env"]
    assert sorted(p.name for p in (game / "mods").iterdir()) == ["mod-a.jar"]
    assert facts["mods"]["removed"] == ["viewfinder.jar"]
    assert facts["mods"]["sha512"] == [sha512(MOD_A)]
    assert facts["logMods"] == ["fabricloader", "java", "minecraft", "mod-a"]
    assert facts["join"]["seconds"] == 1.0 and "entity id 11" in facts["join"]["line"]
    assert facts["uuid"] == {"value": UUID, "from": f"players/data/{UUID}.dat"}
    assert facts["settings"]["overrides"] == {"maxFps": "120"}
    assert facts["settings"]["token"] is True
    assert facts["settings"]["sodiumOptions"] == DISPLAY["sodiumOptions"]
    assert "-Doptilux.token=<redacted>" in facts["command"]["arguments"]
    assert launched.token not in json.dumps(facts)
    assert facts["hashes"]["classpathJars"] == 2 and len(facts["hashes"]["packs"]) == 2
    assert said[0] == (
        "gate: open: no process from runtime/mc-fixture/, no optilux-* ETW session; AMD "
        "(recorded, never stopped): no PresentMon-x64.exe, no RSXTraceSession"
    )
    assert said[2] == "mods: game/mods/ holds the bench set: mod-a.jar (copied); removed " + (
        "viewfinder.jar; optilux-helper not in the store yet (mod build, 0.01.04)"
    )
    assert said[-2] == "log: the mods are the bench set (fabricloader, java, minecraft, mod-a)"
    assert said[-1] == (
        "AMD after the join (recorded, never stopped): no PresentMon-x64.exe, no RSXTraceSession"
    )
    quit_facts = launch.quit_game(launched.process, host)
    assert quit_facts == {"how": "WM_CLOSE", "windows": 1, "exitCode": 0, "seconds": 0.0}
    back = launch.read_back(launched.game, launched.prelaunch)
    assert back["ok"] and back["options"] == {"keys": 24, "moved": {}}


def test_a_closed_gate_or_a_bad_input_writes_nothing(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    game = root / "runtime" / PLATFORM / "game"
    before = (game / "options.txt").read_bytes()
    host = FakeGame(game, FAKE_LOG)
    host.procs = [proc(9, "java.exe", "java.exe", str(game), [])]
    with pytest.raises(launch.LaunchError, match=r"gate is closed: pid 9 java.exe \(cwd\) \(F2\)"):
        launch.launch(root, "spike", host=host)
    host.procs = []
    host.logman_text = with_sessions("optilux-a1")
    with pytest.raises(launch.LaunchError, match="gate is closed: ETW session optilux-a1"):
        launch.launch(root, "spike", host=host)
    host.logman_text = LOGMAN
    with pytest.raises(launch.LaunchError, match="no world 'nowhere' under runtime/mc-fixture/"):
        launch.launch(root, "nowhere", host=host)
    with pytest.raises(launch.LaunchError, match=r"no world '../spike'"):
        launch.launch(root, "../spike", host=host)
    with pytest.raises(launch.LaunchError, match="tier lod lacks voxy: pending; fix"):
        launch.launch(root, "spike", "lod", host=host)
    # A bad --set is refused before the gate is even asked (the gate is closed here).
    host.procs = [proc(9, "java.exe", "java.exe", str(game), [])]
    with pytest.raises(launch.LaunchError, match="--set nope: not an option the suite writes"):
        launch.launch(root, "spike", overrides={"nope": "1"}, host=host)
    with pytest.raises(launch.LaunchError, match="is not one printable line"):
        launch.launch(root, "spike", overrides={"maxFps": "1\r\nao:false"}, host=host)
    host.procs = []
    write(game / "shaderpacks" / "Ref.zip", b"edited")
    with pytest.raises(launch.LaunchError, match="referencePack runtime/mc-fixture/game/shader"):
        launch.launch(root, "spike", host=host)
    assert host.started is None and (game / "options.txt").read_bytes() == before
    assert (game / "mods" / "viewfinder.jar").is_file()


def test_a_failed_check_after_the_start_ends_the_game(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    game = root / "runtime" / PLATFORM / "game"
    # A wrapper added an argument: the game is killed at once (it has no window yet).
    host = FakeGame(game, FAKE_LOG)
    host.edit = lambda command: [*command, "--demo"]
    with pytest.raises(
        launch.LaunchError, match=r"command line differs: \d+ arguments started.*ended \(killed\)"
    ):
        launch.launch(root, "spike", host=host)
    assert host.process.killed
    # No join within 120 s: WM_CLOSE ends it (its window exists), the world saved.
    host = FakeGame(game, None)
    with pytest.raises(launch.LaunchError, match=r"within 120 s \(F11\); the game was ended \(WM"):
        launch.launch(root, "spike", host=host)
    assert host.closed == [77] and not host.process.killed
    # The log lists a mod outside the tier.
    host = FakeGame(game, FAKE_LOG.replace("\t- mod-a 1\n", "\t- mod-a 1\n\t- viewfinder 2\n"))
    with pytest.raises(launch.LaunchError, match=r"the log lists mods \[.*'viewfinder'\], not the"):
        launch.launch(root, "spike", host=host)


def test_the_cli_holds_quits_and_reads_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_root(tmp_path)
    game = root / "runtime" / PLATFORM / "game"
    hosts: list[FakeGame] = []
    exit_codes = [0]
    flips: list[dict[str, str]] = [{}]

    def fake_host() -> FakeGame:
        hosts.append(FakeGame(game, FAKE_LOG, exit_code=exit_codes[-1]))
        hosts[-1].flip = flips[-1]
        return hosts[-1]

    monkeypatch.setattr(launch_verb, "REPO_ROOT", root)
    monkeypatch.setattr(launch, "Host", fake_host)
    assert cli.main(["launch", "spike", "--quit-after", "2"]) == 0
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert err == "" and lines[0].startswith("gate: open: no process from runtime/mc-fixture/")
    assert lines[1] == (
        "hashes: 2 classpath jars, asset index 34 and the version JSON sha1-equal to the spec; "
        "2 packs sha512-equal"
    )
    assert lines[3].startswith("pre-launch: options.txt (24 keys), sodium-options.json (sha256 ")
    assert lines[4].startswith("started pid 4242: 38 arguments, KnotClient, 2 jars, ")
    assert lines[5].startswith("joined in 1.0 s: [03:28:01] [Server thread/INFO]: optilux[")
    assert lines[7] == (
        "AMD after the join (recorded, never stopped): no PresentMon-x64.exe, no RSXTraceSession"
    )
    assert lines[8:] == [
        "mod: no optilux-helper jar in the store, no mod session (fix: `optilux mod build`)",
        "held 2 s in the world",
        "quit: WM_CLOSE to 1 window, exit code 0 in 0.0 s",
        "read back: options.txt 24 of 24 keys as written",
        "read back: iris.properties 5 of 5 keys as written; sodium-options.json flags held, "
        "text unchanged",
        "optilux launch: ok; pid 4242, joined in 1.0 s, log "
        "runtime/mc-fixture/game/logs/latest.log",
    ]
    assert hosts[-1].now == 1.0 + 2.0  # the join's four polls, then the hold
    # --json, --no-token and --set: recorded in the settings for the run record.
    assert cli.main(["launch", "spike", "--no-token", "--set", "maxFps=120", "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["ok"] is True and found["problem"] is None and "quit" not in found
    assert found["settings"]["token"] is False and found["settings"]["overrides"] == {
        "maxFps": "120"
    }
    assert not any(a.startswith("-Doptilux.") for a in hosts[-1].started["command"])
    assert b"maxFps:120\n" in (game / "options.txt").read_bytes()
    # An F3 key the game moved fails the launch like any written key: it is identity.
    flips.append({"exclusiveFullscreen": "true"})
    assert cli.main(["launch", "spike", "--quit-after", "0"]) == 1
    assert (
        "read back: options.txt 23 of 24 keys as written; moved: exclusiveFullscreen: false -> true"
    ) in capsys.readouterr().out.splitlines()
    flips.append({})
    # A quit that does not exit 0 fails the run.
    exit_codes.append(-8)
    assert cli.main(["launch", "spike", "--quit-after", "0"]) == 1
    out, err = capsys.readouterr()
    assert err.startswith("optilux launch: failed: exit code -8; pid 4242, joined in 1.0 s")
    # Refusals name the fix.
    finite = "is not a finite count of seconds, 0 or more; fix: give one"
    for argv, problem in (
        (["--set", "x"], "--set 'x' is not key=value; fix: --set <key>=<value>"),
        (["--set", "a=1", "--set", "a=2"], "--set a is given twice; fix: give it once"),
        (["--quit-after", "-1"], f"--quit-after -1 {finite}"),
        (["--quit-after", "nan"], f"--quit-after nan {finite}"),
        (["--quit-after", "inf"], f"--quit-after inf {finite}"),
    ):
        assert cli.main(["launch", "spike", *argv]) == 1
        assert capsys.readouterr().err == f"optilux launch: {problem}\n"
    assert cli.main(["launch", "spike", "--set", "nope=1", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["problem"].startswith("--set nope: not an option")
    assert "launch" in [verb.name for verb in cli.VERBS]


# The mod session (0.01.05) through the protocol fake.

USER_SID = "S-1-5-21-7"
HELPER_LOG = FAKE_LOG.replace("\t- mod-a 1\n", "\t- mod-a 1\n\t- optilux-helper 0.1.0\n")


class ModGame(FakeGame):
    """A fake game with the helper loaded: connect() serves a protocol fake over a socket pair,
    whose `quit` makes the process exit 0; `dacl`, `pid` and `refused` steer the pipe checks."""

    def __init__(self, game: Path, log: str | None = HELPER_LOG) -> None:
        super().__init__(game, log)
        self.dacl = f"D:(A;;FA;;;{USER_SID})"
        self.pid = 4242
        self.refused = 231
        self.fakes: list[modfake.Fake] = []
        self.frames_step = modfake.FRAMES_PER_CALL

    def connect(self, token: str, pid: int, log: Path) -> modclient.Client:
        process, step = self.process, self.frames_step

        class Exiting(modfake.Fake):
            def _answer(self, request_id, name, args):
                if name == "quit":
                    process.returncode = 0
                if name == "frames.index" and step == 0:
                    return self._ok(request_id, {})
                return super()._answer(request_id, name, args)

        fake = Exiting(token, pid=self.pid)
        self.fakes.append(fake)
        stream, _ = modfake.serve_streams(fake)
        client = modclient.Client(stream, token, log, pid)
        client.server_pid = pid
        client.dacl = self.dacl
        return client

    def second_instance(self, name: str) -> int:
        return self.refused

    def user_sid(self) -> str:
        return USER_SID

    def canonical_sid(self, text: str) -> str:
        return {"LA": "S-1-5-21-500"}.get(text, text)


def with_helper(root: Path) -> None:
    write(root / "runtime" / PLATFORM / "files" / "optilux-helper-0.1.0.jar", HELPER)


def test_the_cli_runs_the_mod_session_and_quits_through_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_root(tmp_path)
    with_helper(root)
    game = root / "runtime" / PLATFORM / "game"
    hosts: list[ModGame] = []

    def fake_host() -> ModGame:
        hosts.append(ModGame(game))
        return hosts[-1]

    monkeypatch.setattr(launch_verb, "REPO_ROOT", root)
    monkeypatch.setattr(launch, "Host", fake_host)
    assert cli.main(["launch", "spike", "--quit-after", "1"]) == 0
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert err == ""
    mod = [line for line in lines if line.startswith(("mod: ", "quit: ", "request log: "))]
    assert mod[0] == (
        f"mod: pipe served by pid 4242 (the launched game); DACL D:(A;;FA;;;{USER_SID}) (one "
        "allow ACE, this user); a second server instance refused (Windows error 231)"
    )
    assert mod[1].startswith("mod: hello: protocol 1, optilux-helper fake on fake (), pid 4242, ")
    assert mod[2].startswith("mod: frames.index 100 -> 103 after 0.5 s (qpcNs ")
    assert mod[3] == "quit: the mod's quit, exit code 0 in 0.0 s"
    assert mod[4].startswith("request log: results/raw/launch-") and mod[4].endswith(
        "/requests.jsonl, 9 lines, the token absent"
    )
    logs = list((root / "results" / "raw").glob("launch-*/requests.jsonl"))
    assert len(logs) == 1
    records = modfake.log_lines(logs[0])
    token = hosts[-1].fakes[0].token
    assert token not in logs[0].read_text(encoding="utf-8")
    sent = [r["message"] for r in records if r["dir"] == "sent"]
    assert [m["cmd"] for m in sent] == ["hello", "frames.index", "frames.index", "quit"]
    assert sent[0]["args"] == {"token": modclient.REDACTED}
    assert lines[-1].startswith("optilux launch: ok; pid 4242")
    # --json carries the session's facts.
    assert cli.main(["launch", "spike", "--quit-after", "0", "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["ok"] is True and found["quit"]["how"] == "quit"
    assert found["mod"]["hello"]["pid"] == 4242
    assert found["mod"]["pipe"] == {
        "serverPid": 4242,
        "dacl": f"D:(A;;FA;;;{USER_SID})",
        "secondInstanceError": 231,
    }
    assert found["mod"]["logCheck"]["tokenAbsent"] is True
    assert hosts[-1].fakes[0].token not in json.dumps(found)


def test_a_failed_mod_check_ends_the_game(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    with_helper(root)
    game = root / "runtime" / PLATFORM / "game"
    for change, problem in (
        (
            {"dacl": f"D:(A;;FA;;;{USER_SID})(A;;FR;;;WD)"},
            "the pipe's DACL is .*, not one allow ACE for",
        ),
        ({"refused": 0}, "a second server instance of the mod's pipe was created"),
        ({"pid": 999}, "hello answered pid 999, not the launched 4242"),
        ({"frames_step": 0}, r"frames.index stayed at 100 for 30 s: no frame was rendered"),
    ):
        host = ModGame(game)
        for key, value in change.items():
            setattr(host, key, value)
        launched = launch.launch(root, "spike", host=host)
        with pytest.raises(launch.LaunchError, match="the mod session: " + problem):
            launch.open_mod(launched, root, host, lambda text: None)


def test_the_cli_ends_the_game_when_the_mod_session_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_root(tmp_path)
    with_helper(root)
    game = root / "runtime" / PLATFORM / "game"
    hosts: list[ModGame] = []

    def fake_host() -> ModGame:
        hosts.append(ModGame(game))
        hosts[-1].pid = 999  # hello answers another pid
        return hosts[-1]

    monkeypatch.setattr(launch_verb, "REPO_ROOT", root)
    monkeypatch.setattr(launch, "Host", fake_host)
    assert cli.main(["launch", "spike", "--quit-after", "1"]) == 1
    err = capsys.readouterr().err
    assert err.startswith(
        "optilux launch: the mod session: hello answered pid 999, not the launched 4242; the "
        "game was ended (WM_CLOSE, exit code 0)"
    )
    assert hosts[-1].closed == [77]
    fake = hosts[-1].fakes[0]
    deadline = time.monotonic() + 5
    while fake._write is not None and time.monotonic() < deadline:  # the client closed
        time.sleep(0.01)
    assert fake._write is None


def test_the_dacl_aces_and_the_log_check(tmp_path: Path) -> None:
    assert launch.dacl_aces(f"D:P(A;;FA;;;{USER_SID})") == [
        {"type": "A", "rights": "FA", "sid": USER_SID}
    ]
    assert [a["sid"] for a in launch.dacl_aces("D:(D;;GA;;;WD)(A;;FA;;;SY)S:(ML;;NW;;;LW)")] == [
        "WD",
        "SY",
    ]
    log = tmp_path / "requests.jsonl"
    write(log, b'{"a":1}\n{"b":2}\n')
    assert launch.check_log(log, TOKEN) == {"lines": 2, "bytes": 16, "tokenAbsent": True}
    write(log, f'{{"token":"{TOKEN}"}}\n'.encode())
    with pytest.raises(launch.LaunchError, match="holds the token"):
        launch.check_log(log, TOKEN)


def test_a_dacl_written_with_an_alias_passes(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    with_helper(root)
    host = ModGame(root / "runtime" / PLATFORM / "game")
    host.dacl = "D:P(A;;FA;;;LA)"  # the built-in Administrator, as SDDL names it
    host.user_sid = lambda: "S-1-5-21-500"
    launched = launch.launch(root, "spike", host=host)
    client, facts = launch.open_mod(launched, root, host, lambda text: None)
    client.close()
    assert facts["pipe"]["dacl"] == "D:P(A;;FA;;;LA)"


def test_the_options_file_the_game_reads_is_recorded_before_the_launch(tmp_path: Path) -> None:
    """The game reads every options.txt key, the harness writes 24: the rest are recorded with
    their values and the file's hash as the launch leaves it (inactivityFpsLimit moved frame
    time unwritten in 0.01.11)."""
    game = tmp_path / "game"
    write(game / "options.txt", GAME_OPTIONS.encode())
    pre = launch.prelaunch(DISPLAY, "bench", "Ref.zip", {})
    found = launch.write_prelaunch(game, pre)
    written = (game / "options.txt").read_bytes()
    assert found["sha256"] == hashlib.sha256(written).hexdigest()
    read = launch.options_values(written.decode())
    assert found["unwritten"] == {k: v for k, v in read.items() if k not in pre.options}
    assert found["unwritten"]["ao"] == "true" and "renderDistance" not in found["unwritten"]


def test_end_reports_a_game_that_outlasts_its_kill() -> None:
    """A killed game still running after QUIT_TIMEOUT is said, not raised over the error that
    made the harness end it."""

    class Stuck(FakeProcess):
        def kill(self) -> None:
            self.killed = True  # the process stays

    process = Stuck()
    host = FakeGame(Path("."), None)
    host.windows = lambda pid: []  # type: ignore[method-assign]
    how = launch.end(process, host)
    assert process.killed and "still running" in how


def test_the_gate_refuses_a_gradle_build_and_records_other_java(tmp_path: Path) -> None:
    """A Gradle build competes with the game for the CPU and the store's jars: it blocks. An
    idle daemon (VS Code's Gradle extension) and other JVMs (its language server) are recorded,
    as AMD's PresentMon is (roadmap.md#qa-pass-open-questions)."""
    base, _ = paths(tmp_path)
    jdk = "C:\\jdk\bin\\java.exe"
    wrapper = proc(8, "java.exe", jdk, r"C:\work\mod", ["java", "-classpath", "gradle-wrapper.jar"])
    wrapper.cmdline.append("org.gradle.wrapper.GradleWrapperMain")
    daemon = proc(
        9, "java.exe", jdk, None, ["java", "org.gradle.launcher.daemon.bootstrap.GradleDaemon"]
    )
    server = proc(10, "javaw.exe", jdk, None, ["javaw", "-jar", "equinox.launcher.jar"])
    found = launch.gate(base, [wrapper, daemon, server], LOGMAN, own_pid=0)
    assert found.builds == [{"pid": 8, "name": "java.exe"}] and not found.ok
    assert [(j["pid"], j["role"]) for j in found.java] == [
        (8, "gradle build"),
        (9, "gradle daemon"),
        (10, "other"),
    ]
    found = launch.gate(base, [daemon, server], LOGMAN, own_pid=0)
    assert found.builds == [] and found.ok


def test_the_quits_kill_a_game_that_will_not_go(tmp_path: Path) -> None:
    """WM_CLOSE without a window, WM_CLOSE outlasted, the mod's quit outlasted and an exit while
    held: each kills the game and raises, so no run goes on with it."""
    host = FakeGame(tmp_path, None)
    host.windows = lambda pid: []  # type: ignore[method-assign]
    process = FakeProcess()
    with pytest.raises(launch.LaunchError, match="no window"):
        launch.quit_game(process, host)
    assert process.killed

    class Deaf(FakeGame):
        def windows(self, pid: int) -> list[int]:
            return [77]

        def close(self, hwnd: int) -> bool:
            return True

    process = FakeProcess()
    with pytest.raises(launch.LaunchError, match="outlasted WM_CLOSE"):
        launch.quit_game(process, Deaf(tmp_path, None))
    assert process.killed
    process = FakeProcess()
    process.returncode = -1
    with pytest.raises(launch.LaunchError, match="exited with code -1 before the quit"):
        launch.quit_game(process, FakeGame(tmp_path, None))
    with pytest.raises(launch.LaunchError, match="while held"):
        launch.hold(process, FakeGame(tmp_path, None), 5.0)

    class Client:
        closed = False

        def request(self, command: str) -> dict:
            return {}

        def close(self) -> None:
            self.closed = True

    client, process = Client(), FakeProcess()
    with pytest.raises(launch.LaunchError, match="outlasted quit"):
        launch.quit_mod(client, process, FakeGame(tmp_path, None))  # type: ignore[arg-type]
    assert process.killed and client.closed


def test_saved_pack_settings_refuse_a_launch_at_the_packs_defaults(tmp_path: Path) -> None:
    """Iris.loadExternalShaderpack reads a pack's saved options from shaderpacks/<pack>.txt; a
    launch at the pack's defaults (profile null) refuses one before writing anything."""
    root = make_root(tmp_path)
    game = root / "runtime" / PLATFORM / "game"
    before = (game / "options.txt").read_bytes()
    write(game / "shaderpacks" / "Ref.zip.txt", b"SHADOW_QUALITY=2\n")
    host = FakeGame(game, FAKE_LOG)
    with pytest.raises(launch.LaunchError, match=r"Ref\.zip\.txt holds saved settings"):
        launch.launch(root, "spike", host=host)
    assert host.started is None and (game / "options.txt").read_bytes() == before
