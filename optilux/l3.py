"""docs/offline.md#levels' L3 (plans/m4.md M4.P02): the pack's functions tested before any launch.
`check L3` runs it (optilux/verbs/check.py); no module here enters run's imports (P4).

Each include under the pack's shaders/lib/ with a test file under tests/l3/ (lib/fog.glsl's is
tests/l3/lib/fog.py) runs on the GPU: moderngl's standalone context, GL 3.3 core as the game's,
compiles the include, expanded as Iris expands it (offline.expand) at the test's option values
under Iris's macros, into a fragment program that calls the function once per texel of a float
target, its arguments read from a float texture of synthetic cases, one column per case; the
target is read back and each case held to the test's numpy golden within its tolerance. A failure
names the include, the function and the input.

A test file is Python: its TESTS list holds Function entries, their cases and goldens numpy arrays
of float32, each golden computed from the formula the function implements, never read off the GPU.
"""

import hashlib
import importlib.util
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import moderngl
import numpy as np

from optilux import offline

TESTS_DIR = "tests/l3"
LIBRARY = "lib"
INCLUDE_ENDING = ".glsl"
# The game's context (docs/shader.md#facts); create_standalone_context gives the same here
# (docs/offline.md#tools: "3.3.0 Core Profile Context" on the RX 7800 XT).
GL_VERSION = 330
# What a case's argument takes of the case texture: texel rows, and how the program reads them (a
# mat4 by column, as GLSL's mat4(vec4, ...) builds it).
ROWS = {"float": 1, "int": 1, "bool": 1, "vec2": 1, "vec3": 1, "vec4": 1, "mat4": 4}
READ = {
    "float": "{0}.x",
    "int": "int({0}.x)",
    "bool": "({0}.x > 0.5)",
    "vec2": "{0}.xy",
    "vec3": "{0}.xyz",
    "vec4": "{0}",
    "mat4": "mat4({0}, {1}, {2}, {3})",
}
COMPONENTS = {"float": 1, "int": 1, "bool": 1, "vec2": 2, "vec3": 3, "vec4": 4}
WRITE = {
    "float": "vec4({0}, 0.0, 0.0, 0.0)",
    "int": "vec4(float({0}), 0.0, 0.0, 0.0)",
    "bool": "vec4(({0}) ? 1.0 : 0.0, 0.0, 0.0, 0.0)",
    "vec2": "vec4({0}, 0.0, 0.0)",
    "vec3": "vec4({0}, 0.0)",
    "vec4": "({0})",
}
# A float32 holds every integer of magnitude up to 2^24 exactly, so an int crosses the float
# texture and target unchanged within it.
EXACT_INT = 1 << 24
# The harness's own names, apart from any the pack declares.
OWN = "l3_"
VERTEX = """#version 330 core
// One triangle over the whole target, its corners from gl_VertexID: no vertex buffer.
void main() {
    vec2 corner = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(corner * 2.0 - 1.0, 0.0, 1.0);
}
"""
# The driver's compile log (AMD: "ERROR: 0:4: 'x' : undeclared identifier", seen 2026-10-27).
DRIVER_LINE = re.compile(r"(?:ERROR|WARNING): 0:(?P<line>\d+): (?P<text>.*)")
DECLARED = r"\buniform\s+\w+\s+{0}\s*[;\[]"
# Cases shown per failing function: enough to see a pattern, few enough to read.
SHOWN = 3


class L3Error(RuntimeError):
    """A test file, a pack or an OpenGL context L3 cannot use; the message names the fix."""


@dataclass(frozen=True)
class Argument:
    """An argument per case: its name in messages, its GLSL type, its values as float32 (cases,),
    (cases, n) for a vecn or (cases, 4, 4) by row and column for a mat4."""

    name: str
    type: str
    values: np.ndarray | Sequence


@dataclass(frozen=True)
class Texture:
    """A sampler the include reads: RGBA float texels (height, width, 4), filtered nearest or
    linear, clamped to its edges."""

    texels: np.ndarray
    filter: str = "nearest"


