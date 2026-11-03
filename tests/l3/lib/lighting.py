"""L3 tests of shaders/lib/lighting.glsl (docs/research/lighting.md#l3-golden-tests): the sky's
access gate, a smooth step from sky level 0.2 to 0.6, and the lit surface against float32 numpy
on random inputs: the direct light only where the normal faces it, scaled by the shadow and the
gate; the sky's light weighted toward faces looking up (45 % for one looking down); block light
and the floor light, both under vanilla's AO. Asserted here: a surface with no light anywhere
and no floor is black, and zero shadow at no sky and no block light leaves only the floor."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
BLOCK_FALLOFF, SKY_FALLOFF = F(4), F(2)
# A dot, a smoothstep, two divisions and a dozen products and sums: a few ulp of values up to ~10.
ABSOLUTE = 2e-6
RELATIVE = 2e-6


def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - F(edge0)) / F(edge1 - edge0), 0, 1).astype(F)
    return (t * t * (F(3) - F(2) * t)).astype(F)


def curve(level: np.ndarray, falloff: F) -> np.ndarray:
    return (level / (F(1) + falloff * (F(1) - level))).astype(F)


def radiance(albedo, normal, levels, ao, shadow, to_light, light, sky, block, floor) -> np.ndarray:
    facing = np.maximum((normal * to_light).sum(axis=1), 0).astype(F)
    direct = light * (facing * shadow * smoothstep(0.2, 0.6, levels[:, 1]))[:, None]
    upward = (F(0.45) + (F(1) - F(0.45)) * (normal[:, 1] * F(0.5) + F(0.5))).astype(F)
    ambient = sky * (curve(levels[:, 1], SKY_FALLOFF) * upward)[:, None]
    ambient = ambient + block * curve(levels[:, 0], BLOCK_FALLOFF)[:, None]
    return (albedo * (direct + (ambient + floor) * ao[:, None])).astype(F)


def unit(count: int) -> np.ndarray:
    v = RANDOM.normal(size=(count, 3))
    return (v / np.linalg.norm(v, axis=1, keepdims=True)).astype(F)


COUNT = 2048
INPUTS = {
    "albedo": RANDOM.uniform(0, 1, (COUNT, 3)).astype(F),
    "normal": unit(COUNT),
    "levels": RANDOM.uniform(0, 1, (COUNT, 2)).astype(F),
    "ao": RANDOM.uniform(0, 1, COUNT).astype(F),
    "shadow": RANDOM.uniform(0, 1, COUNT).astype(F),
    "toLight": unit(COUNT),
    "lightColor": RANDOM.uniform(0, 3, (COUNT, 3)).astype(F),
    "skyColor": RANDOM.uniform(0, 1, (COUNT, 3)).astype(F),
    "blockColor": RANDOM.uniform(0, 2, (COUNT, 3)).astype(F),
    "floorColor": RANDOM.uniform(0, 0.05, (COUNT, 3)).astype(F),
}
INPUTS["levels"][:4] = ((0, 0), (1, 1), (0, 1), (1, 0))
INPUTS["shadow"][:4] = (0, 1, 1, 0)
TYPES = {"ao": "float", "shadow": "float", "levels": "vec2"}
GOLDEN = radiance(*INPUTS.values())
dark = {**INPUTS, "levels": np.zeros((COUNT, 2), F), "shadow": np.zeros(COUNT, F)}
assert np.allclose(
    radiance(*dark.values()),
    INPUTS["albedo"] * INPUTS["floorColor"] * dark["ao"][:, None],
    rtol=1e-6,
    atol=0,
)
assert not radiance(*{**dark, "floorColor": np.zeros((COUNT, 3), F)}.values()).any()
SKY_LEVELS = np.linspace(0, 1, 101, dtype=F)

TESTS = [
    l3.Function(
        "skyAccess",
        "float",
        (l3.Argument("skyLevel", "float", SKY_LEVELS),),
        smoothstep(0.2, 0.6, SKY_LEVELS),
        tolerance=1e-6,
    ),
    l3.Function(
        "surfaceRadiance",
        "vec3",
        tuple(
            l3.Argument(name, TYPES.get(name, "vec3"), values) for name, values in INPUTS.items()
        ),
        GOLDEN,
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
]
