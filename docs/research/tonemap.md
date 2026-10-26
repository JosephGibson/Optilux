# Tonemap, exposure and color
Status: Research for M4's output path: HDR scene format, tonemap, exposure, grading, encoding and dither, and TAA's place against the tonemap. Not yet measured in Optilux: every cost is a hypothesis until a cost row or timer row confirms it.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
Read for this doc unless marked "not read".
- R1 Lottes, "Advanced Techniques and Optimization of HDR VDR Color Pipelines", GDC talk, 2016, https://gpuopen.com/wp-content/uploads/2016/03/GdcVdrLottes.pdf. Not read; its curve is read in R20, which credits it.
- R2 Narkowicz, "ACES Filmic Tone Mapping Curve", blog, 2016, https://knarkowicz.wordpress.com/2016/01/06/aces-filmic-tone-mapping-curve/.
- R3 Hill's ACES fit, BakingLab ACES.hlsl, code (MIT), https://github.com/TheRealMJP/BakingLab/blob/master/BakingLab/ACES.hlsl.
- R4 Hable, "Filmic Tonemapping with Piecewise Power Curves", blog and CC0 code, 2017, http://filmicworlds.com/blog/filmic-tonemapping-with-piecewise-power-curves/.
- R5 Reinhard et al., "Photographic Tone Reproduction for Digital Images", paper, 2002, https://users.cs.utah.edu/docs/techreports/2002/pdf/UUCS-02-001.pdf. Not read.
- R6 Uchimura, "HDR theory and practice", CEDEC talk (Japanese), 2017, https://www.slideshare.net/nikuque. Not read.
- R7 AgX: Blender 4.0 release notes, vendor doc, 2023, https://developer.blender.org/docs/release_notes/4.0/color_management/; EaryChow's README, https://github.com/EaryChow/AgX.
- R8 Khronos PBR Neutral, spec and sample, 2024, https://github.com/KhronosGroup/ToneMapping/tree/main/PBR_Neutral.
- R9 ACES 2, vendor doc, 2025, https://docs.acescentral.com/background/about-aces-2/.
- R10 Karis, "Tone mapping", blog, 2013, http://graphicrants.blogspot.com/2013/12/tone-mapping.html.
- R11 Lottes, "Optimized Reversible Tonemapper for Resolve", vendor doc (GPUOpen), 2016, https://gpuopen.com/learn/optimized-reversible-tonemapper-for-resolve/.
- R12 Wronski, "Small float formats - R11G11B10F precision", blog, 2017, https://bartwronski.com/2017/04/02/small-float-formats-r11g11b10f-precision/.
- R13 Wronski, "Dithering part three", blog, 2016, https://bartwronski.com/2016/10/30/dithering-part-three-real-world-2d-quantization-dithering/.
- R14 Opsenica, "Automatic Exposure Using a Luminance Histogram", blog, 2019, https://bruop.github.io/exposure/.
- R16 Photon (sixthsurge), pack source, Photon Shaders License Agreement (custom: study and personal modification; no redistribution for money without permission), https://github.com/sixthsurge/photon: shaders/program/c4_taa_exposure.vsh and .fsh.
- R17 Iris docs, project doc, current, https://shaders.properties/current/reference/ (image_format, colortex_mipmaps, eyebrightnesshalflife, programs/composite, rendering, custom_uniforms).
- R18 XFX RX 7800 XT page, vendor spec, 2023, https://xfxforce.com/shop/xfx-speedster-swft-210-radeon-tm-rx-7800-xt-core-edition: "Up to 624 GB/s", 64 MB Infinity Cache, 3840 stream processors, 2430 MHz boost.
- R19 Jimenez, "Next Generation Post Processing in Call of Duty: Advanced Warfare", SIGGRAPH course talk, 2014, https://www.iryoku.com/next-generation-post-processing-in-call-of-duty-advanced-warfare/ (IGN; slides not read).
- R20 Complementary Unbound r5.9.3, pack source, Complementary License Agreement 1.7 (reference/complementary-unbound-r5.9.3/License.txt); studied, never copied (docs/shader.md#policy).
- R21 64, "Tone Mapping", blog, 2019, https://64.github.io/tonemapping/: extended Reinhard (R5), its white point.
- R22 Iris source, branch 26.3, https://github.com/IrisShaders/Iris: SmoothFloat, SmoothedFloat, SystemTimeUniforms, CommonUniforms, PackDirectives, CustomTextureData, IrisRenderSystem. A branch, not the jar: [verify in jar] stays; it outranks R17.

## Unbound r5.9.3
Files under reference/complementary-unbound-r5.9.3/shaders/ (R20).
- Formats (lib/pipelineSettings.glsl): scene colour colortex0 R11F_G11F_B10F; the tonemapped image colortex3 RGBA8; TAA history colortex2 RGB16F, Clear=false (a new pipeline still clears it: docs/gpu-iris.md#frame-counters-and-reload).
- Order: composite4 builds bloom tiles from colortex0's mip chain, in RGBA8 under a fourth-root encoding; composite5 divides the scene by a "bloom fog" factor (distance, rain, night, water, Nether; none in the End), lerps bloom in, applies the optional grade, the tonemap and a display-space saturation step, and writes RGBA8; composite6 runs TAA on that display-encoded image, clipping history to the 3x3 min-max box with no colour-space change (lib/antialiasing/taa.glsl), reading and writing colortex3 and colortex2 in that pass through Iris's flip; final sharpens, adds a static per-pixel offset from the noise texture (-0.5 to +1.5 codes, not zero-mean) and writes the screen.
- Tonemap (program/composite5.glsl, credited to R1): an exposure scale; per channel the Lottes curve (contrast option, default 1.05; shoulder 1; white point 8; mid-grey held); the piecewise sRGB encode; a dark lift (luminance under 0.1 blended toward a gamma-2.2 encode of the untonemapped value), a path to white (as luminance nears 16) and a partial desaturation of darks; then a BSL-derived saturation and vibrance step, by default a slight boost (TM_* and T_* in lib/common.glsl).
- Exposure: one TM_EXPOSURE for every dimension; no metering or adaptation. Time of day lives in the light and sky colours (lib/colors/; per-time multipliers exist, off by default). Vanilla's Brightness enters through screenBrightness: minimum light, ambient and fog colours (vsBrightness in lib/common.glsl, lib/colors/lightAndAmbientColors.glsl). Fog and bloom fog read smoothed custom uniforms (eyeBrightnessM, rainFactor: smooth() in shaders.properties; lib/atmospherics/fog/bloomFog.glsl), which BENCH_DETERMINISTIC never reads (docs/measurement.md#visual-protocol).
- Grading (COLORGRADING, off by default and in played): a per-channel power, then a 3x3 mix, before the curve.
- Cost: no ablation isolates the tonemap. BLOOM_ENABLED=-1, which also undefines BLOOM_FOG (lib/common.glsl), measured 0.128 ms mean, 0.165 worst (underwater) [ALC m, MC 1.21.11] (config/profiles/complementary-unbound-played.json). PB's forest replay, on a Complementary Reimagined fork, gives "Bloom, tonemap, final" "a few % each", to rank, not bound (docs/sources/shader-optimization-playbook.md#11-find-where-the-frame-goes-before-touching-code).
- Contrast, R16: Photon's c4 pass resolves TAA in a per-channel Reinhard space, rgb / (1 + rgb) and back, before its bloom and grading passes; its vertex stage meters exposure from colortex0's mips (one coarse texel, or a 32x18 grid binned into a log histogram read at a percentile), keeps it in one history texel and smooths it by frame time; it updates history in place through the flip.

## Techniques
### T1 HDR scene format
- Claim: R11G11B10F has 6-bit mantissas in R and G and 5 in B, no sign or alpha. R12: "Mantissa suffers the most"; the uneven mantissas "will produce various discolorations and hue shifts" (yellow/blue); against 8-bit sRGB the 10-bit float's "Maximum error is almost 2x larger around 1", though better below linear 0.125. R12's fix, a stored power read back by a root, trades range for precision and loses filtering and blending, so it does not suit a scene buffer that translucents blend into and bloom mips [inferred]. Iris lists R11F_G11F_B10F ("Requires Iris 1.8+"), RGB10_A2, RGBA16F, RGB16F (R17); RGB16F pads to 8 bytes (docs/gpu-iris.md#bandwidth).
- In display codes [inferred]: an encoded value v moves by about v x r / 2.4 for a relative step r, so near white R11G11B10F steps up to ~1.7 codes in R and G and ~3.3 in B before the shoulder compresses them; RGBA16F ~0.1. Sky gradients are the risk (forest_noon, ocean_sunset).
- Cost: 8.29 M px; one full-screen read or write is 33 MB at 4 B/px, 66 MB at 8: 0.053 or 0.106 ms at 624 GB/s (R18). 33 MB fits the 64 MB Infinity Cache between producer and consumer, 66 MB does not [inferred]. At 4-8 DRAM-bound touches a frame [inferred], RGBA16F costs 0.2-0.4 ms more; more if R11G11B10F stays in the cache.
- Constraints: (1) the format is deterministic; a write dither, if banding needs one, is static or frameCounter mod the pack's cycle; (2) `colortexNFormat`; Unbound's R11F_G11F_B10F colortex0 loads here (docs/platform.md#mc-263-verified, L1) [verify in jar: InternalTextureFormat]; (3) a plain render target; Aperture's formats are an open question; (4) above; no ladder, an A/B.

### T2 Tonemap operator
Judged on the look: Optilux starts "from a similar tonemap" (user, 2026-10-20; docs/shader.md#look-and-scope).

| Operator | Shape, hue | ALU [inferred] | Src |
|---|---|---|---|
| Lottes (Unbound) | per channel x^a / (x^ad b + c) through mid-grey and hdrMax; hue skew in bright saturated colours [inferred], eased by the path to white | 3 pow, 3 rcp | R1, R20 |
| ACES fit (Narkowicz) | rational, pre-exposed; "over saturates brights" | 3 rcp, ~12 FMA | R2 |
| ACES fit (Hill) | matrix, rational RRT+ODT fit, matrix | 2 mat3, 3 rcp | R3 |
| ACES 2 | "gentler highlight rolloff", gamut mapping | LUT fetch | R9 |
| AgX | inset, log2 over -10..+15 stops, sigmoid, outset [unverified]; "bright colors go towards white" | 2 mat3, 3 log2, 3 poly | R7 |
| Hable piecewise | toe, linear, shoulder power segments | 3 exp, 3 log | R4 |
| Uchimura (GT) | toe, linear, shoulder [unverified] | pow + exp a channel | R6 |
| Extended Reinhard | white point maps to 1 | ~6 | R5, R21 |
| PBR Neutral | base colours 0.08-0.8 kept, highlights toward neutral, "no hue shifts" | ~15 | R8 |

- Cost: 3840 lanes x 2430 MHz is ~1,100 lane-ops per pixel per ms (R18; no dual issue), transcendentals at quarter rate (docs/gpu-iris.md#transcendentals). An Unbound-like pass (~25 transcendentals, ~60 other ops, 4 B/px in and out, 66 MB) is ~0.14 ms ALU and ~0.11 ms memory, +0.05 ms if it reads depth for a bloom fog: 0.1-0.25 ms [inferred]; a few % of ALC's 4.6-7.7 ms Unbound frames (docs/shader.md#method) is 0.1-0.3 ms. The operator choice moves it under 0.05 ms [inferred].
- Exact trim: the dark lift's weight is zero above luminance 0.1, a zero-weight skip [PB b] (docs/sources/shader-optimization-playbook.md#43-exact-arithmetic-trims).
- Constraints: (1) pointwise, stateless; (2) a composite pass; options as #defines fold b and c at compile time [inferred]; (3) one Iris-free include taking its parameters, run standalone by L3; (4) above; no ladder: an operator is look.

### T3 Exposure
- Fixed (Unbound: one TM_EXPOSURE); per dimension it is free through the world folders' defines (Unbound's world0 wrappers define OVERWORLD) [inferred]; 0 ms.
- Metering without compute: the smallest mip of the HDR scene, or mip tiles binned into a log histogram in a full-screen vertex stage, passed on as a flat varying (R16; docs/gpu-iris.md#uniform-math). colortexNMipmapEnabled builds the chain "directly before the program where the directive is included" (R17); an unread chain cost 0.06-0.1 ms at 4K [ALC m, PB m] (docs/gpu-iris.md#bandwidth), ~0 extra if bloom builds it anyway [inferred]. A compute histogram (R14: 256 bins, shared-memory atomics) needs compute, an optional composite stage (R17); Iris enables it when glDispatchCompute loads (R22, IrisRenderSystem), so here it rests on the driver exposing ARB_compute_shader to a 3.3 core context [inferred; verify in jar].
- Smoothing: R14 and R16 step toward the target each frame, R16 by exp(-rate x frameTime). R17 calls smooth()'s fades a "halflife in ticks" and eyeBrightnessSmooth's default "10 ticks"; R22 scales both by 0.1 s and steps by the last frame's time in whole ms, a wall clock (docs/gpu-iris.md#frame-counters-and-reload): smooth(x, 5, 5) is a 0.5 s and eyeBrightnessSmooth a 1 s half-life of wall time, hence smoothing moves under /tick freeze (docs/measurement.md#visual-protocol) [verify in jar]. BENCH_DETERMINISTIC reads none of them.
- Deterministic form [inferred]: under BENCH_DETERMINISTIC exposure is the metered target with no state, so a static view repeats every cycle and needs no flush; off it, a per-frame step at a frame-count rate. Raw eyeBrightness is the eye block's block and sky light x 16, each frame, unsmoothed (R22, CommonUniforms); Unbound feeds eyeBrightness.y to custom uniforms (shaders.properties), so this platform takes it as an input [verify in jar].
- Ladder: Off (fixed); Low (eyeBrightness factor, custom uniform, 0 ms); Medium (one coarse-mip sample, 0-0.1 ms); High (vertex-stage histogram, the same plus 576 fetches a vertex).
- Constraints: (1) above; the live pass checks "exposure smoothing"; (2) mipmaps in composite [ALC v], a 1x1 state buffer (integer size.buffer is "the resolution of the buffer in pixels", R17), Clear=false, which a new pipeline still clears [verify in jar]; (3) state in an explicit ping-pong pair (two 1x1 textures, or the TAA history pair), never read and written in one pass (docs/platform.md#renderer-transition); (4) above.

### T4 Grading and white balance
- One 3x3 matrix in linear before the curve carries white balance (a chromatic adaptation), saturation and channel mix, built at compile time: 9 FMA a pixel, ~0.01 ms [inferred]. Unbound's power grade adds 3 pows; its display-space saturation and vibrance ~25 ALU.
- A 3D LUT folds curve and grade into one fetch; Iris has raw 3D custom textures (R22, CustomTextureData) [verify in jar]; the build would generate it. Not v1.
- Constraints: (1) stateless; (2) composite ALU; (3) Iris-free include; (4) 0.01-0.03 ms.

### T5 Output encoding and dither
- Encode with the piecewise sRGB curve, as Unbound, into the game's main framebuffer [verify in jar: RGBA8 in 26.3].
- Dither before 8 bits (R13): "Using triangular noise distribution fixes those bands without over-noising the image"; "avoid ordered Bayer!"; blue noise if a fetch is affordable, interleaved gradient noise (R19) if only ALU is. Triangular noise clips at 0 and 1, lifting blacks by about 20 % of a step (a reader's comment on R13): fade it toward both ends [inferred].
- Noise inside (-1, 1) codes moves a pixel by at most one code, so dither on against off is near by construction (config/suite.json fidelity near maxAbsDiff 1) [inferred; L3 proves it].
- Constraints: (1) static per pixel (cycle 1), as Unbound's final; if animated, frameCounter mod the pack's cycle; (2) customTexture for blue noise [verify in jar]; (3) trivial; (4) triangular IGN, two hashes or one remap: ~10-15 ALU, ~0.01 ms [inferred].

### T6 TAA against the tonemap
- After the tonemap (Unbound, PB): values in [0, 1] allow an RGB10_A2 history, 4 B/px against RGB16F's 8 (docs/playbook.md#54-sample-count-and-precision-trades), and N_conv's w^n <= 1/255 (docs/measurement.md#visual-protocol) bounds a residue in display codes; before it the bound scales with the HDR peak [inferred].
- Before the tonemap: resolve in a reversible space, c / (1 + max3(c)) and back; max3 "removes the hue shift on mixed color edges of similar value", where R10's luma weight varies with hue (R11). Needs an HDR history.
- The LDR target is gamma-encoded: 10-bit linear steps 10 % at 0.01 [inferred]. Unbound's RGBA8 target quantizes TAA's input to 8 bits; RGB10_A2 costs the same bytes [inferred].
- Constraints: (1) the placement adds no frame-varying term; PB's +-1/2-step write dither on an RGB10_A2 history takes frameCounter mod the pack's cycle and, as all history, rests on the flush and N_conv (A12): under E4's fallback TAA-on frames get review only; (2) RGB10_A2 is listed (R17) [verify in jar]; (3) Unbound and Photon update history in place through the flip; Optilux reads one texture and writes another (docs/shader.md#pipeline-spec), the alternation being taa's; (4) RGB10_A2 saves ~0.05 ms per full-screen history read or write at 624 GB/s [inferred], in a memory-bound pass (docs/gpu-iris.md#bandwidth).

## For Optilux
- First version (M4):
  - scene colour R11G11B10F, RGBA16F its A/B variant; a pass needing alpha keeps its own buffer;
  - one pass ends the HDR chain: bloom in (post), grade matrix, exposure, an Unbound-like Lottes curve, sRGB encode, the three look terms, display saturation; output RGB10_A2, gamma-encoded; the maths in one Iris-free include;
  - TAA after it; final: sharpening, a static triangular IGN dither, the screen;
  - exposure fixed per dimension; eye adaptation waits for D72's look target (docs/roadmap.md#decisions);
  - nothing in this path reads smooth(), eyeBrightnessSmooth, frameTime or random().
- Options, fewer than Unbound's: exposure, contrast, white path, saturation; dither On/Off; later eye adaptation Off/Low/Medium/High.
- Cost hypothesis, alike on every view (screen-bound): tonemap pass 0.1-0.25 ms; grade and dither under 0.02 ms; the scene format 0.2-0.4 ms of the frame. Visual risk by view type: forest_noon and ocean_sunset banding; cave, night and nether_soul the dark lift and desaturation; underwater and the End tints near the white point.
- Confirming measurements (docs/measurement.md#verdicts-and-cost-rows):
  - tonemap pass: timer row (docs/design.md#8-open-decisions E3) or cost row against a passthrough variant on a base above the CPU floor (docs/roadmap.md#findings-assigned F25): 0.1-0.25 ms;
  - scene format: cost row in full mode, review tier, sky views pre-screened for banding;
  - RGB10_A2 against RGBA8 target: inside threshold; near or close;
  - dither on against off: inside threshold; near on every view;
  - a metering mode: cost row; M3's TAA-off check, every perf view identical across two sessions (docs/design.md#8-open-decisions E4);
  - any look change: review tier beside Unbound's played frames.
- L3 golden tests (docs/offline.md#levels):
  - sRGB encode: 0 and 1 exact, continuous at 0.0031308, a 4096-step ramp's 8-bit codes equal to a float64 reference;
  - curve: f(0) = 0, f(midIn) = midOut and f(hdrMax) = 1 within 1e-5, monotonic over 2^-14..2^16, finite at denormals, 64512 and 65024 (R11G11B10F's B and R/G maxima) and 65504, NaN sanitized to 0;
  - look terms continuous at their thresholds; the dark-lift skip equal to the unskipped path;
  - dither: zero mean over a 64x64 tile, at most one code from undithered, 0 stays 0, 255 stays 255;
  - an exposure custom uniform, once one exists (Low), in Iris's engine against float32 GLSL (docs/gpu-iris.md#custom-uniforms);
  - an R11G11B10F rounding model in numpy: per-channel max error on a sky ramp, a regression number.
- Offline look comparison [inferred]: an L4 capture's HDR target tonemapped in Python by each candidate gives D72's look review side by side.
- Pitfalls: a colortex without a format is RGBA8 (config/pipeline.json formatWhy) and clips HDR; with TAA off, final must read the tonemap target, not stale history (docs/playbook.md#7-pitfalls); the Lottes constants solved the way Unbound writes them may share a 72-token run (docs/shader.md#policy): solve them another way [inferred]; options.txt's gamma is unwritten, "recorded, never matched" (docs/roadmap.md#findings-assigned F21), yet Unbound's frames move with it through screenBrightness (R22, CommonUniforms) and Optilux's may through the lightmap's sky column [inferred].
- Dependencies: taa (placement, target format, N_conv, cycle, history pair); lighting (radiance scale, time of day in light colours, screenBrightness); post (bloom in HDR, its mips as the meter, sharpening); sky (white point, gradients); fog-volumetrics (Unbound's smoothed bloom fog); clouds, water (white point, tints); reflections (scene precision); iris (each [verify in jar]); next-gen (HDR output, local tonemapping).

## Open questions
- Scene format R11G11B10F or RGBA16F? The format A/B's cost row and the sky views' review; and whether a consumer needs scene alpha.
- Eye adaptation in the look at all? D72's look target (user); then Medium and High cost rows and the live pass.
- The Unbound-like curve, or AgX, Hable or PBR Neutral? D72's look review from L4 HDR captures re-tonemapped offline.
- Compute on the 3.3 core context? Whether a dump defines MC_GL_ARB_compute_shader (docs/gpu-iris.md#programs-and-alpha-tests), then the jar (iris topic); only a compute histogram needs it.
- smooth()'s clock: R22's wall clock in 0.1 s units, or R17's ticks? The jar; it bounds an off-bench adaptation.
- Does options.txt's gamma move Optilux's frames? 26.3's lightmap code and a static A/B of two values; if so, suite.json display.optionsTxt pins it (identity: recalibration).
- 26.3's main framebuffer format? The jar or an L4 capture.
- Aperture's B10G11R11 and A2B10G10R10 render targets? Recheck when public (docs/platform.md#renderer-transition).
