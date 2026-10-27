"""`check L3` (docs/offline.md#levels, plans/m4.md M4.P02): the judge, the case texture's layout and
the refusals before a draw, then moderngl runs on fixture includes (a pass, a wrong golden naming
its input, a compile error at its line, every argument and result type) and on the hello pack and a
broken copy of it, skipped without a GL 3.3 context (CI)."""

import shutil
from pathlib import Path

import numpy as np
import pytest

from optilux import REPO_ROOT, l3, offline
from optilux.verbs import check as check_verb

F = np.float32
CURVE = (
    "#ifndef CURVE\n"
    "#define CURVE 1\n"
    "#define DOUBLED // an on/off option\n"
    "#ifdef DOUBLED\n"
    "#endif\n"
    "uniform float offset;\n"
    "float twice(float x) {\n"
    "#ifdef DOUBLED\n"
    "    return 2.0 * x + offset;\n"
    "#else\n"
    "    return x + offset;\n"
    "#endif\n"
    "}\n"
    "int add(int a, int b) { return a + b; }\n"
    "bool positive(float x) { return x > 0.0; }\n"
    "vec4 column(mat4 m, int i) { return m[i]; }\n"
    "#endif\n"
)
XS = np.linspace(-4, 4, 33, dtype=F)
TEST_FILE = """
import numpy as np
from optilux import l3

XS = np.linspace(-4, 4, 33, dtype=np.float32)
GOLDEN = 2 * XS + np.float32(0.5)
GOLDEN[{wrong}] += 1
TESTS = [
    l3.Function("twice", "float", (l3.Argument("x", "float", XS),), GOLDEN, tolerance=0.0,
                uniforms={{"offset": 0.5}}),
]
"""


@pytest.fixture(scope="module")
def gl():
    try:
        ctx = l3.context()
    except l3.L3Error as error:
        pytest.skip(str(error))
    yield ctx
    ctx.release()


def curve_pack(source: str = CURVE) -> offline.Pack:
    """The include, reached from a program as Iris needs to register its options."""
    program = '#include "/lib/curve.glsl"\nvoid main() {}\n'
    return offline.Pack("fixture/", {"lib/curve.glsl": source, "final.fsh": program})


def l3_folder(tmp_path: Path, wrong: int | None) -> Path:
    folder = tmp_path / "l3"
    (folder / "lib").mkdir(parents=True)
    text = TEST_FILE.format(wrong="[]" if wrong is None else wrong)
    (folder / "lib" / "curve.py").write_text(text, encoding="utf-8")
    return folder


def test_the_judge_holds_tolerance_nan_and_infinity() -> None:
    golden = np.array([[1.0], [np.nan], [np.inf], [1.0], [0.0]], F)
    got = np.array([[1.0 + 1e-6], [np.nan], [np.inf], [np.nan], [2e-6]], F)
    failed, diff = l3.judge(got, golden, tolerance=1e-6, relative=1e-6)
    assert failed.tolist() == [False, False, False, True, True]
    assert diff[3] == np.inf and diff[2] == 0.0


def test_the_case_texture_holds_a_mat4_by_column_and_refuses_inexact_ints() -> None:
    rows = np.arange(16, dtype=F).reshape(1, 4, 4)
    texels = l3.case_texels(
        (l3.Argument("m", "mat4", rows), l3.Argument("i", "int", np.array([2]))), 1
    )
    assert texels.shape == (5, 1, 4)
    assert texels[1, 0].tolist() == rows[0, :, 1].tolist()  # texel row 1: the second column
    assert texels[4, 0, 0] == 2
    with pytest.raises(l3.L3Error, match="whole values below 2"):
        l3.case_texels((l3.Argument("i", "int", np.array([1 << 24])),), 1)
    with pytest.raises(l3.L3Error, match=r"a vec3 per case takes \(2, 3\)"):
        l3.case_texels((l3.Argument("v", "vec3", np.zeros((2, 2))),), 2)


def test_a_test_file_without_its_include_is_named(tmp_path: Path) -> None:
    folder = l3_folder(tmp_path, None)
    (folder / "lib" / "gone.py").write_text("TESTS = []\n", encoding="utf-8")
    found, problems = l3.test_files(folder, curve_pack())
    assert list(found) == ["lib/curve.glsl"]
    assert problems == [
        "tests/l3/lib/gone.py tests shaders/lib/gone.glsl, which fixture/ lacks; fix: its include, "
        "or remove the test"
    ]