@dataclass(frozen=True)
class Function:
    """A function of an include over its cases, held to its golden (cases,) or (cases, n): within
    `tolerance` plus `relative` times the golden's magnitude, per component, else equal or both
    NaN. The include is expanded at `options` (the pack's own options, Iris's edits), its uniforms
    set to `uniforms` and its samplers to `textures`; `note` tells apart tests that differ only
    there (far 32)."""

    function: str
    returns: str
    arguments: tuple[Argument, ...]
    golden: np.ndarray | Sequence
    tolerance: float
    relative: float = 0.0
    options: Mapping[str, str] = field(default_factory=dict)
    uniforms: Mapping[str, object] = field(default_factory=dict)
    textures: Mapping[str, Texture] = field(default_factory=dict)
    note: str = ""


def context() -> moderngl.Context:
    """moderngl's standalone context at the game's GL version."""
    try:
        return moderngl.create_standalone_context(require=GL_VERSION)
    except Exception as error:  # noqa: BLE001 glcontext raises bare Exception without a driver
        raise L3Error(
            f"no OpenGL {GL_VERSION // 100}.{GL_VERSION % 100 // 10} core context ({error}); fix: "
            "run L3 on the bench machine, whose driver gives one"
        ) from None


def renderer(ctx: moderngl.Context) -> str:
    return f"{ctx.info['GL_RENDERER']}, {ctx.info['GL_VERSION']}"


# Test files.


def test_files(tests: Path, pack: offline.Pack) -> tuple[dict[str, Path], list[str]]:
    """Each include under lib/ that has a test file, by its path from shaders/; and the problems:
    a test file under tests/l3/lib/ whose include the pack lacks."""
    found: dict[str, Path] = {}
    problems = []
    home = tests / LIBRARY
    for path in sorted(home.rglob("*.py")) if home.is_dir() else []:
        include = PurePosixPath(path.relative_to(tests).as_posix()).with_suffix(INCLUDE_ENDING)
        if str(include) in pack.files:
            found[str(include)] = path
        else:
            problems.append(
                f"{shown_path(path, tests)} tests {offline.SHADERS}/{include}, which {pack.label} "
                "lacks; fix: its include, or remove the test"
            )
    return found, problems


def shown_path(path: Path, tests: Path) -> str:
    return f"{TESTS_DIR}/{path.relative_to(tests).as_posix()}"


def load(path: Path, name: str, kind: type) -> list:
    """A test file's list `name` of `kind` entries, its module run apart from sys.modules."""
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(f"optilux_l3_{digest}", path)
    if spec is None or spec.loader is None:
        raise L3Error(f"{path} is no Python file importlib loads; fix: a .py test file")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 the test file's own failure, named with its file
        raise L3Error(f"{path.name} failed to load: {type(error).__name__}: {error}") from None
    found = getattr(module, name, None)
    if not isinstance(found, list) or not all(isinstance(entry, kind) for entry in found):
        raise L3Error(
            f"{path.name} holds no list {name} of {kind.__name__} entries; fix: define it"
        )
    return found


# The program.


def option_values(pack: offline.Pack, options: Mapping[str, str]) -> dict[str, str]:
    """A test's option values, each an option the pack declares at one of its values: a name Iris
    does not register would leave the include as written, untested at the value meant."""
    declared = offline.declared(pack).found
    for name, value in options.items():
        found = declared.get(name)
        if found is None:
            raise L3Error(
                f"option {name}: the pack declares no such option; fix: one of "
                f"{', '.join(declared) or 'none'}"
            )
        if value not in found.values:
            raise L3Error(f"option {name} {value!r}: fix: one of {' '.join(found.values)}")
    return dict(options)


def label(options: Mapping[str, str]) -> str:
    return ", ".join(f"{n} {v}" for n, v in sorted(options.items())) or "the defaults"


