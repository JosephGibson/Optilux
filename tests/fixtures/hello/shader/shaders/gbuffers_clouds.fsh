#version 330 core
// gbuffers_clouds: nothing under BENCH_DETERMINISTIC (clouds drift with the game time, which no command
// sets); else their vertex colour (26.3's clouds have no texture), as gbuffers_basic.
#define SURFACE_NOT_IN_BENCH 1
#include "/lib/surface_fragment.glsl"
