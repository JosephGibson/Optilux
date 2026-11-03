// The fragment stage of the forward programs (plans/m4.md D76): each draw lit (or unlit) here and
// written into the scene with the draw's own blend, vanilla's. A draw after deferred lands on the
// lit scene. A draw before it is overwritten there by deferred, so a program that also draws
// before deferred writes the same value into the target of its blend's operation, which deferred
// applies and nothing reads after it: one value right for both sides, whichever side a draw
// falls on (renderStage cannot tell them apart: M4.P06's probe). Lit, a fragment takes the shared
// shading (program/scene.glsl) with its own normal, levels and Low shadow tap; unlit, vertex colour
// times texture in linear light. Both fade into the sky with the edge fog at their own distance.
// Switches, set by the program file before including this:
//   FORWARD_TEXTURE    the albedo texture times the vertex colour;
//   FORWARD_LIT        the shared shading; FORWARD_NORMAL with the vertex normal, else facing the
//                      camera (rain, particles, leashes); FORWARD_SMOOTH the sharper highlight of
//                      translucent terrain; FORWARD_TERRAIN Sodium's vertex alpha as AO (separateAo,
//                      P16), the texture's alpha the coverage; FORWARD_HAND no shadow and the held
//                      light at half a block (MC_HAND_DEPTH, as program/surface.fsh.glsl);
//   FORWARD_EMISSIVE   unlit at EMISSIVE_STRENGTH (beacon beam, spider eyes, lightning);
//   FORWARD_ADDITIVE   an added blend: the fog fades the light out rather than toward the sky;
//   FORWARD_GLINT      off BENCH_DETERMINISTIC the item's own glint, mc_sampleGlint() (P19), added;
//   FORWARD_NOT_IN_BENCH  nothing under BENCH_DETERMINISTIC (their state moves with the ticks
//                      before /tick freeze and the stepped ones, or with the game time);
//   one target beside the scene, by the draw's blend (OVERLAYS keeps the three overlays):
//   FORWARD_TRANS      trans: the colour and alpha, which vanilla's translucent blend premultiplies
//                      over (banner patterns, armour cracks, sign text);
//   FORWARD_MOD        mod: crumbling's multiply (vanilla's DST_COLOR, SRC_COLOR: twice the colour
//                      times what is there), as linear light;
//   FORWARD_EMIT       emit: the glint's add (vanilla's SRC_COLOR, ONE: the colour squared added),
//                      so its square root is written, into emit before the edge fog, which
//                      deferred applies to it;
//   FORWARD_GBUFFER    the G-buffer (LIGHT_PATH 1) or the early target (0): an opaque part drawn
//                      before deferred writes depth, so deferred decodes this pixel (the beacon
//                      beam's core, leashes); with the overlays' neutral values, as an opaque draw
//                      after terrain (program/surface.fsh.glsl).

#include "/lib/options.glsl"
#include "/lib/srgb.glsl"
#include "/lib/fog.glsl"
#include "/program/targets.glsl"
#include "/program/scene.glsl"
#if defined FORWARD_LIT && !defined FORWARD_HAND && !defined DIMENSION_NETHER && SHADOWS == 1
#define FORWARD_SHADOWED 1
#include "/program/shadowing.glsl"
#endif
#if defined FORWARD_GBUFFER && LIGHT_PATH == 1
#include "/lib/gbuffer.glsl"
#include "/lib/normals.glsl"
#endif

in vec4 vertexColor;
in vec3 fromCamera;

// Iris's cutoff for this draw (program/surface.fsh.glsl).
uniform float alphaTestRef;
uniform float far;

#ifdef FORWARD_TEXTURE
uniform sampler2D gtexture;
in vec2 albedoCoord;
#endif

#ifdef FORWARD_LIT
in vec2 levels;
#ifdef FORWARD_NORMAL
in vec3 worldNormal;
#endif
#endif

