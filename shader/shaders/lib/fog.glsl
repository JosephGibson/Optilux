// Vanilla's two fogs (26.3's FogRenderer), rebuilt from the uniforms Iris exposes. The
// environment's fog runs over the straight-line distance from fogStart to fogEnd (the dimension,
// the weather, water and lava set them). The edge fog hides the end of the render distance: it
// runs over the larger of the horizontal and the vertical distance and ends at `far`, after a
// band a tenth of `far` wide, kept between 4 and 64 blocks. A fragment takes the denser of the two.
// Under BENCH_DETERMINISTIC only the edge fog is drawn: 26.3 eases fogStart and fogEnd by each
// frame's wall-clock length, under /tick freeze too (AtmosphericFogEnvironment's rain fog
// multiplier; the water fog's end follows the player's water vision), so neither is read.

#ifndef OPTILUX_FOG
#define OPTILUX_FOG 1

#include "/lib/options.glsl"

uniform vec3 fogColor;
uniform float far;

#ifndef BENCH_DETERMINISTIC
uniform float fogStart;
uniform float fogEnd;
#endif

// The two distances, from a position relative to the camera: x for the environment, y for the edge.
vec2 fogDistances(vec3 fromCamera) {
    float horizontal = length(fromCamera.xz);
    return vec2(length(fromCamera), max(horizontal, abs(fromCamera.y)));
}

// None up to `near`, all from `full` on, a straight ramp between; a reversed range is a step.
float fogRamp(float dist, float near, float full) {
    if (dist <= near) return 0.0;
    if (dist >= full) return 1.0;
    return (dist - near) / (full - near);
}

vec3 withFog(vec3 color, vec2 distances) {
    float band = clamp(far * 0.1, 4.0, 64.0);
    float amount = fogRamp(distances.y, far - band, far);
#ifndef BENCH_DETERMINISTIC
    amount = max(amount, fogRamp(distances.x, fogStart, fogEnd));
#endif
    return mix(color, fogColor, amount);
}

#endif
