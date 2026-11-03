"""config/pipeline.json v1 against the pack under shader/shaders/ (docs/shader.md#pipeline-spec,
plans/m4.md M4.P06): the colour targets as resources (name, buffer, format, clear, history,
scale), and one pass per program, in frame order, its dimensions the ones whose folder holds it
(the root is the overworld's, world-1 the Nether's, world1 the End's: offline.WORLD_FOLDERS), the
samplers and uniforms its two stages declare there at the pack's defaults, its outputs (the
fragment stage's RENDERTARGETS; none for an empty DRAWBUFFERS; the screen for final), the options
whose setting changes its code, and every view of its dimensions in the views file it names."""

import json
import re
from pathlib import Path

import pytest

from optilux import REPO_ROOT, offline, record

PIPELINE = REPO_ROOT / "config" / "pipeline.json"
SHADERS = REPO_ROOT / "shader" / "shaders"
STAGES = ("vsh", "fsh")
PASS_KEYS = (
    "name",
    "program",
    "stage",
    "dimensions",
    "inputs",
    "outputs",
    "feature",
    "options",
    "budget",
    "views",
)
RESOURCE_KEYS = ("name", "buffer", "format", "clear", "history", "scale", "why")
# The dimension each world folder serves; the root serves the overworld (offline.WORLD_FOLDERS).
FOLDERS = {
    "minecraft:overworld": "",
    "minecraft:the_nether": "world-1",
    "minecraft:the_end": "world1",
}
INCLUDE = re.compile(r'\s*#include\s+"(?P<path>[^"]+)"\s*$')
DIRECTIVE = re.compile(r"\s*#\s*(?P<name>\w+)\s*(?P<rest>.*)$")
# Inputs that move from frame to frame, so a pass reading one breaks cycle 1
# (docs/shader.md#determinism-and-taa): Iris's frame counters and its wall-clock and smoothed
# uniforms (plans/m3.md P19), and 26.3's fogStart and fogEnd (eased by each frame's wall-clock
# length, under /tick freeze too) and textureMatrix (the glint's wall-clock scroll).
MOVING = {
    "frameCounter",
    "frameTime",
    "frameTimeCounter",
    "frameTimeSmooth",
    "currentDate",
    "currentTime",
    "currentYearTime",
    "eyeBrightnessSmooth",
    "wetness",
    "fogStart",
    "fogEnd",
    "textureMatrix",
}
UNIFORM = re.compile(r"\s*uniform\s+(?P<type>\w+)\s+(?P<name>\w+)\s*;")
TARGETS = re.compile(r"/\*\s*(?:RENDERTARGETS|DRAWBUFFERS):\s*(?P<list>[0-9,\s]*?)\s*\*/")
FORMAT = re.compile(r"const\s+int\s+(?P<buffer>colortex\d+)Format\s*=\s*(?P<format>\w+)\s*;")
CLEARED = re.compile(r"const\s+bool\s+(?P<buffer>colortex\d+)Clear\s*=\s*false\s*;")
CLEAR_COLOR = re.compile(
    r"const\s+vec4\s+(?P<buffer>colortex\d+)ClearColor\s*=\s*vec4\((?P<values>[^)]*)\)\s*;"
)
# Iris's colortex format when a pack sets none (InternalTextureFormat.RGBA, GL_RGBA8).
DEFAULT_FORMAT = "RGBA8"
# #if's words, as Python reads them; `defined` is taken first.
OPERATORS = (("&&", " and "), ("||", " or "), ("!", " not "))


def expand(path: Path) -> list[str]:
    """A stage file with its includes in place, as Iris expands them: a path from the shaders/
    root, or one relative to the including file."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = INCLUDE.match(line)
        if match is None:
            lines.append(line)
            continue
        target = match["path"]
        base = SHADERS if target.startswith("/") else path.parent
        lines += expand(base / target.lstrip("/"))
    return lines


def number(name: str, defined: dict[str, str]) -> str:
    """A name in #if: its value when it is an integer, else 0, as C's preprocessor reads it."""
    value = defined.get(name, "0")
    return f" {int(value)} " if re.fullmatch(r"-?\d+", value) else " 0 "


def condition(rest: str, defined: dict[str, str]) -> bool:
    """A #if or #elif expression: `defined NAME` (or with parentheses), names (number()),
    integers, comparisons and ! && ||."""
    text = re.sub(
        r"defined\s*\(?\s*(\w+)\s*\)?", lambda m: f" {int(m[1] in defined)} ", rest.split("//")[0]
    )
    text = re.sub(r"[A-Za-z_]\w*", lambda m: number(m[0], defined), text)
    text = text.replace("!=", " <> ")
    for operator, word in OPERATORS:
        text = text.replace(operator, word)
    text = text.replace("<>", "!=")
    assert re.fullmatch(r"[\d\s()<>=!andort]*", text), f"#if {rest}: not read here"
    return bool(eval(text, {"__builtins__": {}}))  # noqa: S307 digits, comparisons and and/or/not


