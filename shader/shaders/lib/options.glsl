// The pack's options, listed on its settings screen (shaders.properties: screen). Iris takes a
// `#define NAME` with only a comment after it as an on/off option once a file tests NAME with
// #ifdef, and `#define NAME value // [values] text` as a value option. The programs' own switches
// (SURFACE_*, FORWARD_*, SHADOW_*, DIMENSION_*) carry the value 1, so they are no options.

#ifndef OPTILUX_OPTIONS
#define OPTILUX_OPTIONS 1

#define BENCH_DETERMINISTIC // Bench frames repeat bit for bit: nothing that moves between frames is read or drawn.

// Lighting (docs/research/lighting.md#first-version-m4).
#define SHADOWS 1 // [0 1] 0 Off: no shadow pass and no lookup; 1 Low: one hardware compare tap on a 2048 map.
#define HELD_LIGHT // The held items' light around the player.
#define BLOCK_FLICKER 1 // [0 1 2 3] Block light's flicker: 0 Off, 1 Low, 2 Medium, 3 High; at rest under BENCH_DETERMINISTIC.
#define SUN_SPECULAR // The sun's highlight on every lit surface, sharper on translucent terrain.
#define FOLIAGE_TRANSLUCENCY // Leaves and plants take light from behind and wrap it round their faces.
#define DITHER // The display dither of one 8-bit step against banding.

// Dev options for E2 and the cost rows (docs/research/lighting.md#first-version-m4), on the DEV screen.
#define LIGHT_PATH 1 // [0 1] 0 lights each opaque fragment in its own program, 1 lights each pixel once in deferred.
#define E2_LOAD 0 // [0 4 8 16] Shadow-map fetches added to each lit fragment, standing in for M5's lookups.
#define SCENE_FORMAT 0 // [0 1] The HDR scene's format: 0 R11F_G11F_B10F, 1 RGBA16F.
#define OVERLAYS // The blended draws before deferred (crumbling, the shield and trim glint, banner patterns, sign text) kept in their own targets.

#endif