def program_source(
    pack: offline.Pack,
    includes: Sequence[str],
    values: Mapping[str, str],
    macros: Sequence[tuple[str, str | None]],
    harness: Sequence[str],
) -> tuple[str, list[tuple[str, int] | None]]:
    """The fragment program: #version, Iris's macros, the includes expanded at the option values,
    then the harness; and per line where it came from in the pack (None: L3's own)."""
    text = [
        f"#version {GL_VERSION} core",
        *(f"#define {n}" if v is None else f"#define {n} {v}" for n, v in macros),
    ]
    origins: list[tuple[str, int] | None] = [None] * len(text)
    for include in includes:
        try:
            expanded = offline.expand(pack, include, values)
        except offline.L0Error as error:
            raise L3Error(str(error)) from None
        for file, number, line in expanded:
            text.append(line)
            origins.append((file, number))
    text += harness
    origins += [None] * len(harness)
    return "\n".join(text) + "\n", origins


def driver_lines(log: str, origins: Sequence[tuple[str, int] | None]) -> list[str]:
    """The driver's compile errors, each line mapped to the pack's file and line."""
    found = []
    for raw in log.splitlines():
        match = DRIVER_LINE.search(raw)
        if match is None or not match["text"].strip(" '") or "compilation terminated" in raw:
            continue
        number = int(match["line"])
        origin = origins[number - 1] if 0 < number <= len(origins) else None
        at = f"{offline.SHADERS}/{origin[0]}:{origin[1]}" if origin else f"L3's line {number}"
        found.append(f"{at}: {match['text'].strip()}")
    return found or [log.strip()]


def harness(test: Function) -> list[str]:
    """main: the case's arguments from its column of the case texture, the call, its result."""
    calls = []
    row = 0
    for arg in test.arguments:
        texels = [f"texelFetch({OWN}cases, ivec2({OWN}at, {row + j}), 0)" for j in range(4)]
        calls.append(READ[arg.type].format(*texels))
        row += ROWS[arg.type]
    call = f"{test.function}({', '.join(calls)})"
    return [
        f"uniform sampler2D {OWN}cases;",
        f"layout(location = 0) out vec4 {OWN}result;",
        "void main() {",
        f"    int {OWN}at = int(gl_FragCoord.x);",
        f"    {OWN}result = {WRITE[test.returns].format(call)};",
        "}",
    ]


def argument_values(arg: Argument, cases: int) -> np.ndarray:
    """An argument's values as float32 in the case texture's form: (cases, n) or (cases, 4, 4)."""
    if arg.type not in ROWS:
        raise L3Error(f"argument {arg.name}: no type {arg.type!r}; fix: one of {', '.join(ROWS)}")
    values = np.asarray(arg.values)
    shape = (cases, 4, 4) if arg.type == "mat4" else (cases, COMPONENTS[arg.type])
    if values.shape == (cases,) and shape[1:] == (1,):
        values = values.reshape(shape)
    if values.shape != shape:
        raise L3Error(
            f"argument {arg.name}: a {arg.type} per case takes {shape}, not {values.shape}"
        )
    if arg.type in ("int", "bool") and (
        not np.array_equal(values, np.round(values)) or np.abs(values).max(initial=0) >= EXACT_INT
    ):
        raise L3Error(f"argument {arg.name}: an {arg.type} takes whole values below 2^24")
    return values.astype(np.float32)


def case_texels(arguments: Sequence[Argument], cases: int) -> np.ndarray:
    """The case texture's texels (rows, cases, 4): per argument its rows, a mat4's by column."""
    data = np.zeros((max(1, sum(ROWS[a.type] for a in arguments)), cases, 4), np.float32)
    row = 0
    for arg in arguments:
        values = argument_values(arg, cases)
        if arg.type == "mat4":
            for column in range(4):
                data[row + column] = values[:, :, column]
        else:
            data[row, :, : values.shape[1]] = values
        row += ROWS[arg.type]
    return data


