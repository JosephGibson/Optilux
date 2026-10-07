"""`optilux mod build|test` with Gradle mocked: the depends generator from the platform file and
the pinned jars, the inputs Gradle reads, the wrapper's command and environment, the jar into the
store, the JUnit counts, and the refusals that run no Gradle. The wrapper's pins are read from
mod/. Nothing here runs Gradle or reads runtime/ (docs/plans/m1.md D19)."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from optilux import REPO_ROOT, cli, launch, platform
from optilux.verbs import mod as mod_verb

PLATFORM = "mc-fixture"
BENCH = json.loads((REPO_ROOT / "config" / "java" / "bench.json").read_text(encoding="utf-8"))
LOGMAN = (REPO_ROOT / "tests" / "fixtures" / "launch" / "logman.txt").read_text(encoding="utf-8")
CLIENT = b"client jar"
# docs/plans/m1.md P18, and Gradle's published sha256 of its 9.7.1 wrapper jar.
DISTRIBUTION_SHA256 = "acd53f1edaf02f1a8ff99879f8a34b302661a057d9b063ae9e35b552f804d20a"
WRAPPER_JAR_SHA256 = "7a9ce74cff467ca1bf60a4fcd9f05185acceda4d0f382434d393e17864262c5d"


def jar(meta: dict | None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if meta is not None:
            archive.writestr("fabric.mod.json", json.dumps(meta))
        archive.writestr("a/B.class", b"x")
    return buffer.getvalue()


MODS = {
    "fabric-api": ("fabric-api-0.161.0+26.3.jar", "0.161.0+26.3", "fabric-api", "0.161.0+26.3"),
    "sodium": ("sodium-fabric-0.9.2+mc26.3.jar", "mc26.3-0.9.2-fabric", "sodium", "0.9.2+mc26.3"),
    "iris": ("iris-fabric-1.11.7+mc26.3.jar", "1.11.7+26.3-fabric", "iris", "1.11.7+mc26.3"),
}
JARS = {slug: jar({"id": mod_id, "version": v}) for slug, (_, _, mod_id, v) in MODS.items()}


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_root(tmp_path: Path) -> Path:
    """A repo for platform mc-fixture: bench pins fabric-api, sodium and iris under their
    Modrinth versions (which differ from what their jars declare), dev adds one more; the store,
    the client jar named by the spec, the Temurin java.exe and mod/'s wrapper."""
    root = tmp_path / "repo"
    write(root / "config" / "suite.json", json.dumps({"platform": PLATFORM}).encode())

    def pin(slug: str) -> dict:
        name, version, _, _ = MODS[slug]
        sha = hashlib.sha512(JARS[slug]).hexdigest()
        return {
            "slug": slug,
            "version": version,
            "file": name,
            "modrinthVersionId": "X",
            "sha512": sha,
        }

    extra = jar({"id": "viewfinder", "version": "2"})
    plat = {
        "id": PLATFORM,
        "minecraft": "26.3",
        "loader": {"name": "fabric", "version": "0.19.5"},
        "tiers": {
            "bench": {"extends": None, "mods": [pin(slug) for slug in MODS]},
            "dev": {
                "extends": "bench",
                "mods": [
                    {
                        "slug": "viewfinder",
                        "version": "2",
                        "file": "viewfinder.jar",
                        "modrinthVersionId": "X",
                        "sha512": hashlib.sha512(extra).hexdigest(),
                    }
                ],
            },
        },
    }
    write(root / "config" / "platforms" / f"{PLATFORM}.json", json.dumps(plat).encode())
    spec = {
        "classpath": [
            {"path": "libraries/a.jar", "sha1": "0" * 40, "from": "mojang:a"},
            {
                "path": "versions/26.3/26.3.jar",
                "sha1": hashlib.sha1(CLIENT, usedforsecurity=False).hexdigest(),
                "from": "mojang:client",
            },
        ]
    }
    write(platform.spec_path(root, PLATFORM), json.dumps(spec).encode())
    write(root / "config" / "java" / "bench.json", json.dumps(BENCH).encode())
    write(root / "runtime" / "java" / BENCH["runtime"]["build"] / "bin" / "java.exe", b"MZ")
    base = root / "runtime" / PLATFORM
    write(base / "versions" / "26.3" / "26.3.jar", CLIENT)
    for slug, (name, _, _, _) in MODS.items():
        write(base / "files" / name, JARS[slug])
    write(base / "files" / "viewfinder.jar", extra)
    write(root / "mod" / "gradlew.bat", b"@rem fake\r\n")
    return root


