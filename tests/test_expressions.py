"""The expression runner (optilux/expressions.py, docs/offline.md#tools): the classpath's pins
refused off their hash in a fake root, the lines it refuses before a start, a mat4's column order;
then Iris's engine on the fixture expressions (a product, a mat4's column, frameCounter % 16)
against float32 numpy, skipped without runtime/ (CI)."""

from pathlib import Path

import numpy as np
import pytest
from conftest import copy_config

from optilux import REPO_ROOT, expressions, platform

needs_runtime = pytest.mark.skipif(
    not (REPO_ROOT / "runtime").is_dir(), reason="no runtime/ (`optilux install`)"
)
# Random frames per fixture, from a fixed seed: the same inputs on every run.
FRAMES = 16


def fake_root(tmp_path: Path) -> tuple[Path, Path]:
    """The repo's config under tmp_path, and where the store's Iris jar would sit."""
    copy_config(tmp_path)
    plat = platform.load(tmp_path)
    iris = next(p for p in plat.tier_files("bench") if p.slug == expressions.IRIS)
    return tmp_path, tmp_path / "runtime" / plat.id / "files" / iris.file


def test_a_jar_off_its_pin_is_refused(tmp_path: Path) -> None:
    root, jar = fake_root(tmp_path)
    with pytest.raises(expressions.ExpressionError, match=r"iris-fabric.*\.jar is missing"):
        expressions.classpath(root)
    jar.parent.mkdir(parents=True)
    jar.write_bytes(b"not Iris")
    with pytest.raises(
        expressions.ExpressionError, match=r"iris-fabric.*\.jar: sha512 \w+ differs from its pin"
    ):
        expressions.classpath(root)


def test_a_line_the_runner_cannot_carry_is_refused_before_a_start(tmp_path: Path) -> None:
    root, _ = fake_root(tmp_path)  # no java: a start would fail on its own
    with pytest.raises(expressions.ExpressionError, match="no type 'mat3'"):
        expressions.evaluate(root, [("mat3", "m", 0.0)], [])
    with pytest.raises(expressions.ExpressionError, match="a name is an identifier"):
        expressions.evaluate(root, [], [("float", "x", "1.0\t2.0")])
    with pytest.raises(expressions.ExpressionError, match=r"a vec3 takes shape \(3,\)"):
        expressions.evaluate(root, [("vec3", "v", [1.0, 2.0])], [])
    with pytest.raises(expressions.ExpressionError, match="an int takes an int"):
        expressions.evaluate(root, [("int", "frameCounter", 1.5)], [])
    with pytest.raises(expressions.ExpressionError, match=r"no runtime/java/.*/java\.exe"):
        expressions.evaluate(root, [], [("float", "x", "1.0")])


def test_floats_cross_exactly_and_a_mat4_column_by_column() -> None:
    value = np.float32(0.1)
    assert np.float32(float.fromhex(expressions.exact(value))) == value
    assert [expressions.exact(x) for x in (np.nan, np.inf, -np.inf)] == [
        "NaN",
        "Infinity",
        "-Infinity",
    ]
    rows = np.arange(16, dtype=np.float32).reshape(4, 4)  # rows[row, column]
    line = expressions.encode("mat4", "m", rows)
    assert line.split("\t")[3].split(",")[:4] == [expressions.exact(x) for x in rows[:, 0]]
    printed = rows.T.ravel().tolist()  # the runner prints column by column
    assert np.array_equal(expressions.decode("mat4", printed), rows)


@needs_runtime
@pytest.mark.windows
def test_irises_engine_matches_float32_numpy() -> None:
    random = np.random.default_rng(26_3)
    inputs: list[tuple[str, str, expressions.Value]] = []
    exprs: list[tuple[str, str, str]] = []
    expected: dict[str, object] = {}
    for frame in range(FRAMES):
        a, b = random.uniform(-1e3, 1e3, 2).astype(np.float32)
        matrix = random.uniform(-10, 10, (4, 4)).astype(np.float32)
        counter = int(random.integers(0, 720_720))
        inputs += [
            ("float", f"a{frame}", a),
            ("float", f"b{frame}", b),
            ("mat4", f"gbufferModelView{frame}", matrix),
            ("int", f"frameCounter{frame}", counter),
        ]
        exprs += [
            ("float", f"product{frame}", f"a{frame} * b{frame}"),
            ("vec4", f"column{frame}", f"gbufferModelView{frame}.y"),
            ("int", f"phase{frame}", f"frameCounter{frame} % 16"),
        ]
        expected |= {
            f"product{frame}": np.float32(a) * np.float32(b),
            f"column{frame}": matrix[:, 1],  # GLSL's m[1]: the second column
            f"phase{frame}": counter % 16,
        }
    values = expressions.evaluate(REPO_ROOT, inputs, exprs)
    assert values.keys() == expected.keys()
    for name, value in expected.items():
        got = values[name]
        if isinstance(value, np.ndarray):
            assert isinstance(got, np.ndarray) and got.dtype == np.float32, name
            assert np.array_equal(got, value), name
        else:
            assert got == value and type(got) is type(value), name


@needs_runtime
@pytest.mark.windows
def test_an_expression_irises_engine_refuses_is_named() -> None:
    with pytest.raises(
        expressions.ExpressionError, match=r"refused 'expr\\tfloat\\tx\\tnoSuchFunction\(1\.0\)'"
    ):
        expressions.evaluate(REPO_ROOT, [], [("float", "x", "noSuchFunction(1.0)")])
