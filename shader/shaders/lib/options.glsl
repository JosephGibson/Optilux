// The pack's options, listed on its settings screen (shaders.properties: screen). Iris takes a
// `#define NAME` with only a comment after it as an on/off option once a file tests NAME with
// #ifdef, and `#define NAME value // [values] text` as a value option. The programs' own switches
// (SURFACE_*, SHADOW_*, DIMENSION_*) carry the value 1, so they are no options.

#ifndef OPTILUX_OPTIONS
#define OPTILUX_OPTIONS 1

#define BENCH_DETERMINISTIC // Bench frames repeat bit for bit: nothing that moves between frames is read or drawn.

// Dev options for E2 (docs/research/lighting.md#first-version-m4), on the DEV screen.
#define LIGHT_PATH 1 // [0 1] 0 lights each opaque fragment in its own program, 1 lights each pixel once in deferred.
#define E2_LOAD 0 // [0 4 8 16] Shadow-map fetches added to each lit fragment, standing in for M5's lookups.

#endif
