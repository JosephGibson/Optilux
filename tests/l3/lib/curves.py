"""L3 tests of shaders/lib/curves.glsl (docs/research/lighting.md#l3-golden-tests 3): vaUV2 to a
level, 0 to 240 onto [0, 1] and clamped outside; the curve l / (1 + k (1 - l)) over a grid of
levels and falloffs; the block and the sky curve as golden tables over every vaUV2 from 0 to 240,
0 at 0 and exactly 1 at 240, rising throughout (the tables are asserted here)."""

import numpy as np

from optilux import l3

F = np.float32
# One division: 2.5 ulp (GLSL 4.60 section 4.7.1).
RELATIVE = 4e-7
ABSOLUTE = 1e-7
BLOCK_FALLOFF = F(4)
SKY_FALLOFF = F(2)


def level(uv2: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(uv2, F) * F(1 / 240), F(0), F(1)).astype(F)


def curve(value: np.ndarray, falloff: np.ndarray) -> np.ndarray:
    value = np.asarray(value, F)
    return (value / (F(1) + np.asarray(falloff, F) * (F(1) - value))).astype(F)


UV2 = np.concatenate([np.arange(241, dtype=F), np.array([-16, 255, 4096], F)])
LEVELS = level(np.arange(241, dtype=F))
GRID = np.linspace(0, 1, 101, dtype=F)
FALLOFFS = np.array([0, 0.5, 2, 4, 10], F)
VALUE, FALLOFF = (a.ravel() for a in np.meshgrid(GRID, FALLOFFS))
BLOCK = curve(LEVELS, BLOCK_FALLOFF)
SKY = curve(LEVELS, SKY_FALLOFF)
for table in (BLOCK, SKY):
    assert table[0] == 0 and table[-1] == 1
    assert np.all(np.diff(table) > 0)

TESTS = [
    l3.Function(
        "lightLevel", "float", (l3.Argument("uv2", "float", UV2),), level(UV2), tolerance=ABSOLUTE
    ),
    l3.Function(
        "lightCurve",
        "float",
        (l3.Argument("level", "float", VALUE), l3.Argument("falloff", "float", FALLOFF)),
        curve(VALUE, FALLOFF),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
    l3.Function(
        "blockLight",
        "float",
        (l3.Argument("level", "float", LEVELS),),
        BLOCK,
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
    l3.Function(
        "skyLight",
        "float",
        (l3.Argument("level", "float", LEVELS),),
        SKY,
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
]
