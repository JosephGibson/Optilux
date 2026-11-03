// The pack's colour targets (config/pipeline.json's resources), read by Iris from this comment in
// deferred's source. The scene is HDR (plans/m4.md D78); the G-buffer is one RGBA16UI texel a
// pixel (D75), never cleared, as Iris's float clear is undefined on an integer target (P14): deferred
// reads it only where depth shows geometry, and every opaque draw writes it whole. The overlays
// (D76) are cleared each frame to the value that leaves the scene as it is.
/*
const int colortex0Format = R11F_G11F_B10F;
const bool colortex0Clear = false;
const int colortex1Format = RGBA16UI;
const bool colortex1Clear = false;
const int colortex2Format = R11F_G11F_B10F;
const vec4 colortex2ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const int colortex3Format = RGBA8;
const vec4 colortex3ClearColor = vec4(1.0, 1.0, 1.0, 1.0);
const int colortex4Format = R11F_G11F_B10F;
const vec4 colortex4ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const int colortex5Format = RGBA16F;
const vec4 colortex5ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const int colortex6Format = RGB10_A2;
const bool colortex6Clear = false;
*/

#ifndef OPTILUX_TARGETS
#define OPTILUX_TARGETS 1

// The G-buffer's material field (lib/gbuffer.glsl).
#define MATERIAL_TERRAIN 0.0
#define MATERIAL_ENTITY 1.0
#define MATERIAL_BLOCK 2.0
#define MATERIAL_HAND 3.0
#define MATERIAL_PARTICLE 4.0

#endif
