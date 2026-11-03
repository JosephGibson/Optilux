// The vertex stage of the opaque programs that fill the G-buffer (terrain_solid, terrain_cutout,
// entities, block, hand, particles). Inputs are Iris's core-profile names (`#version 330 core`):
// Iris renames them to the vertex format's attributes, or to Sodium's for terrain
// (docs/shader.md#facts). Switches: SURFACE_PARTICLE (no normal attribute: the face is taken to
// look at the camera).

#include "/lib/options.glsl"
#include "/lib/curves.glsl"

in vec3 vaPosition;
in vec4 vaColor;
in vec2 vaUV0;
in ivec2 vaUV2;
#ifndef SURFACE_PARTICLE
in vec3 vaNormal;
uniform mat3 normalMatrix;
#endif

uniform mat4 modelViewMatrix;
uniform mat4 projectionMatrix;
uniform vec3 chunkOffset;
uniform mat4 gbufferModelViewInverse;

out vec2 albedoCoord;
out vec4 tint;
out vec2 levels;
out vec3 worldNormal;
out vec3 fromCamera;

void main() {
    vec4 view = modelViewMatrix * vec4(vaPosition + chunkOffset, 1.0);
    gl_Position = projectionMatrix * view;
    // Relative to the camera in world axes (Iris's player space).
    fromCamera = (gbufferModelViewInverse * view).xyz;
    albedoCoord = vaUV0;
    tint = vaColor;
    levels = vec2(lightLevel(float(vaUV2.x)), lightLevel(float(vaUV2.y)));
#ifdef SURFACE_PARTICLE
    worldNormal = -fromCamera;
#else
    worldNormal = mat3(gbufferModelViewInverse) * (normalMatrix * vaNormal);
#endif
}