class FakeHost:
    def __init__(self, procs: list[launch.ProcessInfo] | None = None) -> None:
        self.procs = procs or []

    def processes(self) -> list[launch.ProcessInfo]:
        return self.procs

    def logman(self) -> str:
        return LOGMAN


class FakeGradle:
    """Records each call; `build` leaves a jar in build/libs/, `test` JUnit XML reports."""

    def __init__(self, code: int = 0, tests: tuple[int, int, int] | None = (5, 0, 0)) -> None:
        self.calls: list[tuple[list[str], Path, dict[str, str], bool]] = []
        self.code = code
        self.tests = tests
        self.jar = b"helper jar"

    def __call__(self, command: list[str], cwd: Path, env: dict[str, str], to_stderr: bool) -> int:
        self.calls.append((command, cwd, env, to_stderr))
        write(cwd / "build" / "libs" / "optilux-helper-0.1.0.jar", self.jar)  # `test` needs `jar`
        if (
            command[-1] != "jar" and self.tests is not None
        ):  # None: Gradle ran no test, so wrote no report
            count, failures, skipped = self.tests
            results = cwd / "build" / "test-results" / "test"
            for name, attrs in (
                ("A", f'tests="{count}" failures="{failures}" errors="0" skipped="{skipped}"'),
                ("B", 'tests="2" failures="0" errors="0" skipped="0"'),
            ):
                write(results / f"TEST-optilux.{name}.xml", f"<testsuite {attrs}/>".encode())
        return self.code


def quiet(text: str) -> None:
    pass


