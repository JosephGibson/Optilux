// Block light's flicker (BLOCK_FLICKER; docs/research/lighting.md#block-light-flicker): one value
// per frame, the block light's multiplier, so shaders.properties computes it as the custom uniform
// blockFlicker and no program includes this file: it is the GLSL that uniform replaces, which
// tests/l3/uniforms.py holds it to. Two sines whose periods (0.6 s and 1.8 s) divide 3600 s, so the
// flicker runs on across frameTimeCounter's wrap at 3600 s; their weights sum to 1, so the value
// stays within `amplitude` of 1, its mean and its rest: at clock 0, which BENCH_DETERMINISTIC holds.

#ifndef OPTILUX_FLICKER
#define OPTILUX_FLICKER 1

#define FLICKER_FAST 10.4719755
#define FLICKER_SLOW 3.49065850

float flickerFactor(float clock, float amplitude) {
    return 1.0 + amplitude * (0.6 * sin(clock * FLICKER_FAST) + 0.4 * sin(clock * FLICKER_SLOW));
}

#endif