#ifdef OVERLAYS
#if defined FORWARD_TRANS
/* RENDERTARGETS: 0,5 */
#define FORWARD_SECOND transOut
#elif defined FORWARD_MOD
/* RENDERTARGETS: 0,3 */
#define FORWARD_SECOND modOut
#elif defined FORWARD_EMIT
/* RENDERTARGETS: 0,4 */
#define FORWARD_SECOND emitOut
#endif
#endif
#if defined FORWARD_GBUFFER && defined OVERLAYS
#if LIGHT_PATH == 1
/* RENDERTARGETS: 0,1,3,4,5 */
#else
/* RENDERTARGETS: 0,2,3,4,5 */
#endif
#elif defined FORWARD_GBUFFER
#if LIGHT_PATH == 1
/* RENDERTARGETS: 0,1 */
#else
/* RENDERTARGETS: 0,2 */
#endif
#elif !defined FORWARD_SECOND
/* RENDERTARGETS: 0 */
#endif
layout(location = 0) out vec4 sceneOut;
#ifdef FORWARD_SECOND
layout(location = 1) out vec4 FORWARD_SECOND;
#endif
#ifdef FORWARD_GBUFFER
#if LIGHT_PATH == 1
layout(location = 1) out uvec4 gbufferOut;
#else
layout(location = 1) out vec4 earlyOut;
#endif
#ifdef OVERLAYS
layout(location = 2) out vec4 modOut;
layout(location = 3) out vec4 emitOut;
layout(location = 4) out vec4 transOut;
#endif
#endif

void main() {
#if defined FORWARD_NOT_IN_BENCH && defined BENCH_DETERMINISTIC
    discard;
#endif
    vec4 color = vertexColor;
    float coverage = vertexColor.a;
#ifdef FORWARD_TEXTURE
    vec4 texel = texture(gtexture, albedoCoord);
    coverage = texel.a;
#ifdef FORWARD_TERRAIN
    color = vec4(vertexColor.rgb * texel.rgb, texel.a);
#else
    color *= texel;
#endif
#endif
    if (coverage < alphaTestRef && alphaTestRef <= 1.0) discard;
    vec3 direction = normalize(fromCamera);
    vec3 light = linearFromSrgb(color.rgb);
#if defined FORWARD_LIT
#ifdef FORWARD_NORMAL
    vec3 normal = normalize(worldNormal);
    if (!gl_FrontFacing) normal = -normal;
#else
    vec3 normal = -direction;
#endif
#ifdef FORWARD_HAND
    vec2 lit = sceneLevels(levels, 0.5);
#else
    vec2 lit = sceneLevels(levels, length(fromCamera));
#endif
#ifdef FORWARD_TERRAIN
    float ao = vertexColor.a;
#else
    float ao = 1.0;
#endif
#ifdef FORWARD_SHADOWED
    float shadow = shadowAt(fromCamera, normal);
#else
    float shadow = 1.0;
#endif
#ifdef FORWARD_SMOOTH
    float roughness = ROUGHNESS_TRANSLUCENT;
#else
    float roughness = ROUGHNESS_OPAQUE;
#endif
    light = shadeSurface(light, normal, lit, ao, shadow, false, -direction, roughness);
#elif defined FORWARD_EMISSIVE
    light *= EMISSIVE_STRENGTH;
#endif
#if defined FORWARD_GLINT && !defined BENCH_DETERMINISTIC
    light += linearFromSrgb(mc_sampleGlint());
#endif
    float fog = edgeFog(edgeDistance(fromCamera), far);
#ifdef FORWARD_MOD
    // The multiply crumbling's blend makes of it: twice the colour, as linear light, halved again.
    vec3 shown = 0.5 * linearFromSrgb(min(2.0 * color.rgb, 1.0));
#elif defined FORWARD_EMIT
    vec3 shown = sqrt(light * (1.0 - fog));
#elif defined FORWARD_ADDITIVE
    vec3 shown = light * (1.0 - fog);
#else
    vec3 shown = mix(light, sceneSky(direction), fog);
#endif
    sceneOut = vec4(shown, color.a);
#ifdef FORWARD_SECOND
#ifdef FORWARD_EMIT
    FORWARD_SECOND = vec4(sqrt(light), color.a);
#else
    FORWARD_SECOND = sceneOut;
#endif
#endif
#ifdef FORWARD_GBUFFER
#if LIGHT_PATH == 1
#ifdef FORWARD_EMISSIVE
    float material = MATERIAL_EMISSIVE;
#else
    float material = MATERIAL_ENTITY;
#endif
#ifdef FORWARD_LIT
    vec2 stored = levels;
#else
    vec2 stored = vec2(1.0);
#endif
    gbufferOut = gbufferEncode(color.rgb, normalCodes(-direction), stored, 1.0, material);
#else
    earlyOut = vec4(light, 1.0);
#endif
#ifdef OVERLAYS
    modOut = MOD_NEUTRAL;
    emitOut = EMIT_NEUTRAL;
    transOut = TRANS_NEUTRAL;
#endif
#endif
}