def test_options_and_uniforms_the_include_lacks_are_refused() -> None:
    pack = curve_pack()
    with pytest.raises(l3.L3Error, match="option FAST: the pack declares no such option"):
        l3.option_values(pack, {"FAST": "true"})
    with pytest.raises(l3.L3Error, match=r"option DOUBLED '1': fix: one of true false"):
        l3.option_values(pack, {"DOUBLED": "1"})
    source = l3.program_source(pack, ["lib/curve.glsl"], {}, [], [])[0]
    assert l3.declared_names(source, ["offset", "ofset"]) == ["ofset"]


def test_a_fixture_include_passes(gl, tmp_path: Path) -> None:
    found = l3.check(gl, curve_pack(), l3_folder(tmp_path, None), [])
    assert found["problems"] == []
    (entry,) = found["includes"]
    assert entry["test"] == "tests/l3/lib/curve.py"
    assert [(f["function"], f["cases"], f["failed"]) for f in entry["functions"]] == [
        ("twice", 33, 0)
    ]


def test_a_wrong_golden_fails_naming_the_include_function_and_input(gl, tmp_path: Path) -> None:
    found = l3.check(gl, curve_pack(), l3_folder(tmp_path, 12), [])
    assert found["problems"] == [
        "shaders/lib/curve.glsl: twice(x -1.0) = -1.5, golden -0.5, off by 1.0 beyond 0.0, at the "
        "defaults (case 12 of 33)"
    ]


def test_every_argument_and_result_type_crosses(gl) -> None:
    pack = curve_pack()
    rng = np.random.default_rng(3)
    a, b = rng.integers(-1000, 1000, (2, 64))
    matrices = rng.uniform(-9, 9, (64, 4, 4)).astype(F)
    index = rng.integers(0, 4, 64)
    tests = [
        l3.Function(
            "add",
            "int",
            (l3.Argument("a", "int", a), l3.Argument("b", "int", b)),
            a + b,
            tolerance=0.0,
        ),
        l3.Function("positive", "bool", (l3.Argument("x", "float", XS),), XS > 0, tolerance=0.0),
        l3.Function(
            "column",
            "vec4",
            (l3.Argument("m", "mat4", matrices), l3.Argument("i", "int", index)),
            matrices[np.arange(64), :, index],  # GLSL's m[i]: column i
            tolerance=0.0,
        ),
        l3.Function(
            "twice",
            "float",
            (l3.Argument("x", "float", XS),),
            XS + F(0.25),
            tolerance=0.0,
            options={"DOUBLED": "false"},
            uniforms={"offset": 0.25},
        ),
    ]
    found = [l3.run_function(gl, pack, "lib/curve.glsl", t, []) for t in tests]
    assert [(f["function"], f["failed"], f["problems"]) for f in found] == [
        ("add", 0, []),
        ("positive", 0, []),
        ("column", 0, []),
        ("twice", 0, []),
    ]


def test_a_compile_error_names_the_include_line(gl) -> None:
    pack = curve_pack(CURVE.replace("return a + b;", "return a + undeclared;"))
    test = l3.Function(
        "add",
        "int",
        (l3.Argument("a", "int", [1]), l3.Argument("b", "int", [2])),
        [3],
        tolerance=0.0,
    )
    found = l3.run_function(gl, pack, "lib/curve.glsl", test, [])
    assert found["cases"] == 0
    assert found["problems"][0].startswith(
        "shaders/lib/curve.glsl: add at the defaults does not compile: shaders/lib/curve.glsl:14: "
    )
    assert "undeclared" in found["problems"][0]


def test_the_hello_pack_passes(gl) -> None:
    pack = check_verb.load_pack(REPO_ROOT, None)
    found = l3.check(gl, pack, REPO_ROOT / l3.TESTS_DIR, check_verb.macros(REPO_ROOT))
    assert found["problems"] == []
    tested = {e["include"] for e in found["includes"] if e["test"]}
    assert tested == {"shaders/lib/fog.glsl", "shaders/lib/light.glsl"}


def test_a_broken_copy_fails_naming_the_function_and_input(gl, tmp_path: Path) -> None:
    home = tmp_path / "pack"
    shutil.copytree(REPO_ROOT / "shader" / "shaders", home / "shaders")
    fog = home / "shaders" / "lib" / "fog.glsl"
    text = fog.read_text(encoding="utf-8").replace("abs(fromCamera.y)", "fromCamera.y")
    fog.write_text(text, encoding="utf-8")
    found = l3.check(
        gl,
        offline.from_folder("copy", home),
        REPO_ROOT / l3.TESTS_DIR,
        check_verb.macros(REPO_ROOT),
    )
    assert found["problems"]
    assert all(p.startswith("shaders/lib/fog.glsl: fogDistances(") for p in found["problems"][:3])
    assert "fromCamera (" in found["problems"][0]


# Custom uniforms (gpu-iris.md#custom-uniforms): Iris's engine against the GLSL they replace.

