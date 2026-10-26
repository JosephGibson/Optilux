"""Iris's expression engine outside the game (docs/offline.md#tools, gpu-iris.md#custom-uniforms):
optilux/IrisExpressions.java run by the pinned Temurin's java as a single source file, with the
pinned Iris jar (sha512, the platform file) and the launch spec's JOML and fastutil jars (sha1) on
its classpath, each hash-checked before every start; L3 evaluates a pack's custom uniforms in it.

- Inputs and expressions go in order: each expression may read the inputs and the expressions
  before it, as a custom uniform reads Iris's inputs and the variables it resolves first; the
  caller orders them.
- Floats cross as float32 both ways: an input as its exact hex form, a result as Java's shortest
  decimal that reads back to the same float32. A mat4 is a 4x4 array by row and column, like
  numpy's, crossing column by column as JOML's Matrix4f holds it.
"""

import json
import math
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from optilux import platform
from optilux.launch import JAVA_ENV
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, STORE

RUNNER = "optilux/IrisExpressions.java"
IRIS = "iris"
# The launch spec's classpath entries the engine needs besides Iris: Matrix4f and the vectors, and
# the resolver's maps; each by its Maven group and artifact, the loader's prefix dropped.
LIBRARIES = ("org.joml:joml", "it.unimi.dsi:fastutil")
TYPES = ("bool", "int", "float", "vec2", "vec3", "vec4", "mat4")
SIZES = {"vec2": 2, "vec3": 3, "vec4": 4}
# JOML reads its vectors through sun.misc.Unsafe by default, which JDK 25 warns about on stderr;
# its plain path keeps stderr for errors. The arithmetic is the same.
JAVA_OPTIONS = ("-Djoml.nounsafe=true",)
# The source compile and Iris's function table take about 1 s.
TIMEOUT = 120

Value = bool | int | float | Sequence[float] | np.ndarray
Result = bool | int | np.float32 | np.ndarray


class ExpressionError(RuntimeError):
    """A runner that cannot start, or an input or expression it refused; the message names the
    fix."""


def maven(source: str) -> str:
    """A spec entry's `from` without its loader: mojang:org.joml:joml:1.10.9 -> org.joml:joml:..."""
    return source.split(":", 1)[-1]


def classpath(root: Path) -> list[Path]:
    """The Iris jar from the store and the spec's JOML and fastutil, each against its pin."""
    plat = platform.load(root)
    mods = [p for p in plat.tier_files("bench") if p.kind == "mod" and p.slug == IRIS]
    if len(mods) != 1:
        raise ExpressionError(f"the bench tier pins no single {IRIS}; fix: restore its pin")
    jars = [(root / RUNTIME / plat.id / STORE / mods[0].file, "sha512", mods[0].sha512)]
    spec = platform.load_spec(root, plat.id)
    if spec is None:
        raise ExpressionError(f"no launch spec for {plat.id}; fix: run `optilux install`")
    for library in LIBRARIES:
        found = [e for e in spec["classpath"] if maven(e["from"]).startswith(library + ":")]
        if len(found) != 1:
            raise ExpressionError(
                f"the launch spec holds {len(found)} {library} jars, not one; fix: read the "
                "engine's classpath again"
            )
        jars.append((root / RUNTIME / plat.id / found[0]["path"], "sha1", found[0]["sha1"]))
    for path, algorithm, pin in jars:
        shown = path.relative_to(root).as_posix()
        if not path.is_file():
            raise ExpressionError(f"{shown} is missing; fix: run `optilux install`")
        actual = platform.digest(path, algorithm)
        if actual != pin:
            raise ExpressionError(
                f"{shown}: {algorithm} {actual} differs from its pin {pin}; fix: never work around "
                "it: run `optilux install`, which names the pin it breaks"
            )
    return [path for path, _, _ in jars]


