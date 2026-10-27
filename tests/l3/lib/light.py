"""L3 tests of shaders/lib/light.glsl (docs/offline.md#levels): under BENCH_DETERMINISTIC the block
light at the flicker's rest over every level vaUV2 can carry (0-240) and between, and the surface
light with it on a synthetic lightmap; without the define, the lightmap alone. Each against float32
numpy from the formulas the include's comments state (vanilla's brightness curve L / (4 - 3L),
its tint #FFD88C toward white by 0.9 (2L - 1)^2, the flicker's rest 1.4)."""

import itertools

import numpy as np

from optilux import l3

F = np.float32
# The curve divides once and the surface light divides again for its level: 2.5 ulp each (GLSL
# 4.60 section 4.7.1); 8 ulp of the value (8 x 2^-23, about 1e-6) covers both, with an absolute
# floor of 1e-7 where the tint's (2L - 1)^2 cancels toward 0.
RELATIVE = 1e-6
FLOOR = 1e-7
TINT = np.array([1.0, 216.0 / 255.0, 140.0 / 255.0], F)
REST = F(1.4)


def resting(level: np.ndarray) -> np.ndarray:
    """restingBlockLight: tint x brightness x 1.4."""
    brightness = level / (F(4) - F(3) * level)
    pale = F(2) * level - F(1)
    weight = (F(0.9) * pale * pale)[:, None]
    tint = TINT * (F(1) - weight) + np.ones(3, F) * weight
    return (tint * brightness[:, None] * REST).astype(F)


def lightmap() -> np.ndarray:
    """A synthetic 16 x 16 lightmap, texels[sky][block], each channel a different slope in
    1/255 steps as an RGBA8 texture holds them."""
    sky, block = np.meshgrid(np.arange(16), np.arange(16), indexing="ij")
    channels = [(block * 13 + sky * 3) % 256, (sky * 15 + block) % 256, (block * 7 + sky * 9) % 256]
    texels = np.stack([*channels, np.full_like(sky, 255)], axis=2)
    return (texels / 255.0).astype(F)


LEVELS = np.concatenate([np.arange(241, dtype=F) / F(240), np.linspace(0, 1, 1024, dtype=F)])
# Every level pair at its texel's centre: vaUV2 = 16 x the level, so (vaUV2 + 8) / 256 is
# (level + 0.5) / 16, where nearest and linear filtering agree.
PAIRS = np.array(list(itertools.product(range(16), range(16))), F) * F(16)
MAP = lightmap()
BLOCK, SKY = (PAIRS[:, 0] / F(16)).astype(int), (PAIRS[:, 1] / F(16)).astype(int)
TEXTURES = {"lightmap": l3.Texture(MAP)}

TESTS = [
    l3.Function(
        "restingBlockLight",
        "vec3",
        (l3.Argument("level", "float", LEVELS),),
        resting(LEVELS),
        tolerance=FLOOR,
        relative=RELATIVE,
    ),
    l3.Function(
        "surfaceLight",
        "vec3",
        (l3.Argument("levels16", "vec2", PAIRS),),
        np.minimum(MAP[SKY, 0, :3] + resting(PAIRS[:, 0] / F(240)), F(1)),
        tolerance=FLOOR,
        relative=RELATIVE,
        textures=TEXTURES,
    ),
    l3.Function(
        "surfaceLight",
        "vec3",
        (l3.Argument("levels16", "vec2", PAIRS),),
        MAP[SKY, BLOCK, :3],
        tolerance=0.0,
        options={"BENCH_DETERMINISTIC": "false"},
        textures=TEXTURES,
    ),
]
