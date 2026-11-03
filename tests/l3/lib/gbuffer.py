"""L3 tests of shaders/lib/gbuffer.glsl (docs/research/lighting.md#l3-golden-tests 1, plans/m4.md
D75): the encoder against numpy's packing of the same fields into four 16-bit words, exactly,
on random surfaces (each value a quarter step or more from a rounding boundary), on every field at
its maximum with the others 0 (no bit crosses into another field) and on all fields at 0 and at
their maxima; each decoder against the fields numpy packed, every field round-tripping over its
whole domain (asserted here)."""

import numpy as np

from optilux import l3

F = np.float32
RANDOM = np.random.default_rng(263)
# Field: (offset, width), lowest bit first, as the include's GBUFFER_* defines.
FIELDS = {
    "red": (0, 8),
    "green": (8, 8),
    "blue": (16, 8),
    "u": (24, 7),
    "v": (31, 7),
    "block": (38, 7),
    "sky": (45, 7),
    "ao": (52, 6),
    "material": (58, 6),
}
ORDER = tuple(FIELDS)
# A decoded field is its code over its steps: one division, 2.5 ulp.
ABSOLUTE = 2e-7


def pack(codes: np.ndarray) -> np.ndarray:
    """Per case its nine field codes (cases, 9) as the four 16-bit words (cases, 4)."""
    bits = np.zeros(len(codes), np.uint64)
    for column, name in enumerate(ORDER):
        offset, width = FIELDS[name]
        field = codes[:, column].astype(np.uint64)
        assert np.all(field < (1 << width))
        bits |= field << np.uint64(offset)
    return np.stack([(bits >> np.uint64(16 * w)) & np.uint64(0xFFFF) for w in range(4)], axis=1)


def unpack(words: np.ndarray) -> np.ndarray:
    bits = sum(words[:, w].astype(np.uint64) << np.uint64(16 * w) for w in range(4))
    return np.stack(
        [(bits >> np.uint64(o)) & np.uint64((1 << w) - 1) for o, w in FIELDS.values()], axis=1
    )


def random_codes(count: int) -> np.ndarray:
    return np.stack(
        [RANDOM.integers(0, 1 << width, count) for _, width in FIELDS.values()], axis=1
    ).astype(np.int64)


def single_fields() -> np.ndarray:
    """Each field at its maximum alone, then every field at 0 and every field at its maximum."""
    rows = []
    for column, (_, width) in enumerate(FIELDS.values()):
        row = np.zeros(len(FIELDS), np.int64)
        row[column] = (1 << width) - 1
        rows.append(row)
    rows.append(np.zeros(len(FIELDS), np.int64))
    rows.append(np.array([(1 << w) - 1 for _, w in FIELDS.values()], np.int64))
    return np.array(rows)


def arguments(codes: np.ndarray) -> tuple[l3.Argument, ...]:
    """The encoder's inputs for the codes: each value inside its code's step, a quarter step or
    more from either boundary; the normal codes signed; the material as a whole number."""
    jitter = RANDOM.uniform(-0.25, 0.25, codes.shape)
    jitter[:, [3, 4, 8]] = 0

    def scaled(column: int, steps: float) -> np.ndarray:
        return ((codes[:, column] + jitter[:, column]) / steps).astype(F)

    albedo = np.stack([scaled(c, 255) for c in range(3)], axis=1)
    normal = (codes[:, 3:5] - 63).astype(F)
    levels = np.stack([scaled(5, 127), scaled(6, 127)], axis=1)
    return (
        l3.Argument("albedo", "vec3", albedo),
        l3.Argument("normalCodes", "vec2", normal),
        l3.Argument("levels", "vec2", levels),
        l3.Argument("ao", "float", scaled(7, 63)),
        l3.Argument("material", "float", codes[:, 8].astype(F)),
    )


CODES = np.concatenate([random_codes(4096), single_fields()])
# Normal codes run 0..126 stored (-63..63): 127 is no code.
CODES[:, 3:5] = np.minimum(CODES[:, 3:5], 126)
WORDS = pack(CODES)
assert np.array_equal(unpack(WORDS), CODES)
for column in range(len(FIELDS)):
    alone = single_fields()[column : column + 1]
    if column in (3, 4):
        alone = np.minimum(alone, 126)
    assert np.array_equal(unpack(pack(alone))[0], alone[0])
DECODE = random_codes(4096)
DECODE[:, 3:5] = np.minimum(DECODE[:, 3:5], 126)
DECODE_WORDS = pack(DECODE).astype(F)
WORD_ARGUMENT = (l3.Argument("words", "uvec4", DECODE_WORDS),)

TESTS = [
    l3.Function("gbufferEncode", "uvec4", arguments(CODES), WORDS.astype(F), tolerance=0.0),
    l3.Function(
        "gbufferAlbedo",
        "vec3",
        WORD_ARGUMENT,
        (DECODE[:, 0:3] / F(255)).astype(F),
        tolerance=ABSOLUTE,
    ),
    l3.Function(
        "gbufferNormalCodes",
        "vec2",
        WORD_ARGUMENT,
        (DECODE[:, 3:5] - 63).astype(F),
        tolerance=0.0,
    ),
    l3.Function(
        "gbufferLevels",
        "vec2",
        WORD_ARGUMENT,
        (DECODE[:, 5:7] / F(127)).astype(F),
        tolerance=ABSOLUTE,
    ),
    l3.Function(
        "gbufferAo", "float", WORD_ARGUMENT, (DECODE[:, 7] / F(63)).astype(F), tolerance=ABSOLUTE
    ),
    l3.Function("gbufferMaterial", "float", WORD_ARGUMENT, DECODE[:, 8].astype(F), tolerance=0.0),
]
