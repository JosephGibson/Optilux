#version 330 core
// gbuffers_hand_water in the Nether: the translucent held items lit forward, unshadowed, vanilla's blend; the glint off BENCH_DETERMINISTIC.
#define DIMENSION_NETHER 1
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NORMAL 1
#define FORWARD_HAND 1
#define FORWARD_GLINT 1
#include "/program/forward.fsh.glsl"
