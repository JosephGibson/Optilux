#version 330 core
// gbuffers_weather in the overworld: rain and snow lit forward, facing the camera; not drawn under BENCH_DETERMINISTIC (shaders.properties: weather).
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#include "/program/forward.vsh.glsl"
