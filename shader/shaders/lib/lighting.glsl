// The lighting core (docs/research/lighting.md#first-version-m4): one surface lit by the sun or
// moon through its shadow term, by the sky in proportion to how open it is, by block light and by
// the floor light every surface keeps, with the sun's highlight on top. Deferred calls it once per
// pixel on the decoded G-buffer; LIGHT_PATH 0 calls it in each opaque program on the values it
// would have stored, and the forward programs on their own fragments. Everything is passed in, so
// the same functions serve every path and any backend.
//   albedo: linear reflectance; normal: world-space unit normal; levels: block and sky level in
//   [0, 1] (lib/curves.glsl); ao: vanilla's ambient occlusion, 1 for none; shadow: 1 lit to 0
//   shadowed; toLight: world-space unit vector toward the sun or moon; toEye: unit vector from the
//   surface toward the camera; the colours: each light's radiance at full strength.
// Direct light reaches only where the sky does: past the shadow map a cave's shadow term is 1,
// so the sky level (open sky at 0.6 and above) gates it. The sky's light comes mostly from above:
// a face looking down keeps 45 % of it.

#ifndef OPTILUX_LIGHTING
#define OPTILUX_LIGHTING 1

#include "/lib/curves.glsl"

#define PI 3.14159265

float skyAccess(float skyLevel) {
    return smoothstep(0.2, 0.6, skyLevel);
}

// The light falling on a surface, before its albedo: `facing` is how squarely the direct light
// meets it (N.L for a plain surface), `up` the normal's upward component.
vec3 surfaceLight(float facing, float up, vec2 levels, float ao, float shadow, vec3 lightColor,
                  vec3 skyColor, vec3 blockColor, vec3 floorColor) {
    vec3 direct = lightColor * (facing * shadow * skyAccess(levels.y));
    float upward = mix(0.45, 1.0, up * 0.5 + 0.5);
    vec3 ambient = skyColor * (skyLight(levels.y) * upward) + blockColor * blockLight(levels.x);
    return direct + (ambient + floorColor) * ao;
}

vec3 surfaceRadiance(vec3 albedo, vec3 normal, vec2 levels, float ao, float shadow, vec3 toLight,
                     vec3 lightColor, vec3 skyColor, vec3 blockColor, vec3 floorColor) {
    float facing = max(dot(normal, toLight), 0.0);
    return albedo * surfaceLight(facing, normal.y, levels, ao, shadow, lightColor, skyColor,
                                 blockColor, floorColor);
}

// A leaf's or plant's facing: N.L wrapped half way round its back, so the side turned away still
// takes some light, plus what passes through it toward an eye looking at the light from behind.
float foliageFacing(vec3 normal, vec3 toLight, vec3 toEye) {
    float facing = dot(normal, toLight);
    float wrapped = clamp((facing + 0.5) * (1.0 / 1.5), 0.0, 1.0);
    float through = max(-dot(toEye, toLight), 0.0);
    through *= through;
    through *= through;
    return wrapped + 0.4 * through * (1.0 - max(facing, 0.0));
}

// The sun's highlight per unit of its radiance: GGX's distribution at `roughness` (perceptual,
// squared into alpha), Schlick's Fresnel from `f0` and the Schlick-GGX visibility, times N.L; 0
// where the light or the eye is behind the face.
float sunSpecular(vec3 normal, vec3 toLight, vec3 toEye, float roughness, float f0) {
    float nl = dot(normal, toLight);
    float nv = dot(normal, toEye);
    if (nl <= 0.0 || nv <= 0.0) return 0.0;
    vec3 halfway = normalize(toLight + toEye);
    float nh = max(dot(normal, halfway), 0.0);
    float vh = max(dot(toEye, halfway), 0.0);
    float alpha = roughness * roughness;
    float alpha2 = alpha * alpha;
    float spread = nh * nh * (alpha2 - 1.0) + 1.0;
    float distribution = alpha2 / (PI * spread * spread);
    float edge = 1.0 - vh;
    float edge2 = edge * edge;
    float fresnel = f0 + (1.0 - f0) * edge2 * edge2 * edge;
    float k = alpha * 0.5;
    float visibility = 1.0 / ((nl * (1.0 - k) + k) * (nv * (1.0 - k) + k) * 4.0);
    return distribution * fresnel * visibility * nl;
}

#endif
