// The gradient sky (plans/m4.md D78; docs/research/sky.md#t5-fitted-gradient-the-low-level) and
// the light the sky and the sun give, all from where the sun stands and how hard it rains.
// `sunHeight` is the sun direction's up component (-1 to 1); a direction is a world-space unit
// vector. Day and night blend as the sun crosses the horizon; a warm glow gathers around the sun
// while it is low; rain greys the sky and dims the sun. Radiance is in the scene's linear units
// (lib/lighting.glsl), exposed later by the composite.

#ifndef OPTILUX_SKY
#define OPTILUX_SKY 1

const vec3 ZENITH_DAY = vec3(0.16, 0.32, 0.78);
const vec3 HORIZON_DAY = vec3(0.55, 0.68, 0.9);
const vec3 ZENITH_NIGHT = vec3(0.004, 0.006, 0.014);
const vec3 HORIZON_NIGHT = vec3(0.01, 0.013, 0.022);
const vec3 GLOW = vec3(1.0, 0.42, 0.13);
const vec3 SUN_DAY = vec3(2.6, 2.45, 2.2);
const vec3 SUN_LOW = vec3(1.6, 0.85, 0.42);
const vec3 MOON = vec3(0.045, 0.055, 0.08);

// 0 at night, 1 by day, a smooth step across the horizon.
float daylight(float sunHeight) {
    return smoothstep(-0.12, 0.18, sunHeight);
}

// 1 while the sun is near the horizon, 0 when it is high or deep below.
float twilight(float sunHeight) {
    return clamp(1.0 - abs(sunHeight + 0.02) * 5.0, 0.0, 1.0);
}

vec3 rainy(vec3 color, float rain, float keep) {
    float grey = dot(color, vec3(0.2126, 0.7152, 0.0722));
    return mix(color, vec3(grey * keep), rain);
}

// The sky's radiance seen along `direction`; below the horizon it keeps the horizon's colour.
vec3 skyRadiance(vec3 direction, vec3 sunDirection, float rain) {
    float day = daylight(sunDirection.y);
    float horizon = 1.0 - max(direction.y, 0.0);
    horizon *= horizon * horizon;
    vec3 zenith = mix(ZENITH_NIGHT, ZENITH_DAY, day);
    vec3 low = mix(HORIZON_NIGHT, HORIZON_DAY, day);
    vec3 sky = mix(zenith, low, horizon);
    float facing = max(dot(direction, sunDirection), 0.0);
    sky += GLOW * (twilight(sunDirection.y) * horizon * facing * facing * facing * 0.9);
    return rainy(sky, rain, 0.6);
}

// The directional light: the sun by day, the moon by night (Iris's shadow light follows the same
// switch), dimmed by rain.
vec3 sunLight(float sunHeight, float rain) {
    float day = daylight(sunHeight);
    vec3 sun = mix(SUN_LOW, SUN_DAY, smoothstep(0.0, 0.4, sunHeight));
    vec3 light = mix(MOON, sun, day);
    return light * (1.0 - 0.75 * rain);
}

// The sky's light on an upward face under open sky: the sky's mean over the upper hemisphere,
// taken as its colour halfway between zenith and horizon.
vec3 skyLightColor(float sunHeight, float rain) {
    float day = daylight(sunHeight);
    vec3 sky = mix(mix(ZENITH_NIGHT, ZENITH_DAY, day), mix(HORIZON_NIGHT, HORIZON_DAY, day), 0.5);
    return rainy(sky, rain, 0.5);
}

#endif
