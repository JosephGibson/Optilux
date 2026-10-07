"""`optilux mod build|test [--json]` (docs/mod.md#11-build-and-test).

Gradle runs only through this verb: mod/'s wrapper with JAVA_HOME and org.gradle.java.home set to
the Temurin `install` unpacked under runtime/java/ (gradlew.bat starts its JVM from JAVA_HOME,
docs/plans/m1.md P37), --no-daemon, no JDK detected or downloaded (mod/gradle.properties). First
the verb writes mod/build/optilux/inputs.json from the platform file and the hash-checked pinned
jars: the versions Loom resolves, fabric.mod.json's `depends`, the compile-only Iris and Sodium
jars and the jars the mixin-target test reads; Gradle reads nothing else under config/ or
runtime/. `build` runs `jar` and copies mod/build/libs/optilux-helper-<version>.jar into the store
runtime/<platform>/files/, where `launch` takes it, replacing any older helper jar; `test` runs
the JUnit tests, counts their results and compares the tested jar with the store's. Both refuse
while the launch gate is closed, so Gradle never starts beside a session (`launch` itself does not
look for Gradle).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from optilux import REPO_ROOT, launch, platform
from optilux.verbs import Verb
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, STORE, Say, shown

PREFIX = "optilux mod"
ACTIONS = ("build", "test")
MOD = "mod"
WRAPPER = "gradlew.bat"
INPUTS = "build/optilux/inputs.json"
LIBS = "build/libs"
RESULTS = "build/test-results/test"
HELPER = "optilux-helper"
# The bench tier is what every session loads, so the helper depends on its mods at their pins.
TIER = "bench"
FABRIC_API = "fabric-api"
# Iris and Sodium are compile-only from their pinned jars (docs/mod.md#11-build-and-test).
COMPILE_ONLY = ("sodium", "iris")
CLIENT = f"{platform.MOJANG}:{platform.CLIENT}"
# --rerun: `mod test` runs the tests even when Gradle finds them up to date.
TASKS = {"build": ["jar"], "test": ["test", "--rerun"]}
FLAGS = ("--no-daemon", "--console=plain")
# JVM option variables that would reach Gradle's JVM through gradlew.bat or the JVM itself.
JAVA_ENV = (*launch.JAVA_ENV, "JAVA_OPTS", "GRADLE_OPTS")
INPUTS_SCHEMA = 1
WRITTEN_BY = "optilux mod build|test, before Gradle reads it (docs/mod.md#11-build-and-test)"


class ModError(RuntimeError):
    """A mod build or test that cannot proceed; the message names the problem and the fix."""


@dataclass
class Outcome:
    """One run: the action, the inputs, Gradle's command and exit, and the jar or the tests."""

    action: str
    depends: dict[str, str] = field(default_factory=dict)
    gradle: dict = field(default_factory=dict)
    jar: dict = field(default_factory=dict)
    tests: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        return {"ok": True, **self.__dict__, "problem": None}


Runner = Callable[[list[str], Path, dict[str, str], bool], int]


def run_gradle(command: list[str], cwd: Path, env: dict[str, str], to_stderr: bool) -> int:
    """Gradle's exit code; its output goes to the terminal (to stderr under --json). The tests
    replace it."""
    return subprocess.run(  # noqa: S603 argv list: the wrapper under mod/, no shell
        command, cwd=cwd, env=env, stdout=sys.stderr if to_stderr else None
    ).returncode


def jar_metadata(path: Path) -> tuple[str, str]:
    """(id, version) a mod jar declares in its fabric.mod.json."""
    try:
        with zipfile.ZipFile(path) as jar:
            meta = json.loads(jar.read("fabric.mod.json"))
        return meta["id"], meta["version"]
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        raise ModError(
            f"{path.name} declares no Fabric id and version ({error}); fix: re-pin it"
        ) from None


def check(path: Path, algorithm: str, pin: str, what: str, root: Path) -> None:
    try:
        launch.check_hash(path, algorithm, pin, what, root)
    except launch.LaunchError as error:
        raise ModError(str(error)) from None


def depends(root: Path, plat: platform.Platform) -> dict[str, str]:
    """fabric.mod.json's `depends`: minecraft and fabricloader at the platform file's versions,
    then every bench mod at the version its pinned jar declares (the pin is the jar's sha512), each
    with "=". Fabric's comparison ignores the +build suffix (SemanticVersionImpl.compareTo in
    fabric-loader 0.19.5), so =0.9.2+mc26.3 also admits 0.9.2+mc26.2; `launch`'s sha512 pins are
    the exact check."""
    store = root / RUNTIME / plat.id / STORE
    found = {"minecraft": f"={plat.minecraft}", "fabricloader": f"={plat.loader[1]}"}
    for pinned in plat.tier_files(TIER):
        if pinned.kind != "mod":
            continue
        path = store / pinned.file
        check(path, "sha512", pinned.sha512, "store jar", root)
        mod_id, version = jar_metadata(path)
        if mod_id in found:
            raise ModError(f"two pins declare mod id {mod_id!r}; fix: pin one")
        found[mod_id] = f"={version}"
    return found


