"""L3 tests of shaders/lib/fog.glsl (docs/offline.md#levels): the two distances, the ramp and the
fog applied, under BENCH_DETERMINISTIC (the edge fog alone) and without it (the environment's fog
too), each against float32 numpy from the formulas the include's comments state (26.3's
FogRenderer): the edge fog over max(length(xz), |y|) ends at far after a band of
clamp(far / 10, 4, 64); the environment's runs over length(xyz) from fogStart to fogEnd; a fragment
takes the denser of the two."""

import itertools

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
# GLSL leaves sqrt and division a few ulp off the correctly rounded float32 numpy computes (GLSL
# 4.60 section 4.7.1: inversesqrt within 2 ulp, x / y within 2.5 ulp), and length's sum may run in
# another order: 8 ulp of the value (8 x 2^-23, about 1e-6) covers both.
RELATIVE = 1e-6
# A ramp and a mix end in [0, 1]: 8 ulp at 1 (8 x 2^-24 x 2, about 1e-6), after one division.
ABSOLUTE = 1e-6
FOG_COLOR = np.array([0.62, 0.71, 0.93], F)
# far = render distance x 16: 2 chunks (the band clamped to 4), 16 (the bench's: 25.6) and 64 (64).
FARS = (F(32), F(256), F(1024))
# The environment's fog off the define: a range, and a reversed one (a step at fogEnd).
ENVIRONMENT = ((F(0), F(192)), (F(200), F(120)))


def distances(position: np.ndarray) -> np.ndarray:
    """fogDistances: (length, max(horizontal, |y|))."""
    horizontal = np.sqrt(position[:, 0] * position[:, 0] + position[:, 2] * position[:, 2])
    straight = np.sqrt((position * position).sum(axis=1, dtype=F))
    return np.stack([straight, np.maximum(horizontal, np.abs(position[:, 1]))], axis=1)


def ramp(dist: np.ndarray, near: np.ndarray, full: np.ndarray) -> np.ndarray:
    """fogRamp: 0 up to near, 1 from full on, straight between; a reversed range is a step."""
    with np.errstate(divide="ignore", invalid="ignore"):
        inside = (dist - near) / (full - near)
    return np.where(dist <= near, F(0), np.where(dist >= full, F(1), inside)).astype(F)


def fogged(color: np.ndarray, dists: np.ndarray, far: F, environment=None) -> np.ndarray:
    """withFog: GLSL's mix(color, fogColor, amount), color x (1 - a) + fogColor x a."""
    band = np.clip(far * F(0.1), F(4), F(64))
    amount = ramp(dists[:, 1], far - band, np.full(len(dists), far, F))
    if environment is not None:
        start, end = (np.full(len(dists), v, F) for v in environment)
        amount = np.maximum(amount, ramp(dists[:, 0], start, end))
    a = amount[:, None]
    return (color * (F(1) - a) + FOG_COLOR * a).astype(F)


def positions() -> np.ndarray:
    """Random points out to past the farthest far, the camera itself and the axes."""
    axes = [np.eye(3, dtype=F)[i] * s for i in range(3) for s in (F(-300), F(77.5))]
    found = RANDOM.uniform(-1200, 1200, (4093 - len(axes), 3)).astype(F)
    return np.concatenate([found, np.zeros((1, 3), F), np.array(axes, F)]).astype(F)


def ramp_cases() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distances across and around each range, equal and reversed ranges among them."""
    ends = (F(0), F(10), F(96), F(150), F(160))
    found = [
        (d, n, f)
        for n, f in itertools.product(ends, ends)
        for d in np.linspace(-10, 200, 211, dtype=F)
    ]
    dist, near, full = (np.array(c, F) for c in zip(*found, strict=True))
    return dist, near, full


def fog_cases(far: F) -> tuple[np.ndarray, np.ndarray]:
    """Random colours, and distances around the edge band and the environment's ranges."""
    count = 2048
    color = RANDOM.uniform(0, 1, (count, 3)).astype(F)
    edge = RANDOM.uniform(0, float(far) * 1.2, count).astype(F)
    edge[:4] = (far - np.clip(far * F(0.1), F(4), F(64)), far, F(0), far * F(2))
    straight = (edge * RANDOM.uniform(1, 1.8, count)).astype(F)
    return color, np.stack([straight, edge], axis=1)


POINTS = positions()
DIST, NEAR, FULL = ramp_cases()

TESTS = [
    l3.Function(
        "fogDistances",
        "vec2",
        (l3.Argument("fromCamera", "vec3", POINTS),),
        distances(POINTS),
        tolerance=0.0,
        relative=RELATIVE,
    ),
    l3.Function(
        "fogRamp",
        "float",
        (
            l3.Argument("dist", "float", DIST),
            l3.Argument("near", "float", NEAR),
            l3.Argument("full", "float", FULL),
        ),
        ramp(DIST, NEAR, FULL),
        tolerance=ABSOLUTE,
    ),
]
for far in FARS:
    color, dists = fog_cases(far)
    arguments = (l3.Argument("color", "vec3", color), l3.Argument("distances", "vec2", dists))
    uniforms = {"far": far, "fogColor": FOG_COLOR}
    TESTS.append(
        l3.Function(
            "withFog",
            "vec3",
            arguments,
            fogged(color, dists, far),
            tolerance=ABSOLUTE,
            uniforms=uniforms,
            note=f"far {far:g}",
        )
    )
    TESTS.extend(
        l3.Function(
            "withFog",
            "vec3",
            arguments,
            fogged(color, dists, far, environment),
            tolerance=ABSOLUTE,
            options={"BENCH_DETERMINISTIC": "false"},
            uniforms={**uniforms, "fogStart": environment[0], "fogEnd": environment[1]},
            note=f"far {far:g}, fogStart {environment[0]:g}, fogEnd {environment[1]:g}",
        )
        for environment in ENVIRONMENT
    )