def set_uniform(program: moderngl.Program, name: str, value: object) -> None:
    """One uniform of the program to a value: a bool, an int, a float, a vector or a mat4 by row
    and column; none when the driver dropped it as unread."""
    if name not in program:
        return
    member = program[name]
    if not isinstance(member, moderngl.Uniform):
        raise L3Error(f"uniform {name}: no plain uniform in the program; fix: a sampler texture")
    array = np.asarray(value)
    if array.shape == (4, 4):
        member.write(np.asarray(value, np.float32).T.tobytes())  # GL takes a mat4 by column
    elif isinstance(value, bool | np.bool_ | int | np.integer):
        member.value = int(value)
    elif array.ndim == 0:
        member.value = float(np.float32(array))
    else:
        member.value = tuple(float(x) for x in array.astype(np.float32))


def declared_names(source: str, names: Sequence[str]) -> list[str]:
    """The names no uniform declaration of the source gives: a test setting one sets nothing."""
    bare = offline.COMMENT.sub(" ", source)
    return [n for n in names if not re.search(DECLARED.format(re.escape(n)), bare)]


# Running and judging.


def number(value: float) -> str:
    """A float32 as its shortest decimal."""
    single = np.float32(value)
    if single == 0 or 1e-4 <= abs(single) < 1e7 or not np.isfinite(single):
        return np.format_float_positional(single, unique=True, trim="0")
    return np.format_float_scientific(single, unique=True, trim="0")


def shown_value(kind: str, values: np.ndarray) -> str:
    """One case's value as the message gives it."""
    flat = np.asarray(values, np.float64).ravel()
    if kind == "bool":
        return "true" if flat[0] > 0.5 else "false"
    if kind == "int":
        return str(int(flat[0]))
    if flat.size == 1:
        return number(flat[0])
    if kind == "mat4":
        rows = np.asarray(values).reshape(4, 4)
        return "mat4 rows " + " ".join(f"({', '.join(number(x) for x in r)})" for r in rows)
    return f"({', '.join(number(x) for x in flat)})"


def judge(
    got: np.ndarray, golden: np.ndarray, tolerance: float, relative: float
) -> tuple[np.ndarray, np.ndarray]:
    """Per case whether it fails and its largest difference (infinite where one side alone is
    NaN or infinite): a component passes when it equals the golden, both are NaN, or it lies
    within tolerance + relative x |golden|."""
    wide, gold = got.astype(np.float64), golden.astype(np.float64)
    with np.errstate(invalid="ignore"):
        same = (got == golden) | (np.isnan(got) & np.isnan(golden))
        diff = np.where(same, 0.0, np.nan_to_num(np.abs(wide - gold), nan=np.inf))
        ok = same | (diff <= tolerance + relative * np.abs(gold))
    return ~ok.all(axis=1), diff.max(axis=1)


