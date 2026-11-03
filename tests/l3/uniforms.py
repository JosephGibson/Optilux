"""L3 tests of shaders.properties' custom uniforms (optilux/l3.py's Uniform): each held to the GLSL
it replaces, Iris's own engine against the GPU. blockFlicker (BLOCK_FLICKER) is
lib/flicker.glsl's flickerFactor of its clock and its level's amplitude: at the defaults
(BENCH_DETERMINISTIC on, Low) the clock held at 0, the rest; off the define frameTimeCounter
across the hour, at each level. e2Load (E2_LOAD) is the loop count it names."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
CLOCKS = np.concatenate([np.zeros(1, F), RANDOM.uniform(0, 3600, 255).astype(F)]).astype(F)
AMPLITUDES = {"1": 0.04, "2": 0.08, "3": 0.12}

UNIFORMS = [
    l3.Uniform(
        "blockFlicker",
        "flickerFactor(0.0, 0.04)",
        (),
        tolerance=1e-6,
        includes=("lib/flicker.glsl",),
        note="the rest",
    ),
    *(
        l3.Uniform(
            "blockFlicker",
            f"flickerFactor(frameTimeCounter, {amplitude})",
            (l3.Argument("frameTimeCounter", "float", CLOCKS),),
            # the clock's float32 step at 3600 s times the slope (tests/l3/lib/flicker.py).
            tolerance=4e-3 * amplitude,
            options={"BENCH_DETERMINISTIC": "false", "BLOCK_FLICKER": level},
            includes=("lib/flicker.glsl",),
        )
        for level, amplitude in AMPLITUDES.items()
    ),
    *(
        l3.Uniform("e2Load", str(load), (), tolerance=0.0, options={"E2_LOAD": str(load)})
        for load in (4, 8, 16)
    ),
]
