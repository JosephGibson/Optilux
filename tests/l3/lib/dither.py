"""L3 tests of shaders/lib/dither.glsl (docs/research/tonemap.md#for-optilux): the gradient noise
and the display dither against float32 numpy over a 64 x 64 tile, at black, white, a step from
each, and values between. Asserted here, on numpy's: the noise's mean over the tile within 0.01
of 0; each dithered value at most one 8-bit code from the undithered one's; 0 stays code 0 and
1 stays code 255. Pixels whose noise lies within 1e-3 of a fract() wrap are left out of the GPU
cases: there one rounding step of the GPU flips the value across the wrap."""

import numpy as np

from optilux import l3

F = np.float32
STEPS = F(255)
# The noise multiplies a fract() by 53: a float32 step of the first fract becomes ~1e-5.
NOISE_TOLERANCE = 1e-4
DISPLAY_TOLERANCE = 1e-6


def fract(x: np.ndarray) -> np.ndarray:
    return (x - np.floor(x)).astype(F)


def inner(pixel: np.ndarray) -> np.ndarray:
    return fract(pixel[:, 0] * F(0.06711056) + pixel[:, 1] * F(0.00583715))


def noise(pixel: np.ndarray) -> np.ndarray:
    return fract(F(52.9829189) * inner(pixel))


def wrap_margin(pixel: np.ndarray) -> np.ndarray:
    """How far each fract() lies from its wrap, the smaller of the two."""
    a = inner(pixel)
    b = F(52.9829189) * a
    return np.minimum(np.minimum(a, 1 - a), np.minimum(fract(b), 1 - fract(b)))


def dither(display: np.ndarray, pixel: np.ndarray) -> np.ndarray:
    n = noise(pixel) + noise(pixel + F([47, 17])) - F(1)
    room = np.minimum(display, F(1) - display) * STEPS
    return (display + n[:, None] * np.clip(room, F(0), F(1)) / STEPS).astype(F)


TILE = np.array([(x, y) for y in range(64) for x in range(64)], F) + F(0.5)
assert abs(float((noise(TILE) + noise(TILE + F([47, 17])) - 1).mean())) < 0.01
LEVELS = np.array([0, 1 / 255, 0.5 / 255, 0.25, 0.5, 0.7531, 254 / 255, 254.6 / 255, 1], F)
CODE = np.floor(LEVELS * 255 + 0.5)
for level, code in zip(LEVELS, CODE, strict=True):
    dithered = dither(np.full((len(TILE), 3), level, F), TILE)
    codes = np.floor(dithered * 255 + 0.5)
    assert np.abs(codes - code).max() <= 1, level
assert np.all(np.floor(dither(np.zeros((len(TILE), 3), F), TILE) * 255 + 0.5) == 0)
assert np.all(np.floor(dither(np.ones((len(TILE), 3), F), TILE) * 255 + 0.5) == 255)

CLEAR = (wrap_margin(TILE) > 1e-3) & (wrap_margin(TILE + F([47, 17])) > 1e-3)
PIXELS = TILE[CLEAR]
# A thousand pixels a level keep the cases within one texture row.
SOME = PIXELS[:1000]
DISPLAY = np.repeat(LEVELS, len(SOME))[:, None] * np.ones((1, 3), F)
DISPLAY_PIXELS = np.tile(SOME, (len(LEVELS), 1))

TESTS = [
    l3.Function(
        "gradientNoise",
        "float",
        (l3.Argument("pixel", "vec2", PIXELS),),
        noise(PIXELS),
        tolerance=NOISE_TOLERANCE,
    ),
    l3.Function(
        "ditherDisplay",
        "vec3",
        (
            l3.Argument("display", "vec3", DISPLAY.astype(F)),
            l3.Argument("pixel", "vec2", DISPLAY_PIXELS),
            l3.Argument("steps", "float", np.full(len(DISPLAY), STEPS, F)),
        ),
        dither(DISPLAY.astype(F), DISPLAY_PIXELS),
        tolerance=DISPLAY_TOLERANCE,
    ),
]
