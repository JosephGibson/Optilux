#version 330 core
// gbuffers_entities in the End: entities into the G-buffer, alpha-tested, the overlays reset, the glint off BENCH_DETERMINISTIC; the end crystals hidden under it.
#define DIMENSION_END 1
#define SURFACE_ENTITY 1
#define SURFACE_OVERLAYS 1
#define SURFACE_GLINT 1
#define SURFACE_MATERIAL MATERIAL_ENTITY
#include "/program/surface.fsh.glsl"
