#version 330 core
// gbuffers_terrain_cutout in the Nether: Sodium's cutout terrain into the G-buffer, alpha-tested.
#define DIMENSION_NETHER 1
#define SURFACE_TERRAIN 1
#define SURFACE_MATERIAL MATERIAL_TERRAIN
#include "/program/surface.fsh.glsl"
