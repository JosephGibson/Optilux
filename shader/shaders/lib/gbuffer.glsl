// The G-buffer's 64 bits (plans/m4.md D75; docs/research/lighting.md#g-buffer-packing), stored as
// one RGBA16UI texel: four 16-bit words, word 0 the lowest bits. Fields, lowest bit first:
//   albedo red 8, green 8, blue 8 (sRGB-encoded as the texture is, so dark texels keep their
//   8 bits; the reader linearizes it), normal codes 7 and 7 (lib/normals.glsl,
//   stored + 63), block level 7 and sky level 7 (0-127), vanilla AO 6 (0-63), material 6.
// The bits are built in two 32-bit words; the second normal code straddles them. Every draw writes
// all four words, so no field keeps an earlier draw's bits (integer targets are never blended).

#ifndef OPTILUX_GBUFFER
#define OPTILUX_GBUFFER 1

#define GBUFFER_RED 0
#define GBUFFER_GREEN 8
#define GBUFFER_BLUE 16
#define GBUFFER_NORMAL_U 24
#define GBUFFER_NORMAL_V 31
#define GBUFFER_BLOCK 38
#define GBUFFER_SKY 45
#define GBUFFER_AO 52
#define GBUFFER_MATERIAL 58

// `value`'s low `width` bits placed at bit `offset` of the 64.
uvec2 placeBits(uvec2 bits, uint value, int offset, int width) {
    value &= (1u << uint(width)) - 1u;
    if (offset >= 32) {
        bits.y |= value << uint(offset - 32);
    } else {
        bits.x |= value << uint(offset);
        if (offset + width > 32) bits.y |= value >> uint(32 - offset);
    }
    return bits;
}

uint takeBits(uvec2 bits, int offset, int width) {
    uint mask = (1u << uint(width)) - 1u;
    if (offset >= 32) return (bits.y >> uint(offset - 32)) & mask;
    uint low = bits.x >> uint(offset);
    if (offset + width > 32) low |= bits.y << uint(32 - offset);
    return low & mask;
}

// A value in [0, 1] as the nearest of `steps` + 1 levels.
uint quantize(float value, float steps) {
    return uint(floor(clamp(value, 0.0, 1.0) * steps + 0.5));
}

uvec4 gbufferEncode(vec3 albedo, vec2 normalCodes, vec2 levels, float ao, float material) {
    uvec2 bits = uvec2(0u);
    bits = placeBits(bits, quantize(albedo.r, 255.0), GBUFFER_RED, 8);
    bits = placeBits(bits, quantize(albedo.g, 255.0), GBUFFER_GREEN, 8);
    bits = placeBits(bits, quantize(albedo.b, 255.0), GBUFFER_BLUE, 8);
    bits = placeBits(bits, uint(normalCodes.x + 63.0), GBUFFER_NORMAL_U, 7);
    bits = placeBits(bits, uint(normalCodes.y + 63.0), GBUFFER_NORMAL_V, 7);
    bits = placeBits(bits, quantize(levels.x, 127.0), GBUFFER_BLOCK, 7);
    bits = placeBits(bits, quantize(levels.y, 127.0), GBUFFER_SKY, 7);
    bits = placeBits(bits, quantize(ao, 63.0), GBUFFER_AO, 6);
    bits = placeBits(bits, uint(material), GBUFFER_MATERIAL, 6);
    return uvec4(bits.x & 0xFFFFu, bits.x >> 16u, bits.y & 0xFFFFu, bits.y >> 16u);
}

uvec2 gbufferBits(uvec4 words) {
    return uvec2(words.x | (words.y << 16u), words.z | (words.w << 16u));
}

vec3 gbufferAlbedo(uvec4 words) {
    uvec2 bits = gbufferBits(words);
    return vec3(takeBits(bits, GBUFFER_RED, 8), takeBits(bits, GBUFFER_GREEN, 8),
                takeBits(bits, GBUFFER_BLUE, 8)) / 255.0;
}

vec2 gbufferNormalCodes(uvec4 words) {
    uvec2 bits = gbufferBits(words);
    return vec2(takeBits(bits, GBUFFER_NORMAL_U, 7), takeBits(bits, GBUFFER_NORMAL_V, 7)) - 63.0;
}

// The block and the sky level, each in [0, 1].
vec2 gbufferLevels(uvec4 words) {
    uvec2 bits = gbufferBits(words);
    return vec2(takeBits(bits, GBUFFER_BLOCK, 7), takeBits(bits, GBUFFER_SKY, 7)) / 127.0;
}

float gbufferAo(uvec4 words) {
    return float(takeBits(gbufferBits(words), GBUFFER_AO, 6)) / 63.0;
}

float gbufferMaterial(uvec4 words) {
    return float(takeBits(gbufferBits(words), GBUFFER_MATERIAL, 6));
}

#endif
