"""config/pipeline.json v0 against the pack under shader/shaders/ (docs/shader.md#pipeline-spec,
plans/m3.md D57): one pass per program file pair, and per pass the samplers and uniforms its two
stages declare (with the program's switches and every option as written), its outputs (the
fragment stage's RENDERTARGETS; the screen for final), the option whose setting changes its code,
and every view of its dimensions in the views file it names."""

import json
import re
from pathlib import Path

import pytest

from optilux import REPO_ROOT, record

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
    "option",
    "budget",
    "views",
)
INCLUDE = re.compile(r'\s*#include\s+"(?P<path>[^"]+)"\s*$')
DIRECTIVE = re.compile(r"\s*#\s*(?P<name>\w+)\s*(?P<rest>.*)$")
DEFINED = re.compile(r"defined\s+(?P<name>\w+)")
# Iris's on/off option: a bare `#define NAME`, an optional comment after it, or the line commented
# out when the option is off (docs/gpu-iris.md#properties-and-options).
OPTION = re.compile(r"\s*(?://)?\s*#define\s+(?P<name>\w+)\s*(?://.*)?$")
# Iris registers an on/off option only when a file tests it with #ifdef or #ifndef
# (OptionAnnotatedSource, 1.11.7); `#if defined` is no reference.
TESTED = re.compile(r"#\s*(?:ifdef|ifndef)\s+(\w+)")
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
TARGETS = re.compile(r"/\*\s*RENDERTARGETS:\s*(?P<list>[0-9][0-9,\s]*?)\s*\*/")
# Iris's colortex format when a pack sets none (InternalTextureFormat.RGBA, GL_RGBA8).
DEFAULT_FORMAT = "RGBA8"


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


def active(lines: list[str]) -> list[str]:
    """The lines a C preprocessor keeps, for the directives this pack uses: #ifdef, #ifndef, #if
    over `defined NAME` terms joined by &&, #else, #endif, #define and #version. Any other directive
    fails the test, so a new form is taught here before the pack uses it."""
    defined: set[str] = set()
    kept: list[bool] = []
    found = []
    for line in lines:
        match = DIRECTIVE.match(line)
        if match is None:
            if all(kept):
                found.append(line)
            continue
        name, rest = match["name"], match["rest"].split("//")[0].strip()
        if name in ("ifdef", "ifndef"):
            kept.append((rest in defined) == (name == "ifdef"))
        elif name == "if":
            terms = [DEFINED.fullmatch(term.strip()) for term in rest.split("&&")]
            assert all(terms), f"#if {rest}: only `defined NAME` terms joined by && are read here"
            kept.append(all(term["name"] in defined for term in terms if term))
        elif name == "else":
            kept[-1] = not kept[-1]
        elif name == "endif":
            kept.pop()
        elif name in ("define", "version"):
            if all(kept):
                found.append(line)
                if name == "define":
                    defined.add(rest.split()[0])
        else:
            raise AssertionError(f"#{name} is not read here")
    assert not kept, "an #if without its #endif"
    return found


def pack_files() -> list[Path]:
    return sorted(path for path in SHADERS.rglob("*") if path.is_file())


def options() -> set[str]:
    """The pack's on/off options: a bare define that some file tests (Iris registers no other)."""
    texts = [path.read_text(encoding="utf-8") for path in pack_files()]
    named = {m["name"] for text in texts for line in text.splitlines() if (m := OPTION.match(line))}
    tested = {name for text in texts for name in TESTED.findall(text)}
    return named & tested


def stage_lines(program: str, suffix: str, off: str | None = None) -> list[str]:
    """A stage's kept lines, every option as written, or `off` switched off as Iris does it."""
    lines = expand(SHADERS / f"{program}.{suffix}")
    if off is not None:
        lines = [
            f"//{line}" if (m := OPTION.match(line)) and m["name"] == off else line
            for line in lines
        ]
    return active(lines)


def code(program: str, off: str | None = None) -> list[str]:
    """Both stages' kept lines that are neither a directive nor a comment."""
    return [
        line
        for suffix in STAGES
        for line in stage_lines(program, suffix, off)
        if line.strip() and not DIRECTIVE.match(line) and not line.strip().startswith(("//", "/*"))
    ]


def load() -> dict:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_the_spec_names_the_pack_its_cycle_and_its_views() -> None:
    spec = load()
    assert (spec["schema"], spec["pack"], spec["cycle"]) == (0, "optilux", 1)
    assert (REPO_ROOT / record.VIEWS / f"{spec['views']}.json").is_file()
    assert all(tuple(p) == PASS_KEYS for p in spec["passes"])
    names = [p["name"] for p in spec["passes"]]
    assert len(set(names)) == len(names)


