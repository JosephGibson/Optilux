// The vertex stage every gbuffers program of the pack shares. A program file sets its switches
// before including this: SURFACE_TEXTURE (the albedo texture is drawn) and SURFACE_LIGHT (the
// lightmap's light). Inputs are Iris's core-profile names (`#version 330 core`): Iris renames them
// to the vertex format's attributes, or to Sodium's for terrain (docs/shader.md#facts).

#include "/lib/options.glsl"
#include "/lib/fog.glsl"

in vec3 vaPosition;
in vec4 vaColor;

uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform vec3 chunkOffset;

out vec4 vertexColor;
out vec2 fogDistance;

#ifdef SURFACE_TEXTURE
in vec2 vaUV0;
out vec2 albedoCoord;
#ifndef BENCH_DETERMINISTIC
uniform mat4 textureMatrix;
#endif
#endif

#ifdef SURFACE_LIGHT
#include "/lib/light.glsl"
in ivec2 vaUV2;
out vec3 light;
#endif

void main() {
    // vaPosition plus chunkOffset is the vertex relative to the camera, in world axes.
    vec3 fromCamera = vaPosition + chunkOffset;
    gl_Position = projectionMatrix * (modelViewMatrix * vec4(fromCamera, 1.0));
    vertexColor = vaColor;
    fogDistance = fogDistances(fromCamera);
#ifdef SURFACE_TEXTURE
#ifdef BENCH_DETERMINISTIC
    // The texture matrix scrolls the enchantment glint by the wall clock (26.3's TextureTransform).
    albedoCoord = vaUV0;
#else
    albedoCoord = (textureMatrix * vec4(vaUV0, 0.0, 1.0)).xy;
#endif
#endif
#ifdef SURFACE_LIGHT
    light = surfaceLight(vec2(vaUV2));
#endif
}
