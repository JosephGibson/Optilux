# Ambient occlusion
Status: research for Optilux's ambient occlusion (M4's lighting hooks, M5's AO pass): screen-space families, resolution, noise and TAA reliance, vanilla AO, and Unbound's SSAO with its cost. Nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
Tags as docs/gpu-iris.md#sources-and-tags; [inferred] marks reasoning, not reading. Web pages read 2026-10-26.
- R1 Jimenez, Wu, Pesce, Jarabo, "Practical Realtime Strategies for Accurate Indirect Occlusion" (GTAO), Activision ATVI-TR-16-01, 2016, paper; abstract page only: https://research.activision.com/publications/archives/atvi-tr-16-01practical-realtime-strategies-for-accurate-indirect-occlusion
- R2 XeGTAO, Intel, 2021, MIT, archived 2024, vendor sample (README; DirectX 12 compute): https://github.com/GameTechDev/XeGTAO
- R3 Therrien, Levesque, Gilet, "Screen Space Indirect Lighting with Visibility Bitmask", The Visual Computer 2022, paper (abstract): https://arxiv.org/abs/2301.11376
- R4 Bevy 0.15 release notes, 2024, engine doc: https://bevy.org/news/bevy-0-15/
- R5 McGuire, Mara, Luebke, "Scalable Ambient Obscurance", HPG 2012, paper (abstract): https://research.nvidia.com/publication/2012-06_scalable-ambient-obscurance
- R6 HBAO+ README, NVIDIA, vendor doc: https://github.com/NVIDIAGameWorks/HBAOPlus
- R7 FidelityFX CACAO 1.4 manual, AMD, vendor doc: https://gpuopen.com/manuals/fidelityfx_sdk/techniques/combined-adaptive-compute-ambient-occlusion/
- R8 Klehm, Ritschel, Eisemann, Seidel, "Bent Normals and Cones in Screen-space", VMV 2011, paper (listing only): https://diglib.eg.org/items/2cf56bda-f0f2-45a1-9c7f-330f690e58ca/full
- R9 Lysenko, "Ambient occlusion for Minecraft-like worlds", 0fps, 2013, blog: https://0fps.net/2013/07/03/ambient-occlusion-for-minecraft-like-worlds/
- R10 Interleaved gradient noise (Jimenez, 2014, not opened) as described by demofox, 2022, blog: https://blog.demofox.org/2022/01/01/interleaved-gradient-noise-a-different-kind-of-low-discrepancy-sequence/
- R11 Photon (sixthsurge), pack source, Photon Shaders License Agreement, branch main (shaders/program/d3_ao.fsh, d4_deferred_shading.fsh; shaders/include/lighting/): https://github.com/sixthsurge/photon
- R12 Iris source, branch 1.21.9, not the pinned 1.11.7 (IrisRenderSystem, ShaderProperties, PackDirectives, WorldRenderingSettings): https://github.com/IrisShaders/Iris/tree/1.21.9/common/src/main/java/net/irisshaders/iris
- R13 OptiFine shaders.properties doc, vendor doc: https://github.com/sp614x/optifine/blob/master/OptiFineDoc/doc/shaders.properties
- R14 Iris feature flags, vendor doc: https://github.com/IrisShaders/ShaderDoc/blob/master/iris-features.md
- R15 Wisdom Shaders V3 Build3300, Apache-2.0, pack source: reference/wisdom-shaders-v3-build3300/shaders/ (Lighting.glsl.frag, composite2.fsh, GlslConfig)
- R16 ALC's ablations [m]: config/profiles/complementary-unbound-played.json; MC 1.21.11, Iris 1.10.7, RX 7800 XT, 4K, ALC's views (docs/gpu-iris.md#sources-and-tags); context only: "the platform, pack build and views all differ" (docs/design.md#6-milestones).
- R17 ARB_gpu_shader5, Khronos extension spec: https://registry.khronos.org/OpenGL/extensions/ARB/ARB_gpu_shader5.txt
- Unbound r5.9.3: Complementary License Agreement 1.7 (a Modified Pack only on its section 1.3 terms); studied, never copied (docs/shader.md#policy); files under reference/complementary-unbound-r5.9.3/shaders/.

## Unbound r5.9.3
- Pass: deferred1, full resolution, opaque depth, before translucents, beside clouds and sky fog (program/deferred1.glsl; docs/shader.md#method). It multiplies the forward-lit colortex0, so it darkens sun, sky and block light alike [inferred from the order].
- Estimator: depth only, no normal; tap pairs mirrored about the pixel, spreading outward with the tap index. A tap occludes when more than about a quarter block in front of the centre and stops counting between one and two blocks in front; a pair occludes only when both taps do, so a plane does not occlude itself [inferred from the code]. Pairs are averaged, the mean softened by a power from SSAO_I. The world-space radius is projected by the FOV and the pixel's distance with a near clamp, so near geometry spreads the taps far apart (program/deferred1.glsl).
- Levels: SSAO_QUALI_DEFINE 0, 2 (default, kept by `played`) or 3: 0, 4 or 12 pairs, 8 or 24 depth fetches per pixel; SSAO_I 0 also turns it off (lib/common.glsl).
- Cost [ALC m, R16]: SSAO_QUALI_DEFINE=0 saves 0.138 ms mean and 0.394 ms at underwater, its worst view. deferred1 is 12 % of a 4.6-7.7 ms frame (docs/shader.md#method), about 0.55-0.9 ms, so SSAO is about 15-25 % of it; underwater has no sky to skip and near terrain everywhere [inferred].
- Noise: the pack's own 128-pixel noise texture (shaders.properties texture.noise; lib/pipelineSettings.glsl), advanced by the golden ratio x (frameCounter mod 3600) only under TAA, static with TAA off; no blur, no history: TAA is the only denoiser (program/deferred1.glsl).
- Exclusions: the hand, by a depth threshold below about 0.56 given Iris 1.11.7's MC_HAND_DEPTH 0.125 (optilux/offline.py, FIXED_MACROS) [inferred]; entities, the hand, lightning and most particles write a material code that resets SSAO to 1 (lib/materials/materialHandling/deferredMaterials.glsl) and skips TAA (lib/antialiasing/taa.glsl).
- Vanilla AO: separateAo = true (shaders.properties). Lighting reads it from the vertex colour's alpha; on terrain it reshapes it per dimension by the up-facing normal (in the Overworld also sky light), floors it, applies VANILLAAO_I as a power and scales every diffuse term but emission (lib/lighting/mainLighting.glsl). Two AO layers multiply: per vertex, then SSAO.
- No camera-distance fade; only the projected radius shrinks.
- Other packs: Wisdom V3 (R15) blurs a normal-based obscurance under a Bayer dither, applies it to ambient and torch light and to sun only on plants, and turns vanilla AO off (ambientOcclusionLevel 0 by default). Photon (R11) runs GTAO at half resolution with a bent normal and its own age-capped history (Catmull-Rom, depth rejection, frameCounter noise), upsamples 4 texels weighted bilinear x depth, and applies AO to sky, ambient, block and bounced light, to direct sun only under AO_IN_SUNLIGHT. It reads and writes its history at one colortex index, relying on Iris's flip [inferred], which Aperture lacks (docs/platform.md#renderer-transition).

## Techniques
Checked against Det (docs/shader.md#determinism-and-taa), Iris (1.11.7, 3.3 core; every Iris fact [verify in jar]), Aperture (docs/shader.md#pipeline-spec) and Cost (4K, this GPU). Cost unit: R16's 0.138 ms for 8 full-resolution taps, about 0.017 ms per full-resolution fetch per pixel [inferred; its mean includes skipped sky]. TAA-reliant: only TAA's history resolves the noise, so TAA-on frames depend on A12; under E4's fallback (docs/design.md#8-open-decisions) they get review only.

### T1 Pair-difference SSAO (Unbound's class)
- Claim: creases from depth alone, no normal or cosine weighting: a mask shaped by its constants, not an occlusion estimate [inferred].
- Cost: 0.138 ms mean, 0.394 ms worst for 8 taps [ALC m, R16]; 24 taps 2-3x [inferred]. Det: TAA-reliant. Iris: depthtex0 in deferred. Aperture: portable. Use: the reference to beat.

### T2 Horizon-based AO (HBAO, GTAO)
- Claim: per slice, march both sides for the highest horizon and integrate visibility in closed form. R1's abstract: it can "match a ground truth reference in half a millisecond on current console hardware", using "spatio-temporal filtering" (no resolution given).
- R2 defaults to "3 slices per pixel with 6 samples (3 per side) each for a total of 18spp" at full resolution, with a lower preset of "2 slices per pixel and 4 samples (2 per side)"; the "Original GTAO implementation runs at half-resolution with one slice per pixel, 12 samples per hemisphere slice". It stores fp16 view-space depth with a prefiltered MIP chain and turns thin-occluder compensation off "for performance reasons".
- Multi-bounce: R2 cites R1's "multi-bounce diffuse" fit; Photon uses one (R11). Look decides.
- Needs a per-pixel normal: terrain normals are axis-aligned except on plants, and lighting's normal beats one rebuilt from depth, which breaks at block edges [inferred].
- Cost: High at full resolution "costs roughly 1.4ms at 3840x2160 on RTX 3070" and 0.56 ms at 1920x1080 on RTX 2060 (ASSAO Medium about 0.72 ms there); Medium is "roughly 2/3" of High (R2) [vendor m, NVIDIA]. Here, half resolution, 1 slice, 4 steps a side is 2 full-resolution-equivalent fetches (about 0.035 ms by the unit) plus heavier per-step maths; with T5 and T6, 0.10-0.20 ms [inferred]. Full-resolution High: 1.4 ms or less only if this GPU at least matches an RTX 3070 [inferred; no AMD number found].
- Det: TAA-reliant (the slice rotates by frameCounter mod C, T7); with TAA off, index 0 plus T6 gives a frame-invariant image. Iris: half-size deferred fragment passes, RG16F; no compute, SSBO or flip. Aperture: the march in an Iris-free include; no history, so no ping-pong.

### T3 Visibility-bitmask AO (VBAO)
- Claim: "replaces the two horizon angles by a bit field representing the binary state (occluded / un-occluded) of N sectors", letting light "pass behind surfaces of constant thickness" (R3). Bevy "replaced our old GTAO algorithm entirely", the gain "particularly important on thin geometry" (R4). Minecraft is full of thin geometry, where horizon AO darkens what lies behind a fence as if a wall stood there [inferred].
- Cost: no measured number (R3's abstract: "low performance overhead"). Each tap adds two angle-to-bit conversions and an OR; the count needs bitCount, GLSL 4.00 or ARB_gpu_shader5 (R17), not #version 330 core, else a manual popcount. Expect GTAO plus 10-30 % [inferred].
- Det, Iris, Aperture: as T2. Its indirect-light form (SSIL) is outside the in-scope list (D72 input).

### T4 Bent normals
- Claim: the mean unoccluded direction, for directional sky or ambient lookups (R8). GTAO derives it from the same horizons; in R2 it "increases overal effect computation time by roughly 25%", packed in RGBA8 with AO in alpha. Photon feeds it only to a spherical-harmonics sky light (R11).
- Use: only if lighting's sky light is directional [inferred]. Det, Iris, Aperture: as T2, one RGBA8 output more.

### T5 Half resolution, depth-aware upsample
- Claim: docs/playbook.md#51-structural [PB b]: the representative pixel, the -0.5 texel offset, 4 texels weighted bilinear x depth similarity, 1/viewZ per texel with sky as 0, a low-confidence fallback. GTAO ran at half resolution (R2); CACAO's downsampled mode ends in "an additional bilateral upsample" (R7); Photon uses the 4-texel form (R11). Against it: HBAO+ renders "in full resolution, from full-resolution depths" to minimize flickering (R6).
- Cost: a quarter of the AO pixels; the upsample, fused into the consumer, is two textureGathers per pixel on one RG16F (AO, 1/viewZ): 0.03-0.06 ms [inferred]. Gathering the second channel needs ARB_gpu_shader5's component select (R17); without it, two R16F textures or texelFetches. Det: frame-invariant.
- Pitfalls: a half-pixel offset shifts the whole field (docs/playbook.md#51-structural); features one or two pixels wide lose AO; the AO pass reads its representative pixel's own jittered depth.
- Iris: `size.buffer.colortexN = 0.5 0.5` draws the pass at that size while viewWidth stays full (docs/gpu-iris.md#passes-and-buffers [PB v], 1.10.7). R13: fixed-size buffers only from prepare, deferred and composite, never beside normal ones in one pass, all of one size. Aperture: an explicit half-size texture.

### T6 Denoise: spatial, TAA, or an AO history
- R2 "uses only a 5x5 depth-aware spatial denoising filter and relies on TAA for the temporal component". Unbound has neither; Wisdom blurs (R15); Photon keeps a history (R11).
- A filter covering one period of the rotation pattern sees every rotation each frame, so TAA-off frames are smooth and TAA averages the rotations [inferred]. IGN (T7) has no 4x4 period: use a 4x4 interleaved rotation set [inferred].
- An AO history: a second history for the flush to clear in the same frame, with its own N_conv, previous-frame matrices and ping-pong pair, repeating TAA's work [inferred]. Not in the first version.
- Cost: a 4x4 depth-aware box at half resolution, 8 gathers per half-resolution pixel: 0.03-0.07 ms [inferred]. Det: frame-invariant. Iris: a half-size deferred pass (T5). Aperture: writes a second texture, never the one it reads.

### T7 Noise and per-frame rotation
- IGN (R10) is arithmetic, and "every 3x3 block of pixels makes a low discrepancy set", which suits TAA's 3x3 clamp box. demofox's frame index wraps at 64, as R2's noise offset does (frameIndex mod 64). Neither 64 nor Unbound's 3600 divides 720720 = 2^4 x 3^2 x 5 x 7 x 11 x 13, so Optilux wraps at 16 [inferred].
- docs/playbook.md#54-sample-count-and-precision-trades: "SSAO: half the sample pairs per frame, alternating" [PB b], tier review, cycle 2 [inferred].
- Det: index = frameCounter mod C, C the pack cycle (config/pipeline.json, 1 today); 0 with TAA off, as Unbound's noise is static then. Cost: a few ALU instructions. Iris, Aperture: arithmetic in the include.

### T8 Vanilla per-vertex AO and sky light
- Claim: voxel vertex AO counts a vertex's two side neighbours and corner, "4 possible ambient occlusion values", and needs a consistent quad diagonal (R9); its scale is one block [inferred]. It sits in the vertex colour unless separateAo moves it (R13); the hello pack multiplies the vertex colour through (shader/shaders/lib/surface_vertex.glsl, surface_fragment.glsl).
- separateAo: "the AO brightness (smooth lighting) is separated from" the RGB "and put in" the alpha (R13). Iris parses it, and a change sets reloadRequired (R12), which re-meshes [inferred]. ambientOcclusionLevel (clamped to 0-1, R12) is a 1.11.7 const option (optilux/offline.py, CONST_OPTIONS).
- Both layers detect concave corners, so multiplying them, as Unbound does, darkens corners twice; min() or a softened vanilla curve avoids it [inferred]; look decides.
- AO belongs on indirect terms (sky, ambient, block light); direct sun is the shadow map's, as in R11 (by default) and R15. The lightmap's sky level already gives coarse occlusion, so screen-space AO adds the small and middle scales [inferred].
- Det: per vertex, exact. Cost: no pass. Aperture: vertex AO delivery unknown.

### T9 Distance fade
- Far away the projected radius shrinks to a few pixels, the estimate turns to noise, and fog hides it [inferred]. Unbound does not fade it; Photon only shrinks its radius near the camera (R11). Fade AO to 1 over a band inside the fog and branch out beyond it.
- Det: the band reads far or a constant, never fogStart or fogEnd, which the wall clock eases (docs/shader.md#determinism-and-taa). Cost: saves the pass on far terrain [inferred]. Iris, Aperture: arithmetic in the include.

### T10 Later: depth MIP, deinterleave, compute
- SAO's improvements, a depth prefilter among them, "collectively produce a 7x performance increase at 2560x1600" (R5); CACAO splits depth into "four separate textures, each a quarter of the resolution" (R7). At half resolution with small radii one level suffices, and Iris's mipmap flags (docs/gpu-iris.md#passes-and-buffers) would average depth across edges, so a depth MIP takes explicit passes [inferred]. Iris enables compute when glDispatchCompute resolves (R12; flags in R14), unknown on the 3.3 core context. Optimization phase only.

## For Optilux
### First version
- M4, lighting: separateAo = true; vanilla AO, on its own curve, scales only the indirect terms, kept separable for deferred (a channel, or deferred lighting if E2 picks it); lighting provides a normal for the AO pass.
- M5, `ao_trace` (deferred, half size): T2 with 1 slice, T9's fade, hand and sky skipped, rotation as in T7; writes RG16F (AO, 1/viewZ).
- M5, `ao_filter` (deferred, half size): T6's 4x4 depth-aware box into a second RG16F.
- Consumer (lighting's deferred pass): T5's upsample; AO on the indirect terms, combined with vanilla AO by the rule the look review picks (T8).
- No AO history; TAA is the temporal part. Entities: Unbound leaves them out; look decides at entities and coverage_mobs.
- Vanilla `ao` is identity (docs/run-record.md#identity: every unwritten options.txt key); the calibration records hold "true" (results/records/cal-full-4edbb05a97ab-1-p1.json).

### Options and levels
One option, AO_QUALITY; no intensity knob, proposed from docs/shader.md#look-and-scope's "fewer look knobs than Unbound".

| Level | Pass | Taps | Extras |
|---|---|---|---|
| Off | none | 0 | vanilla AO only |
| Low | half | 1 slice x 2 a side | 4x4 filter |
| Medium | half | 1 slice x 4 a side | 4x4 filter |
| High | half | 2 slices x 4 a side | thickness (T3); bent normal only if lighting reads it |

### Cost hypothesis
Medium against Off, TAA on [inferred from T2, T5, T6], beside Unbound's SSAO row (R16, ALC's views):

| Views | Medium | Unbound SSAO |
|---|---|---|
| forest_noon, ocean_sunset, rain, night | 0.08-0.15 ms | mean 0.138 |
| cave, underwater, nether_crimson, nether_soul, end_city, entities | 0.12-0.25 ms | underwater 0.394 |
| end_dragon | under 0.08 ms | - |

Low about 0.6x Medium, High 1.6-2x [inferred].

### Dependencies
- lighting: where AO applies, the normal, the vanilla curve, E2.
- taa: C, N_conv, the flush, jitter and the representative pixel.
- shadows: a shared noise scheme, decorrelated from AO's.
- clouds: one shared half-size depth texture and representative-pixel rule.
- fog-volumetrics: the fade band.
- water: AO before translucents; underwater the worst case.
- reflections: specular occlusion (GTSO, R1 via R2).
- sky: sky pixels skipped; a bent normal only for a directional sky.
- iris: the capability list. next-gen: SSIL and voxel AO, for D72.

### What would confirm each claim
- Cost: cost rows per level against Off on all 11 views, full mode (docs/measurement.md#verdicts-and-cost-rows); at the 0.5 % floor, on frames of a few ms, a row resolves about 0.02 ms [inferred]. The worst view: those rows plus L4 attribution (docs/offline.md#levels).
- Look: a feature goes to review beside Unbound's `played` frames (docs/measurement.md#visual-protocol); TAA-off frames are deterministic (index 0), TAA-on ones captured 64 frames after an aligned flush (A12), or review only under E4's fallback.
- Later optimizations (gather upsample, depth MIP) must be identical or near; the alternating pairs go to review.
- Live pass: shimmer at leaf edges (forest_noon), AO trails at disocclusions, hand edges.

### L3 golden tests
- A plane at several tilts and FOVs gives AO 1 within the fp16 1/viewZ tolerance; a 90-degree crease matches the closed form against a numpy quadrature; a box on a floor leaves no occlusion beyond the falloff radius.
- VBAO: a thin wall occludes only its own sectors; the manual popcount equals bitCount on random words.
- Upsample: a constant stays constant; a half-resolution step lands on the right pixel; with every weight low the fallback is taken.
- Noise: index(f) = index(f + C), C divides 720720, one period of the pattern holds every rotation once, TAA off gives one index.
- Fade: AO is 1 at and beyond the band's end, and continuous. 1/viewZ survives the fp16 round trip; sky stays 0.
- The radius custom uniform, evaluated in Iris's engine (docs/gpu-iris.md#custom-uniforms).

## Open questions
- Does separateAo on Iris 1.11.7 with Sodium 0.9.2 put terrain AO in vaColor.a, and do entities carry any? Decided by a debug variant writing vaColor.a, read in an L1 dump and an L4 capture.
- Where does AO apply under forward lighting? Decided by the lighting research and E2's build at forest_noon.
- Does half resolution shimmer at leaves under jitter? Decided by a motion path, the live pass, and ColorVideoVDP once the positive controls pass.
- GTAO or VBAO on thin geometry? Decided by review frames at forest_noon and the coverage views, plus cost rows.
- Vanilla and screen-space AO: min or multiply? Decided by review.
- textureGather's component select, bitCount and compute on the 3.3 core context? Decided by MC_GL_ARB_texture_gather, MC_GL_ARB_gpu_shader5 and MC_GL_ARB_compute_shader in a dump's defines (docs/gpu-iris.md#programs-and-alpha-tests).
- Should entities receive AO? Decided by look review at entities and coverage_mobs.
