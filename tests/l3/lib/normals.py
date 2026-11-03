"""L3 tests of shaders/lib/normals.glsl (docs/research/lighting.md#l3-golden-tests 2): the six axis
normals give their exact codes and come back exact; random unit normals give numpy's codes (cases
within 1e-4 of a code's rounding boundary left out, where the GPU's last bit may round the other
way); every one of the 127 x 127 codes decodes to numpy's normal; over 10^6 random normals the
round trip strays at most MAX_DEGREES, 2 degrees (1.90 measured; asserted here, in float64)."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
STEPS = F(63)
# normalize's inversesqrt is within 2 ulp: 1e-6 on a unit vector's components.
ABSOLUTE = 1e-6
MAX_DEGREES = 2.0


def sign_or_one(v: np.ndarray) -> np.ndarray:
    return np.where(v >= 0, 1, -1).astype(v.dtype)


def codes_of(normals: np.ndarray, dtype=F) -> tuple[np.ndarray, np.ndarray]:
    """The codes and, per case, how far x * 63 lies from a rounding boundary."""
    n = np.asarray(normals, dtype)
    square = n[:, :2] / np.abs(n).sum(axis=1, keepdims=True)
    folded = (1 - np.abs(square[:, ::-1])) * sign_or_one(square)
    square = np.where(n[:, 2:3] < 0, folded, square)
    scaled = np.clip(square, -1, 1) * dtype(STEPS)
    margin = np.abs(scaled - np.floor(scaled) - 0.5).min(axis=1)
    return np.floor(scaled + 0.5).astype(dtype), margin


def normals_of(codes: np.ndarray, dtype=F) -> np.ndarray:
    square = np.asarray(codes, dtype) / dtype(STEPS)
    z = 1 - np.abs(square).sum(axis=1)
    folded = (1 - np.abs(square[:, ::-1])) * sign_or_one(square)
    xy = np.where(z[:, None] < 0, folded, square)
    n = np.concatenate([xy, z[:, None]], axis=1)
    return (n / np.linalg.norm(n, axis=1, keepdims=True)).astype(dtype)


def unit(count: int) -> np.ndarray:
    v = RANDOM.normal(size=(count, 3))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


AXES = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], F)
AXIS_CODES = np.array([[63, 0], [-63, 0], [0, 63], [0, -63], [0, 0], [63, 63]], F)
assert np.array_equal(codes_of(AXES)[0], AXIS_CODES)
assert np.array_equal(normals_of(AXIS_CODES), AXES)

wide = unit(1_000_000)
back = normals_of(codes_of(wide, np.float64)[0], np.float64)
worst = np.degrees(np.arccos(np.clip((wide * back).sum(axis=1), -1, 1))).max()
assert worst < MAX_DEGREES, worst

found = unit(4096).astype(F)
CODES, MARGIN = codes_of(found)
RANDOM_NORMALS = found[MARGIN > 1e-4]
RANDOM_CODES = CODES[MARGIN > 1e-4]
EVERY = np.array([(u, v) for u in range(-63, 64) for v in range(-63, 64)], F)

TESTS = [
    l3.Function(
        "normalCodes", "vec2", (l3.Argument("normal", "vec3", AXES),), AXIS_CODES, tolerance=0.0
    ),
    l3.Function(
        "normalFromCodes",
        "vec3",
        (l3.Argument("codes", "vec2", AXIS_CODES),),
        AXES,
        tolerance=0.0,
        note="the axes",
    ),
    l3.Function(
        "normalCodes",
        "vec2",
        (l3.Argument("normal", "vec3", RANDOM_NORMALS),),
        RANDOM_CODES,
        tolerance=0.0,
        note="random normals",
    ),
    l3.Function(
        "normalFromCodes",
        "vec3",
        (l3.Argument("codes", "vec2", EVERY),),
        normals_of(EVERY),
        tolerance=ABSOLUTE,
        note="every code",
    ),
]
