"""L3 tests of shaders/lib/shadow.glsl (docs/research/shadows.md#for-optilux): the distortion and
its inverse against float32 numpy over the map's disc, their round trip within 1e-6 and the texel
size against the distortion's finite differences (both asserted here, in float64); the texel size
at the centre and the edge of the pack's map (2048 texels, 96 blocks): 0.01875 and 0.46875 blocks,
53.3 texels a block at the camera."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
K = 0.8
RESOLUTION, DISTANCE = 2048.0, 96.0
# A length, a division: a few ulp of values up to 1.
ABSOLUTE = 1e-6
RELATIVE = 1e-6


def distort(p: np.ndarray, dtype=F) -> np.ndarray:
    p = np.asarray(p, dtype)
    r = np.linalg.norm(p, axis=1, keepdims=True).astype(dtype)
    return (p / (dtype(K) * r + dtype(1 - K))).astype(dtype)


def undistort(d: np.ndarray, dtype=F) -> np.ndarray:
    d = np.asarray(d, dtype)
    s = np.linalg.norm(d, axis=1, keepdims=True).astype(dtype)
    return (d * (dtype(1 - K) / (dtype(1) - dtype(K) * s))).astype(dtype)


def texel(radius: np.ndarray, distance: float, resolution: float) -> np.ndarray:
    stretch = K * np.asarray(radius, np.float64) + (1 - K)
    return 2 * distance / resolution * stretch * stretch / (1 - K)


angle = RANDOM.uniform(0, 2 * np.pi, 4096)
radius = np.sqrt(RANDOM.uniform(0, 1, 4096))
radius[:3] = (0, 1, 0.5)
DISC = np.stack([np.cos(angle) * radius, np.sin(angle) * radius], axis=1)
assert np.abs(undistort(distort(DISC, np.float64), np.float64) - DISC).max() < 1e-6
step = 1e-6
for r in (0.0, 0.1, 0.5, 0.9, 0.999):
    ahead, here = (distort(np.array([[x, 0.0]]), np.float64)[0, 0] for x in (r + step, r))
    ds = ahead - here
    size = 2 / RESOLUTION / (ds / step) * DISTANCE
    assert abs(size - texel(r, DISTANCE, RESOLUTION)) < 1e-5 * size, r
assert abs(texel(0, DISTANCE, RESOLUTION) - 0.01875) < 1e-12
assert abs(texel(1, DISTANCE, RESOLUTION) - 0.46875) < 1e-12
RADII = np.linspace(0, 1, 101, dtype=F)
DISTANCES = np.array([64, 96, 160], F)
R, D = (a.ravel() for a in np.meshgrid(RADII, DISTANCES))
DISTORTED = distort(DISC)

TESTS = [
    l3.Function(
        "shadowDistort",
        "vec2",
        (l3.Argument("position", "vec2", DISC.astype(F)),),
        distort(DISC),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
    l3.Function(
        "shadowUndistort",
        "vec2",
        (l3.Argument("distorted", "vec2", DISTORTED),),
        undistort(DISTORTED),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
    l3.Function(
        "shadowTexelBlocks",
        "float",
        (
            l3.Argument("radius", "float", R),
            l3.Argument("distance", "float", D),
            l3.Argument("resolution", "float", np.full(len(R), RESOLUTION, F)),
        ),
        texel(R, D, RESOLUTION).astype(F),
        tolerance=0.0,
        relative=RELATIVE,
    ),
]
