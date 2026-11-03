#version 330 core
// gbuffers_lightning in the overworld: lightning and the dragon's death beams, emissive and added; nothing under BENCH_DETERMINISTIC.
#define FORWARD_EMISSIVE 1
#define FORWARD_ADDITIVE 1
#define FORWARD_NOT_IN_BENCH 1
#include "/program/forward.fsh.glsl"
