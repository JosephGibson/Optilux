#version 330 core
// gbuffers_block in the End: block entities into the G-buffer, alpha-tested, the overlays reset.
#define DIMENSION_END 1
#define SURFACE_OVERLAYS 1
#define SURFACE_MATERIAL MATERIAL_BLOCK
#include "/program/surface.fsh.glsl"
