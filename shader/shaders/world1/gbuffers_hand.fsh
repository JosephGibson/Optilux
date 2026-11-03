#version 330 core
// gbuffers_hand in the End: the held items into the G-buffer, alpha-tested, unshadowed, the overlays reset, the glint off BENCH_DETERMINISTIC.
#define DIMENSION_END 1
#define SURFACE_HAND 1
#define SURFACE_OVERLAYS 1
#define SURFACE_GLINT 1
#define SURFACE_MATERIAL MATERIAL_HAND
#include "/program/surface.fsh.glsl"
