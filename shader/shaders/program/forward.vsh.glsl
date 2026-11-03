// The vertex stage of the forward programs (program/forward.fsh.glsl): every program drawn with a
// blend or after deferred, and the roots Iris falls back to (basic, textured, textured_lit).
// Switches: FORWARD_TEXTURE (the albedo texture is drawn; off BENCH_DETERMINISTIC through the
// texture matrix, which scrolls the glint by the wall clock: 26.3's TextureTransform), FORWARD_LIT
// (lit from vaUV2's levels), FORWARD_NORMAL (the vertex normal; else the face looks at the camera).

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
uniform mat4 textureMatrix;
#endif
#endif

#ifdef FORWARD_LIT
in ivec2 vaUV2;
out vec2 levels;
#ifdef FORWARD_NORMAL
in vec3 vaNormal;
uniform mat3 normalMatrix;
out vec3 worldNormal;
#endif
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
#ifdef FORWARD_NORMAL
    worldNormal = mat3(gbufferModelViewInverse) * (normalMatrix * vaNormal);
#endif
#endif
}
