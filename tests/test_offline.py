"""`check L0` (docs/offline.md#levels, plans/m3.md M3.P04): Iris's option rules, the variant matrix
from a fixture pack, the profile check's refusals, and glslang's runs on the hello pack and broken
copies of it, skipped where runtime/tools/ lacks glslang (CI), as `windows` tests skip elsewhere."""

import json
import re
import shutil
from pathlib import Path

import pytest
from conftest import copy_config, similarity_home

from optilux import REPO_ROOT, offline
from optilux.verbs import check as check_verb

PINS = json.loads((REPO_ROOT / "config" / "tools.json").read_text(encoding="utf-8"))["glslang"]
GLSLANG = REPO_ROOT / "runtime" / "tools" / PINS["unpack"] / PINS["exe"]
needs_glslang = pytest.mark.skipif(not GLSLANG.is_file(), reason="no glslang under runtime/tools/")
DIMENSIONS = list(offline.WORLD_FOLDERS)
PASSES = [
    {"name": "surface", "program": "gbuffers_basic", "dimensions": DIMENSIONS},
    {"name": "present", "program": "final", "dimensions": DIMENSIONS},
]
OPTIONS = (
    "#define FAST // a switch on\n"
    "//#define SLOW // a switch off\n"
    "#define QUALITY 2 // [1 2 3]\n"
    "#define UNTESTED\n"
    "#define NO_LIST 4\n"
    "const float shadowDistance = 96.0; //[64.0 96.0]\n"
    "const int notIrisConst = 2; //[1 2]\n"
    "#ifdef FAST\n#endif\n#ifndef SLOW\n#endif\n"
    "#ifdef UNTESTED // a comment voids the test\n#endif\n"
)
VERTEX = (
    '#version 330 core\n#include "/lib/options.glsl"\nvoid main() { gl_Position = vec4(0.0); }\n'
)
FRAGMENT = (
    "#version 330 core\n"
    '#include "lib/options.glsl"\n'
    "out vec4 color;\n"
    "void main() { color = vec4(QUALITY); }\n"
)


def fixture_pack(world_nether: bool = False) -> offline.Pack:
    files = {
        "lib/options.glsl": OPTIONS,
        "gbuffers_basic.vsh": VERTEX,
        "gbuffers_basic.fsh": FRAGMENT,
        "final.vsh": VERTEX,
        "final.fsh": FRAGMENT,
        "shaders.properties": "screen = FAST\n",
    }
    if world_nether:
        files |= {
            "world-1/gbuffers_basic.vsh": VERTEX,
            "world-1/gbuffers_basic.fsh": FRAGMENT.replace('"lib/', '"/lib/'),
            "world-1/final.vsh": VERTEX,
            "world-1/final.fsh": FRAGMENT.replace('"lib/', '"/lib/'),
        }
    return offline.Pack("fixture/", files)


def test_the_matrix_is_the_defaults_and_each_option_switched_alone() -> None:
    options, points, builds, problems = offline.plan(fixture_pack(), PASSES)
    assert {n: (o.kind, o.default, o.values) for n, o in options.found.items()} == {
        "FAST": ("bool", "true", ("true", "false")),
        "QUALITY": ("value", "2", ("1", "2", "3")),
        "SLOW": ("bool", "false", ("true", "false")),
        "shadowDistance": ("value", "96.0", ("64.0", "96.0")),
    }  # UNTESTED: no #ifdef reads it; NO_LIST: no list; notIrisConst: no const Iris takes
    assert [v.label for v in points] == [
        "defaults",
        "FAST false",
        "QUALITY 1",
        "QUALITY 3",
        "SLOW true",
        "shadowDistance 64.0",
    ]
    assert len(builds) == 2 * 3 * 6 and not problems
    assert {b.folder for b in builds} == {""}  # no world folder: every dimension the root's


def test_a_dimension_takes_its_world_folder_whole() -> None:
    """ShaderPack: world-1 holds programs, so the Nether's come from it alone, never merged."""
    _, _, builds, problems = offline.plan(fixture_pack(world_nether=True), PASSES)
    assert not problems
    by_dimension = {b.dimension: b.folder for b in builds}
    assert by_dimension == {
        "minecraft:overworld": "",
        "minecraft:the_nether": "world-1",
        "minecraft:the_end": "",
    }


