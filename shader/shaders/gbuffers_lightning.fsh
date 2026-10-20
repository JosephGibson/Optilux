#version 330 core
// gbuffers_lightning: nothing under BENCH_DETERMINISTIC; else its vertex colour (lightning has no texture),
// as gbuffers_basic.
#define SURFACE_NOT_IN_BENCH 1
#include "/lib/surface_fragment.glsl"
