// Light levels to light. Terrain carries its block and sky light as vaUV2, 0 to 240: Sodium's
// smooth lighting averages the levels of the blocks around each corner, so it is no multiple of 16
// (plans/m4.md P16). A level is that over 240, in [0, 1]. Each curve has the form
//   curve(l) = l / (1 + k (1 - l)),
// 0 at 0, 1 at 1, rising faster as it nears 1 the larger k is: light that falls off with distance
// from its source, each level one block nearer. Block light falls off harder than sky light.

#ifndef OPTILUX_CURVES
#define OPTILUX_CURVES 1

#define BLOCK_FALLOFF 4.0
#define SKY_FALLOFF 2.0

float lightLevel(float uv2) {
    return clamp(uv2 * (1.0 / 240.0), 0.0, 1.0);
}

float lightCurve(float level, float falloff) {
    return level / (1.0 + falloff * (1.0 - level));
}

float blockLight(float level) {
    return lightCurve(level, BLOCK_FALLOFF);
}

float skyLight(float level) {
    return lightCurve(level, SKY_FALLOFF);
}

#endif