def active(lines: list[str], defined: dict[str, str] | None = None) -> list[str]:
    """The lines a C preprocessor keeps, for the directives this pack uses: #ifdef, #ifndef, #if
    and #elif over condition()'s expressions, #else, #endif, #define and #version. Any other
    directive fails the test, so a new form is taught here before the pack uses it."""
    defined = dict(defined or {})
    # Per open #if: (this branch taken, an earlier branch was taken).
    kept: list[tuple[bool, bool]] = []
    found = []
    for line in lines:
        match = DIRECTIVE.match(line)
        if match is None:
            if all(k for k, _ in kept):
                found.append(line)
            continue
        name, rest = match["name"], match["rest"].split("//")[0].strip()
        live = all(k for k, _ in kept)
        if name in ("ifdef", "ifndef"):
            taken = (rest in defined) == (name == "ifdef")
            kept.append((taken, taken))
        elif name == "if":
            taken = live and condition(rest, defined)
            kept.append((taken, taken))
        elif name == "elif":
            before = kept[-1][1]
            outer = all(k for k, _ in kept[:-1])
            taken = not before and outer and condition(rest, defined)
            kept[-1] = (taken, before or taken)
        elif name == "else":
            kept[-1] = (not kept[-1][1], True)
        elif name == "endif":
            kept.pop()
        elif name in ("define", "version"):
            if live:
                found.append(line)
                if name == "define":
                    parts = rest.split(None, 1)
                    defined[parts[0]] = parts[1].strip() if len(parts) > 1 else ""
        else:
            raise AssertionError(f"#{name} is not read here")
    assert not kept, "an #if without its #endif"
    return found


def pack() -> offline.Pack:
    return offline.from_folder("shader/", REPO_ROOT / "shader")


def option_values() -> dict[str, list[str]]:
    """Each option's values, its default first, as Iris registers them (offline.declared)."""
    options = offline.declared(pack()).found
    return {
        name: [found.default, *[v for v in found.values if v != found.default]]
        for name, found in options.items()
    }


def edit(lines: list[str], values: dict[str, str]) -> list[str]:
    return [offline.edited(line, values) for line in lines]


def stage_lines(
    program: str, folder: str, suffix: str, values: dict[str, str] | None = None
) -> list[str]:
    """A stage's kept lines at the defaults, or with `values` set as Iris edits them."""
    path = SHADERS / folder / f"{program}.{suffix}"
    return active(edit(expand(path), values or {}))


def code(program: str, folder: str, values: dict[str, str] | None = None) -> list[str]:
    """Both stages' kept lines that are neither a directive nor a comment."""
    return [
        line
        for suffix in STAGES
        for line in stage_lines(program, folder, suffix, values)
        if line.strip() and not DIRECTIVE.match(line) and not line.strip().startswith(("//", "/*"))
    ]


def folders_of(program: str) -> dict[str, str]:
    """The dimensions whose folder holds the program, each with that folder."""
    return {
        dim: folder
        for dim, folder in FOLDERS.items()
        if all((SHADERS / folder / f"{program}.{s}").is_file() for s in STAGES)
    }


def declared(program: str) -> dict[str, set[str]]:
    """The samplers and uniforms both stages declare at the defaults, over every folder of it."""
    found: dict[str, set[str]] = {"samplers": set(), "uniforms": set()}
    for folder in folders_of(program).values():
        for suffix in STAGES:
            for line in stage_lines(program, folder, suffix):
                if m := UNIFORM.match(line):
                    found["samplers" if "sampler" in m["type"] else "uniforms"].add(m["name"])
    return found


def load() -> dict:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def all_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SHADERS.rglob("*") if p.is_file())


def test_the_spec_names_the_pack_its_cycle_and_its_views() -> None:
    spec = load()
    assert (spec["schema"], spec["pack"], spec["cycle"]) == (1, "optilux", 1)
    assert (REPO_ROOT / record.VIEWS / f"{spec['views']}.json").is_file()
    assert all(tuple(p) == PASS_KEYS for p in spec["passes"])
    assert all(tuple(r) == RESOURCE_KEYS for r in spec["resources"])
    for key in ("passes", "resources"):
        names = [p["name"] for p in spec[key]]
        assert len(set(names)) == len(names)


def test_the_resources_are_the_formats_and_clears_the_pack_sets() -> None:
    text = all_text()
    formats = {m["buffer"]: m["format"] for m in FORMAT.finditer(text)}
    kept = {m["buffer"] for m in CLEARED.finditer(text)}
    colors = {
        m["buffer"]: [float(v) for v in m["values"].split(",")] for m in CLEAR_COLOR.finditer(text)
    }
    resources = load()["resources"]
    assert {r["buffer"]: r["format"] for r in resources} == formats
    for found in resources:
        buffer = found["buffer"]
        assert found["clear"] == (False if buffer in kept else colors[buffer]), buffer
        assert found["scale"] == 1.0
        assert found["why"]