def java(root: Path) -> Path:
    """The pinned Temurin's java under runtime/java/<build>/, as launch starts the game's."""
    profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    exe = root / JAVA_DIR / profile["runtime"]["build"] / "bin" / "java.exe"
    if not exe.is_file():
        raise ExpressionError(f"no {exe.relative_to(root).as_posix()}; fix: run `optilux install`")
    return exe


def exact(value: float | np.floating) -> str:
    """A float32 as Float.parseFloat reads it back bit for bit."""
    single = float(np.float32(value))
    if math.isnan(single):
        return "NaN"
    if math.isinf(single):
        return "Infinity" if single > 0 else "-Infinity"
    return single.hex()


def encode(kind: str, name: str, value: Value) -> str:
    """One input's line: its values in the runner's form."""
    if kind == "bool":
        if not isinstance(value, bool):
            raise ExpressionError(f"input {name}: a bool takes True or False, not {value!r}")
        text = "true" if value else "false"
    elif kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExpressionError(f"input {name}: an int takes an int, not {value!r}")
        text = str(value)
    else:
        floats = np.asarray(value, dtype=np.float32)
        shape = {"float": (), "mat4": (4, 4)}.get(kind, (SIZES.get(kind),))
        if floats.shape != shape:
            raise ExpressionError(f"input {name}: a {kind} takes shape {shape}, not {floats.shape}")
        # A mat4 crosses column by column (JOML's Matrix4f.set(float[])).
        flat = floats.T.ravel() if kind == "mat4" else floats.ravel()
        text = ",".join(exact(x) for x in flat)
    return f"in\t{kind}\t{name}\t{text}"


def decode(kind: str, value: object) -> Result:
    """One printed value as float32 numpy, a mat4 back to rows and columns."""
    if kind in ("bool", "int"):
        return value  # type: ignore[return-value]  # JSON's own bool and int
    if kind == "float":
        return np.float32(value)  # type: ignore[arg-type]  # a JSON number
    floats = np.asarray(value, dtype=np.float32)
    return floats.reshape(4, 4).T if kind == "mat4" else floats


def check_line(kind: str, name: str, text: str = "") -> None:
    """A line's type, name and text as the runner's tab-separated lines can carry them."""
    if kind not in TYPES:
        raise ExpressionError(f"{name}: no type {kind!r}; fix: one of {', '.join(TYPES)}")
    if not name.isidentifier() or any(c in text for c in "\t\r\n"):
        raise ExpressionError(f"{name!r}: a name is an identifier and an expression one line")


def evaluate(
    root: Path,
    inputs: Sequence[tuple[str, str, Value]],
    expressions: Sequence[tuple[str, str, str]],
) -> dict[str, Result]:
    """Each (type, name, expression) evaluated by Iris's engine over the (type, name, value)
    inputs, by name; ExpressionError on a refused line, naming it and the engine's message."""
    lines = []
    for kind, name, value in inputs:
        check_line(kind, name)
        lines.append(encode(kind, name, value))
    for kind, name, text in expressions:
        check_line(kind, name, text)
        lines.append(f"expr\t{kind}\t{name}\t{text}")
    command = [
        str(java(root)),
        *JAVA_OPTIONS,
        "-cp",
        os.pathsep.join(str(path) for path in classpath(root)),
        str(root / RUNNER),
    ]
    env = {key: value for key, value in os.environ.items() if key not in JAVA_ENV}
    try:
        done = subprocess.run(  # noqa: S603 argv list of the pinned java and the repo's source
            command,
            input="\n".join(lines) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExpressionError(f"the expression runner did not run: {error}") from None
    printed = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
    refused = [entry for entry in printed if "error" in entry]
    if refused:
        line = lines[refused[0]["line"] - 1]
        raise ExpressionError(f"Iris's engine refused {line!r}: {refused[0]['error']}")
    if done.returncode != 0 or len(printed) != len(expressions):
        raise ExpressionError(
            f"the expression runner exited {done.returncode} with {len(printed)} of "
            f"{len(expressions)} values: {done.stderr.strip()}"
        )
    return {entry["name"]: decode(entry["type"], entry["value"]) for entry in printed}
