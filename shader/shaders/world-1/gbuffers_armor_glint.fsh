#version 330 core
// gbuffers_armor_glint in the Nether: the shield and trim glint, added into emit before deferred and into the scene after it; unscrolled under BENCH_DETERMINISTIC.
#define DIMENSION_NETHER 1
#define FORWARD_TEXTURE 1
#define FORWARD_EMIT 1
#include "/program/forward.fsh.glsl"
