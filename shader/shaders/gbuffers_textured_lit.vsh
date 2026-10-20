#version 330 core
// gbuffers_textured_lit: texture times vertex colour times the lightmap's light, with vanilla's fog: terrain,
// water, entities, block entities, items and the hand fall back to it. Under BENCH_DETERMINISTIC
// it hides the end crystals.
#define SURFACE_TEXTURE 1
#define SURFACE_LIGHT 1
#include "/lib/surface_vertex.glsl"
