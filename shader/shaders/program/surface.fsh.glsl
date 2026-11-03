// The fragment stage of the opaque programs (plans/m4.md D75): the albedo (texture x vertex colour,
// sRGB-encoded), the normal facing the viewer, the light levels, vanilla's AO and the material,
// written whole into the G-buffer (LIGHT_PATH 1); or, under LIGHT_PATH 0, lit here by the shared
// shading (program/scene.glsl) on the exact values and written into the early target, which
// deferred takes as lit.
// Switches, set by the program file before including this:
//   SURFACE_SOLID      no alpha test and no discard at all (terrain_solid: early depth stays on);
//   SURFACE_TERRAIN    the vertex alpha is vanilla's AO times the face shade (separateAo, P16), and
//                      foliage (block.properties' block.10) is its own material;
//   SURFACE_ENTITY     under BENCH_DETERMINISTIC the end crystals are hidden: each starts its spin
//                      at a random angle every launch (entity.properties: entity.1);
//   SURFACE_NOT_IN_BENCH  nothing under BENCH_DETERMINISTIC (particles: their state moves with the
//                      ticks before /tick freeze and the stepped ones);
//   SURFACE_HAND       no shadow lookup and its held light at half a block: Iris squeezes the
//                      hand's depth (MC_HAND_DEPTH), so deferred cannot rebuild its position,
//                      and LIGHT_PATH 0 does the same;
//   SURFACE_OVERLAYS   drawn after terrain (entities, block entities, particles, the hand), so it
//                      writes the overlays' neutral values (D76, OVERLAYS): an overlay drawn earlier
//                      behind it is not laid over it;
//   SURFACE_GLINT      off BENCH_DETERMINISTIC the item's own glint, mc_sampleGlint() (Iris's,
//                      on its wall-clock matrix: P19), into emit; under it never called (D79);
//   SURFACE_MATERIAL   the G-buffer's material (program/targets.glsl).

#include "/lib/options.glsl"
#include "/lib/srgb.glsl"
#include "/lib/normals.glsl"
#include "/program/targets.glsl"

#if defined SURFACE_OVERLAYS && defined OVERLAYS
#define SURFACE_WRITES_OVERLAYS 1
#endif

in vec2 albedoCoord;
in vec4 tint;
in vec2 levels;
in vec3 worldNormal;
in vec3 fromCamera;
#if defined SURFACE_TERRAIN && defined FOLIAGE_TRANSLUCENCY
in float foliage;
#endif

uniform sampler2D gtexture;
#ifndef SURFACE_SOLID
// Iris's cutoff for this draw: 0 when none, else 1e-4, 0.1 or 0.5; core programs get none
// injected, so the pack applies it on the texture's alpha as vanilla does. Entity-alpha draws
// carry a sentinel above 1, which the pack ignores: they draw whole.
uniform float alphaTestRef;
#endif
#if defined SURFACE_ENTITY && defined BENCH_DETERMINISTIC
uniform int entityId;
const int END_CRYSTAL = 1;
#endif

#if LIGHT_PATH == 1
#include "/lib/gbuffer.glsl"
#ifdef SURFACE_WRITES_OVERLAYS
/* RENDERTARGETS: 1,3,4,5 */
#else
/* RENDERTARGETS: 1 */
#endif
layout(location = 0) out uvec4 gbufferOut;
#else
#include "/program/scene.glsl"
#if !defined DIMENSION_NETHER && SHADOWS == 1
#include "/program/shadowing.glsl"
#endif
#ifdef SURFACE_WRITES_OVERLAYS
/* RENDERTARGETS: 2,3,4,5 */
#else
/* RENDERTARGETS: 2 */
#endif
layout(location = 0) out vec4 litOut;
#endif
#ifdef SURFACE_WRITES_OVERLAYS
layout(location = 1) out vec4 modOut;
layout(location = 2) out vec4 emitOut;
layout(location = 3) out vec4 transOut;
#endif

void main() {
#if defined SURFACE_NOT_IN_BENCH && defined BENCH_DETERMINISTIC
    discard;
#endif
#if defined SURFACE_ENTITY && defined BENCH_DETERMINISTIC
    if (entityId == END_CRYSTAL) discard;
#endif
    vec4 texel = texture(gtexture, albedoCoord);
#ifndef SURFACE_SOLID
    if (texel.a < alphaTestRef && alphaTestRef <= 1.0) discard;
#endif
    // sRGB-encoded, as the texture: the G-buffer keeps its 8 bits, deferred linearizes it.
    vec3 albedo = texel.rgb * tint.rgb;
#ifdef SURFACE_TERRAIN
    float ao = tint.a;
#else
    float ao = 1.0;
#endif
#if defined SURFACE_TERRAIN && defined FOLIAGE_TRANSLUCENCY
    bool isFoliage = foliage > 0.5;
#else
    bool isFoliage = false;
#endif
    vec3 normal = normalize(worldNormal);
    if (!gl_FrontFacing) normal = -normal;
#if LIGHT_PATH == 1
    float material = isFoliage ? MATERIAL_FOLIAGE : SURFACE_MATERIAL;
    gbufferOut = gbufferEncode(albedo, normalCodes(normal), levels, ao, material);
#else
#ifdef SURFACE_HAND
    vec2 lit = sceneLevels(levels, 0.5);
#else
    vec2 lit = sceneLevels(levels, length(fromCamera));
#endif
#if defined DIMENSION_NETHER || defined SURFACE_HAND || SHADOWS == 0
    float shadow = 1.0;
#else
    float shadow = shadowAt(fromCamera, normal);
#endif
    litOut = vec4(shadeSurface(linearFromSrgb(albedo), normal, lit, ao, shadow, isFoliage,
                               -normalize(fromCamera), ROUGHNESS_OPAQUE), 1.0);
#endif
#ifdef SURFACE_WRITES_OVERLAYS
    modOut = MOD_NEUTRAL;
    emitOut = EMIT_NEUTRAL;
    transOut = TRANS_NEUTRAL;
#if defined SURFACE_GLINT && !defined BENCH_DETERMINISTIC
    emitOut = vec4(linearFromSrgb(mc_sampleGlint()), 0.0);
#endif
#endif
}
