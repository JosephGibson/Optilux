"""L3 tests of shaders/lib/lighting.glsl (docs/research/lighting.md#l3-golden-tests): the sky's
access gate, a smooth step from sky level 0.2 to 0.6, and the lit surface against float32 numpy
on random inputs: the direct light only where the normal faces it, scaled by the shadow and the
gate; the sky's light weighted toward faces looking up (45 % for one looking down); block light
and the floor light, both under vanilla's AO. Asserted here: a surface with no light anywhere
and no floor is black, and zero shadow at no sky and no block light leaves only the floor.
Then the light before the albedo at a given facing (surfaceLight), foliage's facing (N.L wrapped
half way round, plus the light through it toward an eye behind it) and the sun's highlight (GGX,
Schlick, Schlick-GGX visibility, times N.L; 0 with the light or the eye behind the face), each
against float32 numpy; asserted here: the highlight is 0 behind the face and peaks at the mirror
direction."""

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


def light_at(facing, up, levels, ao, shadow, light, sky, block, floor) -> np.ndarray:
    direct = light * (facing * shadow * smoothstep(0.2, 0.6, levels[:, 1]))[:, None]
    upward = (F(0.45) + (F(1) - F(0.45)) * (up * F(0.5) + F(0.5))).astype(F)
    ambient = sky * (curve(levels[:, 1], SKY_FALLOFF) * upward)[:, None]
    ambient = ambient + block * curve(levels[:, 0], BLOCK_FALLOFF)[:, None]
    return (direct + (ambient + floor) * ao[:, None]).astype(F)


def dot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a * b).sum(axis=1).astype(F)


def foliage(normal, to_light, to_eye) -> np.ndarray:
    facing = dot(normal, to_light)
    wrapped = np.clip((facing + F(0.5)) * F(1 / 1.5), 0, 1).astype(F)
    through = np.maximum(-dot(to_eye, to_light), 0).astype(F) ** 4
    return (wrapped + F(0.4) * through * (F(1) - np.maximum(facing, 0))).astype(F)


def specular(normal, to_light, to_eye, roughness, f0) -> np.ndarray:
    nl, nv = dot(normal, to_light), dot(normal, to_eye)
    halfway = to_light + to_eye
    halfway = (halfway / np.linalg.norm(halfway, axis=1, keepdims=True)).astype(F)
    nh = np.maximum(dot(normal, halfway), 0)
    vh = np.maximum(dot(to_eye, halfway), 0)
    alpha = (roughness * roughness).astype(F)
    alpha2 = alpha * alpha
    spread = nh * nh * (alpha2 - F(1)) + F(1)
    distribution = alpha2 / (F(np.pi) * spread * spread)
    fresnel = f0 + (F(1) - f0) * (F(1) - vh) ** 5
    k = alpha * F(0.5)
    visibility = F(1) / ((nl * (F(1) - k) + k) * (nv * (F(1) - k) + k) * F(4))
    value = (distribution * fresnel * visibility * nl).astype(F)
    return np.where((nl <= 0) | (nv <= 0), F(0), value).astype(F)


FACING = RANDOM.uniform(0, 1.4, COUNT).astype(F)
UP = RANDOM.uniform(-1, 1, COUNT).astype(F)
LIGHT_INPUTS = {
    "facing": FACING,
    "up": UP,
    **{k: INPUTS[k] for k in ("levels", "ao", "shadow")},
    "lightColor": INPUTS["lightColor"],
    "skyColor": INPUTS["skyColor"],
    "blockColor": INPUTS["blockColor"],
    "floorColor": INPUTS["floorColor"],
}
LIGHT_TYPES = {"facing": "float", "up": "float", **TYPES}
TO_EYE = unit(COUNT)
ROUGHNESS = RANDOM.uniform(0.1, 1.0, COUNT).astype(F)
F0 = RANDOM.uniform(0.02, 0.08, COUNT).astype(F)
# A highlight peaks where the eye looks along the light's mirror direction, at roughness 0.15.
up_normal = np.tile(np.array([[0, 1, 0]], F), (3, 1))
sun = np.array([[0.6, 0.8, 0]], F)
eyes = np.array([[-0.6, 0.8, 0], [0, 1, 0], [0.6, -0.8, 0]], F)
peak = specular(up_normal, np.tile(sun, (3, 1)), eyes, np.full(3, F(0.15)), np.full(3, F(0.04)))
assert peak[0] > peak[1] > 0 and peak[2] == 0
SPECULAR_GOLDEN = specular(INPUTS["normal"], INPUTS["toLight"], TO_EYE, ROUGHNESS, F0)

TESTS += [
    l3.Function(
        "surfaceLight",
        "vec3",
        tuple(
            l3.Argument(name, LIGHT_TYPES.get(name, "vec3"), values)
            for name, values in LIGHT_INPUTS.items()
        ),
        light_at(*LIGHT_INPUTS.values()),
        tolerance=ABSOLUTE,
        relative=RELATIVE,
    ),
    l3.Function(
        "foliageFacing",
        "float",
        (
            l3.Argument("normal", "vec3", INPUTS["normal"]),
            l3.Argument("toLight", "vec3", INPUTS["toLight"]),
            l3.Argument("toEye", "vec3", TO_EYE),
        ),
        foliage(INPUTS["normal"], INPUTS["toLight"], TO_EYE),
        tolerance=ABSOLUTE,
    ),
    # GGX's peak grows as 1 / roughness^4: a relative bound on values up to ~10^3 at roughness 0.1.
    l3.Function(
        "sunSpecular",
        "float",
        (
            l3.Argument("normal", "vec3", INPUTS["normal"]),
            l3.Argument("toLight", "vec3", INPUTS["toLight"]),
            l3.Argument("toEye", "vec3", TO_EYE),
            l3.Argument("roughness", "float", ROUGHNESS),
            l3.Argument("f0", "float", F0),
        ),
        SPECULAR_GOLDEN,
        tolerance=1e-5,
        relative=2e-5,
    ),
]