def test_depends_are_exact_at_the_versions_the_pinned_jars_declare(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    plat = platform.load(root)
    assert mod_verb.depends(root, plat) == {
        "minecraft": "=26.3",
        "fabricloader": "=0.19.5",
        "fabric-api": "=0.161.0+26.3",
        "sodium": "=0.9.2+mc26.3",
        "iris": "=1.11.7+mc26.3",
    }  # the bench tier only: dev's viewfinder is no dependency
    store = root / "runtime" / PLATFORM / "files"
    write(store / MODS["iris"][0], jar({"id": "iris", "version": "9"}))
    with pytest.raises(mod_verb.ModError, match=r"store jar .*iris-fabric-1.11.7.*: sha512 "):
        mod_verb.depends(root, plat)
    # A jar on its pin that declares no version is refused, never guessed.
    bare = jar({"id": "iris"})
    write(store / MODS["iris"][0], bare)
    data = json.loads(plat.path.read_text(encoding="utf-8"))
    data["tiers"]["bench"]["mods"][2]["sha512"] = hashlib.sha512(bare).hexdigest()
    plat.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(mod_verb.ModError, match="declares no Fabric id and version"):
        mod_verb.depends(root, platform.load(root))


def test_inputs_name_the_versions_and_the_pinned_jars(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    plat = platform.load(root)
    data = mod_verb.inputs(root, plat)
    base = (root / "runtime" / PLATFORM).as_posix()
    assert (data["minecraft"], data["loader"], data["fabricApi"]) == (
        "26.3",
        "0.19.5",
        MODS["fabric-api"][1],
    )
    assert [Path(c["path"]).name for c in data["compileOnly"]] == [
        MODS["sodium"][0],
        MODS["iris"][0],
    ]
    assert data["targetJars"][0] == {
        "path": f"{base}/versions/26.3/26.3.jar",
        "algorithm": "sha1",
        "digest": hashlib.sha1(CLIENT, usedforsecurity=False).hexdigest(),
    }
    assert [t["algorithm"] for t in data["targetJars"]] == ["sha1", "sha512", "sha512"]
    assert data["platformFile"] == plat.path.as_posix() and data["store"] == f"{base}/files"
    write(root / "runtime" / PLATFORM / "versions" / "26.3" / "26.3.jar", b"other")
    with pytest.raises(mod_verb.ModError, match=r"client jar .*26.3.jar: sha1 "):
        mod_verb.inputs(root, plat)


def test_build_runs_the_wrapper_on_temurin_and_stores_the_jar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_root(tmp_path)
    store = root / "runtime" / PLATFORM / "files"
    write(store / "optilux-helper-0.0.9.jar", b"old")  # launch refuses two helper jars
    write(root / "mod" / "build" / "libs" / "optilux-helper-0.0.9.jar", b"stale")
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Xmx1m")
    monkeypatch.setenv("GRADLE_OPTS", "-Dx=y")
    gradle = FakeGradle()
    lines: list[str] = []
    outcome = mod_verb.mod(root, "build", lines.append, runner=gradle, host=FakeHost())
    home = root / "runtime" / "java" / BENCH["runtime"]["build"]
    command, cwd, env, to_stderr = gradle.calls[0]
    assert command == [
        str(root / "mod" / "gradlew.bat"),
        "--no-daemon",
        "--console=plain",
        f"-Dorg.gradle.java.home={home}",
        "jar",
    ]
    assert cwd == root / "mod" and env["JAVA_HOME"] == str(home) and to_stderr is False
    assert "JAVA_TOOL_OPTIONS" not in env and "GRADLE_OPTS" not in env
    written = (root / "mod" / "build" / "optilux" / "inputs.json").read_bytes()
    assert b"\r" not in written and json.loads(written)["depends"]["sodium"] == "=0.9.2+mc26.3"
    digest = hashlib.sha512(gradle.jar).hexdigest()
    assert sorted(p.name for p in store.glob("optilux-helper*")) == ["optilux-helper-0.1.0.jar"]
    assert (store / "optilux-helper-0.1.0.jar").read_bytes() == gradle.jar
    assert outcome.jar == {
        "path": "mod/build/libs/optilux-helper-0.1.0.jar",
        "bytes": len(gradle.jar),
        "sha512": digest,
        "store": f"runtime/{PLATFORM}/files/optilux-helper-0.1.0.jar",
        "removed": ["optilux-helper-0.0.9.jar"],
    }
    assert lines[-2] == f"jar: mod/build/libs/optilux-helper-0.1.0.jar, 10 bytes, sha512 {digest}"
    assert lines[-1] == (
        f"store: runtime/{PLATFORM}/files/optilux-helper-0.1.0.jar sha512-equal; removed "
        "optilux-helper-0.0.9.jar"
    )
    # `launch` then places exactly that jar beside the tier.
    assert launch.store_helper(store) == store / "optilux-helper-0.1.0.jar"


def test_test_runs_junit_and_counts_its_reports(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    results = root / "mod" / "build" / "test-results" / "test"
    write(results / "TEST-optilux.Gone.xml", b'<testsuite tests="9" failures="9"/>')  # stale
    gradle = FakeGradle(tests=(5, 0, 1))
    lines: list[str] = []
    outcome = mod_verb.mod(root, "test", lines.append, runner=gradle, host=FakeHost())
    assert gradle.calls[0][0][-2:] == ["test", "--rerun"]
    assert outcome.tests == {"tests": 7, "failures": 0, "skipped": 1, "classes": 2}
    assert lines[-2] == "tests: 6 passed, 1 skipped, in 2 classes (mod/build/test-results/test/)"
    digest = hashlib.sha512(gradle.jar).hexdigest()
    assert lines[-1] == (
        f"tested jar: mod/build/libs/optilux-helper-0.1.0.jar sha512 {digest}; the store holds no "
        "helper jar; fix: `optilux mod build`"
    )
    # `test` stores nothing; the store's jar, the one `launch` places, is compared with the tested.
    store = root / "runtime" / PLATFORM / "files"
    assert not (store / "optilux-helper-0.1.0.jar").exists()
    write(store / "optilux-helper-0.1.0.jar", gradle.jar)
    outcome = mod_verb.mod(root, "test", quiet, runner=gradle, host=FakeHost())
    assert outcome.jar["store"] == "the store's copy is equal"
    write(store / "optilux-helper-0.1.0.jar", b"older build")
    outcome = mod_verb.mod(root, "test", quiet, runner=gradle, host=FakeHost())
    assert outcome.jar["store"] == (
        "the store's optilux-helper-0.1.0.jar differs; fix: `optilux mod build`"
    )
    with pytest.raises(
        mod_verb.ModError, match=r"Gradle exited 1 after .* \(2 of 7 tests failed\)"
    ):
        mod_verb.mod(root, "test", quiet, runner=FakeGradle(1, (5, 2, 0)), host=FakeHost())
    with pytest.raises(mod_verb.ModError, match=r"JUnit reports .*'tests': 0,"):
        mod_verb.mod(root, "test", quiet, runner=FakeGradle(0, None), host=FakeHost())


def test_a_failed_build_stores_nothing(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    with pytest.raises(mod_verb.ModError, match="Gradle exited 1 after"):
        mod_verb.mod(root, "build", quiet, runner=FakeGradle(1), host=FakeHost())
    assert not list((root / "runtime" / PLATFORM / "files").glob("optilux-helper*"))


def test_a_running_game_or_a_missing_jdk_runs_no_gradle(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    java = root / "runtime" / PLATFORM / "game" / "java.exe"
    game = launch.ProcessInfo(77, "java.exe", str(java), None, [])
    gradle = FakeGradle()
    with pytest.raises(
        mod_verb.ModError, match=r"a session may be running: pid 77 java.exe \(exe\); fix"
    ):
        mod_verb.mod(root, "build", quiet, runner=gradle, host=FakeHost([game]))
    (root / "runtime" / "java" / BENCH["runtime"]["build"] / "bin" / "java.exe").unlink()
    with pytest.raises(mod_verb.ModError, match=r"bin/java.exe; fix: run `optilux install`"):
        mod_verb.mod(root, "build", quiet, runner=gradle, host=FakeHost())
    assert gradle.calls == []


def test_the_cli_prints_the_jar_or_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_root(tmp_path)
    gradle = FakeGradle()
    monkeypatch.setattr(mod_verb, "REPO_ROOT", root)
    monkeypatch.setattr(mod_verb, "run_gradle", gradle)
    monkeypatch.setattr(launch, "Host", FakeHost)
    assert cli.main(["mod", "build"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("inputs: mod/build/optilux/inputs.json: minecraft 26.3, ")
    assert out[-1] == "optilux mod build: ok"
    assert cli.main(["mod", "test", "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["ok"] is True and found["tests"]["tests"] == 7 and gradle.calls[-1][3] is True
    monkeypatch.setattr(mod_verb, "run_gradle", FakeGradle(code=1))
    assert cli.main(["mod", "build"]) == 1
    assert capsys.readouterr().err.startswith("optilux mod build: Gradle exited 1 after ")


def test_the_wrapper_is_pinned_and_gradle_finds_no_other_jdk() -> None:
    mod = REPO_ROOT / "mod"
    wrapper = (mod / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(encoding="utf-8")
    assert (
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.7.1-bin.zip"
        in wrapper
    )
    assert f"distributionSha256Sum={DISTRIBUTION_SHA256}" in wrapper.splitlines()
    jar_sha = hashlib.sha256((mod / "gradle" / "wrapper" / "gradle-wrapper.jar").read_bytes())
    assert jar_sha.hexdigest() == WRAPPER_JAR_SHA256
    properties = (mod / "gradle.properties").read_text(encoding="utf-8").splitlines()
    for line in (
        "org.gradle.daemon=false",
        "org.gradle.java.installations.auto-detect=false",
        "org.gradle.java.installations.auto-download=false",
    ):
        assert line in properties
    build = (mod / "build.gradle").read_text(encoding="utf-8")
    assert "id 'net.fabricmc.fabric-loom' version '1.18.2'" in build
    assert "withSourcesJar" not in build and "accessWidener" not in build


def test_a_gradle_that_hangs_is_stopped_with_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import sys

    monkeypatch.setattr(mod_verb, "GRADLE_TIMEOUT", 0.5)
    command = [sys.executable, "-c", "import time; time.sleep(5)"]
    with pytest.raises(mod_verb.ModError, match=r"ran past 0.5 s"):
        mod_verb.run_gradle(command, Path.cwd(), dict(os.environ), False)
