#version 330 core
// gbuffers_weather in the overworld: rain and snow lit forward, facing the camera; nothing under BENCH_DETERMINISTIC.
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#include "/program/forward.vsh.glsl"
