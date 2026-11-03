#version 330 core
// gbuffers_particles in the Nether: opaque particles into the G-buffer, the overlays reset; nothing under BENCH_DETERMINISTIC.
#define DIMENSION_NETHER 1
#define SURFACE_NOT_IN_BENCH 1
#define SURFACE_OVERLAYS 1
#define SURFACE_MATERIAL MATERIAL_PARTICLE
#include "/program/surface.fsh.glsl"
