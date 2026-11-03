// The shadow pass's fragment stage: depth only (an empty DRAWBUFFERS gives no colour target, P20).
// shadow_solid tests nothing, so it never discards; shadow_cutout and the root (entities, block
// entities, translucents, which Low reads no colour of) test the texture's alpha at Iris's cutoff.
// Under BENCH_DETERMINISTIC the root hides the end crystals, as gbuffers_entities does.
// Switches: SHADOW_TEXTURED (the alpha test), SHADOW_ENTITIES (the end crystals).

#include "/lib/options.glsl"

#ifdef SHADOW_TEXTURED
in vec2 albedoCoord;
uniform sampler2D gtexture;
uniform float alphaTestRef;
#endif
#if defined SHADOW_ENTITIES && defined BENCH_DETERMINISTIC
uniform int entityId;
const int END_CRYSTAL = 1;
#endif

/* DRAWBUFFERS: */

void main() {
#if defined SHADOW_ENTITIES && defined BENCH_DETERMINISTIC
    if (entityId == END_CRYSTAL) discard;
#endif
#ifdef SHADOW_TEXTURED
    if (texture(gtexture, albedoCoord).a < alphaTestRef && alphaTestRef <= 1.0) discard;
#endif
}