def test_the_spec_and_the_pack_must_agree() -> None:
    pack = fixture_pack()
    pack.files["gbuffers_textured.vsh"] = VERTEX
    pack.files["gbuffers_textured.fsh"] = FRAGMENT
    _, _, _, problems = offline.plan(
        pack, [*PASSES, {"name": "x", "program": "composite", "dimensions": DIMENSIONS}]
    )
    assert any("names program gbuffers_textured" in p for p in problems)  # it would go unchecked
    assert any("composite lacks its .vsh or .fsh" in p for p in problems)
    pack.files[offline.DIMENSION_PROPERTIES] = "dimension.world0 = minecraft:overworld\n"
    with pytest.raises(offline.L0Error, match=r"dimension\.properties maps its dimensions"):
        offline.plan(pack, PASSES)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("#define X", ("bool", "true")),
        ("   //#define X // off", ("bool", "false")),
        ("// #define X", ("bool", "false")),
        ("#define X//glued", ("bool", "true")),
        ("#define X 1 // [1 2]", ("value", "1")),
        ("#define X -0.5 //[-0.5 0.5]", ("value", "-0.5")),
        ("#define X 1", None),
        ("#define X 1 // no list", None),
        ("//#define X 1 //[1 2]", None),  # a leading comment only on an on/off define
        ("#define X(a) a", None),
        ("const bool shadowHardwareFiltering = true;", ("bool", "true")),
        ("const float sunPathRotation = -40.0; // [-40.0 0.0]", ("value", "-40.0")),
        ("const float notIrisConst = 1.0; //[1.0 2.0]", None),
        ("const int shadowMapResolution = 2048;", None),  # a number needs its list
    ],
)
def test_iris_reads_an_option_line(line: str, expected: tuple[str, str] | None) -> None:
    found = offline.parse_line(line)
    assert (None if found is None else (found.kind, found.default)) == expected  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("line", "tested"),
    [("#ifdef X", "X"), ("  #ifndef X  ", "X"), ("#ifdef X // why", None), ("#if defined X", None)],
)
def test_only_a_bare_ifdef_or_ifndef_registers_an_on_off_option(
    line: str, tested: str | None
) -> None:
    assert offline.parse_line(line) == tested


def test_a_value_option_lists_its_default_and_conflicts_drop_it() -> None:
    """StringOption.create adds a default its list lacks (Unbound's COLORED_LIGHTING 0); two
    declarations with different defaults drop the option (OptionSet's merge), equal ones join
    their lists."""
    found = offline.parse_line("#define COLORED_LIGHTING 0 //[128 192 256]")
    assert isinstance(found, offline.Declaration) and found.allowed == ("128", "192", "256", "0")
    pack = offline.Pack(
        "two/",
        {
            "final.vsh": '#include "/a.glsl"\n#include "/b.glsl"\nvoid main() {}\n',
            "final.fsh": "void main() {}\n",
            "a.glsl": "#define SAME 1 //[1 2]\n#define DIFFERENT 1 //[1 2]\n",
            "b.glsl": "#define SAME 1 //[1 3]\n#define DIFFERENT 2 //[1 2]\n",
        },
    )
    options = offline.declared(pack)
    assert options.found["SAME"].values == ("1", "2", "3")
    assert "DIFFERENT" not in options.found and list(options.conflicts) == ["DIFFERENT"]


def test_a_variant_edits_its_lines_as_iris_does() -> None:
    values = {"FAST": "false", "SLOW": "true", "QUALITY": "3", "shadowDistance": "64.0"}
    assert offline.edited("#define FAST // a switch on", values) == "//#define FAST // a switch on"
    assert offline.edited("  //#define SLOW // off", values) == "#define SLOW // off"
    assert offline.edited("#define QUALITY 2 // [1 2 3]", values) == "#define QUALITY 3"
    assert (
        offline.edited("const float shadowDistance = 96.0; //[64.0 96.0]", values)
        == "const float shadowDistance = 64.0; //[64.0 96.0]"
    )
    assert offline.edited("#define OTHER 2 //[1 2]", values) == "#define OTHER 2 //[1 2]"


