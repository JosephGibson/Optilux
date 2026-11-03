#version 330 core
// gbuffers_weather: rain and snow: nothing under BENCH_DETERMINISTIC; else as gbuffers_textured_lit.
#define SURFACE_TEXTURE 1
#define SURFACE_LIGHT 1
#define SURFACE_NOT_IN_BENCH 1
#include "/lib/surface_fragment.glsl"
