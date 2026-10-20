// The light on a surface, read in the vertex stage from vanilla's lightmap as vanilla does.
// vaUV2 holds 16 times the block and the sky light level (0 to 240); the lightmap has 16 texels
// per axis, level L's centre at (L + 0.5) / 16, so a level pair maps to (vaUV2 + 8) / 256.

#ifndef OPTILUX_LIGHT
#define OPTILUX_LIGHT 1

uniform sampler2D lightmap;

#ifdef BENCH_DETERMINISTIC
// The lightmap's block light flickers: the client adds a random step to it every tick, also under
// /tick freeze (26.3: LightmapRenderStateExtractor.tick, blockFactor = flicker + 1.4). The column
// without block light holds still, so the bench reads that column and adds the block light at the
// flicker's rest (1.4) with vanilla's brightness curve and its default block tint (#FFD88C, which
// no 26.3 dimension or biome overrides). Unlike vanilla, the brightness setting's curve is not
// applied to the block part.
vec3 restingBlockLight(float level) {
    float brightness = level / (4.0 - 3.0 * level);
    float pale = 2.0 * level - 1.0;
    vec3 tint = mix(vec3(1.0, 216.0 / 255.0, 140.0 / 255.0), vec3(1.0), 0.9 * pale * pale);
    return tint * brightness * 1.4;
}
#endif

vec3 surfaceLight(vec2 levels16) {
#ifdef BENCH_DETERMINISTIC
    vec3 skyAndAmbient = texture(lightmap, vec2(8.0, levels16.y + 8.0) / 256.0).rgb;
    return min(skyAndAmbient + restingBlockLight(levels16.x / 240.0), vec3(1.0));
#else
    return texture(lightmap, (levels16 + 8.0) / 256.0).rgb;
#endif
}

#endif
