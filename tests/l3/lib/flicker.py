"""L3 tests of shaders/lib/flicker.glsl: block light's flicker, 1 + amplitude x (0.6 sin(2 pi t /
0.6) + 0.4 sin(2 pi t / 1.8)), against float32 numpy at each level's amplitude (0.04, 0.08, 0.12)
over clocks from 0 to frameTimeCounter's wrap at 3600 s. Asserted here: 1 at clock 0 (the rest
BENCH_DETERMINISTIC holds), within the amplitude of 1, and the same at 0 and 3600 s (the periods
divide the wrap)."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
FAST, SLOW = F(10.4719755), F(3.49065850)
# Per unit of amplitude: the clock's float32 step near 3600 s is 2.4e-4 s, and the flicker's
# steepest slope 0.6 x 10.47 + 0.4 x 3.49 = 7.7 a second, so one step of the clock moves it by
# 1.9e-3; the GPU's sin reduces its argument (up to 37,700 radians) with an error of that order.
ABSOLUTE = 4e-3


def flicker(clock: np.ndarray, amplitude: F) -> np.ndarray:
    wave = F(0.6) * np.sin(clock * FAST) + F(0.4) * np.sin(clock * SLOW)
    return (F(1) + amplitude * wave).astype(F)


CLOCKS = np.concatenate([np.zeros(1, F), RANDOM.uniform(0, 3600, 2047).astype(F)]).astype(F)
TESTS = []
for amplitude in (F(0.04), F(0.08), F(0.12)):
    values = flicker(CLOCKS, amplitude)
    assert values[0] == 1 and np.all(np.abs(values - 1) <= amplitude + 1e-6)
    ends = flicker(np.array([0, 3600], np.float64), amplitude)
    assert abs(float(ends[0]) - float(ends[1])) < 1e-4
    TESTS.append(
        l3.Function(
            "flickerFactor",
            "float",
            (
                l3.Argument("clock", "float", CLOCKS),
                l3.Argument("amplitude", "float", np.full(len(CLOCKS), amplitude, F)),
            ),
            values,
            tolerance=ABSOLUTE * float(amplitude),
            note=f"amplitude {amplitude:g}",
        )
    )
