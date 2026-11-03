#version 330 core
// gbuffers_terrain_solid in the End: Sodium's solid terrain into the G-buffer, no alpha test and no discard; foliage its own material.
#define DIMENSION_END 1
#define SURFACE_SOLID 1
#define SURFACE_TERRAIN 1
#define SURFACE_MATERIAL MATERIAL_TERRAIN
#include "/program/surface.fsh.glsl"
