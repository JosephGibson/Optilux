// The lighting core (docs/research/lighting.md#first-version-m4): one surface lit by the sun or
// moon through its shadow term, by the sky in proportion to how open it is, by block light and by
// the floor light every surface keeps. Deferred calls it once per pixel on the decoded G-buffer;
// LIGHT_PATH 0 calls it in each opaque program on the values it would have stored. Everything is
// passed in, so the same function serves both paths and any backend.
//   albedo: linear reflectance; normal: world-space unit normal; levels: block and sky level in
//   [0, 1] (lib/curves.glsl); ao: vanilla's ambient occlusion, 1 for none; shadow: 1 lit to 0
//   shadowed; toLight: world-space unit vector toward the sun or moon; the colours: each light's
//   radiance at full strength.
// Direct light reaches only where the sky does: past the shadow map a cave's shadow term is 1,
// so the sky level (open sky at 0.6 and above) gates it. The sky's light comes mostly from above:
// a face looking down keeps 45 % of it.

#ifndef OPTILUX_LIGHTING
#define OPTILUX_LIGHTING 1

#include "/lib/curves.glsl"

float skyAccess(float skyLevel) {
    return smoothstep(0.2, 0.6, skyLevel);
}

vec3 surfaceRadiance(vec3 albedo, vec3 normal, vec2 levels, float ao, float shadow, vec3 toLight,
                     vec3 lightColor, vec3 skyColor, vec3 blockColor, vec3 floorColor) {
    float facing = max(dot(normal, toLight), 0.0);
    vec3 direct = lightColor * (facing * shadow * skyAccess(levels.y));
    float upward = mix(0.45, 1.0, normal.y * 0.5 + 0.5);
    vec3 ambient = skyColor * (skyLight(levels.y) * upward) + blockColor * blockLight(levels.x);
    return albedo * (direct + (ambient + floorColor) * ao);
}

#endif
