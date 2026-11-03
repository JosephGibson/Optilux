// The shadow pass's vertex stage (plans/m4.md D77): Iris's shadow matrices put the caster on its
// orthographic map, then the radial distortion (lib/shadow.glsl) moves it as the lookup expects.
// Switch: SHADOW_TEXTURED (the alpha-tested programs read the texture).

#include "/lib/shadow.glsl"

in vec3 vaPosition;

uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform vec3 chunkOffset;

#ifdef SHADOW_TEXTURED
in vec2 vaUV0;
out vec2 albedoCoord;
#endif

void main() {
    vec4 clip = projectionMatrix * (modelViewMatrix * vec4(vaPosition + chunkOffset, 1.0));
    clip.xy = shadowDistort(clip.xy / clip.w) * clip.w;
    gl_Position = clip;
#ifdef SHADOW_TEXTURED
    albedoCoord = vaUV0;
#endif
}