def inputs(root: Path, plat: platform.Platform) -> dict:
    """What Gradle and the JUnit tests read: the versions Loom resolves, `depends`, the compile-only
    jars and the jars holding the mixin targets (the client jar by the spec's sha1, Iris and Sodium
    by sha512), every path absolute."""
    spec = platform.load_spec(root, plat.id)
    if spec is None:
        raise ModError(f"no launch spec for {plat.id}; fix: run `optilux install`")
    base = root / RUNTIME / plat.id
    mods = {p.slug: p for p in plat.tier_files(TIER) if p.kind == "mod"}
    missing = [slug for slug in (FABRIC_API, *COMPILE_ONLY) if slug not in mods]
    if missing:
        raise ModError(f"the {TIER} tier pins no {', '.join(missing)}; fix: pin it")
    client = [entry for entry in spec["classpath"] if entry["from"] == CLIENT]
    if len(client) != 1:
        raise ModError(f"the launch spec lists {len(client)} client jars; fix: `install --refresh`")
    client_path = base / client[0]["path"]
    check(client_path, "sha1", client[0]["sha1"], "client jar", root)
    compile_only = []
    for slug in COMPILE_ONLY:
        path = base / STORE / mods[slug].file
        check(path, "sha512", mods[slug].sha512, "store jar", root)
        compile_only.append({"path": path.as_posix(), "sha512": mods[slug].sha512})
    client_jar = {"path": client_path.as_posix(), "algorithm": "sha1", "digest": client[0]["sha1"]}
    targets = [client_jar]
    targets += [
        {"path": c["path"], "algorithm": "sha512", "digest": c["sha512"]} for c in compile_only
    ]
    return {
        "schema": INPUTS_SCHEMA,
        "writtenBy": WRITTEN_BY,
        "platform": plat.id,
        "platformFile": plat.path.as_posix(),
        "store": (base / STORE).as_posix(),
        "minecraft": plat.minecraft,
        "loader": plat.loader[1],
        "fabricApi": mods[FABRIC_API].version,
        "depends": depends(root, plat),
        "compileOnly": compile_only,
        "targetJars": targets,
    }


def java_home(root: Path) -> Path:
    """The Temurin `install` unpacked, named by config/java/bench.json."""
    build = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))["runtime"]["build"]
    home = root / JAVA_DIR / build
    if not (home / "bin" / "java.exe").is_file():
        raise ModError(f"no {shown(home, root)}/bin/java.exe; fix: run `optilux install`")
    return home


def gradle_command(mod: Path, home: Path, action: str) -> list[str]:
    return [str(mod / WRAPPER), *FLAGS, f"-Dorg.gradle.java.home={home}", *TASKS[action]]


def gradle_env(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() not in JAVA_ENV}
    env["JAVA_HOME"] = str(home)
    return env


def built_jar(libs: Path, root: Path) -> Path:
    found = sorted(libs.glob(f"{HELPER}-*.jar"))
    if len(found) != 1:
        names = ", ".join(path.name for path in found) or "none"
        raise ModError(
            f"{shown(libs, root)}/ holds {names}, not one helper jar; fix: read Gradle's output"
        )
    return found[0]


def to_store(jar: Path, store: Path, root: Path) -> dict:
    """Copy the jar into the store through a .part file, removing every other helper jar there
    (`launch` refuses two); the copy is re-hashed."""
    digest = platform.sha512(jar)
    removed = []
    for old in sorted(store.glob(launch.HELPER_GLOB)):
        if old.name != jar.name:
            old.unlink()
            removed.append(old.name)
    target = store / jar.name
    part = target.with_name(target.name + ".part")
    shutil.copyfile(jar, part)
    os.replace(part, target)
    check(target, "sha512", digest, "store copy", root)
    return {
        "path": shown(jar, root),
        "bytes": jar.stat().st_size,
        "sha512": digest,
        "store": shown(target, root),
        "removed": removed,
    }


def tested_jar(libs: Path, store: Path, root: Path) -> dict:
    """The jar the tests read and how the store's helper jar, the one `launch` places, compares."""
    jar = built_jar(libs, root)
    digest = platform.sha512(jar)
    placed = launch.store_helper(store)
    if placed is None:
        state = "the store holds no helper jar; fix: `optilux mod build`"
    elif placed.name == jar.name and platform.sha512(placed) == digest:
        state = "the store's copy is equal"
    else:
        state = f"the store's {placed.name} differs; fix: `optilux mod build`"
    return {"path": shown(jar, root), "sha512": digest, "store": state}


