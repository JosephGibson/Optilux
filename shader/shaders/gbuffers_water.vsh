#version 330 core
// gbuffers_water in the overworld: translucent terrain (water, glass, ice) lit forward with its normal and the sharper highlight, vanilla's blend.
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NORMAL 1
#include "/program/forward.vsh.glsl"
