#version 330 core
// gbuffers_entities_translucent in the overworld: translucent entities, name tags and texts lit forward, vanilla's blend, also into trans for a draw before deferred (armour cracks); the glint off BENCH_DETERMINISTIC.
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NORMAL 1
#define FORWARD_GLINT 1
#define FORWARD_TRANS 1
#include "/program/forward.fsh.glsl"
