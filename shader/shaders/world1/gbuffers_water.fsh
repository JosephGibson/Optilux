#version 330 core
// gbuffers_water in the End: translucent terrain (water, glass, ice) lit forward with its normal and the sharper highlight, vanilla's blend.
#define DIMENSION_END 1
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NORMAL 1
#define FORWARD_TERRAIN 1
#define FORWARD_SMOOTH 1
#include "/program/forward.fsh.glsl"
