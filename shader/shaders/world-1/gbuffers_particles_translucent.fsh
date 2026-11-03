#version 330 core
// gbuffers_particles_translucent in the Nether: translucent particles lit forward, facing the camera, vanilla's blend; nothing under BENCH_DETERMINISTIC.
#define DIMENSION_NETHER 1
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NOT_IN_BENCH 1
#include "/program/forward.fsh.glsl"
