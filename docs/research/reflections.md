# Block reflections and rain puddles
Status: research on screen-space block reflections and rain puddles over the minimal material map, for M4-M5 and D72. It is sourced research, not yet measured in Optilux.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
- R1 McGuire, Mara 2014, "Efficient GPU Screen-Space Ray Tracing", JCGT 3(4), paper: https://jcgt.org/published/0003/04/04/ (not read; claims via R2).
- R2 McGuire 2014, "Screen Space Ray Tracing", blog post on R1: https://casual-effects.blogspot.com/2014/08/screen-space-ray-tracing.html
- R3 Stachowiak, Uludag 2015, "Stochastic Screen-Space Reflections", SIGGRAPH Advances, slides: https://www.slideshare.net/slideshow/stochastic-screenspace-reflections/51840375
- R4 Uludag 2014, "Hi-Z Screen-Space Cone-Traced Reflections", GPU Pro 5, chapter (not read): https://gameenginegems.com/gemsdb/article.php?id=1221
- R5 AMD FidelityFX SSSR, vendor doc: https://gpuopen.com/manuals/fidelityfx_sdk/fidelityfx_sdk-page_techniques_stochastic-screen-space-reflections/
- R6 Wronski 2014, "The future of screenspace reflections", blog: https://bartwronski.com/2014/01/25/the-future-of-screenspace-reflections/
- R7 Lagarde 2013, "Water drop 3b - Physically based wet surfaces", blog: https://seblagarde.wordpress.com/2013/04/14/water-drop-3b-physically-based-wet-surfaces/
- R8 Lagarde 2013, "Water drop 2b - Dynamic rain and its effects", blog: https://seblagarde.wordpress.com/2013/01/03/water-drop-2b-dynamic-rain-and-its-effects/
- R9 Karis 2014, "Physically Based Shading on Mobile", vendor blog, an analytic environment BRDF after Lazarov (fetch refused; read via search): https://www.unrealengine.com/en-US/blog/physically-based-shading-on-mobile
- R10 Iris docs (shaders.properties), vendor doc: https://shaders.properties/current/reference/ (colortex, depthtex, custom_images, ssbo, colortex_mipmaps, programs overview, mc_hand_depth, uniforms).
- R11 Iris source, branch 1.21.9, not the pinned 1.11.7: https://github.com/IrisShaders/Iris/tree/1.21.9/common/src/main/java/net/irisshaders/iris/ (CommonUniforms, SmoothedFloat, SmoothFloat, NativeImageBackedNoiseTexture, IrisRenderSystem).
- R12 Photon (sixthsurge), pack source, Photon Shaders License Agreement (custom; "Examine and learn from" allowed): shaders/include/misc/raytracer.glsl, lighting/specular_lighting.glsl, surface/rain_puddles.glsl in https://github.com/sixthsurge/photon
- R13 PS4 "1.84 Teraflops", "176 GB/second" (Sony 2013: https://www.engadget.com/2013-02-20-sony-further-details-playstation-4-hardware-specs.html); RX 7800 XT 3840 shaders at 2430 MHz, 624.1 GB/s, 37.32 TFLOPS with dual issue (spec site: https://technical.city/en/gpu/Radeon-RX-7800-XT).
- Unbound r5.9.3: reference/complementary-unbound-r5.9.3/ (Complementary License Agreement 1.7; studied, never copied: docs/shader.md#policy).

## Unbound r5.9.3
- Played draws no block SSR: config/profiles/complementary-unbound-played.json sets BLOCK_REFLECT_QUALITY 1 and RP_MODE 0, RAIN_PUDDLES stays 0; shaders/lib/common.glsl enables PBR_REFLECTIONS only from quality 2 with RP_MODE 1 or more, and lang/en_US.lang calls Low "Sun/moon highlights only". So ALC's BLOCK_REFLECT_QUALITY=0 row (0.132 ms mean, rain 0.303) prices the GGX highlight of lib/lighting/mainLighting.glsl, not SSR [ALC m; MC 1.21.11, Iris 1.10.7]. ALC never measured Unbound's SSR or puddles.
- Trace (program/composite.glsl, lib/materials/materialMethods/reflections.glsl) where no translucent covers the pixel and the stored reflection weight lies strictly between 0 and 1:
  - half resolution by default: composite writes colortex7 and colortex1, sized by REFLECTION_RES (shaders.properties), default Half (common.glsl);
  - the normal is offset by noisetex (Unbound's own lib/textures/noise.png) scaled by (1 - smoothness) squared; the dither turns each frame by a golden-ratio step on frameCounter mod 3600;
  - a view-space march from a start pushed off the surface; the step doubles to a fixed count, and refinements step back and shrink it on a near hit; the dither scales each step slightly;
  - a hit needs depth below 1.0 and an error under a tolerance growing with distance, loosened by Fresnel; screen edges fade it;
  - colour: colortex5, deferred1's pre-fog lit colour (RGBA8, square-root encoded: lib/pipelineSettings.glsl), mipmapped by composite's flag, LOD from smoothness and hit distance.
- Fallback (reflectionBackground.glsl): sky along the ray x a sky-light factor; the End sky, stars and beams; black in the Nether.
- Temporal (PBR_REFLECTIONS): colortex7 (Clear false) accumulates through buffer flipping, reprojecting a virtual reflected point with the previous matrices; history drops on motion, normal change (last normals in colortex1), depth change and off-screen; the minimum blend toward the new frame is 0.035 at smoothness 0, rising with smoothness. Spatial: reflectionBlurFilter.glsl, a 5x5 normal-aware Gaussian with a dithered radius.
- Puddles (program/gbuffers_terrain.glsl, overworld):
  - mask: near-full sky light x low block light x an upward normal x inRainy, a smooth() of biome_precipitation (shaders.properties); lava and snow opt out;
  - the mask x wetness to the 4th power gates it; three octaves of noisetex over world XZ place it, the threshold biased by the square root of wetness;
  - normal: two noise taps scrolled by frameTimeCounter, blended in by rainFactor (a smooth() of rainStrength); reflection smoothness goes to 1;
  - at quality 1 a forward low-quality sky reflection is added, so puddles work under RP_MODE 0; the fix under glass (PUDDLE_VOXELIZATION) needs colored light.
- Under BENCH_DETERMINISTIC it breaks on frameTimeCounter ripples, the wetness and smooth() uniforms, a 3600-frame dither period (not a divisor of 720720) and colortex7 history built while chunks re-mesh.

## Techniques
### T1 Sky-only reflection (Low)
- Claim: weight the sky colour along the reflected ray by an analytic environment BRDF (R9: built so mobile avoids the LUT fetch), gated by sky light; glossy blocks and puddles reflect with no trace. Unbound scales its fallback by a sky-light factor; Photon applies a skylight falloff to a projected sky map (R12).
- Cost: one sky evaluation or sky-map fetch per reflective pixel; <= 0.1 ms on rain [inferred: ALU on a minority of pixels].
- Determinism: nothing per-frame if the sky reads no smoothed uniform (sky topic); no accumulation. Iris: sky light from vaUV2 (docs/shader.md#facts). Aperture: sky and BRDF in Iris-free includes.

### T2 Screen-space march with binary refinement
- Claim: R2, "Due to perspective, marching in regular steps along a 3D ray doesn't generally give 2D steps across the screen"; R1 steps in screen space (DDA): "25 iterations for every pixel on the screen at 1920x1080 in less than 1 ms on a high-end GPU" (GeForce Titan), about 5 ms on a GeForce 650M (R2). Photon: equal screen-space steps to the edge, then binary search (R12); Unbound: a growing view-space step; neither uses depth mips.
- Thickness: "Depth buffer is essentially a heightfield" (R6); R2's code gives each pixel a camera-space thickness; Photon's tolerance is the larger of a multiple of the per-step depth change and a term falling with view depth squared (R12). For blocks [inferred]: max(k x per-step delta, about half a block); reject hits whose normal faces along the ray.
- Pitfalls: push the start off the surface; depth 1.0 is a miss; reject rays toward the camera early (Photon); fade where rays "exit viewport area" (R6); depthtex is forward (docs/platform.md#mc-263); the hand: Photon tests a hand depth; Iris has MC_HAND_DEPTH and depthtex2, which "excludes transparent and hand geometry" (R10) [verify in jar: valid in deferred].
- Cost: N depth fetches plus K refinements per traced pixel; N from an int custom uniform, as constant-count fetch loops unroll fully (docs/gpu-iris.md#occupancy).
- Determinism: fixed counts, a spatial-hash dither (cycle 1) or frameCounter mod the TAA cycle, no history. Iris: depthtex1, gbufferProjection and inverse (R10) [verify in jar]. Aperture: trace in an Iris-free include, fetch in glue.

### T3 Roughness from a colour mip chain
- Claim: blur grows with roughness and hit distance; R6: "Use blur with varying radius (according to surface roughness)". Unbound sets the LOD from smoothness and hit distance; Photon raises the mip with roughness, capped at 5 (R12); R4 cone-traces over Hi-Z (title only). Deterministic, no temporal reliance.
- Iris: `const bool <buffer>MipmapEnabled = true;` has the chain "generated directly before the program where the directive is included", again before each such program (R10): one program holds it. R10 lists begin, prepare, deferred and composite; ALC verified composite, deferred and final (docs/gpu-iris.md#passes-and-buffers) [verify in jar].
- Cost: 0.06-0.1 ms per unread chain at 4K (docs/gpu-iris.md#bandwidth) [ALC m, PB m; Iris 1.10.7]. Coarse mips bleed across depth edges and smear HDR highlights [inferred]. Aperture: mips of explicit textures are open.

### T4 Half-resolution tracing
- Claim: R3, "Raytrace at a reduced resolution" and "Reuse multiple rays at full-res"; Unbound defaults to half. R6: at half resolution "even more aliasing is present" and "more intensive flickering".
- R3, PS4, Frostbite testbed, 1600x900, every pixel reflective, all passes compute: 1 ray per half-res pixel, 4 resolve samples, 2.19 ms (as extracted: linear trace 0.20, Hi-Z trace 0.37, resolve 0.81, temporal 0.30); 2 rays 3.34 ms; 4 rays with 1 resolve sample 4.41 ms.
- Scaling [inferred]: 4K has 5.76x the pixels; the 7800 XT has 3.5x the PS4's bandwidth and about 10x its FP32 without dual issue (R13), so R3's trace stages (0.57 ms) become 0.3-0.95 ms and its pipeline 1.3-3.6 ms, every pixel reflective; a fragment-pass linear march may cost more per ray.
- Optilux: docs/playbook.md#51-structural's representative pixel and depth-aware upsample, plus normal and smoothness similarity [inferred]. Iris: a pass whose buffers share one size draws at that size (docs/gpu-iris.md#passes-and-buffers) [verify in jar]; no gbuffers program can write a resized buffer (R10). Deterministic. Aperture: an explicit half-size texture.

### T5 Hierarchical Z
- Claim: R3 takes a "Stackless ray walk of min-Z pyramid", up a level above the cell's depth, down below it. R5 builds "A pyramid of 7 mip maps" with its Single Pass Downsampler and traces "from full-rate for mirror reflections" down to quarter rate.
- Iris: the mip flag filters, it does not min-reduce [inferred]; a min-Z chain needs passes into an atlas or compute with imageStore. R10: "Compute shaders require OpenGL 4.3 support", "Custom images require OpenGL 4.2 support"; the context is 3.3 core, but R11 tests entry points (glDispatchCompute; glBindImageTexture or the load/store extensions), so extensions may enable both [verify in jar]. `check L0` refuses compute (docs/offline.md#levels).
- Deterministic. Aperture merges composite and compute (docs/platform.md#renderer-transition, an outdated guide). Not for the first version: few pixels reflect [inferred].

### T6 Stochastic SSR with a temporal resolve
- Claim: R3 uses importance-sampled rays, ray reuse and a neighbourhood-clamped temporal filter, adding reflection depth to the reprojection because G-buffer depth "smears". R5: SSSR "is not a temporal algorithm", but its denoiser needs motion vectors and its blue noise changes "every frame based on the frame index". Photon samples GGX VNDF rays with per-frame noise (R12).
- Determinism: needs TAA or a reflection history, so A12; the flush must zero it too. N_conv follows the slowest history: Unbound's 0.035 blend (w 0.965) needs 156 frames, 53 at w 0.9 (docs/measurement.md#visual-protocol). E4's fallback: review tier only (docs/design.md#8-open-decisions).
- Iris: Unbound's self-read relies on "Each colortex sampler actually contains two buffers" (R10); Aperture needs explicit ping-pong. Cost: R3's rows scaled as in T4 [inferred].

### T7 Puddles
- Wet look (R7): "We lerp between no attenuation (1.0) and full attenuation (0.2) based on porosity"; an empirical factor limits the gloss boost; water's 0.02 F0 against 0.04 is "not visible enough in game", so specular colour stays; puddles are flat and "blended to water properties".
- Occlusion: R8 renders a rain-direction depth map (256x256; ~0.32 ms PS3, ~0.20 ms Xbox 360). Sky light does it for free: Unbound needs near-full sky light, Photon above 14/15, both suppress block-lit spots (R12). Sky light passes glass, so puddles form under glass roofs (lang/en_US.lang; the fix is not-yet: docs/shader.md#dropped-features).
- Masks: Photon needs an up-facing flat normal (R12). The rain view overlooks canopy (config/views/bench_263.json) whose leaf tops pass such a mask, so the material map decides [inferred].
- Placement: low-frequency world-XZ noise, a narrow threshold band; Photon one channel tiling every 40 blocks (R12), Unbound three octaves.
- Wetness: `wetness` is a SmoothedFloat of rainStrength advanced by the last frame time, "There is no smoothing on the first value", and smooth() works alike (R11); rainStrength is the rain level at the tick delta, clamped, PER_TICK (R11). Under BENCH_DETERMINISTIC (docs/shader.md#determinism-and-taa) puddles read rainStrength and raw biome_precipitation (0 none, 1 rain, 2 snow; R10), ripples (frameTimeCounter in both packs) held at phase 0.
- The rain view (thunder) steps 120 ticks after its weather change (config/suite.json: "weather ramps only while ticking", [verify on the platform]); vanilla's 0.01-a-tick ramp then holds rainStrength at 1.0 [inferred].
- Cost [inferred]: a scalar branch on rainStrength (docs/playbook.md#4-design-defaults); on rain one hash or noise tap per up-facing sky-lit fragment, <= 0.05 ms; the reflection is T1-T4's.
- Iris: noisetex comes from "Random random = new Random(0);" (R11), the same every launch [verify in jar]; an ALU hash ports to Aperture [inferred]; cameraPositionInt and cameraPositionFract (Iris-exclusive, R10) keep world noise precise.

### D72 input: world-space and sky-effect reflections (not-yet list)
- World-space: Unbound enables them only with IRIS_FEATURE_CUSTOM_IMAGES, shadows and colored lighting (lib/common.glsl); worldSpaceRef.glsl marches a voxel image with face data in an SSBO of about 50 MB to 0.8 GB (shaders.properties), filled in the shadow pass. ALC never measured them. They need custom images (GL 4.2) and SSBOs (GL 4.3, R10) on the 3.3 context [verify in jar] and colored light's voxelization (not-yet). The face data blends each lightmap with last frame's (lib/voxelization/reflectionVoxelData.glsl), a history the flush must cover; a per-frame rebuild avoids it [inferred]. Cost [inferred]: 0.5-2 ms on reflective views plus the build; Aperture fits [inferred]. Decide with colored light, not for 1.0.
- Sky-effect: aurora, nebula, stars and clouds along the reflected ray (reflectionBackground.glsl), on water ("ON - Water") or blocks too ("ON - Full", en_US.lang). Unbound's clouds cost 0.302 ms mean, 0.649 at ocean_sunset [ALC m]; a second march over reflective pixels is that order [inferred]. Reflected clouds follow the clouds topic's BENCH_DETERMINISTIC rule (the hello pack discards vanilla clouds: docs/shader.md#determinism-and-taa). Cheap path: a lookup into a sky and cloud map, as Photon's fallback samples a sky map (R12). Defer.

## For Optilux
- Material map (M4, with lighting): block.properties groups set a smoothness class and F0 in the gbuffer, with the normal and sky light. Puddles: near-mirror smoothness, F0 0.02 like water and Photon's puddles (R12); R7 finds 0.02 against 0.04 "not visible enough in game".
- REFLECTIONS: Off (lighting's highlight stays); Low: T1 in the lighting pass, no pass or buffer; Medium: half-res trace (T4), 16 steps + 4 refinements [inferred], LOD by roughness (T3), T1 sky on a miss or low confidence, depth- and normal-aware upsample; High: full-res, 32 + 6 [inferred]; T6 only after A12. PUDDLES: Off / On (rain only).
- Pass order [inferred]: lighting writes the pre-fog lit colour (R11F_G11F_B10F, one copy with water's refraction); a deferred trace pass, the only program with the mip flag, reads depthtex1 (it "will first contain meaningful data in the deferred stage", R10), the gbuffer and the lit colour, and writes the reflection with a confidence in alpha (default clear 0: none, R10); the next deferred pass combines it before fog. Deferred precedes translucent gbuffers (R10), so glass and water layer over a reflective floor; ice and stained glass reflect in the water topic's forward trace.
- Determinism: cycle 1 with TAA off (spatial hash); with TAA on, High offsets by frameCounter mod the TAA cycle (16). No history, no last-frame colour: Photon samples colour at a reprojected position (hit_uv_prev, R12), apparently last frame's, a loop the flush would also have to cover [inferred].
- Budget hypothesis, ms at 4K [inferred: T4's scaling x a reflective share of 0.2-0.4 on rain, a guess an L4 mask count replaces, plus the mip chain, which with the trace pass sets the Medium floor]:

  | View type | Low | Medium | High |
  |---|---|---|---|
  | clear, no smooth blocks (forest_noon, cave, night, nether_*, entities, underwater, ocean_sunset's blocks) | 0 | <= 0.1 | <= 0.15 |
  | rain (puddles) | <= 0.1 | 0.2-0.8 | 0.5-2.0 |
  | end_city if purpur is grouped, end_dragon if obsidian is | <= 0.05 | 0.1-0.4 | 0.2-1.0 |

- Views: perf rain; visual coverage_items, coverage_mobs and coverage_beacon over the smooth-stone floor and iron-block base (optilux/world.py), clear so without puddles, and end_city and end_dragon, if those blocks are grouped.
- Dependencies: lighting (map, gbuffer, highlight, E2), sky (fallback), fog (pre-fog source), water (shared trace, F0), taa (cycle, flush), iris (flags).
- Confirmation (docs/measurement.md#verdicts-and-cost-rows, docs/measurement.md#visual-protocol): cost rows of each level against Off on every view in full mode, and of the mip flag alone; review tier on rain and the coverage views; TAA off identical across two launches; TAA on two captures 64 frames after an aligned flush identical (A12); live pass for wetness transitions and ghosting; L4 golden image and attribution share of the trace pass.
- L3 golden tests (docs/offline.md#levels): hits on a floor and wall at known depth within 1 px for every dither in the cycle, misses for an off-screen ray, a ray toward the camera, depth 1.0, a hand hit, a back-facing hit and a pillar thinner than the tolerance; LOD 0 at smoothness 1, monotonic, clamped; the BRDF fit against Schlick and an integrated table at F0 0.04 and 0.02; edge fade; the puddle mask over sky light (15, 14, 0), block light, normal, rainStrength (0, 1), precipitation (0, 1, 2) and a leaf group, continuous across x = 0 and chunk borders, with no wetness read under the define; dither(n) = dither(n + cycle), the cycle dividing 720720; step-count uniforms in Iris's engine (docs/gpu-iris.md#custom-uniforms).

## Open questions
- Does mc_Entity (block.properties) reach a native #version 330 core terrain program on Iris 1.11.7 and Sodium 0.9.2? Unbound's terrain reads it through Iris's #version 130 rewrite (docs/platform.md#mc-263) [inferred: delivered there]. Decided by the jar's vertex formats and an L1 dump of a test pack.
- Which blocks get smoothness (smooth stone, purpur, obsidian, metals, glass, ice), and do leaves take puddles? A look decision with the user on review-tier coverage frames.
- Does rainStrength read exactly 1.0 at rain under /tick freeze? Decided by a debug variant writing it to a pixel, or 26.3's rain ramp in the jar.
- Does a mipmapped R11F_G11F_B10F chain cost 0.06-0.1 ms here? Decided by the mip-flag cost row.
- Is a half-res trace acceptable on mirror puddles? Decided by review of Medium against High on rain.
- Does Iris 1.11.7 enable compute, custom images and SSBOs on this 3.3 core context? Decided by the jar's capability checks (R11 tests entry points) and a .csh test pack; it gates T5 and world-space reflections.
- Aperture: mips for explicit textures? Decided when Aperture is public.
- Should non-puddle surfaces darken when wet (R7 porosity)? It needs a porosity group; a look decision.
- iso: map Low puddles to Unbound's RAIN_PUDDLES 1 at BLOCK_REFLECT_QUALITY 1 and leave block SSR unmatched, since matching it moves RP_MODE into IPBR+ (config/profiles/complementary-unbound-iso.json)? Decided by D72's ratio part.