needs_runtime = pytest.mark.skipif(
    not (REPO_ROOT / "runtime").is_dir(), reason="no runtime/ (`optilux install`)"
)
PROPERTIES = (
    "# the uniform before the variable it reads: Iris resolves forward references\n"
    "uniform.vec3.upView = vec3(upColumn.x, upColumn.y, upColumn.z)\n"
    "variable.vec4.upColumn = gbufferModelView.y\n"
    "uniform.int.phase = frameCounter % 16\n"
    "#ifdef DOUBLED\n"
    "uniform.float.doubled = 3.0 * offset + 0.5\n"
    "#endif\n"
)


def uniform_pack(properties: str = PROPERTIES) -> offline.Pack:
    pack = curve_pack()
    pack.files["shaders.properties"] = properties
    return pack


def uniform_tests(up_glsl: str = "gbufferModelView[1].xyz") -> list[l3.Uniform]:
    rng = np.random.default_rng(26)
    matrices = rng.uniform(-10, 10, (16, 4, 4)).astype(F)
    frames = np.array([*range(720_710, 720_720), *range(6)])  # across the wrap to 0
    return [
        l3.Uniform(
            "upView", up_glsl, (l3.Argument("gbufferModelView", "mat4", matrices),), tolerance=0.0
        ),
        l3.Uniform(
            "phase", "frameCounter % 16", (l3.Argument("frameCounter", "int", frames),), 0.0
        ),
        l3.Uniform(
            "doubled",
            "twice(offset) + 0.5",  # twice() adds offset itself
            (l3.Argument("offset", "float", np.linspace(-3, 3, 7, dtype=F)),),
            tolerance=0.0,
            includes=("lib/curve.glsl",),
        ),
    ]


def test_definitions_resolve_after_what_they_read_and_a_cycle_is_refused() -> None:
    found = offline.customs(uniform_pack(), offline.declared(uniform_pack()), offline.Variant(), [])
    definitions = {c.name: c for c in found}
    assert [c.name for c in l3.resolved(definitions["upView"], definitions)] == [
        "upColumn",
        "upView",
    ]
    assert l3.renamed("vec3(upColumn.x, m.y)", {"upColumn", "m"}, "_l3c4") == (
        "vec3(upColumn_l3c4.x, m_l3c4.y)"
    )
    looped = {
        "a": offline.Custom("variable", "float", "a", "b + 1.0", 1),
        "b": offline.Custom("variable", "float", "b", "a * 2.0", 2),
    }
    with pytest.raises(l3.L3Error, match="a -> b -> a reads itself"):
        l3.resolved(looped["a"], looped)


def test_a_uniform_without_a_test_is_named(tmp_path: Path) -> None:
    found = l3.check_uniforms(None, uniform_pack(), tmp_path, [], None)  # type: ignore[arg-type]
    assert found["defined"] == ["upView", "phase", "doubled"]
    assert found["problems"][0] == (
        "shaders/shaders.properties:2: uniform upView has no test in tests/l3/uniforms.py "
        "holding it to the GLSL it replaces; fix: add one"
    )


@needs_runtime
def test_custom_uniforms_match_the_glsl_they_replace(gl) -> None:
    engine = check_verb.engine(REPO_ROOT)
    found = [l3.run_uniform(gl, uniform_pack(), t, [], engine) for t in uniform_tests()]
    assert [(u["uniform"], u["reads"], u["cases"], u["failed"], u["problems"]) for u in found] == [
        ("upView", ["upColumn"], 16, 0, []),
        ("phase", [], 16, 0, []),
        ("doubled", [], 7, 0, []),
    ]


@needs_runtime
def test_a_uniform_off_its_glsl_names_the_uniform_and_input(gl) -> None:
    engine = check_verb.engine(REPO_ROOT)
    (test, *_) = uniform_tests(up_glsl="gbufferModelView[2].xyz")
    found = l3.run_uniform(gl, uniform_pack(), test, [], engine)
    assert found["failed"] == 16
    first = found["problems"][0]
    assert first.startswith("shaders/shaders.properties:2: uniform upView at gbufferModelView mat4")
    assert "its GLSL 'gbufferModelView[2].xyz'" in first and "(case 0 of 16)" in first


def test_a_clocked_function_is_refused_before_the_engine_runs() -> None:
    pack = uniform_pack("uniform.float.eased = smooth(rainStrength, 2.0, 2.0)\n")
    test = l3.Uniform("eased", "rainStrength", (l3.Argument("rainStrength", "float", [0.5]),), 0.0)
    found = l3.run_uniform(None, pack, test, [], lambda i, e: {})  # type: ignore[arg-type]
    assert "calls smooth(), random() or randomInt()" in found["problems"][0]
