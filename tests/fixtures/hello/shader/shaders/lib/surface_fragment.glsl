// The fragment stage every gbuffers program of the pack shares: vertex colour, times the albedo
// texture (SURFACE_TEXTURE), times the light (SURFACE_LIGHT), then vanilla's fog, into colortex0.
// Under BENCH_DETERMINISTIC a program that sets SURFACE_NOT_IN_BENCH draws nothing (particles,
// weather, lightning, clouds), and one that sets SURFACE_HIDES_CRYSTALS hides the end crystals
// (docs/shader.md#determinism-and-taa).

#include "/lib/options.glsl"
#include "/lib/fog.glsl"

in vec4 vertexColor;
in vec2 fogDistance;

// Iris's cutoff for this draw: 0 when none, else 1e-4, 0.1 or 0.5. Core-profile programs get no
// cutoff injected (unlike #version 130 packs), so the pack applies it, on the texture's alpha as
// vanilla does. Entity-alpha draws (the ender dragon dissolving) carry a sentinel above 1, which
// the pack ignores: they draw whole.
uniform float alphaTestRef;

#ifdef SURFACE_TEXTURE
uniform sampler2D gtexture;
in vec2 albedoCoord;
#endif

#ifdef SURFACE_LIGHT
in vec3 light;
#endif

#ifdef SURFACE_HIDES_CRYSTALS
// An entity's id from entity.properties (Iris writes it into the entity's vertices); 0 or -1
// for anything else.
uniform int entityId;
const int END_CRYSTAL = 1;
#endif

/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 surfaceColor;

void main() {
#if defined SURFACE_NOT_IN_BENCH && defined BENCH_DETERMINISTIC
    // Their state moves with the ticks before /tick freeze and the ones the bench steps.
    discard;
#endif
#if defined SURFACE_HIDES_CRYSTALS && defined BENCH_DETERMINISTIC
    // An end crystal starts its spin at a random angle every launch (26.3's EndCrystal).
    if (entityId == END_CRYSTAL) discard;
#endif
    vec4 color = vertexColor;
    float coverage = vertexColor.a;
#ifdef SURFACE_TEXTURE
    vec4 albedo = texture(gtexture, albedoCoord);
    coverage = albedo.a;
    color *= albedo;
#endif
    if (coverage < alphaTestRef && alphaTestRef <= 1.0) discard;
#ifdef SURFACE_LIGHT
    color.rgb *= light;
#endif
    surfaceColor = vec4(withFog(color.rgb, fogDistance), color.a);
}
