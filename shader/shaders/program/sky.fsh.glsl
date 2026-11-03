// The fragment stage of the sky's two programs (program/sky.vsh.glsl): skytextured's sprite in
// linear light, the sun brighter than the moon, into the early target with the draw's own blend
// (Iris clears that target to 0 each frame). skybasic's never runs.

#include "/lib/srgb.glsl"

#ifndef SKY_NONE
in vec4 vertexColor;
in vec2 albedoCoord;
uniform sampler2D gtexture;
uniform int renderStage;
#endif

/* RENDERTARGETS: 2 */
layout(location = 0) out vec4 skyOut;

void main() {
#ifdef SKY_NONE
    skyOut = vec4(0.0);
#else
    vec4 color = texture(gtexture, albedoCoord) * vertexColor;
    float strength = renderStage == MC_RENDER_STAGE_SUN ? 4.0 : 1.0;
    skyOut = vec4(linearFromSrgb(color.rgb) * strength, color.a);
#endif
}