def test_counts(results: Path) -> dict:
    """The JUnit XML reports' totals: tests, failures (errors included), skipped, classes."""
    counts = {"tests": 0, "failures": 0, "skipped": 0, "classes": 0}
    for report in sorted(results.glob("TEST-*.xml")):
        suite = ElementTree.parse(report).getroot()  # noqa: S314 Gradle's own reports, mod/build/
        counts["tests"] += int(suite.get("tests", 0))
        counts["failures"] += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        counts["skipped"] += int(suite.get("skipped", 0))
        counts["classes"] += 1
    return counts


def mod(
    root: Path,
    action: str,
    say: Say,
    to_stderr: bool = False,
    runner: Runner | None = None,
    host: launch.Host | None = None,
) -> Outcome:
    """Write the inputs, run Gradle for `action`, then copy the jar (build) or count the tests."""
    runner = runner or run_gradle
    host = host or launch.Host()
    plat = platform.load(root)
    base = root / RUNTIME / plat.id
    found = launch.gate(base, host.processes(), host.logman(), os.getpid())
    if not found.ok:
        blocking = [f"pid {g['pid']} {g['name']} ({', '.join(g['via'])})" for g in found.games]
        blocking += [f"ETW session {name}" for name in found.sessions]
        raise ModError(
            f"the launch gate is closed, a session may be running: {'; '.join(blocking)}; fix: "
            f"quit that game or stop that session, or leave {shown(base, root)}/ in that shell"
        )
    home = java_home(root)
    data = inputs(root, plat)
    mod_dir = root / MOD
    target = mod_dir / INPUTS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    outcome = Outcome(action, depends=data["depends"])
    say(
        f"inputs: {shown(target, root)}: minecraft {data['minecraft']}, fabric-loader "
        f"{data['loader']}, fabric-api {data['fabricApi']}; compile-only "
        f"{', '.join(Path(c['path']).name for c in data['compileOnly'])} sha512-equal; the client "
        "jar sha1-equal to the spec"
    )
    say(f"depends: {', '.join(f'{k} {v}' for k, v in data['depends'].items())}")
    libs = mod_dir / LIBS
    stale = libs.glob(f"{HELPER}-*.jar") if action == "build" else []
    if action == "test":
        stale = (mod_dir / RESULTS).glob("TEST-*.xml")  # counts from this run only
    for path in list(stale):
        path.unlink()
    command = gradle_command(mod_dir, home, action)
    say(f"gradle: {' '.join(command[1:])} on {home.name} (JAVA_HOME)")
    began = time.monotonic()
    code = runner(command, mod_dir, gradle_env(home), to_stderr)
    seconds = round(time.monotonic() - began, 1)
    outcome.gradle = {"command": command, "exitCode": code, "seconds": seconds}
    if action == "test":
        outcome.tests = test_counts(mod_dir / RESULTS)
    if code != 0:
        junit = ""
        if outcome.tests.get("failures"):
            junit = f" ({outcome.tests['failures']} of {outcome.tests['tests']} tests failed)"
        raise ModError(f"Gradle exited {code} after {seconds} s{junit}; fix: read its output above")
    say(f"gradle: exit 0 in {seconds} s")
    if action == "build":
        outcome.jar = to_store(built_jar(libs, root), base / STORE, root)
        jar = outcome.jar
        removed = f"; removed {', '.join(jar['removed'])}" if jar["removed"] else ""
        say(f"jar: {jar['path']}, {jar['bytes']} bytes, sha512 {jar['sha512']}")
        say(f"store: {jar['store']} sha512-equal{removed}")
    else:
        counts = outcome.tests
        if counts["tests"] == 0 or counts["failures"]:
            raise ModError(f"JUnit reports {counts}; fix: read Gradle's output above")
        outcome.jar = tested_jar(libs, base / STORE, root)
        passed = counts["tests"] - counts["skipped"]
        say(
            f"tests: {passed} passed, {counts['skipped']} skipped, in {counts['classes']} "
            f"classes ({MOD}/{RESULTS}/)"
        )
        jar = outcome.jar
        say(f"tested jar: {jar['path']} sha512 {jar['sha512']}; {jar['store']}")
    return outcome


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action", choices=ACTIONS, help="build: the jar into the store; test: the JUnit tests"
    )


def run(args: argparse.Namespace) -> int:
    prefix = f"{PREFIX} {args.action}"
    say: Say = (lambda text: None) if args.json else print
    try:
        outcome = mod(REPO_ROOT, args.action, say, to_stderr=args.json)
    except (ModError, platform.PlatformError, launch.LaunchError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}, indent=1))
        print(f"{prefix}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(outcome.as_json(), indent=1))
    else:
        print(f"{prefix}: ok")
    return 0


VERB = Verb(
    name="mod",
    help="build the helper mod into the store, or run its JUnit tests (Gradle via the wrapper)",
    run=run,
    configure=configure,
    structured=True,
)
