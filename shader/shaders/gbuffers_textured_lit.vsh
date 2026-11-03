#version 330 core
// gbuffers_textured_lit in the overworld: texture x vertex colour, lit forward: water and translucent terrain fall back to it.
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#include "/program/forward.vsh.glsl"
