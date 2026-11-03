#version 330 core
// gbuffers_terrain_solid in the overworld: Sodium's solid terrain into the G-buffer, no alpha test and no discard; foliage its own material.
#define SURFACE_TERRAIN 1
#include "/program/surface.vsh.glsl"
