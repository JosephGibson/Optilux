// The scene's lights and sky from Iris's uniforms, per dimension: the root's programs are the
// overworld's, world-1's wrappers define DIMENSION_NETHER and world1's DIMENSION_END (Iris has no
// dimension macro). The overworld's come from lib/sky.glsl; the Nether has no sun and no sky light
// (sceneLevels): its sky is its fog colour, its ambient lights every surface; the End has a fixed dim light along Iris's shadow light, and the End
// flash brightens its ambient. Held light (HELD_LIGHT: heldBlockLightValue, each hand its own:
// oldHandLight is off) falls off one level a block from the camera and joins block light by the
// larger; block light takes the flicker's multiplier (BLOCK_FLICKER: shaders.properties'
// blockFlicker, at rest under BENCH_DETERMINISTIC). shadeSurface is the one shading every path
// calls: deferred per pixel, the opaque programs under LIGHT_PATH 0 and the forward programs.

#ifndef OPTILUX_SCENE
#define OPTILUX_SCENE 1

#include "/lib/options.glsl"
#include "/lib/srgb.glsl"
#include "/lib/sky.glsl"
#include "/lib/lighting.glsl"

uniform mat4 gbufferModelViewInverse;
uniform vec3 shadowLightPosition;
#ifdef HELD_LIGHT
uniform int heldBlockLightValue;
uniform int heldBlockLightValue2;
#endif
#if BLOCK_FLICKER > 0
uniform float blockFlicker;
#endif
#if defined DIMENSION_NETHER
uniform vec3 fogColor;
#elif defined DIMENSION_END
uniform float endFlashIntensity;
#else
uniform vec3 sunPosition;
uniform float rainStrength;
#endif

const vec3 BLOCK_COLOR = vec3(1.6, 1.12, 0.66);
const vec3 FLOOR_COLOR = vec3(0.01, 0.01, 0.012);
const vec3 NETHER_AMBIENT = vec3(0.3, 0.17, 0.12);
const vec3 END_LIGHT = vec3(0.32, 0.28, 0.42);
const vec3 END_AMBIENT = vec3(0.07, 0.06, 0.09);
const vec3 END_SKY = vec3(0.004, 0.002, 0.006);
const vec3 END_FLASH = vec3(0.5, 0.25, 0.8);
// The sun's highlight: a dielectric's reflectance head-on, at a roughness per surface kind (no
// material map until M5: docs/shader.md#look-and-scope).
const float SPECULAR_F0 = 0.04;
const float ROUGHNESS_OPAQUE = 0.7;
const float ROUGHNESS_TRANSLUCENT = 0.15;

// A view-space vector Iris gives (shadowLightPosition, sunPosition) as a world-space unit vector.
vec3 worldDirection(vec3 viewVector) {
    return normalize(mat3(gbufferModelViewInverse) * viewVector);
}

vec3 toSceneLight() {
    return worldDirection(shadowLightPosition);
}

vec3 sceneLightColor() {
#if defined DIMENSION_NETHER
    return vec3(0.0);
#elif defined DIMENSION_END
    return END_LIGHT;
#else
    return sunLight(worldDirection(sunPosition).y, rainStrength);
#endif
}

vec3 sceneSkyColor() {
#if defined DIMENSION_NETHER
    return NETHER_AMBIENT;
#elif defined DIMENSION_END
    return END_AMBIENT + END_FLASH * endFlashIntensity;
#else
    return skyLightColor(worldDirection(sunPosition).y, rainStrength);
#endif
}

// The sky behind a world-space view direction; also the colour the edge fog fades into.
vec3 sceneSky(vec3 direction) {
#if defined DIMENSION_NETHER
    return linearFromSrgb(fogColor);
#elif defined DIMENSION_END
    return END_SKY;
#else
    return skyRadiance(direction, worldDirection(sunPosition), rainStrength);
#endif
}

vec3 sceneBlockColor() {
#if BLOCK_FLICKER > 0
    return BLOCK_COLOR * blockFlicker;
#else
    return BLOCK_COLOR;
#endif
}

#ifdef HELD_LIGHT
// The held items' light at `distance` blocks from the camera, as a level in [0, 1].
float heldLevel(float distance) {
    float held = float(max(heldBlockLightValue, heldBlockLightValue2));
    return clamp((held - distance) / 15.0, 0.0, 1.0);
}
#endif

// The levels a surface is lit with, `distance` blocks from the camera: block light raised to the
// held light; in the Nether, which has no sky light (26.3's the_nether: has_skylight false), the
// sky level taken as full, so its ambient reaches every surface.
vec2 sceneLevels(vec2 levels, float distance) {
#ifdef HELD_LIGHT
    float block = max(levels.x, heldLevel(distance));
#else
    float block = levels.x;
#endif
#ifdef DIMENSION_NETHER
    return vec2(block, 1.0);
#else
    return vec2(block, levels.y);
#endif
}

// One surface lit (lib/lighting.glsl): its linear albedo, world-space unit normal, levels (after
// sceneLevels), AO and shadow term; `foliage` takes FOLIAGE_TRANSLUCENCY's facing; `toEye` the unit
// vector toward the camera; `roughness` the sun's highlight (SUN_SPECULAR), skipped where no direct
// light arrives and in the Nether, which has none.
vec3 shadeSurface(vec3 albedo, vec3 normal, vec2 levels, float ao, float shadow, bool foliage,
                  vec3 toEye, float roughness) {
    vec3 toLight = toSceneLight();
    vec3 lightColor = sceneLightColor();
    float facing = max(dot(normal, toLight), 0.0);
#ifdef FOLIAGE_TRANSLUCENCY
    if (foliage) facing = foliageFacing(normal, toLight, toEye);
#endif
    vec3 color = albedo * surfaceLight(facing, normal.y, levels, ao, shadow, lightColor,
                                       sceneSkyColor(), sceneBlockColor(), FLOOR_COLOR);
#ifdef SUN_SPECULAR
#ifndef DIMENSION_NETHER
    float direct = shadow * skyAccess(levels.y);
    if (direct > 0.0) {
        color += lightColor * (direct * sunSpecular(normal, toLight, toEye, roughness, SPECULAR_F0));
    }
#endif
#endif
    return color;
}

#endif
