// The Low shadow lookup (plans/m4.md D77): one hardware compare on shadowtex1, the opaque casters'
// depth (translucents cast none at Low), a bilinear 2x2 percentage-closer tap. shadowtex holds
// forward depth, cleared to 1, and the compare is lit where the reference is at or in front of the
// stored depth (M4.P06's probe, m4-probe-capture-1). The position moves 1.5 texels along the
// normal first, the texel's size taken at its radius on the distorted map (lib/shadow.glsl).
// Iris reads the map's settings from the comment below; the defines repeat them for the code.
// Never in the Nether: world-1 samples no shadow target, so Iris renders no shadow pass there (P20).
/*
const int shadowMapResolution = 2048;
const float shadowDistance = 96.0;
const float shadowDistanceRenderMul = 1.0;
const bool shadowHardwareFiltering1 = true;
*/

#ifndef OPTILUX_SHADOWING
#define OPTILUX_SHADOWING 1

#include "/lib/options.glsl"
#include "/lib/shadow.glsl"

#define SHADOW_RESOLUTION 2048.0
#define SHADOW_DISTANCE 96.0
// Half a stored depth step at the map's depth range, against the compare's own rounding.
#define SHADOW_DEPTH_BIAS 0.0002

uniform sampler2DShadow shadowtex1;
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
#if E2_LOAD > 0
// E2_LOAD's count as a custom uniform (shaders.properties), so no compiler unrolls the loop.
uniform int e2Load;
#endif

vec3 shadowSpace(vec3 fromCamera) {
    return (shadowProjection * (shadowModelView * vec4(fromCamera, 1.0))).xyz;
}

// 1 lit to 0 shadowed, for a point relative to the camera (world axes) and its unit normal;
// 1 off the map. The distortion keeps the whole square inside it (no component grows), so the
// square is the map's reach.
float shadowAt(vec3 fromCamera, vec3 normal) {
    float radius = length(shadowSpace(fromCamera).xy);
    float texel = shadowTexelBlocks(radius, SHADOW_DISTANCE, SHADOW_RESOLUTION);
    vec3 position = shadowSpace(fromCamera + normal * (1.5 * texel));
    if (max(abs(position.x), abs(position.y)) >= 1.0 || abs(position.z) >= 1.0) return 1.0;
    vec3 coords = vec3(shadowDistort(position.xy), position.z) * 0.5 + 0.5;
    coords.z -= SHADOW_DEPTH_BIAS;
    float lit = texture(shadowtex1, coords);
#if E2_LOAD > 0
    float extra = 0.0;
    for (int i = 0; i < e2Load; i++) {
        vec2 offset = vec2(float(i % 4) - 1.5, float(i / 4) - 1.5) / SHADOW_RESOLUTION;
        extra += texture(shadowtex1, coords + vec3(offset, 0.0));
    }
    // Never true (a compare returns 0 to 1), but no compiler can drop the fetches.
    if (extra < 0.0) lit = 0.0;
#endif
    return lit;
}

#endif