def run_function(
    ctx: moderngl.Context,
    pack: offline.Pack,
    include: str,
    test: Function,
    macros: Sequence[tuple[str, str | None]],
) -> dict:
    """One Function on the GPU: its program built and drawn over its cases, each judged."""
    where = label(test.options) + (f", {test.note}" if test.note else "")
    entry = {
        "function": test.function,
        "options": where,
        "cases": 0,
        "failed": 0,
        "worst": 0.0,
        "tolerance": test.tolerance,
        "relative": test.relative,
        "problems": [],
    }
    shown = f"{offline.SHADERS}/{include}"
    try:
        if test.returns not in WRITE:
            raise L3Error(f"returns {test.returns!r}; fix: one of {', '.join(WRITE)}")
        golden = np.asarray(test.golden, np.float32)
        cases = len(golden)
        limit = int(ctx.info["GL_MAX_TEXTURE_SIZE"])
        if not 0 < cases <= limit:
            raise L3Error(f"{cases} cases; fix: 1 to {limit}, the texture width this context takes")
        golden = golden.reshape(cases, COMPONENTS[test.returns])
        texels = case_texels(test.arguments, cases)
        values = option_values(pack, test.options)
        source, origins = program_source(pack, [include], values, macros, harness(test))
        unset = declared_names(source, [*test.uniforms, *test.textures])
        if unset:
            raise L3Error(
                f"sets {', '.join(unset)}, which the include declares no uniform of at "
                f"{where}; fix: the include's own names"
            )
    except L3Error as error:
        entry["problems"].append(f"{shown}: {test.function} at {where}: {error}")
        return entry
    try:
        program = ctx.program(vertex_shader=VERTEX, fragment_shader=source)
    except moderngl.Error as error:
        entry["problems"] += [
            f"{shown}: {test.function} at {where} does not compile: {line}"
            for line in driver_lines(str(error), origins)
        ]
        return entry
    owned: list = [program]
    try:
        got = draw(ctx, program, test, texels, cases, owned)
    except L3Error as error:
        entry["problems"].append(f"{shown}: {test.function} at {where}: {error}")
        return entry
    finally:
        for thing in owned:
            thing.release()
    entry["cases"] = cases
    got = got[:, : golden.shape[1]]
    failed, diff = judge(got, golden, test.tolerance, test.relative)
    entry["failed"] = int(failed.sum())
    entry["worst"] = float(diff.max(initial=0.0))
    allowed = number(test.tolerance) + (
        f" + {number(test.relative)} x |golden|" if test.relative else ""
    )
    for case in np.flatnonzero(failed)[:SHOWN]:
        inputs = ", ".join(
            f"{a.name} {shown_value(a.type, argument_values(a, cases)[case])}"
            for a in test.arguments
        )
        entry["problems"].append(
            f"{shown}: {test.function}({inputs}) = {shown_value(test.returns, got[case])}, "
            f"golden {shown_value(test.returns, golden[case])}, off by "
            f"{number(float(diff[case]))} beyond {allowed}, at {where} (case {case} of {cases})"
        )
    if entry["failed"] > SHOWN:
        entry["problems"].append(
            f"{shown}: {test.function} at {where}: {entry['failed']} of {cases} cases fail in all"
        )
    return entry


def draw(
    ctx: moderngl.Context,
    program: moderngl.Program,
    test: Function,
    texels: np.ndarray,
    cases: int,
    owned: list,
) -> np.ndarray:
    """The program drawn once over a (cases, 1) RGBA32F target, read back as (cases, 4)."""
    rows = texels.shape[0]
    cases_texture = ctx.texture((cases, rows), 4, texels.tobytes(), dtype="f4")
    owned.append(cases_texture)
    cases_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
    cases_texture.use(0)
    if f"{OWN}cases" in program:
        program[f"{OWN}cases"].value = 0  # type: ignore[union-attr]  # a sampler: its unit
    for unit, (name, texture) in enumerate(test.textures.items(), start=1):
        data = np.asarray(texture.texels, np.float32)
        if data.ndim != 3 or data.shape[2] != 4:
            raise L3Error(f"texture {name}: texels (height, width, 4), not {data.shape}")
        bound = ctx.texture((data.shape[1], data.shape[0]), 4, data.tobytes(), dtype="f4")
        owned.append(bound)
        mode = {"nearest": moderngl.NEAREST, "linear": moderngl.LINEAR}[texture.filter]
        bound.filter = (mode, mode)
        bound.repeat_x = bound.repeat_y = False
        bound.use(unit)
        if name in program:
            program[name].value = unit  # type: ignore[union-attr]  # a sampler: its unit
    for name, value in test.uniforms.items():
        set_uniform(program, name, value)
    target = ctx.texture((cases, 1), 4, dtype="f4")
    owned.append(target)
    frame = ctx.framebuffer(color_attachments=[target])
    owned.append(frame)
    frame.use()
    shape = ctx.vertex_array(program, [])
    owned.append(shape)
    shape.render(moderngl.TRIANGLES, vertices=3)
    return np.frombuffer(target.read(), np.float32).reshape(cases, 4).copy()


# Custom uniforms: each held to the GLSL it replaces (gpu-iris.md#custom-uniforms), its definition
# evaluated by Iris's own engine (optilux/expressions.py), the GLSL on the GPU.