def test_includes_expand_from_the_root_or_the_file_and_refuse_a_cycle() -> None:
    pack = offline.Pack(
        "p/",
        {
            "a.fsh": '#include "/lib/b.glsl"\nmain\n',
            "lib/b.glsl": '#include "c.glsl"\nb\n',
            "lib/c.glsl": "c\n",
            "loop.fsh": '#include "loop.fsh"\n',
        },
    )
    assert [(f, n, t) for f, n, t in offline.expand(pack, "a.fsh", {})] == [
        ("lib/c.glsl", 1, "c"),
        ("lib/b.glsl", 2, "b"),
        ("a.fsh", 2, "main"),
    ]
    with pytest.raises(offline.L0Error, match="an include cycle"):
        offline.expand(pack, "loop.fsh", {})


def test_iris_macros_follow_the_pins() -> None:
    macros = dict(offline.iris_macros("26.3", "1.11.7+26.3-fabric", "4"))
    assert (macros["MC_VERSION"], macros["IRIS_VERSION"], macros["MC_MIPMAP_LEVEL"]) == (
        "260300",
        "11107",
        "4",
    )  # platform.md R8; formatVersionString
    assert macros["IS_IRIS"] is None and macros["MC_RENDER_STAGE_HAND_TRANSLUCENT"] == "23"
    assert "MC_GLSL_VERSION" not in macros  # the driver's: unmodeled
    assert check_verb.macros(REPO_ROOT) == list(
        offline.iris_macros("26.3", "1.11.7+26.3-fabric", "4")
    )


def test_a_stage_naming_a_macro_only_the_game_sets_fails_unchecked(tmp_path: Path) -> None:
    pack = fixture_pack()
    pack.files["gbuffers_basic.fsh"] = FRAGMENT.replace(
        "out vec4", "#ifdef MC_GL_ARB_gpu_shader5\n#endif\nout vec4"
    )
    done = offline.compile_build(
        pack, "", "gbuffers_basic", offline.Variant(), [], tmp_path / "none"
    )
    assert [(f.step, f.stage) for f in done.failures] == [
        ("unmodeled", "shaders/gbuffers_basic.fsh")
    ]
    assert "MC_GL_ARB_gpu_shader5" in done.failures[0].lines[0] and done.runs == 0


# The profile check.


def test_the_profile_check_refuses_a_missing_key_and_a_value_off_its_list() -> None:
    options = offline.declared(fixture_pack())
    data = {
        "options": {"QUALITY": "3", "FAST": False, "shadowDistance": "64.0"},
        "kept": {"keys": {"SLOW": "a switch"}},
        "ablations": {"rows": [{"set": "FAST=false"}]},
    }
    assert offline.check_profile("p.json", data, options) == (5, [])
    data = {
        "options": {"QUALITY": "4", "MISSING": "1", "FAST": "0", "SLOW": "true"},
        "dropped": ["UNTESTED"],
        "ablations": {"rows": [{"set": "QUALITY=2.0"}]},
    }
    keys, problems = offline.check_profile("p.json", data, options)
    assert keys == 6
    assert problems == [
        "p.json options: QUALITY '4' is not among its values [1 2 3]; fix: one of them, as the "
        "pack's own text",
        "p.json options: MISSING is not declared by the pack; fix: one of its options",
        "p.json options: FAST '0' for an on/off option; fix: true or false",
        "p.json options: SLOW 'true' for an on/off option; fix: true or false",
        "p.json dropped: UNTESTED is not declared by the pack; fix: one of its options",
        "p.json ablations: QUALITY '2.0' is not among its values [1 2 3]; fix: one of them, as "
        "the pack's own text",
    ]


