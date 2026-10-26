# Temporal anti-aliasing
Status: research on TAA for Optilux on Iris 1.11.7 at 3840x2160 on the RX 7800 XT, from external sources and Unbound r5.9.3. Nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
Tags: docs/gpu-iris.md#sources-and-tags; [inferred] this doc's derivation; [verify in jar] read in Iris source or docs, not the pinned jar.
- R1 Complementary Unbound r5.9.3, pack source, Complementary License Agreement 1.7 (no redistribution): reference/complementary-unbound-r5.9.3/shaders/.
- R2 Iris, project source, LGPL-3.0, https://github.com/IrisShaders/Iris: FinalPassRenderer, GlImage at adc75283b (docs/roadmap.md#findings-assigned F9); CompositeRenderer, BufferFlipper, IrisRenderSystem, FeatureFlags on 1.21.9.
- R3 Iris docs, project doc: https://shaders.properties/current/reference/uniforms/camera/ and its sibling pages (matrices, custom images, MC_HAND_DEPTH, custom uniforms).
- R4 Playdead, INSIDE's TAA, source, MIT, 2016: https://github.com/playdeadgames/temporal
- R5 A. Tardif, "Temporal Antialiasing Starter Pack", blog, undated, after Karis 2014 and Salvi 2016: https://alextardif.com/TAA.html
- R6 E. Lopez, "Temporal AA and the Quest for the Holy Trail", blog, 2022: https://www.elopezr.com/temporal-aa-and-the-quest-for-the-holy-trail/
- R7 AMD FSR 2.2 README, vendor doc, MIT, 2023: https://github.com/GPUOpen-Effects/FidelityFX-FSR2
- R8 AMD FidelityFX CAS, vendor page and ffx_cas.h, MIT, 2020-2023: https://gpuopen.com/fidelityfx-cas/, https://github.com/GPUOpen-Effects/FidelityFX-CAS
- R9 Mantiuk et al., ColorVideoVDP, SIGGRAPH 2024 paper, MIT code: https://github.com/gfxdisp/ColorVideoVDP
- R10 Photon, pack source, Photon Shaders License Agreement (custom; no sale or monetized redistribution): https://github.com/sixthsurge/photon
- R11 KitGuru, RX 7800 XT review, 2023: 624 GB/s: https://www.kitguru.net/components/graphic-cards/dominic-moass/amd-rx-7800-xt-review/
- R12 ALC, this GPU at 4K, MC 1.21.11, Iris 1.10.7 [m]: config/profiles/complementary-unbound-played.json ablations; docs/shader.md#method.
- R13 Yang, Liu, Salvi, "A Survey of Temporal Antialiasing Techniques", CGF 2020, paper (abstract read): https://research.nvidia.com/labs/rtr/publication/yang2020survey
- R14 OptiFine shaders.txt, project doc: https://github.com/sp614x/optifine/blob/master/OptiFineDoc/doc/shaders.txt