UNIFORMS_FILE = "uniforms.py"
# The runner takes one value per name, so case k's inputs and definitions carry this suffix.
CASE = "_l3c{}"
# Iris's functions that follow the clock or an unseeded Random (SmoothFloat, IrisFunctions): the
# runner's clock is not the game's, so no golden holds them.
CLOCKED = re.compile(r"\b(?:smooth|random|randomInt)\s*\(")
# A name an expression reads: not a member after a dot, not a function before a parenthesis.
NAME = re.compile(r"(?<![\w.])[A-Za-z_]\w*(?![\w(])(?!\s+\()")

# (inputs, expressions) -> values by name, as expressions.evaluate takes and returns them.
Engine = Callable[[list, list], dict]


@dataclass(frozen=True)
class Uniform:
    """A custom uniform of shaders.properties held to the GLSL it replaces, per case: Iris's engine
    evaluates its definition and the definitions it reads, each after those it reads (Iris
    resolves forward references), over `inputs`; the GPU evaluates `glsl` over the same inputs set
    as uniforms, after `includes` (paths under shaders/) for the functions it calls. The engine's
    value is the golden, within `tolerance` plus `relative` times its magnitude; both read the
    pack at `options`."""

    name: str
    glsl: str
    inputs: tuple[Argument, ...]
    tolerance: float
    relative: float = 0.0
    options: Mapping[str, str] = field(default_factory=dict)
    includes: tuple[str, ...] = ()
    note: str = ""


def resolved(
    target: offline.Custom, definitions: Mapping[str, offline.Custom]
) -> list[offline.Custom]:
    """The definitions the target reads, then itself, each after those it reads."""
    order: list[offline.Custom] = []
    state: dict[str, str] = {}

    def visit(custom: offline.Custom, path: tuple[str, ...]) -> None:
        if state.get(custom.name) == "done":
            return
        if state.get(custom.name) == "open":
            raise L3Error(f"{' -> '.join((*path, custom.name))} reads itself; fix: cut the cycle")
        state[custom.name] = "open"
        for name in NAME.findall(custom.expression):
            if name in definitions:
                visit(definitions[name], (*path, custom.name))
        state[custom.name] = "done"
        order.append(custom)

    visit(target, ())
    return order


def renamed(expression: str, names: set[str], suffix: str) -> str:
    """The expression with each of `names` it reads carrying the case's suffix."""
    return NAME.sub(lambda m: m[0] + suffix if m[0] in names else m[0], expression)


def case_value(kind: str, row: np.ndarray) -> object:
    """One case's value of an input, as the runner and moderngl take it."""
    if kind == "bool":
        return bool(row[0] > 0.5)
    if kind == "int":
        return int(row[0])
    if kind == "float":
        return np.float32(row[0])
    return row


def engine_value(value: object) -> np.ndarray:
    """A value the runner printed as float32 components, a bool as 1 or 0."""
    if isinstance(value, bool):
        return np.array([1.0 if value else 0.0], np.float32)
    return np.atleast_1d(np.asarray(value, np.float32)).ravel()


def uniform_harness(test: Uniform, kind: str, undeclared: Sequence[str]) -> list[str]:
    """The inputs no include declares, then main writing the GLSL's value."""
    types = {a.name: a.type for a in test.inputs}
    return [
        *(f"uniform {types[name]} {name};" for name in undeclared),
        f"layout(location = 0) out vec4 {OWN}result;",
        "void main() {",
        f"    {OWN}result = {WRITE[kind].format(test.glsl)};",
        "}",
    ]