def profile_root(tmp_path: Path, profiles: dict[str, dict], version: str = "1") -> Path:
    """A fake root: the repo's config, the studied copy holding the fixture pack's options, the
    given profiles in place of the repo's."""
    root = tmp_path / "root"
    copy_config(root)
    similarity_home(root, {f"shaders/{n}": t for n, t in fixture_pack().files.items()}, 20, 72)
    shutil.rmtree(root / "config" / "profiles")
    (root / "config" / "profiles").mkdir()
    for name, data in profiles.items():
        (root / "config" / "profiles" / name).write_text(json.dumps(data), encoding="utf-8")
    plat = root / "config" / "platforms" / "mc-26.3.json"
    data = json.loads(plat.read_text(encoding="utf-8"))
    data["referencePacks"] = [{**data["referencePacks"][0], "slug": "studied", "version": version}]
    plat.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_each_profile_is_judged_against_its_own_pack(tmp_path: Path) -> None:
    root = profile_root(
        tmp_path,
        {
            "studied-good.json": {"pack": "studied 1", "options": {"QUALITY": "1"}},
            "studied-bad.json": {"pack": "another 1.0", "options": {"QUALITY": "9"}},
            "optilux-iso.json": {"pack": "optilux", "options": {"FAST": True}},
            "stray.json": {"options": {}},
        },
    )
    pack = offline.Pack(
        "shader/", {"final.vsh": VERTEX, "lib/options.glsl": "#define FAST\n#ifdef FAST\n#endif\n"}
    )
    found = {p["profile"].rsplit("/", 1)[1]: p for p in check_verb.check_profiles(root, pack)}
    assert (
        found["studied-good.json"]["problems"] == []
        and found["studied-good.json"]["pack"] == "reference/studied-1/"
    )
    assert found["optilux-iso.json"] == {
        "profile": "config/profiles/optilux-iso.json",
        "pack": "shader/",
        "keys": 1,
        "problems": [],
    }
    bad = found["studied-bad.json"]["problems"]
    assert "pack 'another 1.0', the copy is studied 1" in bad[0] and "QUALITY '9'" in bad[1]
    assert "no pack of its name" in found["stray.json"]["problems"][0]


def test_a_copy_that_is_not_the_platforms_reference_pack_is_refused(tmp_path: Path) -> None:
    """A reference pack moved to version 2 while the copy pinned is studied-1: its profiles are
    never judged by the old copy's options."""
    root = profile_root(tmp_path, {"studied-good.json": {"pack": "studied 2"}}, version="2")
    (found,) = check_verb.check_profiles(root, fixture_pack())
    assert (found["pack"], found["keys"]) == (None, 0)
    assert re.search(r"reference/studied-1/ is not the copy .* \(studied 2\)", found["problems"][0])


# The review's cases (M3.P04): each rule as Iris 1.11.7's bytecode has it.


def screen(source: str) -> list[str]:
    """offline.unmodeled as compile_build calls it: L0's defines and the source's own."""
    macros = {name for name, _ in offline.iris_macros("26.3", "1.11.7", "4")}
    own = {m["name"] for line in source.splitlines() if (m := offline.DEFINES.match(line))}
    return offline.unmodeled(source, macros, own)


@pytest.mark.parametrize(
    ("source", "names"),
    [
        ("#ifdef GL_ARB_gpu_shader5\n#endif", ["GL_ARB_gpu_shader5"]),  # glslang's own
        ("#if __VERSION__ >= 330\n#endif", ["__VERSION__"]),
        ("#elif defined GL_core_profile", ["GL_core_profile"]),
        ("#ifdef MC_WGL_EXT_swap_control\n#endif", ["MC_WGL_EXT_swap_control"]),  # an extension
        ("#if MC_GLSL_VERSION >= 400\n#endif", ["MC_GLSL_VERSION"]),
        ("float a = BIOME_PLAINS;", ["BIOME_PLAINS"]),
        ("#extension GL_ARB_gpu_shader5 : enable", []),  # no conditional
        ("#ifdef MC_OS_LINUX\n#endif", []),  # undefined on the bench, as in game
        ("#if MC_VERSION >= 260300\n#endif", []),  # L0 sets it
        ("//#define MC_OWN\n#ifdef MC_OWN\n#endif", []),  # the pack's own option
        ("// MC_GL_VENDOR_ATI in a comment", []),
    ],
)
def test_the_screen_names_what_only_the_game_sets(source: str, names: list[str]) -> None:
    assert screen(source) == names


def test_world0_is_the_base_set_once_its_folder_exists() -> None:
    """ShaderPack: world0 exists, so the base set is world0's, even with no program in it."""
    pack = fixture_pack()
    for name in ("gbuffers_basic.vsh", "gbuffers_basic.fsh", "final.vsh", "final.fsh"):
        pack.files[f"world0/{name}"] = pack.files[name].replace('"lib/', '"/lib/')
    assert set(offline.folders(pack).values()) == {"world0"}  # the Nether's and End's too
    empty = fixture_pack()
    empty.files["world0/lib.glsl"] = "float a;\n"  # no program: an empty base set
    _, _, builds, problems = offline.plan(empty, PASSES)
    assert not builds and any("world0/gbuffers_basic lacks its .vsh or .fsh" in p for p in problems)
    named = fixture_pack()
    named.files["helper.fsh"] = FRAGMENT  # not an Iris program name: neither a start nor a program
    assert offline.plan(named, PASSES)[3] == []


