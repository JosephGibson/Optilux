"""L3 tests of shaders/lib/tonemap.glsl (docs/research/tonemap.md#for-optilux): the curve's terms
solved from its two points against float64; the curve at the pack's settings against float64 over
2^-14 to 2^16 (rising throughout, asserted here), 0 at 0, midOut at midIn and 1 at hdrMax within
1e-5, 1 at R11G11B10F's and RGBA16F's maxima (64512, 65024, 65504) and past them, finite at
denormals, 0 for NaN and negative light; the whole map, grade then curve, on random light."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
# The pack's settings (the include's CURVE_* and GRADE_* defines).
CONTRAST, SHOULDER, MID_IN, MID_OUT, HDR_MAX = 1.35, 0.97, 0.18, 0.2, 16.0
SATURATION = 1.05
# Two pows and a division a channel: 1e-5 of the value, as the research asks of the curve.
RELATIVE = 1e-5
ABSOLUTE = 1e-6


def terms64(contrast, shoulder, mid_in, mid_out, hdr_max) -> np.ndarray:
    u_mid, v_mid = mid_in**contrast, mid_in ** (contrast * shoulder)
    u_max, v_max = hdr_max**contrast, hdr_max ** (contrast * shoulder)
    b = (u_max - u_mid / mid_out) / (v_max - v_mid)
    return np.array([b, u_max - v_max * b])


TERMS = terms64(CONTRAST, SHOULDER, MID_IN, MID_OUT, HDR_MAX)


def curve64(light: np.ndarray, terms: np.ndarray = TERMS) -> np.ndarray:
    x = np.nan_to_num(np.asarray(light, np.float64), nan=0.0)
    x = np.clip(x, 0, HDR_MAX)
    u, v = np.power(x, CONTRAST), np.power(x, CONTRAST * SHOULDER)
    return np.minimum(u / (v * terms[0] + terms[1]), 1.0)


def grade64(light: np.ndarray) -> np.ndarray:
    luma = np.array([0.2126, 0.7152, 0.0722])
    matrix = np.outer(np.ones(3), luma) * (1 - SATURATION) + np.eye(3) * SATURATION
    return np.asarray(light, np.float64) @ matrix.T


assert abs(curve64(np.array([MID_IN]))[0] - MID_OUT) < 1e-12
assert abs(curve64(np.array([HDR_MAX]))[0] - 1.0) < 1e-12
SWEEP = np.exp2(np.linspace(-14, 16, 3001)).astype(F)
assert np.all(np.diff(curve64(SWEEP)) >= 0)
SPECIAL = np.array(
    [0, MID_IN, HDR_MAX, 64512, 65024, 65504, 1e-40, 1e-44, np.nan, -1, -65504, 1e30], F
)
SETTINGS = [
    (1.35, 0.97, 0.18, 0.2, 16.0),
    (1.6, 0.977, 0.18, 0.267, 8.0),
    (1.2, 0.95, 0.25, 0.25, 64.0),
]


def vec3(values: np.ndarray) -> np.ndarray:
    return np.repeat(np.asarray(values, F)[:, None], 3, axis=1)


def curve_case(light: np.ndarray, note: str, tolerance: float = ABSOLUTE) -> l3.Function:
    count = len(light)
    return l3.Function(
        "displayCurve",
        "vec3",
        (
            l3.Argument("light", "vec3", vec3(light)),
            l3.Argument("contrast", "float", np.full(count, CONTRAST, F)),
            l3.Argument("shoulder", "float", np.full(count, SHOULDER, F)),
            l3.Argument("terms", "vec2", np.tile(TERMS.astype(F), (count, 1))),
            l3.Argument("hdrMax", "float", np.full(count, HDR_MAX, F)),
        ),
        vec3(curve64(light)),
        tolerance=tolerance,
        relative=RELATIVE,
        note=note,
    )


LIGHT = RANDOM.uniform(0, 4, (2048, 3)).astype(F)
LIGHT[:16] = RANDOM.uniform(0, 40, (16, 3))
settings = np.array(SETTINGS, F)

TESTS = [
    l3.Function(
        "curveTerms",
        "vec2",
        tuple(
            l3.Argument(name, "float", settings[:, i])
            for i, name in enumerate(("contrast", "shoulder", "midIn", "midOut", "hdrMax"))
        ),
        np.array([terms64(*s) for s in SETTINGS], F),
        tolerance=0.0,
        relative=RELATIVE,
    ),
    curve_case(SWEEP, "2^-14 to 2^16"),
    curve_case(SPECIAL, "0, midIn, hdrMax, the formats' maxima, denormals, NaN, negatives"),
    l3.Function(
        "tonemap",
        "vec3",
        (l3.Argument("exposed", "vec3", LIGHT),),
        curve64(grade64(LIGHT)).astype(F),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
]
