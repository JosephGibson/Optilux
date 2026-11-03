// deferred: the scene in HDR, once per pixel (plans/m4.md D75-D78). Where depth shows geometry it
// decodes the G-buffer and lights it with the shared shading (program/scene.glsl; LIGHT_PATH 1),
// or takes the early target the opaque programs lit themselves (LIGHT_PATH 0); an emissive
// material shows its albedo unlit; applies the overlays (D76, OVERLAYS: emit adds after
// lighting); fades the edge into the sky behind it, then mod multiplies the finished colour, as
// crumbling's blend multiplies the scene when it draws after deferred. Where depth is at its
// far value (1: Iris hands the pack forward depth, M4.P06's probe) it draws the gradient sky and
// adds the early target's sun and moon. trans goes over both, premultiplied.
// The hand's depth is squeezed by Iris (MC_HAND_DEPTH), so its position is not rebuilt: it takes
// no shadow and its held light at half a block.

#include "/lib/options.glsl"
#include "/lib/fog.glsl"
#include "/program/targets.glsl"
#include "/program/scene.glsl"
#if LIGHT_PATH == 1
#include "/lib/gbuffer.glsl"
#include "/lib/normals.glsl"
#if !defined DIMENSION_NETHER && SHADOWS == 1
#include "/program/shadowing.glsl"
#endif
#endif

uniform sampler2D depthtex0;
uniform sampler2D colortex2;
#ifdef OVERLAYS
uniform sampler2D colortex3;
uniform sampler2D colortex4;
uniform sampler2D colortex5;
#endif
#if LIGHT_PATH == 1
uniform usampler2D colortex1;
#endif
uniform mat4 gbufferProjectionInverse;
uniform float viewWidth;
uniform float viewHeight;
uniform float far;

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 sceneOut;

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    float depth = texelFetch(depthtex0, pixel, 0).r;
    vec2 screen = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
    vec4 view = gbufferProjectionInverse * vec4(vec3(screen, depth) * 2.0 - 1.0, 1.0);
    vec3 fromCamera = (gbufferModelViewInverse * vec4(view.xyz / view.w, 1.0)).xyz;
    vec3 direction = normalize(fromCamera);
    vec3 early = texelFetch(colortex2, pixel, 0).rgb;
    vec3 color;
    if (depth >= 1.0) {
        color = sceneSky(direction) + early;
    } else {
#if LIGHT_PATH == 1
        uvec4 words = texelFetch(colortex1, pixel, 0);
        float material = gbufferMaterial(words);
        vec3 albedo = linearFromSrgb(gbufferAlbedo(words));
        if (material == MATERIAL_EMISSIVE) {
            color = albedo * EMISSIVE_STRENGTH;
        } else {
            vec3 normal = normalFromCodes(gbufferNormalCodes(words));
            bool hand = material == MATERIAL_HAND;
            vec2 levels = sceneLevels(gbufferLevels(words), hand ? 0.5 : length(fromCamera));
#if defined DIMENSION_NETHER || SHADOWS == 0
            float shadow = 1.0;
#else
            float shadow = hand ? 1.0 : shadowAt(fromCamera, normal);
#endif
            color = shadeSurface(albedo, normal, levels, gbufferAo(words), shadow,
                                 material == MATERIAL_FOLIAGE, -direction, ROUGHNESS_OPAQUE);
        }
#else
        // Lit in its own program.
        color = early;
#endif
#ifdef OVERLAYS
        color += texelFetch(colortex4, pixel, 0).rgb;
#endif
        color = mix(color, sceneSky(direction), edgeFog(edgeDistance(fromCamera), far));
#ifdef OVERLAYS
        color *= texelFetch(colortex3, pixel, 0).rgb;
#endif
    }
#ifdef OVERLAYS
    vec4 over = texelFetch(colortex5, pixel, 0);
    color = color * (1.0 - over.a) + over.rgb;
#endif
    sceneOut = vec4(color, 1.0);
}