def run_uniform(
    ctx: moderngl.Context,
    pack: offline.Pack,
    test: Uniform,
    macros: Sequence[tuple[str, str | None]],
    engine: Engine,
) -> dict:
    """One Uniform: its definitions through the engine and its GLSL on the GPU, per case."""
    where = label(test.options) + (f", {test.note}" if test.note else "")
    shown = f"{offline.SHADERS}/{offline.PROPERTIES}"
    entry: dict = {
        "uniform": test.name,
        "options": where,
        "line": None,
        "reads": [],
        "cases": 0,
        "failed": 0,
        "worst": 0.0,
        "tolerance": test.tolerance,
        "relative": test.relative,
        "problems": [],
    }
    try:
        values = option_values(pack, test.options)
        variant = offline.Variant(tuple(sorted(values.items())))
        try:
            found = offline.customs(pack, offline.declared(pack), variant, macros)
        except offline.L0Error as error:
            raise L3Error(str(error)) from None
        definitions = {c.name: c for c in found}
        target = definitions.get(test.name)
        if target is None or target.kind != "uniform":
            raise L3Error(f"{shown} defines no uniform {test.name} at {where}; fix: its name")
        entry["line"] = target.line
        chain = resolved(target, definitions)
        entry["reads"] = [c.name for c in chain[:-1]]
        for custom in chain:
            if CLOCKED.search(custom.expression):
                raise L3Error(
                    f"{shown}:{custom.line}: {custom.kind} {custom.name} calls smooth(), random() "
                    "or randomInt(), which follow the clock or an unseeded Random: no golden holds "
                    "it; fix: test a uniform that reads none"
                )
            if custom.type not in WRITE:
                raise L3Error(f"{shown}:{custom.line}: {custom.name}'s type {custom.type!r}")
        cases = len(np.asarray(test.inputs[0].values)) if test.inputs else 1
        rows = {a.name: argument_values(a, cases) for a in test.inputs}
        names = {a.name for a in test.inputs}
        head, _ = program_source(pack, test.includes, values, macros, [])
        undeclared = declared_names(head, [a.name for a in test.inputs])
        harness_lines = uniform_harness(test, target.type, undeclared)
        source, origins = program_source(pack, test.includes, values, macros, harness_lines)
    except L3Error as error:
        entry["problems"].append(f"{shown}: uniform {test.name} at {where}: {error}")
        return entry
    defined = names | {c.name for c in chain}
    inputs, expressions = [], []
    for case in range(cases):
        suffix = CASE.format(case)
        inputs += [
            (a.type, a.name + suffix, case_value(a.type, rows[a.name][case])) for a in test.inputs
        ]
        expressions += [
            (c.type, c.name + suffix, renamed(c.expression, defined, suffix)) for c in chain
        ]
    try:
        printed = engine(inputs, expressions)
        golden = np.stack(
            [engine_value(printed[test.name + CASE.format(case)]) for case in range(cases)]
        )
    except L3Error as error:
        entry["problems"].append(f"{shown}:{target.line}: uniform {test.name}: {error}")
        return entry
    try:
        program = ctx.program(vertex_shader=VERTEX, fragment_shader=source)
    except moderngl.Error as error:
        entry["problems"] += [
            f"{shown}:{target.line}: uniform {test.name}'s GLSL at {where} does not compile: {line}"
            for line in driver_lines(str(error), origins)
        ]
        return entry
    owned: list = [program]
    try:
        got = draw_cases(ctx, program, test, rows, cases, owned)
    finally:
        for thing in owned:
            thing.release()
    entry["cases"] = cases
    got = got[:, : golden.shape[1]]
    failed, diff = judge(got, golden, test.tolerance, test.relative)
    entry["failed"] = int(failed.sum())
    entry["worst"] = float(diff.max(initial=0.0))
    allowed = number(test.tolerance) + (
        f" + {number(test.relative)} x |golden|" if test.relative else ""
    )
    for case in np.flatnonzero(failed)[:SHOWN]:
        at = ", ".join(f"{a.name} {shown_value(a.type, rows[a.name][case])}" for a in test.inputs)
        entry["problems"].append(
            f"{shown}:{target.line}: uniform {test.name} at {at}: Iris's engine "
            f"{shown_value(target.type, golden[case])}, its GLSL {test.glsl!r} "
            f"{shown_value(target.type, got[case])}, off by {number(float(diff[case]))} beyond "
            f"{allowed}, at {where} (case {case} of {cases})"
        )
    if entry["failed"] > SHOWN:
        entry["problems"].append(
            f"{shown}: uniform {test.name} at {where}: {entry['failed']} of {cases} cases fail"
        )
    return entry


