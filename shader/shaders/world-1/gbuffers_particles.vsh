#version 330 core
// gbuffers_particles in the Nether: opaque particles into the G-buffer, the overlays reset; nothing under BENCH_DETERMINISTIC.
#define DIMENSION_NETHER 1
#define SURFACE_PARTICLE 1
#include "/program/surface.vsh.glsl"