def test_the_passes_are_the_packs_programs() -> None:
    programs = [p["program"] for p in load()["passes"]]
    assert len(set(programs)) == len(programs)
    files = {path.name for path in SHADERS.iterdir() if path.suffix[1:] in STAGES}
    expected = {f"{program}.{suffix}" for program in programs for suffix in STAGES}
    assert files == expected  # each program has both stages, and no stage file is left out
    for found in load()["passes"]:
        assert found["stage"] == ("final" if found["program"] == "final" else "gbuffers")


def test_each_pass_reads_the_samplers_and_uniforms_its_stages_declare() -> None:
    for found in load()["passes"]:
        declared = {
            (m["type"].startswith("sampler"), m["name"])
            for suffix in STAGES
            for line in stage_lines(found["program"], suffix)
            if (m := UNIFORM.match(line))
        }
        assert found["inputs"] == {
            "samplers": sorted(name for sampler, name in declared if sampler),
            "uniforms": sorted(name for sampler, name in declared if not sampler),
        }, found["program"]


def test_each_pass_writes_the_targets_its_fragment_stage_names() -> None:
    for found in load()["passes"]:
        text = "\n".join(stage_lines(found["program"], "fsh"))
        targets = TARGETS.findall(text)
        if found["program"] == "final":
            assert not targets
            assert found["outputs"] == [{"buffer": "screen", "format": None, "scale": 1.0}]
            continue
        assert len(targets) == 1, found["program"]
        buffers = [f"colortex{int(n)}" for n in targets[0].replace(",", " ").split()]
        assert not re.search(r"const\s+int\s+colortex\d+Format", text)  # no format of its own
        assert found["outputs"] == [
            {"buffer": buffer, "format": DEFAULT_FORMAT, "scale": 1.0} for buffer in buffers
        ], found["program"]


def test_each_pass_names_the_option_that_changes_its_code() -> None:
    assert options() == {"BENCH_DETERMINISTIC"}
    for found in load()["passes"]:
        program = found["program"]
        changed = [name for name in sorted(options()) if code(program, name) != code(program)]
        assert len(changed) <= 1, f"{program}: v0 holds one option a pass, {changed} change it"
        assert found["option"] == (changed[0] if changed else None), program


def test_no_pass_reads_an_input_that_moves_between_frames() -> None:
    """cycle 1's premise: in the default build (BENCH_DETERMINISTIC on) no stage declares a frame
    counter, a wall-clock or smoothed uniform, or one 26.3 eases by the wall clock."""
    assert load()["cycle"] == 1
    for found in load()["passes"]:
        declared = {
            m["name"]
            for suffix in STAGES
            for line in stage_lines(found["program"], suffix)
            if (m := UNIFORM.match(line))
        }
        assert not declared & MOVING, found["program"]
        off = {
            m["name"]
            for suffix in STAGES
            for line in stage_lines(found["program"], suffix, off="BENCH_DETERMINISTIC")
            if (m := UNIFORM.match(line))
        }
        if found["program"] != "final":  # with the option off, vanilla's fog comes back
            assert {"fogStart", "fogEnd"} <= off, found["program"]


def test_each_pass_lists_every_view_of_its_dimensions() -> None:
    spec = load()
    views = json.loads(
        (REPO_ROOT / record.VIEWS / f"{spec['views']}.json").read_text(encoding="utf-8")
    )["views"]
    for found in spec["passes"]:
        assert found["dimensions"] and set(found["dimensions"]) <= set(record.DIMENSIONS)
        assert found["views"] == [v["id"] for v in views if v["dim"] in found["dimensions"]]
        assert found["budget"] is None  # M4's


def test_the_preprocessor_reads_branches() -> None:
    lines = [
        "#define A 1",
        "#ifdef A",
        "a",
        "#else",
        "not a",
        "#endif",
        "#if defined A && defined B",
        "a and b",
        "#endif",
        "#ifndef B",
        "no b",
        "#endif",
    ]
    assert [line for line in active(lines) if not line.startswith("#")] == ["a", "no b"]


@pytest.mark.parametrize("line", ["#if A > 1", "#elif defined A", "#undef A"])
def test_the_preprocessor_refuses_a_directive_it_does_not_read(line: str) -> None:
    with pytest.raises(AssertionError, match="read here"):
        active([line, "#endif"])
