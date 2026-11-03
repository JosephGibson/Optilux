"""L3 tests of shaders/lib/fog.glsl: the edge fog's distance, the larger of the horizontal and the
vertical distance from the camera, and its ramp, none before the band clamp(far / 10, 4, 64) wide
that ends at far, all from far on, straight between (26.3's FogRenderer), each against float32
numpy at far 32 (the band clamped to 4), 256 (the bench's: 25.6) and 1024 (64)."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
# A length's sqrt: a few ulp of the value.
RELATIVE = 1e-6
# The ramp: one division of values up to far, into [0, 1].
ABSOLUTE = 1e-6
FARS = (F(32), F(256), F(1024))


def edge_distance(position: np.ndarray) -> np.ndarray:
    horizontal = np.sqrt(position[:, 0] * position[:, 0] + position[:, 2] * position[:, 2])
    return np.maximum(horizontal, np.abs(position[:, 1])).astype(F)


def edge_fog(distance: np.ndarray, far: F) -> np.ndarray:
    band = np.clip(far * F(0.1), F(4), F(64))
    return np.clip((distance - (far - band)) / band, F(0), F(1)).astype(F)


axes = [np.eye(3, dtype=F)[i] * s for i in range(3) for s in (F(-300), F(77.5))]
POINTS = np.concatenate(
    [RANDOM.uniform(-1200, 1200, (4089, 3)).astype(F), np.zeros((1, 3), F), np.array(axes, F)]
).astype(F)

TESTS = [
    l3.Function(
        "edgeDistance",
        "float",
        (l3.Argument("fromCamera", "vec3", POINTS),),
        edge_distance(POINTS),
        tolerance=0.0,
        relative=RELATIVE,
    ),
]
for far in FARS:
    band = np.clip(far * F(0.1), F(4), F(64))
    distance = RANDOM.uniform(0, float(far) * 1.3, 2048).astype(F)
    distance[:4] = (far - band, far, F(0), far * F(2))
    TESTS.append(
        l3.Function(
            "edgeFog",
            "float",
            (
                l3.Argument("distance", "float", distance),
                l3.Argument("far", "float", np.full(len(distance), far, F)),
            ),
            edge_fog(distance, far),
            tolerance=ABSOLUTE,
            note=f"far {far:g}",
        )
    )
