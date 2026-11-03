#version 330 core
// gbuffers_block in the overworld: block entities into the G-buffer, alpha-tested, the overlays reset.
#define SURFACE_OVERLAYS 1
#define SURFACE_MATERIAL MATERIAL_BLOCK
#include "/program/surface.fsh.glsl"
