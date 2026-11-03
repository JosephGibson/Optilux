#version 330 core
// gbuffers_terrain_cutout in the overworld: Sodium's cutout terrain into the G-buffer, alpha-tested.
#define SURFACE_TERRAIN 1
#define SURFACE_MATERIAL MATERIAL_TERRAIN
#include "/program/surface.fsh.glsl"
