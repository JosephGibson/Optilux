// The vertex stage of the forward programs: the roots Iris falls back to (basic, textured,
// textured_lit) and the ones drawn only off BENCH_DETERMINISTIC (clouds, weather, lightning).
// Switches: FORWARD_TEXTURE (the albedo texture is drawn), FORWARD_LIT (lit from vaUV2's levels).

#include "/lib/options.glsl"
#include "/lib/curves.glsl"

in vec3 vaPosition;
in vec4 vaColor;

uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform vec3 chunkOffset;
uniform mat4 gbufferModelViewInverse;

out vec4 vertexColor;
out vec3 fromCamera;

#ifdef FORWARD_TEXTURE
in vec2 vaUV0;
out vec2 albedoCoord;
#ifndef BENCH_DETERMINISTIC
// The texture matrix scrolls the enchantment glint by the wall clock (26.3's TextureTransform).
uniform mat4 textureMatrix;
#endif
#endif

#ifdef FORWARD_LIT
in ivec2 vaUV2;
out vec2 levels;
#endif

void main() {
    vec4 view = modelViewMatrix * vec4(vaPosition + chunkOffset, 1.0);
    gl_Position = projectionMatrix * view;
    fromCamera = (gbufferModelViewInverse * view).xyz;
    vertexColor = vaColor;
#ifdef FORWARD_TEXTURE
#ifdef BENCH_DETERMINISTIC
    albedoCoord = vaUV0;
#else
    albedoCoord = (textureMatrix * vec4(vaUV0, 0.0, 1.0)).xy;
#endif
#endif
#ifdef FORWARD_LIT
    levels = vec2(lightLevel(float(vaUV2.x)), lightLevel(float(vaUV2.y)));
#endif
}
