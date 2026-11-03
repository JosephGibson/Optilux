#version 330 core
// gbuffers_weather in the Nether: rain and snow, lit forward, nothing under BENCH_DETERMINISTIC.
#define DIMENSION_NETHER 1
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NOT_IN_BENCH 1
#include "/program/forward.fsh.glsl"
