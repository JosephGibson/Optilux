#version 330 core
// gbuffers_textured: the albedo texture times the vertex colour, with vanilla's fog: the sun and moon,
// the beacon beam, the separate glint draw and the spider eyes fall back to it (the glint
// drawn with an entity or the hand needs mc_sampleGlint, which the pack does not call).
#define SURFACE_TEXTURE 1
#include "/lib/surface_fragment.glsl"