def test_stages_l0_does_not_build_and_missing_includes_fail() -> None:
    pack = fixture_pack()
    pack.files["gbuffers_basic.tcs"] = VERTEX
    pack.files["composite_a.csh"] = VERTEX
    pack.files["shadow.vsh"] = '#include "/missing.glsl"\n'
    passes = [*PASSES, {"name": "x", "program": "final", "dimensions": ["minecraft:moon"]}]
    problems = offline.plan(pack, passes)[3]
    assert any("a tessellation control stage, which L0 does not build" in p for p in problems)
    assert any("composite_a.csh: a compute stage" in p for p in problems)
    assert any(
        "includes shaders/missing.glsl" in p and "Iris refuses the pack" in p for p in problems
    )
    assert any("'minecraft:moon' is no dimension" in p for p in problems)


def test_an_on_off_option_registers_only_where_its_component_tests_it() -> None:
    """ShaderPackOptions: references count per weakly connected component of the include graph,
    and a const bool needs one as a define does; Iris's numbered const names count."""
    pack = offline.Pack(
        "c/",
        {
            "final.vsh": '#include "/a.glsl"\nvoid main() {}\n',
            "final.fsh": "const bool shadowHardwareFiltering = true;\nvoid main() {}\n",
            "gbuffers_basic.vsh": '#include "/b.glsl"\nvoid main() {}\n',
            "gbuffers_basic.fsh": (
                "const bool shadowcolor0Nearest = false;\n#ifdef shadowcolor0Nearest\n#endif\n"
            ),
            "a.glsl": "#define APART\n",
            "b.glsl": "#ifdef APART\n#endif\n#define TOGETHER\n#ifdef TOGETHER\n#endif\n",
        },
    )
    found = offline.declared(pack).found
    assert sorted(found) == ["TOGETHER", "shadowcolor0Nearest"]


def test_java_split_drops_every_trailing_empty_value() -> None:
    assert (offline.java_split(" "), offline.java_split(""), offline.java_split("a  b ")) == (
        [],
        [""],
        ["a", "", "b"],
    )
    assert offline.allowed_values("[ ]", "1") == ("1",)


def test_the_iso_profile_holds_played_s_options_and_every_dropped_key() -> None:
    """plans/m3.md P15: iso v1's `options` is played's, each dropped key, and the four set off
    (RAIN_STYLE 1: the default, as no off exists); bloom's key is BLOOM_ENABLED in both."""
    folder = REPO_ROOT / "config" / "profiles"
    played, iso = (
        json.loads(
            (folder / f"complementary-unbound-{n}.json").read_text(), parse_float=str, parse_int=str
        )
        for n in ("played", "iso")
    )
    assert iso["version"] == "1" and "unresolved" not in iso
    assert {
        k: v for k, v in iso["options"].items() if k in played["options"] and k != "RAIN_STYLE"
    } == {k: v for k, v in played["options"].items() if k != "RAIN_STYLE"}
    assert set(iso["dropped"]) <= set(iso["options"])
    for name in ("AURORA_STYLE_DEFINE", "SKY_EFFECT_REFLECTION_DEFINE", "IMPROVED_RAIN_DEFINE"):
        assert iso["options"][name] == "0"
    assert iso["options"]["RAIN_STYLE"] == "1"
    assert all(
        isinstance(v, bool) or v.lstrip("-").replace(".", "").isdigit()
        for v in iso["options"].values()
    )
    assert "BLOOM_ENABLED" in iso["kept"]["keys"] and "BLOOM_STRENGTH" not in iso["kept"]["keys"]
    assert any(row["set"].startswith("BLOOM_ENABLED=") for row in played["ablations"]["rows"])


# glslang's runs.


def hello_copy(tmp_path: Path) -> Path:
    shutil.copytree(REPO_ROOT / "shader" / "shaders", tmp_path / "pack" / "shaders")
    return tmp_path / "pack"