def draw_cases(
    ctx: moderngl.Context,
    program: moderngl.Program,
    test: Uniform,
    rows: Mapping[str, np.ndarray],
    cases: int,
    owned: list,
) -> np.ndarray:
    """The program drawn once per case into its texel of a (cases, 1) RGBA32F target, the case's
    inputs set as uniforms first; read back as (cases, 4)."""
    target = ctx.texture((cases, 1), 4, dtype="f4")
    owned.append(target)
    frame = ctx.framebuffer(color_attachments=[target])
    owned.append(frame)
    frame.use()
    shape = ctx.vertex_array(program, [])
    owned.append(shape)
    for case in range(cases):
        for arg in test.inputs:
            set_uniform(program, arg.name, case_value(arg.type, rows[arg.name][case]))
        ctx.viewport = (case, 0, 1, 1)
        shape.render(moderngl.TRIANGLES, vertices=3)
    return np.frombuffer(target.read(), np.float32).reshape(cases, 4).copy()


def check_uniforms(
    ctx: moderngl.Context,
    pack: offline.Pack,
    tests: Path,
    macros: Sequence[tuple[str, str | None]],
    engine: Engine | None,
) -> dict:
    """Every custom uniform of shaders.properties at the defaults named by a test of
    tests/l3/uniforms.py, and each of its tests run."""
    shown = f"{offline.SHADERS}/{offline.PROPERTIES}"
    path = tests / UNIFORMS_FILE
    found: dict = {"file": shown, "test": None, "defined": [], "tests": [], "problems": []}
    try:
        defaults = offline.customs(pack, offline.declared(pack), offline.Variant(), macros)
    except offline.L0Error as error:
        found["problems"].append(str(error))
        return found
    found["defined"] = [c.name for c in defaults if c.kind == "uniform"]
    entries: list[Uniform] = []
    if path.is_file():
        found["test"] = shown_path(path, tests)
        try:
            entries = load(path, "UNIFORMS", Uniform)
        except L3Error as error:
            found["problems"].append(f"{found['test']}: {error}")
    named = {t.name for t in entries}
    found["problems"] += [
        f"{shown}:{c.line}: uniform {c.name} has no test in {TESTS_DIR}/{UNIFORMS_FILE} holding "
        "it to the GLSL it replaces; fix: add one"
        for c in defaults
        if c.kind == "uniform" and c.name not in named
    ]
    if entries and engine is None:
        found["problems"].append(f"{len(entries)} uniform tests and no expression engine to run")
        return found
    for test in entries:
        found["tests"].append(run_uniform(ctx, pack, test, macros, engine))  # type: ignore[arg-type]  # set above
    found["problems"] += [p for t in found["tests"] for p in t["problems"]]
    return found


def check(
    ctx: moderngl.Context,
    pack: offline.Pack,
    tests: Path,
    macros: Sequence[tuple[str, str | None]],
    engine: Engine | None = None,
) -> dict:
    """L3 over a pack: per include under lib/ its test file's functions, or none; the custom
    uniforms of shaders.properties; every problem."""
    files, problems = test_files(tests, pack)
    includes = []
    for include in sorted(p for p in pack.files if is_library(p)):
        path = files.get(include)
        entry: dict = {
            "include": f"{offline.SHADERS}/{include}",
            "test": shown_path(path, tests) if path else None,
            "functions": [],
            "problems": [],
        }
        if path is not None:
            try:
                for test in load(path, "TESTS", Function):
                    entry["functions"].append(run_function(ctx, pack, include, test, macros))
            except L3Error as error:
                entry["problems"].append(f"{shown_path(path, tests)}: {error}")
        entry["problems"] += [p for f in entry["functions"] for p in f["problems"]]
        includes.append(entry)
    uniforms = check_uniforms(ctx, pack, tests, macros, engine)
    problems += [p for entry in includes for p in entry["problems"]] + uniforms["problems"]
    return {"includes": includes, "uniforms": uniforms, "problems": problems}


def is_library(path: str) -> bool:
    return path.startswith(f"{LIBRARY}/") and path.endswith(INCLUDE_ENDING)