## Unbound r5.9.3
Read in R1, in Optilux's words.
- Order: composite5 adds bloom and tonemaps into colortex3 (RGBA8); composite6 runs TAA on it, writing display (colortex3) and history (colortex2, RGB16F, not cleared per frame; lib/pipelineSettings.glsl); composite7 is FXAA (off in played); final sharpens.
- Jitter (lib/antialiasing/jitter.glsl, credited to Chocapic13): 8 phases shaped like the 8x MSAA pattern, by a frameCounter % 8 custom uniform, in the terrain, water, block-entity, basic, beacon-beam and vanilla-cloud vertex stages, never entities, hand, particles or sky; fragment stages remove it before rebuilding positions. Default TAA_JITTER Low: at most about 0.055 px [inferred]. TAA_DEFINE is labelled "Temporal Filtering" (lang/en_US.lang): it denoises more than it anti-aliases.
- Reprojection (lib/antialiasing/taa.glsl, also Chocapic13's): depthtex1 through the inverse matrices plus cameraPosition - previousCameraPosition into the previous ones; hand depths keep their pixel; off-screen drops history.
- History: a 5-tap fetch labelled Catmull-Rom (credited to Filmic SMAA), sharper in tension than standard, on by default; exactly 0 or NaN restarts the pixel.
- Rejection: a 3x3 RGB min/max box, history clipped toward its centre; the loop also flags depth edges, leaves more strongly.
- Weight: a velocity term plus a constant, minus capped camera movement times the edge flag, floored. Still camera: w = 0.9 at every TAA_SMOOTHING level, N_conv 53 [inferred]; End sky (depth 1) always drops the velocity term, so its w is lower.
- Masks: entities, hand, particles (gbuffers_textured) and lightning write a "no TAA" material (table in lib/common.glsl); TAA skips them and writes zero history, so nothing ghosts behind a mob; at DETAIL_QUALITY and CLOUD_QUALITY >= 3 those behind volumetric cloud accumulate.
- Sharpening: a 4-tap cross unsharp mask in final on the display image (IMAGE_SHARPENING 5, halved without TAA), never fed back.
- Frame-varying terms: dithers step by the golden ratio per frame mod 3600, which does not divide 720720 [inferred]; deferred1 also reads an unwrapped frameCounter product and frameTimeSmooth.
- Coupling: SHADOW_QUALITY >= 2 with TAA takes per-frame-rotated PCF pairs (2 at played's Medium), else a fixed 5-tap filter (lib/lighting/shadowSampling.glsl); PB: TAA off "can cost more than the TAA pass itself" (docs/sources/shader-optimization-playbook.md).
- Cost [m, R12]: TAA_DEFINE=0 saves 0.579 ms mean (worst rain 0.662); IMAGE_SHARPENING=0 0.013 (worst end_dragon 0.055). TAA off still runs composite6, writing colortex3 and a zero colortex2, so both arms pay those writes and the frame-end copy (technique 5): the row is TAA's extra reads and maths, the jitter and the shadow swap [inferred]. The 6 % replay share is 0.28-0.46 ms of 4.6-7.7 ms frames [inferred].

## Techniques
Each: claim and sources, then D determinism, I Iris 1.11.7, A Aperture, C cost at 4K. All act only with TAA on, so all depend on A12 (docs/design.md#8-open-decisions E4): under E4's fallback they get review-tier verdicts and the live pass; unjittered TAA-off frames keep other passes judgeable.

### 1. Jitter: Halton(2,3), 16 phases
- Halton(2,3), 8 samples a good default (R5); INSIDE's default Halton(2,3) x16 (R4 FrustumJitter.cs); FSR 2: Halton(2,3), ceil(8 n^2) phases at upscale n, no null vector, "Motion vectors should not have jitter applied" (R7); Photon: an R2 recurrence on the unwrapped frameCounter (R10 shaders.properties). An exponential blend holds (1+w)/(1-w) samples, 19 at w 0.9 [inferred]: 16 phases fill it, 8 repeat in it.
- 720720 = 2^4 x 3^2 x 5 x 7 x 11 x 13: 8, 16, 18 and 72 divide it; 32 and 3600 do not. Halton indices 1-16 minus 0.5 average (-0.029, -0.037) px: subtract that, or the image shifts by it [inferred].
- D: phase = frameCounter mod 16, restarting at each pipeline creation (docs/gpu-iris.md#frame-counters-and-reload); TAA off, no jitter. I: a custom uniform from frameCounter and viewWidth/viewHeight, once per frame (docs/gpu-iris.md#custom-uniforms; R10 reads viewWidth in one) [verify in jar: kroppeb.stareval]; no GLSL constant table (docs/shader.md#policy). A: a per-frame value in the glue. C: a multiply-add per vertex.

### 2. Reprojection, previous-frame data, history fetch
- Iris gives gbufferPreviousModelView, gbufferPreviousProjection, previousCameraPosition and the Iris-only cameraPositionFract/Int pairs with previous forms (R3); no previous shadow matrices or depth. OptiFine's at_velocity, "vertex offset to previous frame" for entities and block entities (R14), is not in R3 [verify in jar]: motion is camera-only. cameraPosition resets every 30000 blocks or after a teleport over 1000 (R3): take the delta from the Fract/Int pairs.
- Dilation: the 3x3's closest depth (R4 USE_DILATION; R5 "I prefer velocity at the closest depth"), in 4 gathers (docs/gpu-iris.md#bandwidth [PB v, ALC v]).
- Still camera: reprojection is the identity and Catmull-Rom one texelFetch (docs/playbook.md#52-cpu-side [PB b]); every perf view is still, so cost rows measure that path (docs/measurement.md#baseline-suite).
- Hand: MC_HAND_DEPTH scales its clip depth (R3), so gbufferProjection misreprojects it; fixed in view space, it takes the identity [inferred].
- Fetch: Catmull-Rom's 16 reads drop to 9 with bilinear taps, 5 in Jimenez's Call of Duty version (R6); bilinear history is "visible blur for little time" (docs/playbook.md#6-did-not-work).
- D: equal uniforms each frame at a held pose [inferred]. I: [verify in jar: MatrixUniforms, CameraUniforms]; a new pipeline's first previous matrices go unread (history cleared). A: matrices as include arguments (docs/shader.md#pipeline-spec). C: ALU, cached gathers, 5 history fetches (1 when still).

### 3. History rectification
- R4 clips (or clamps) to a rounded 3x3 box, "only clips towards aabb center"; YCoCg is an option, off; feedback follows luminance difference, credited to Lottes; colour samples are unjittered (TemporalReprojection.shader, .cs defaults). R5: variance clip at mean +- gamma sigma, gamma 1.0, after a min/max clamp, after Salvi; "somewhat skeptical of dropping in YCoCg"; a 3x3 reconstruction filter (Blackman-Harris; Mitchell-Netravali sharper). R13 surveys accumulation and validation. Unbound: RGB min/max clip (R1).
- Ladder: Low RGB clamp, 5-tap plus; Medium YCoCg variance clip; High adds disocclusion against a stored previous linear depth.
- D: arithmetic, repeatable on one driver and binary. I: texelFetch, textureGather. A: Iris-free include. C: TAA is memory-bound (docs/gpu-iris.md#bandwidth [PB v]): an R16F previous depth, written and read, adds 4 B a pixel, about 0.05 ms [inferred].

### 4. History weight w and N_conv
- Weights: 0.9 (R6), 0.95 (R5), 0.88-0.97 by luminance difference (R4 TemporalReprojection.cs), 0.9 Unbound still (R1). N_conv, the smallest n with w^n <= 1/255 (docs/measurement.md#visual-protocol): 0.875 -> 42, 0.9 -> 53, 0.9375 -> 86, 0.95 -> 109 [inferred].
- Dead band [inferred]: an update moves h only if (1-w)|c-h| exceeds half a step, so h sticks up to 0.5/(1-w) steps off, 5 at w 0.9; likely ALC's "path-dependent rounding of +-1-2 levels" (docs/lessons.md#determinism), which only a flush makes repeat. 5 RGB10_A2 steps are 1.25/255, over 1/255 unless the write is dithered (docs/playbook.md#54-sample-count-and-precision-trades); 16F in [0.5, 1) about 0.6/255.
- Anti-flicker 1/(1+luma) weights (R5; R6 "intensity weighing") matter little after a tonemap [inferred]. A count ramp, w_eff = min(w, n/(n+1)), speeds recovery (R5 quotes "frame counting history greatly reduces ghosting"); w^n stays the bound.
- D: w is constant per variant and the harness derives N_conv, so the pipeline spec would carry w [inferred]. I, A, C: none.

### 5. Storage, validity, flush and ping-pong
- Format: RGBA16F (RGB16F pads to 8 B) or RGB10_A2 at 4 B, only after the tonemap, write dithered, sentinel exact [PB b]; PB saw near-black history quantize into the zero sentinel (docs/playbook.md#3-workflow). INSIDE ping-pongs two 8-bit ARGB32 histories (R4).
- Validity in alpha [inferred]: 0 invalid, else the count (2 bits in RGB10_A2: a ramp saturates at 3); a zero-colour sentinel also restarts truly black pixels (R1), and docs/shader.md#determinism-and-taa says zero marks history invalid. The flush writes the current colour, count 1.
- Reset: a new pipeline clears every colortex (docs/gpu-iris.md#frame-counters-and-reload); custom images are zeroed at creation by ARBClearTexture.glClearTexImage (R2 GlImage), an ARB_clear_texture (GL 4.4) call.
- Iris's flip costs a copy: what a composite pass writes flips unless a flip directive says no (R2 CompositeRenderer); flips toggle (R2 BufferFlipper); after final, each buffer left flipped and not cleared per frame is copied alt to main by glCopyTexSubImage2D: "We don't actually fully swap the content, we merely copy it from alt to main" (R2 FinalPassRenderer) [verify in jar]. RGBA16F: 133 MB, 0.21 ms at 624 GB/s; RGB10_A2 0.11 ms [inferred, R11].
- Explicit ping-pong: (a) two colortex and a copy pass: its target flips too, so the frame-end copy stays unless it is written an even number of times [inferred, R2]; (b) two custom images, imageStore into the one at frameCounter mod 2, the other sampled: no copy. They need "OpenGL 4.2 support" (R3); CUSTOM_IMAGES follows supportsImageLoadStore (R2 FeatureFlags): glBindImageTexture's pointer, GL 4.2, or a load-store extension plus ARB_buffer_storage (R2 IrisRenderSystem). On the "3.3.0 Core Profile Context" (docs/platform.md#mc-263-verified) the driver's extensions decide, ARB_clear_texture too. Iris issues glMemoryBarrier after computes (R2 CompositeRenderer); after a fragment imageStore, unknown [verify in jar]. (c) Compute also needs glDispatchCompute's pointer (R2 supportsCompute).
- D: parity from frameCounter; the flush resets every temporal buffer. I: colortexNClear, Format, flip (R3); image.* [verify in jar]. A: no flipping, every texture explicit (docs/platform.md#renderer-transition): (a) and (b) port. C: Medium reads 4 B colour, 4 B depth, 8 B history, writes 8 B: 24 B, 200 MB, 0.32 ms at peak, 0.3-0.45 ms expected; Unbound's extra TAA-on reads (second depth, mask, history: 20 B, 0.27 ms at peak) fit its 0.579 ms row and replay share (R12) [inferred].

### 6. Masks for what the camera cannot reproject
- FSR 2's reactive mask covers "particles, or alpha-blended objects which do not write depth or motion vectors", capped near 0.9 (R7); R6 lists blended motion vectors, UE4's "responsive AA" factor, or transparency after TAA; Unbound skips with zero history (R1).
- Proposed [inferred]: one 8-bit flag target. Entities: camera reprojection, tight clip, w capped (0.5 to start); hand: identity, tight clip; particles, weather, lines: skip, lines unjittered; water and translucents: depthtex0 where they dominate; clouds: the cloud pass's distance (docs/playbook.md#51-structural); sky: rotation only.
- D: BENCH_DETERMINISTIC discards particles, weather, lightning and vanilla clouds (docs/shader.md#determinism-and-taa), and the entities view's mobs are frozen NoAI (docs/measurement.md#baseline-suite): masks act in the live pass. I: entityId (docs/shader.md#facts), MC_HAND_DEPTH [verify in jar]. A: one explicit target. C: about 0.03 ms [inferred].

### 7. Sharpening
- CAS "was designed to help increase the quality of existing Temporal Anti-Aliasing (TAA) solutions" (R8 page); ffx_cas.h reads a 3x3 (5 taps in its circle path), "is designed to be a linear filter", warns perceptual input over-sharpens, and says "It is best to run CAS after tonemapping" (R8).
- Display copy only; history unsharpened, as in Unbound (R1); fed back, sharpening compounds [inferred]. Ladder: sharpness 0, 0.33, 0.66, 1.
- D: no state. I: final reads the TAA output. A: plain. C: 0.01-0.06 ms [inferred from R12: Unbound's 0.013 mean, 0.055 worst].

### 8. Temporal upscaling (D72 input, outside scope)
- Iris has no render scale (docs/measurement.md#validity). Photon scales clip positions toward a screen corner so gbuffers shade scale^2 of the pixels, then runs TAAU (R10 gbuffers_all_solid.vsh, shaders.properties).
- Basis: FSR 2 at 3840x2160, Quality 1.5x, DX12: 1.2 ms on an RX 6800 XT, 0.7 ms on a 7900 XTX (R7). Terrain, deferred1, composite1 and water, 67 % of Unbound's frame (docs/shader.md#method), would shade 44 % of the pixels: 1-2 ms net of a 4.6-7.7 ms frame [inferred].
- Against: every screen-space pass takes scaled coordinates; 64x textures need a mip bias, -1.58 at 1.5x (R7); 18 phases; no TAA-off frame is left for E4's fallback. Not in M5; a D72 candidate after A12.

## For Optilux
- v0, for A6 and A12 (docs/mod.md#12-acceptance: A6 on the hello pack, TAA on): 16-phase jitter, camera reprojection, RGB clip, Catmull-Rom, w 0.9, RGBA16F flipped history with alpha validity, the flush; it meets E4 and F12 before the full TAA. v1, M5: the ladder, explicit ping-pong, masks, sharpening [inferred].
- Placement: after bloom and the tonemap; final sharpens and applies underwater distortion, reading TAA's output, the history [inferred].
- Options: TAA and TAA_SHARPEN, Off/Low/Medium/High (TAA default Medium). w 0.9 and 16 phases on every level: N_conv 53 for every variant, config/pipeline.json's cycle 16 [inferred].

  | Level | History | Rejection | ms at 4K [inferred] |
  |---|---|---|---|
  | Low | RGB10_A2, dithered | RGB clamp, 5-tap plus | 0.2-0.3 |
  | Medium | RGBA16F | YCoCg variance clip, closest-depth dilation | 0.3-0.45 |
  | High | RGBA16F, previous depth R16F | + depth disocclusion, count ramp | 0.35-0.55 |

  Basis: bytes a pixel x 8.29 M pixels at 624 GB/s (R11), 70-100 % efficiency; add 0.1-0.3 ms if history flips in Iris. Unbound's 0.579 ms row is no cross-check: it carries the shadow swap and the jitter.
- Budget per view type [inferred]: every perf view in its level's band, sky-heavy ones (ocean_sunset, end_dragon) lower if depth-1 pixels skip dilation. entities and coverage views with `hand` stay apart while F12 stands: hideGUI reads 0 there every frame (docs/roadmap.md#findings-assigned F12; docs/measurement.md#session), so TAA flushes every frame.
- Rules for other topics: frame-varying terms use frameCounter mod 16, or the cycle becomes the lcm, which must divide 720720; the flush resets every temporal buffer; no history weight above w; a non-cleared buffer left flipped budgets its copy.
- Confirmation: cost by feature cost rows, Off vs each level, every perf view (docs/measurement.md#verdicts-and-cost-rows), tier review; image ping-pong vs flip by a verdict, tier identical, plus an L4 capture of the copy; RGB10_A2 vs RGBA16F by a verdict, near on night and cave, else review; the still path by a verdict, identical or near [inferred]; weight, rejection and masks by review, the live pass and the positive controls (rejection off as ghosting, jitter off as aliasing) on a camera.path sequence with ColorVideoVDP (R9: it "can also run on a CPU, but the processing times will be much longer"); the flush by A12.
- L3 golden tests (moderngl, docs/offline.md#levels): jitter in [-0.5, 0.5), mean 0 to 1e-6 once removed; N_conv 42, 53, 109 at 0.875, 0.9, 0.95, as the harness's; clip bit-exact inside, onto the box toward the centre outside, the centre for a zero-size box, NaN resets; YCoCg round trip within 2 ulp; equal matrices and zero delta return the pixel within 1e-6 at depth 0.5, 0.9, 1.0, a translation matches float64; Catmull-Rom exact at texel centres, constant in and out; valid RGB10_A2 history never alpha 0, dither mean over 16 phases within 1/4 step; |h_n - c| <= w^n |h_0 - c| + the dead band; flush: current colour, count 1; the custom uniforms in Iris's engine (docs/gpu-iris.md#custom-uniforms).

## Open questions
- F12: a flush signal that holds with the GUI shown: a periodic flush at frameCounter mod K (a multiple of 16 dividing 720720, above N_conv plus the capture, e.g. 240), a uniform the mod can move invisibly (none in R3), or the entities view keeps its hand another way. Decides: the user at M5, then A12 at entities.
- Custom images on the 3.3.0 context? Decides: a dump run's IRIS_FEATURE_CUSTOM_IMAGES, MC_GL_ARB_shader_image_load_store and MC_GL_ARB_clear_texture (docs/gpu-iris.md#programs-and-alpha-tests); javap of IrisRenderSystem and GlImage.
- In 1.11.7: the toggling flip, the frame-end copy, at_velocity? Decides: javap of BufferFlipper, FinalPassRenderer and the vertex formats; one L4 capture.
- Jitter amplitude: full +-0.5 px or Unbound's small one (its lang: higher jitter brings "a lot of flickering and blur")? Decides: the look review against D72's target on forest_noon and the coverage views, with sharpening.
- TAA before or after the tonemap (RGB10_A2 needs after)? Decides: the tonemap topic and emissive flicker in the live pass.
- ColorVideoVDP in useful time here? Decides: a timed CPU run of a 4K 120-frame sequence and both positive controls.
- Entity weight cap; hand and particles skipped or accumulated? Decides: the live pass with moving mobs.
- Hand by depth under 26.3's forward Z, or a flag? Decides: depth values in a capture at entities.
- TAA-off variants, cycle 1 or 16? Decides: the pipeline spec's owner; 16 costs at most 16 frames of alignment.
