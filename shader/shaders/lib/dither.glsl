// The display dither: a fixed triangular noise of at most one 8-bit step before the screen's RGBA8
// quantizes (docs/research/tonemap.md#t5-output-encoding-and-dither). Interleaved gradient noise
// (Jimenez 2014) at two pixel offsets, summed, is triangular in (-1, 1); it depends on the pixel
// alone, so every frame takes the same pattern (cycle 1). Its amplitude fades to 0 within one step
// of 0 and of 1, so black stays black and white stays white.

#ifndef OPTILUX_DITHER
#define OPTILUX_DITHER 1

float gradientNoise(vec2 pixel) {
    return fract(52.9829189 * fract(dot(pixel, vec2(0.06711056, 0.00583715))));
}

// A display value in [0, 1] moved by the pixel's noise, at most one step of `steps` (255).
vec3 ditherDisplay(vec3 display, vec2 pixel, float steps) {
    float noise = gradientNoise(pixel) + gradientNoise(pixel + vec2(47.0, 17.0)) - 1.0;
    vec3 room = min(display, 1.0 - display) * steps;
    return display + noise * clamp(room, 0.0, 1.0) / steps;
}

#endif
