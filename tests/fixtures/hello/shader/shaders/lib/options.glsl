// The pack's options, listed on its settings screen (shaders.properties: screen). Iris takes a
// `#define NAME` with only a comment after it as an on/off option once a file tests NAME with
// #ifdef; a define with a value and no [list] in its comment is no option, so the programs'
// switches (SURFACE_*) carry the value 1.

#ifndef OPTILUX_OPTIONS
#define OPTILUX_OPTIONS 1

#define BENCH_DETERMINISTIC // Bench frames repeat bit for bit: nothing that moves between frames is read or drawn.

#endif