def test_the_passes_are_the_packs_programs() -> None:
    passes = load()["passes"]
    programs = [p["program"] for p in passes]
    assert len(set(programs)) == len(programs)
    for folder in set(FOLDERS.values()):
        files = {p.name for p in (SHADERS / folder).iterdir() if p.suffix[1:] in STAGES}
        expected = {
            f"{p['program']}.{s}"
            for p in passes
            for s in STAGES
            if folder in {FOLDERS[d] for d in p["dimensions"]}
        }
        assert files == expected, folder or "the root"
    for found in passes:
        assert found["dimensions"] == [d for d in FOLDERS if d in folders_of(found["program"])]
        stage = found["program"].split("_")[0]
        assert found["stage"] == stage if stage in ("gbuffers", "shadow") else found["program"]


def test_each_pass_reads_the_samplers_and_uniforms_its_stages_declare() -> None:
    for found in load()["passes"]:
        names = declared(found["program"])
        assert found["inputs"] == {k: sorted(v) for k, v in names.items()}, found["program"]


def test_each_pass_writes_the_targets_its_fragment_stage_names() -> None:
    resources = {r["buffer"]: r for r in load()["resources"]}
    for found in load()["passes"]:
        if found["program"] == "final":
            assert found["outputs"] == [
                {"resource": "screen", "buffer": "screen", "format": None, "scale": 1.0}
            ]
            continue
        lists = set()
        for folder in folders_of(found["program"]).values():
            text = "\n".join(stage_lines(found["program"], folder, "fsh"))
            targets = TARGETS.findall(text)
            assert len(targets) == 1, found["program"]
            lists.add(targets[0])
        assert len(lists) == 1, f"{found['program']} writes other targets in another dimension"
        buffers = [f"colortex{int(n)}" for n in lists.pop().replace(",", " ").split()]
        assert found["outputs"] == [
            {
                "resource": resources[b]["name"],
                "buffer": b,
                "format": resources[b]["format"] if b in resources else DEFAULT_FORMAT,
                "scale": 1.0,
            }
            for b in buffers
        ], found["program"]


def test_each_pass_names_the_options_that_change_its_code() -> None:
    values = option_values()
    assert set(values) == {"BENCH_DETERMINISTIC", "LIGHT_PATH", "E2_LOAD"}
    for found in load()["passes"]:
        program = found["program"]
        changed = sorted(
            name
            for name, (default, *others) in values.items()
            for folder in folders_of(program).values()
            if any(code(program, folder, {name: v}) != code(program, folder) for v in others)
        )
        assert found["options"] == sorted(set(changed)), program


def test_no_pass_reads_an_input_that_moves_between_frames() -> None:
    """cycle 1's premise: in the default build (BENCH_DETERMINISTIC on) no stage declares a frame
    counter, a wall-clock or smoothed uniform, or one 26.3 eases by the wall clock."""
    assert load()["cycle"] == 1
    for found in load()["passes"]:
        names = declared(found["program"])
        assert not (names["uniforms"] & MOVING), found["program"]


def test_each_resource_read_is_written_earlier_or_cleared() -> None:
    """In frame order (the passes' order), a colour target a pass samples was written by an
    earlier pass or is cleared every frame; else it carries the last frame's values, which only
    a resource flagged history may do (none in M4.P06)."""
    spec = load()
    resources = {r["buffer"]: r for r in spec["resources"]}
    written: set[str] = set()
    for found in spec["passes"]:
        for sampler in found["inputs"]["samplers"]:
            if sampler in resources:
                resource = resources[sampler]
                fresh = sampler in written or resource["clear"] is not False
                assert fresh or resource["history"], f"{found['name']} reads {sampler} unwritten"
        written |= {o["buffer"] for o in found["outputs"]}
    assert not any(r["history"] for r in spec["resources"])
    assert {o for p in spec["passes"] for o in (x["buffer"] for x in p["outputs"])} >= set(
        b for b, r in resources.items() if r["clear"] is False
    )


def test_each_pass_lists_every_view_of_its_dimensions() -> None:
    spec = load()
    views = json.loads(
        (REPO_ROOT / record.VIEWS / f"{spec['views']}.json").read_text(encoding="utf-8")
    )["views"]
    for found in spec["passes"]:
        assert found["dimensions"] and set(found["dimensions"]) <= set(record.DIMENSIONS)
        assert found["views"] == [v["id"] for v in views if v["dim"] in found["dimensions"]]
        assert found["budget"] is None  # M4.P11's rows set them (plans/m4.md D84)


def test_the_preprocessor_reads_branches() -> None:
    lines = [
        "#define A 1",
        "#define N 4",
        "#ifdef A",
        "a",
        "#else",
        "not a",
        "#endif",
        "#if defined A && defined B",
        "a and b",
        "#elif N == 4",
        "n is 4",
        "#else",
        "neither",
        "#endif",
        "#if defined(B) || N > 2",
        "b or n over 2",
        "#endif",
        "#ifndef B",
        "no b",
        "#endif",
        "#if !defined A",
        "not a again",
        "#endif",
    ]
    kept = [line for line in active(lines) if not line.startswith("#")]
    assert kept == ["a", "n is 4", "b or n over 2", "no b"]


@pytest.mark.parametrize("line", ["#undef A", "#if A + foo()"])
def test_the_preprocessor_refuses_a_directive_it_does_not_read(line: str) -> None:
    with pytest.raises(AssertionError, match="read here"):
        active([line, "#endif"])
