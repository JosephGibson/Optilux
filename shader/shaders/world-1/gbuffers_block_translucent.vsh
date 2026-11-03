#version 330 core
// gbuffers_block_translucent in the Nether: translucent block entities and sign text lit forward, vanilla's blend, also into trans for a draw before deferred (banner patterns, sign text).
#define DIMENSION_NETHER 1
#define FORWARD_TEXTURE 1
#define FORWARD_LIT 1
#define FORWARD_NORMAL 1
#include "/program/forward.vsh.glsl"
