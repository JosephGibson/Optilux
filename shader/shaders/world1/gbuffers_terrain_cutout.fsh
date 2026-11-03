#version 330 core
// gbuffers_terrain_cutout in the End: Sodium's cutout terrain into the G-buffer, alpha-tested; foliage its own material.
#define DIMENSION_END 1
#define SURFACE_TERRAIN 1
#define SURFACE_MATERIAL MATERIAL_TERRAIN
#include "/program/surface.fsh.glsl"
