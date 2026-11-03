#version 330 core
// gbuffers_particles in the End: opaque particles into the G-buffer, nothing under BENCH_DETERMINISTIC.
#define DIMENSION_END 1
#define SURFACE_NOT_IN_BENCH 1
#define SURFACE_MATERIAL MATERIAL_PARTICLE
#include "/program/surface.fsh.glsl"
