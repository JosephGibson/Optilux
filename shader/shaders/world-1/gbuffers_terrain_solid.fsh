#version 330 core
// gbuffers_terrain_solid in the Nether: Sodium's solid terrain into the G-buffer, no alpha test and no discard.
#define DIMENSION_NETHER 1
#define SURFACE_SOLID 1
#define SURFACE_TERRAIN 1
#define SURFACE_MATERIAL MATERIAL_TERRAIN
#include "/program/surface.fsh.glsl"
