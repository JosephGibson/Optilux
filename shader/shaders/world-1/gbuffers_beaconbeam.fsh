#version 330 core
// gbuffers_beaconbeam in the Nether: the beacon beam, emissive: its core before deferred into the G-buffer, its glow after it with vanilla's blend.
#define DIMENSION_NETHER 1
#define FORWARD_TEXTURE 1
#define FORWARD_EMISSIVE 1
#define FORWARD_GBUFFER 1
#include "/program/forward.fsh.glsl"
