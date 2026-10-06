# GPU and Iris reference
Status: carried 2026-10-05 from ALC (lessons.md) and the user's playbook (sources/shader-optimization-playbook.md, "PB").

## Contents
Sources and tags
GPU: Uniform math · Occupancy · Latency · Depth and discard · Bandwidth · Transcendentals
Iris: Custom uniforms · Passes and buffers · Frame counters and reload · Properties and options · Programs and alpha tests · Toolchain quirks

## Sources and tags
- ALC and PB both ran Iris 1.10.7, Sodium 0.8.x, MC 1.21.11, RX 7800 XT, 4K. Frame counters and reload, the settings re-read and the `#version` rewrite were verified on Iris 1.11.7 in the spike (platform.md#mc-263-verified); every other Iris fact is [MC]: re-verify on 1.11.7 with `javap -c -p`.
- Tags: m = measured in game; v = verified offline (ISA, jar bytecode, numeric check); b = built, never timed. CONFLICT = the sources disagree; measure before relying on either.

## Uniform math
- RDNA3 (gfx11) has no scalar float ALU; RDNA3.5 adds one. Uniform-only float math runs per lane, in every pixel. [ALC v, PB v]
  - PB: the terrain prologue spent ~70 instructions and 7 transcendentals per pixel on global initializers (sun vector, light and sky colours).
- Move uniform-only work out of the pixel shader: [PB v]
  - best: an Iris custom uniform (CPU, once per frame, scalar registers);
  - full-screen passes only: compute in the vertex stage and pass a flat varying.
- Terrain: never flat varyings; the work returns per vertex.
  - ALC m: +1.36 % in the Nether.
  - PB m: neutral.
- A flat varying holds a VGPR while live. Turning deferred1's flat inputs into uniforms was part of PB's 84 -> 48 VGPR drop. [PB v]
- Branches on uniforms are scalar branches; use them to gate rarely-on effects (rain fog, stars by day, held-item light). [PB v]

## Occupancy
- RGA wave64 model, gfx1101: VGPRs allocate in steps of 12. One register over a step costs the whole step. [PB v, ALC v]

  | VGPRs | 48 | 60 | 72 | 84 | 96 | 120 |
  |---|---|---|---|---|---|---|
  | waves per SIMD | 16 | 12 | 10 | 9 | 8 | 6 |

- The allocation is the maximum over all paths, rare ones included. Read the live-register map, not instruction counts. [PB v]
  - PB: a full-screen pass sat at 84 because of an aurora loop and a fallback march; without them it dropped to 48.
- Constant-count loops that fetch textures unroll fully, with every fetch in flight. Take the count from an int custom uniform; prefer one 16-step loop to nested 4x4. [PB v]
- CONFLICT: ALC measured composite4 cut from 60 to 24 VGPRs (12 -> 16 waves) as 0.07-0.46 % slower on every view [ALC m]. PB's occupancy wins are offline or blind.

## Latency
- A PCF shadow tap is a dependent chain: depth compare, then the translucent compare, then the colour fetch. [PB v]
- Issue independent taps together: both compares, then both translucent compares, then both colours.
- Keep each tap's arithmetic and the add order to stay bit-exact. Check the allocation step afterwards.

## Depth and discard
- Any reachable `discard` defers depth writes until after the shader, even if it never fires. Fragments of the same draw cannot reject each other early. [PB v]
- PB: give solid geometry its own program without discard (`gbuffers_terrain_solid`, `shadow_solid`). [PB b]
- CONFLICT: ALC replaced the shader discard with an Iris alpha test and measured it slower (geo-mean +1.2 %, up to +4.4 %). `alphaTest.<program>` reaches every pass of the program, solid included [ALC m]. It is a different mechanism; the split-program version is unmeasured.

## Bandwidth
At 4K a frame is 8.3 M pixels; one RGBA16F target write is ~66 MB.
- TAA is bound by memory traffic, not arithmetic. [PB v]
- Unread mip chains cost 0.06-0.1 ms each at 4K. Skipping them, and skipping unread passes and plain copies, measured as wins. [ALC m, PB m]
- 64x packs at mip 0 thrash the texture cache. Optilux builds on Faithful 64x, so both of these apply: [PB b]
  - manual anisotropic filtering at 4x from a partial mip level, one tap under magnification;
  - shadow-pass alpha at hardware LOD - 2, on solid and cutout passes only (translucent passes keep coloured shadows).
- History formats: RGB16F is padded to 8 bytes; RGB10_A2 is 4 (playbook.md#54-sample-count-and-precision-trades). [PB v]
- Viewport scaling for passes that write one corner (bloom tiles, `scale.compositeN`). [PB b]
- `textureGather` loads 2x2 in one instruction: a 3x3 depth neighbourhood in 4 gathers instead of 9 fetches. [PB v] It compiled and ran under Iris. [ALC v]

## Transcendentals
- pow, exp, log, sqrt, rsq, sin and cos run at quarter rate; pow is a log plus an exp. [ALC v, PB v]
- Cheaper forms: [PB v]
  - integer exponents as squaring chains;
  - `length(normalize(v))` is 1;
  - skip a pow whose mix weight is 0;
  - move uniform-only pows to the CPU.
- ALC measured squaring chains, sin/cos pairing and AF algebra at 0.1-0.3 %, below threshold. Worth it only on hot paths. [ALC m]
- Approximation helpers (e.g. `pow1_5(x) = x - x(1-x)^2`) are not powers; do not fuse identities across them. [PB v]
- `mediump` is ignored. FP16 (`GL_AMD_gpu_shader_half_float`) raised composite4 from 50 to 106 VGPRs [ALC v]; PB skipped it as a precision risk. Avoid.
- No variable-rate shading on AMD OpenGL. [PB]

## Custom uniforms
Declared as `uniform.<type>.<name>` and `variable.<type>.<name>` in shaders.properties. All [PB v].
- Evaluated once per frame on the CPU in `beginLevelRendering`, after the frame's matrices are captured. The previous-frame inputs hold last frame's values; nothing lags a frame.
- Types: float, int, bool, vec2-4. Variables feed later expressions, and forward references resolve.
- Inputs:
  - gbufferModelView and gbufferProjection, with their Previous and Inverse forms;
  - the shadow matrices;
  - cameraPosition, previousCameraPosition;
  - sunAngle, worldTime, frameCounter, screenBrightness, skyColor;
  - the pack's own custom uniforms.
- Not available: per-draw uniforms such as fogColor.
- Matrix `.x/.y/.z/.w` (or `.0`-`.3`) returns a column as vec4, like GLSL `m[i]`. Store it in a `variable.vec4`.
- Functions: frac, if(c,a,b), sin, cos, pow, sqrt, exp, log, clamp, min, max, abs, floor, smooth, vec2-4; `&&`, `||` and comparisons work.
- Write negative literals after an operator as `(0.0 - x)`; that form is known to parse.
- A custom uniform reaches every program that declares it. A declared uniform Iris never defines reads 0 (black clouds, skipped loops).
- float32, like the GPU: 1-2 ulp differences.
- Offline check, a Java harness on the Iris jar (re-read the class names on 1.11.7):
  1. `kroppeb.stareval.parser.Parser.parse` with `IrisOptions.options`;
  2. `ExpressionResolver` with `IrisFunctions.functions`;
  3. `Expression.evaluateTo`;
  4. compare against the shader formula in float32 on random frames.

## Passes and buffers
- A composite or deferred pass whose draw buffers share one size (`size.buffer.colortexN = 0.5 0.5`) draws at that size. viewWidth and viewHeight stay full; gl_FragCoord is in the small buffer. [PB v]
- Iris flips a buffer after a pass writes it, so the next pass reads the new contents. [PB v]
- colortex0-15 are available; newer Iris accepts more, and Voxy-aware packs use 18 and 19. [PB v]
- RENDERTARGETS/DRAWBUFFERS and const directives are parsed from the preprocessed source; comments in inactive branches are dropped. If a directive appears twice, the last one wins silently. [PB v]
- `program.<world>/<name>.enabled=false` disables a pass. Its condition must match every consumer of its output. [PB v, ALC v]
- Iris copies depth for depthtex1 and depthtex2 unconditionally (~0.29 ms replayed); that cost is not the pack's. [ALC v, PB v]
- Mipmap flags exist only for composite, deferred and final programs. [ALC v]

## Frame counters and reload
Iris 1.10.7 bytecode (`javap -c -p` of the pinned jar), read for Optilux on 2026-10-05; re-verified on 1.11.7 source and bytecode in the spike (R5). [ALC v]
- frameCounter: an int, `(count + 1) % 720720`, ticked at the HEAD of `GameRenderer.render`, once per render call, GUI-only frames included.
- frameTimeCounter: a float that adds the frame's whole milliseconds / 1000 each frame. Wall-clock, so it differs per session; set to 0 at 3600.
- Both reset to 0 at every pipeline creation (`PipelineManager.preparePipeline`):
  - `Iris.reload()`;
  - a dimension change;
  - the first level render after a join.
  - So frameCounter counts frames since the last reload; the first frame after one sees 1 (inference).
- A new pipeline's first frame clears every colortex, `Clear=false` ones included. TAA history therefore starts empty after a reload.
  - Default clear colours are 0, except colortex0 (fog colour) and colortex1 (1,1,1,1).
- A new pipeline's first `beginLevelRendering` calls `levelExtractor.allChanged()` (1.11.7; 1.10.7 did it in the reload): every chunk re-meshes asynchronously, so the first frames after a reload are not final.
- Per-pipeline state (previous camera position, previous matrices) lives in the new pipeline's fields; inference: it restarts at a reload.

## Properties and options
- shaders.properties runs through a C preprocessor (JCPP). [PB v, ALC v]
  - Bool options are defined when on; value options are macros.
  - `IS_IRIS` and Iris's standard macros are defined; guard Iris-only syntax with `defined IS_IRIS`.
- A bool option registers only when a shader `#ifdef`/`#ifndef` references it. [ALC v, PB v]
- Screen values split on " +", so use `<empty>`; there is no `*` catch-all. [ALC v]
- A shader `#undef` of an option is invisible to properties, which still see the user's value. [PB v]
- Option screens and profiles parse from `//[...]` comments; the settings .txt is re-read on reload. [ALC v] 1.11.7: `Iris.reload()` re-reads iris.properties and shaderpacks/<pack>.txt, then writes the .txt back with the effective values (spike V1).

## Programs and alpha tests
- Program fallbacks: [PB v]
  - `gbuffers_terrain_solid` and `_cutout` fall back to `gbuffers_terrain`;
  - `shadow_solid`, `shadow_cutout` and `shadow_water` fall back to `shadow`.
- Sodium shadow passes: [PB v]
  - SHADOW -> ShadowSolid;
  - SHADOW_CUTOUT -> ShadowCutout (falling blocks and pistons land here too);
  - SHADOW_TRANS -> ShadowWater.
- Injected alpha tests unless overridden: solid none; cutout `> 0.5`; translucent non-zero. [PB v]
- Iris defines `MC_<extension>` for every exposed GL extension (e.g. `MC_GL_ARB_texture_gather`). [PB v]
- MC_GL_VENDOR_AMD is undefined on AMD; the vendor string is "ATI". [ALC v]
- `#version`: Iris rewrites 130 to 330 core and 460 compatibility to 460 core, and keeps `#extension` lines. [ALC v; 130 to 330 core re-verified on 1.11.7, spike V4]
- Linking: unread vertex outputs link; a fragment input with no vertex output does not. [PB v]
- `#include` is not deduplicated; guard any file that can be reached twice. [PB v]
- Reload is synchronous and falls back to vanilla on failure; `getStoredError` hands an error out once, but only while no player exists; in a world the error goes to chat (1.11.7 source, platform.md#mod-adapter-surface). [ALC v]

## Toolchain quirks
- Offline compiles: [PB v]
  - gbuffers stages may need `#version 150 compatibility` and Iris-injected inputs (e.g. `mc_chunkFade`) declared;
  - supply every runtime macro (e.g. `MC_RENDER_STAGE_*`), or the build fails falsely;
  - keep a list of known offline-only failures.
- RGA's ISA matched Iris's dumps on only 17 of 48 post stages, because Iris rewrites built-ins. Judge only the stages known to match. [ALC v]
- Dumps (`enableDebugOptions`) are fully preprocessed and rewritten on every pipeline build (1.11.7: game/patched_shaders/, numbered per program, a .json each). Debug mode also creates a KHR_debug GL context, reported 30 fps against 141 on the bench tier, and conflicts with Sodium's no-error context on a fresh config (platform.md#mc-263-verified). [ALC v]
