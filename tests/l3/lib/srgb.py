"""L3 tests of shaders/lib/srgb.glsl (docs/research/tonemap.md#for-optilux): sRGB's transfer
function both ways against float64 numpy from IEC 61966-2-1's formulas: 0 and 1 encode exactly;
the two segments meet at 0.0031308 (encode) and 0.04045 (decode) to a float32 step; a 4096-step
ramp of linear values gives the 8-bit codes float64 gives, each ramp value kept clear of a code's
rounding boundary by more than the GPU's error."""

import numpy as np

from optilux import l3

F = np.float32
# pow is exp2(y log2(x)) on the GPU, a few ulp: 8 ulp of the value.
RELATIVE = 1e-6
ABSOLUTE = 1e-7


def encode64(linear: np.ndarray) -> np.ndarray:
    x = np.asarray(linear, np.float64)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 0), 1 / 2.4) - 0.055)


def decode64(encoded: np.ndarray) -> np.ndarray:
    x = np.asarray(encoded, np.float64)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def vec3(values: np.ndarray) -> np.ndarray:
    return np.repeat(np.asarray(values, F)[:, None], 3, axis=1)


def ramp() -> np.ndarray:
    """4096 linear values across [0, 1] whose encoded value lies more than 1e-5 of a code from
    an 8-bit rounding boundary (k + 0.5) / 255."""
    values = np.linspace(0, 1, 4096, dtype=np.float64).astype(F)
    codes = encode64(values) * 255
    clear = np.abs(codes - np.floor(codes) - 0.5) > 1e-5 * 255
    return values[clear]


RAMP = ramp()
assert len(RAMP) > 4000
# The 8-bit codes the ramp gives, which the GPU must give too: its values within ABSOLUTE +
# RELATIVE of float64's never cross a boundary 1e-5 away.
CODES = np.floor(encode64(RAMP) * 255 + 0.5)
ENDS = np.array([0, 1], F)
THRESHOLD = F(0.0031308)
AROUND = np.array([np.nextafter(THRESHOLD, F(0)), THRESHOLD, np.nextafter(THRESHOLD, F(1))], F)
# The segments meet to a float32 step: their values at the threshold within 1e-6.
assert abs(THRESHOLD * 12.92 - (1.055 * THRESHOLD ** (1 / 2.4) - 0.055)) < 1e-6
assert np.array_equal(np.floor(encode64(RAMP) * 255 + 0.5), CODES)
DECODED = np.linspace(0, 1, 4096, dtype=F)

TESTS = [
    l3.Function(
        "srgbFromLinear",
        "vec3",
        (l3.Argument("linear", "vec3", vec3(ENDS)),),
        vec3(ENDS),
        tolerance=0.0,
        note="0 and 1 exactly",
    ),
    l3.Function(
        "srgbFromLinear",
        "vec3",
        (l3.Argument("linear", "vec3", vec3(RAMP)),),
        vec3(encode64(RAMP)),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
        note="the ramp",
    ),
    l3.Function(
        "srgbFromLinear",
        "vec3",
        (l3.Argument("linear", "vec3", vec3(AROUND)),),
        vec3(encode64(AROUND)),
        tolerance=1e-6,
        note="around 0.0031308",
    ),
    l3.Function(
        "linearFromSrgb",
        "vec3",
        (l3.Argument("encoded", "vec3", vec3(DECODED)),),
        vec3(decode64(DECODED)),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
]