def passes() -> list[dict]:
    return json.loads((REPO_ROOT / "config" / "pipeline.json").read_text(encoding="utf-8"))[
        "passes"
    ]


@needs_glslang
def test_the_hello_pack_passes_the_matrix() -> None:
    pack = check_verb.load_pack(REPO_ROOT, None)
    matrix = offline.build_matrix(pack, passes(), check_verb.macros(REPO_ROOT), GLSLANG)
    assert not matrix.failed and not matrix.problems
    assert (len(matrix.builds), len(matrix.compiled)) == (8 * 3 * 2, 8 * 2)
    lit = next(
        c for c in matrix.compiled if c.program == "gbuffers_textured_lit" and not c.variant.values
    )
    assert "entityId" in lit.reflection["Uniform reflection"]  # -q's reflection, the option on
    assert "fogStart" not in lit.reflection["Uniform reflection"]


@needs_glslang
def test_a_broken_stage_fails_naming_its_program_stage_and_macros(tmp_path: Path, capsys) -> None:
    home = hello_copy(tmp_path)
    stage = home / "shaders" / "gbuffers_textured.fsh"
    stage.write_text(
        stage.read_text() + "void broken() { undeclaredValue = 1.0; }\n", encoding="utf-8"
    )
    found = check_verb.run_l0(REPO_ROOT, str(home))
    assert not found["ok"]
    failures = found["matrix"]["failures"]
    assert {(f["program"], f["stage"], f["stageName"], f["variant"]) for f in failures} == {
        ("gbuffers_textured", "shaders/gbuffers_textured.fsh", "fragment", "defaults"),
        (
            "gbuffers_textured",
            "shaders/gbuffers_textured.fsh",
            "fragment",
            "BENCH_DETERMINISTIC false",
        ),
    }
    assert all(
        f["lines"] == ["shaders/gbuffers_textured.fsh:7: 'undeclaredValue' : undeclared identifier"]
        for f in failures
    )
    assert all(f["dimensions"] == DIMENSIONS for f in failures)
    check_verb.print_text(found)
    out = capsys.readouterr().out
    assert "-DMC_VERSION=260300" in out and "-DMC_RENDER_STAGE_SKY=1" in out and "-DIS_IRIS" in out
    assert (
        "FAIL gbuffers_textured, its fragment stage shaders/gbuffers_textured.fsh (compile and "
        "link), at BENCH_DETERMINISTIC false, in minecraft:overworld, minecraft:the_nether, "
        "minecraft:the_end, under the 78 macros above:" in out
    )


@needs_glslang
def test_a_fragment_input_no_vertex_output_writes_fails_to_link(tmp_path: Path) -> None:
    """gpu-iris.md#programs-and-alpha-tests: the driver refuses it; glslang -l alone links it, so
    L0 adds --validate-io."""
    home = hello_copy(tmp_path)
    stage = home / "shaders" / "final.fsh"
    text = stage.read_text().replace("void main() {", "in vec3 neverWritten;\nvoid main() {")
    stage.write_text(text.replace(", 1.0);", " + neverWritten.x, 1.0);"), encoding="utf-8")
    matrix = offline.build_matrix(
        offline.from_folder("copy", home), passes(), check_verb.macros(REPO_ROOT), GLSLANG
    )
    (failed,) = {
        (c.program, f.stage, f.lines[0].split(": ", 1)[1])
        for c in matrix.failed
        for f in c.failures
    }
    assert failed[:2] == ("final", "shaders/final.fsh")
    assert "no matching declaration for statically used input" in failed[2]


@needs_glslang
def test_a_preprocessor_error_fails_its_stage(tmp_path: Path) -> None:
    home = hello_copy(tmp_path)
    stage = home / "shaders" / "gbuffers_basic.vsh"
    stage.write_text(stage.read_text() + "#if\n#endif\n", encoding="utf-8")
    matrix = offline.build_matrix(
        offline.from_folder("copy", home), passes(), check_verb.macros(REPO_ROOT), GLSLANG
    )
    steps = {(c.program, f.step, f.stage) for c in matrix.failed for f in c.failures}
    assert steps == {("gbuffers_basic", "preprocess", "shaders/gbuffers_basic.vsh")}
