# Fog and volumetrics
Status: Research for M4 and M5 on atmospheric, underwater, Nether, End and edge fog, the End beams and volumetric methods, with D72 input on the not-yet fogs. It is research only: nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
- R1 Complementary Unbound r5.9.3, pack source (Complementary License Agreement 1.7: study only, docs/shader.md#policy): reference/complementary-unbound-r5.9.3/shaders/: program/composite1.glsl, deferred1.glsl, composite5.glsl; lib/atmospherics/fog/ and volumetricLight/; lib/common.glsl; shaders.properties; world0/shadowcomp.csh.
- R2 Photon, pack source, main branch read 2026-10-26 (Photon Shaders License Agreement, custom; studied, not copied): https://github.com/sixthsurge/photon (shaders/include/fog/: overworld/analytic.glsl, water_fog_vl.glsl, end_fog_vl.glsl, simple_fog.glsl; program/c0_vl.fsh; shaders.properties).
- R3 Iris source, branch 26.3 read 2026-10-26, not the pinned jar: https://github.com/IrisShaders/Iris (FeatureFlags, IrisRenderSystem, ShaderProperties, CommonUniforms, WorldTimeUniforms).
- R4 Iris docs (vendor doc, current): https://shaders.properties/current/reference/buffers/custom_images/ and https://shaders.properties/current/reference/programs/overview/
- R5 Unreal Engine, Volumetric Fog (vendor doc, UE 5.8): https://dev.epicgames.com/documentation/en-us/unreal-engine/volumetric-fog-in-unreal-engine
- R6 Unreal Engine, Exponential Height Fog (vendor doc, UE5): https://dev.epicgames.com/documentation/en-us/unreal-engine/exponential-height-fog-in-unreal-engine
- R7 B. Wronski, Volumetric Fog: Unified Compute Shader Based Solution to Atmospheric Scattering (talk, SIGGRAPH 2014): https://bartwronski.com/wp-content/uploads/2014/08/bwronski_volumetric_fog_siggraph2014.pdf (not readable here); its cost from his GDC 2014 preview (blog, 2014): https://bartwronski.com/2014/03/09/my-upcoming-gdc-2014-presentation/
- R8 S. Hillaire, Towards Unified and Physically-Based Volumetric Lighting in Frostbite (talk, SIGGRAPH 2015 Advances course): https://advances.realtimerendering.com/s2015/index.html (not read here: origin of the energy-conserving step only).
- R9 A. Wolfe, Interleaved Gradient Noise (blog, 2022, on Jimenez's 2014 noise): https://blog.demofox.org/2022/01/01/interleaved-gradient-noise-a-different-kind-of-low-discrepancy-sequence/
- R10 J. Kopf et al., Joint Bilateral Upsampling (paper, SIGGRAPH 2007): https://johanneskopf.de/publications/jbu/
- R11 K. Mitchell, Volumetric Light Scattering as a Post-Process, GPU Gems 3 ch. 13 (book chapter, 2007): https://developer.nvidia.com/gpugems/gpugems3/part-ii-light-and-shadows/chapter-13-volumetric-light-scattering-post-process
- R12 T. Engelhardt, C. Dachsbacher, Epipolar Sampling for Shadows and Crepuscular Rays in Participating Media with Single Scattering (paper, I3D 2010): https://www.doi.org/10.1145/1730804.1730823
- R13 RX 7800 XT specs (press, 2023): 60 CUs, 3,840 stream processors, 2124 MHz game and 2430 MHz boost clock, 624 GB/s, 64 MB Infinity Cache: https://www.custompc.com/amd-radeon-rx-7800-xt-price-specs-release-date
- R14 Repo: docs/shader.md#method, docs/playbook.md#4-design-defaults, docs/playbook.md#51-structural, config/profiles/complementary-unbound-iso.json (droppedNotes), shader/shaders/lib/fog.glsl, optilux/l1.py IRIS_UNIFORMS (uniform names read in the pinned jar with javap).
- R15 PS4 specs (press, 2013, from Sony's release): 18 CUs, 1.84 TFLOPS, 176 GB/s: https://www.engadget.com/2013-02-20-sony-further-details-playstation-4-hardware-specs.html

## Unbound r5.9.3
- Placement [R1]: opaque fog in deferred1 (DoFog, after SSAO, on the forward-lit colour), translucents in gbuffers_water, the volumetric march in composite1 at full resolution (shaders.properties rescales only colortex1 and colortex7).
- Cost: composite1 is 11 % of the weighted frame (docs/shader.md#method) and 73 % of end_dragon (docs/playbook.md#4-design-defaults), ALC replay shares on MC 1.21.11. Unbound frames run 4.6-7.7 ms at 4K across ALC's views; if end_dragon's does too, its march costs about 3.4-5.6 ms [inferred: 0.73 x the range; end_dragon's own frame time is not in the docs].
- Why the End costs so much: common.glsl defines LIGHTSHAFTS_ACTIVE in the End at any LIGHTSHAFT_QUALI. At the played 0 the End marches 31 near steps (within about 94 blocks at shadowDistance 96) and 10 far steps to 1536 blocks. A near step makes one shadowtex0 texelFetch, plus the translucent compare and colour fetch only where that texel is occluded; every step calls the beam function's four noisetex fetches (volumetricLight.glsl, enderBeams.glsl) [R1]: about 41 steps of up to 7 fetches per 4K pixel [inferred count].
- Atmospheric fog (mainFog.glsl) [R1]: a distance curve that stays near zero, then rises steeply, its exponent changing with rain; scaled by ATM_FOG_MULT less a weather-dependent offset (played 0.50) and by the smoothed eye brightness, which removes it underground; an altitude factor at the fragment's and the camera's height, not integrated along the ray, so from above the fade band a valley is fogged by its own altitude [inferred]. Colour: a night and a day sky colour blended by the night factor, sharpened by the view-sun angle and sun visibility.
- Border fog (off in played and iso), over max(horizontal, vertical) distance: overworld, a sky-coloured steep high-power curve up to far; Nether, a near-linear ramp in the pack's Nether colour up to min(far, NETHER_VIEW_LIMIT). It is the Nether's only distance fog, as the Nether undefines the atmospheric fog (common.glsl; iso droppedNotes) [R1, R14], so played draws only bloom fog there.
- Underwater: one minus the exponential of a squared distance term (shafts on) or a linear one (shafts off), in a colour derived from fogColor by a per-channel power (WATERCOLOR_MODE 3, the default); composite1 then darkens the scene by a fixed tint [R1].
- End fog: the atmospheric fog's non-overworld branch at half strength, limited to low altitudes, in the End sky colour; in the march a far-distance curve pushes the ray's end to its maximum, so distant terrain dissolves into the beams [R1].
- Beams: a world-xz pattern (three noise octaves plus a "fire" noise) in an altitude band around END_BEAM_CENTER_ALT that widens with horizontal distance; purple from the ambient colour, orange on top, brighter toward the End flash [R1].
- Bloom fog (not in the End): composite1 multiplies colour by a distance factor; the bloom tiles are built from that colour and composite5 divides it back out before adding them, so distant pixels bloom more (bloomFog.glsl) [R1].
- Hazards under BENCH_DETERMINISTIC (docs/shader.md#determinism-and-taa) [R1]:
  - smooth() uniforms: rainFactor, eyeBrightnessM, inDry, endFlashIntensityM, frameTimeSmooth, the Nether biome blends (shaders.properties);
  - frameTimeCounter scrolls the beams (and the smoke, off by default);
  - the dither: noisetex plus golden ratio x (frameCounter mod 3600), under TAA only; 3600 does not divide 720720;
  - a colortex5 corner pixel carries state across frames: in the End deferred1 steps it up while heavyFog (the dragon fight) holds and down otherwise, at a cadence from frameTimeSmooth, and it shifts the beams' colours and flash cone; in the overworld it is the scene-aware shaft factor, with shafts on only.

## Techniques
### T1 Analytic exponential height fog
- Claim: density a exp(-b (y - h0)) has a closed-form optical depth along a ray from height y0, direction component dy, length s: tau = a exp(-b (y0 - h0)) (1 - exp(-b dy s)) / (b dy); near |b dy s| = 0 the series a exp(-b (y0 - h0)) s (1 - b dy s / 2) applies [inferred: derived].
- Photon integrates two exponential-in-height density terms (Rayleigh-like and Mie-like) in closed form, dividing by the ray's y with no near-horizontal branch, only a clamp to [0, ray length]; it scales scattering by the larger of the fragment's and the eye's sky light (analytic.glsl) [R2]. UE's height fog "creates more density in low places of a map and less density in high places", with a directional inscattering cone and a second layer [R6].
- Fixes Unbound's endpoint-altitude fog. Colour: T = exp(-tau), mix(fog colour, scene, T); the fog colour from the sky model plus a sun lobe.
- Cost: two exp and about 40 other ops per pixel in an existing pass: 8.3 M px x 80 lane-ops / (3,840 lanes x 2.124 GHz game clock) = 0.08 ms [inferred, R13; one op per lane per clock, quarter-rate exp, docs/gpu-iris.md#transcendentals]. The camera term and the colours are custom uniforms (docs/playbook.md#4-design-defaults). Quality: Off / On (one layer) / High (two layers and the sun lobe).
- Constraints:
  1. No frame-varying term: cameraPosition, custom uniforms and rainStrength (PER_TICK, getRainLevel at the frame's tick delta, not a SmoothedFloat: wetness is; CommonUniforms, R3); never fogStart, fogEnd or smooth(). Underground cut by the fragment's sky light or raw eyeBrightness, not a smoothed value. No TAA.
  2. Custom uniforms, cameraPosition, rainStrength [verify in jar].
  3. A pure function in an Iris-free include.
  4. As above.

### T2 Edge fog
- The hello pack rebuilds 26.3's render-distance band from far: clamp(far / 10, 4, 64) wide, ending at far, over max(|xz|, |y|), in fogColor (shader/shaders/lib/fog.glsl; docs/shader.md#facts). Keep it in every dimension; its colour must equal what the sky draws in that direction, or the band shows as a seam [inferred]. Removing in-medium fog without a fade over the last ~15 % turns the edge into a wall (docs/playbook.md#55-config-level).
- About 10 ops per pixel [inferred]. Deterministic: it reads far and fogColor, and the hello pack, which draws it under BENCH_DETERMINISTIC, gave TAA-off frames identical across launches on 11/11 views (docs/measurement.md#visual-protocol). far, fogColor [verify in jar]; a pure function, portable; no TAA.

### T3 Underwater: per-channel Beer-Lambert with analytic inscatter
- Claim: T_c = exp(-sigma_c s); in a homogeneous, uniformly lit medium the inscatter is L (sigma_s / sigma_t) (1 - T). Photon's water march applies this closed form per step (per-channel absorption, grey scattering), so there the result does not depend on the step size; its shadow taps and caustics (scrolled by frameTimeCounter) vary the light per step (water_fog_vl.glsl) [R2]. The step is attributed to Frostbite [R8].
- Optilux: no march; per-channel sigma (red absorbed first) tuned against the look reference, inscatter from lighting's ambient uniforms; one include shared with the water topic's below-surface absorption. fogColor in water holds after 3 s in a session (docs/shader.md#determinism-and-taa), so it may tint; fogEnd follows water vision and is never read.
- About 0.05 ms or less [inferred]. On, or Off with the 15 % fade. Deterministic: fogColor, isEyeInWater, custom uniforms, no frame term, no TAA [verify in jar]; a pure function, portable.

### T4 Nether and End fog
- Nether: an exponential distance fog in fogColor (the biome's), distances from far and pack constants. Unbound played has none (border fog off) [R1, R14]; Photon draws a spherical exponential fog in its ambient colour (simple_fog.glsl) [R2].
- End: T1 with an End layer. Photon's End density peaks at y 64, halves every 7 blocks above and fades linearly to 0 at y 0 (end_fog_vl.glsl) [R2].
- Each about 0.05 ms or less [inferred]. Deterministic as T2 (fogColor at a fixed pose, far, custom uniforms), no TAA [verify in jar]; pure functions, portable.

### T5 Half-resolution march with depth-aware upsample (End beams)
- Claim: march at half size on each axis in a separate pass, upsample in the consumer with bilinear x depth weights (R10; docs/playbook.md#51-structural, PB b; a design default, docs/playbook.md#4-design-defaults). Photon marches its volumetrics into colortex6 and colortex7 at size.buffer 0.5 0.5 (shaders.properties, c0_vl.fsh), with an explicit flip of colortex6 in composite1 that Aperture would lack [R2].
- Beam march, Optilux-specific [inferred]:
  - clip the ray to the beam altitude slab first; Photon clips its End fog to a y 0-256 slab and returns on a miss (end_fog_vl.glsl) [R2];
  - one fetch per step from a camera-centred beam map, generated procedurally each frame, world-anchored and snapped to texels, instead of Unbound's four noise fetches;
  - the energy-conserving step, so changing the step count keeps the brightness;
  - the step count from an int custom uniform (docs/gpu-iris.md#occupancy).
- Cost [inferred from the Unbound estimate]: 3.4-5.6 ms over 41 full-resolution steps is 0.08-0.14 ms a step, 0.02-0.035 ms at a quarter of the pixels, so Low 8, Medium 12 and High 16 steps cost 0.17-0.27, 0.25-0.41 and 0.33-0.55 ms, less by an unmeasured factor for one fetch a step instead of up to seven; plus 0.05-0.1 ms for the upsample.
- Constraints:
  1. Dither from IGN [R9] offset by frameCounter mod C, C the pack cycle (8 or 16, which divide 720720: docs/mod.md#6-time-and-determinism; R9's 64-frame loop does not). Static with TAA off, as Unbound does [R1]. Animation frozen under BENCH_DETERMINISTIC; off, it follows frameTimeCounter. TAA is the denoiser: the converged look rests on A12, review only under E4's fallback.
  2. size.buffer (ShaderProperties textureScaleOverrides, R3); a pass draws at its buffers' size (docs/gpu-iris.md#passes-and-buffers, PB v on 1.10.7); RGBA16F [verify in jar].
  3. An explicit half-size texture, no flip; march and upsample in Iris-free includes.
  4. As above.

### T6 Temporal reprojection of the volume buffer
- UE "uses a heavy temporal reprojection filter with a different sub-voxel jitter per frame"; fast-changing lights "leave lighting trails" [R5].
- A second history: flushed in the same hideGUI frame (docs/mod.md#6-time-and-determinism), its weight lengthening N_conv, a ping-pong pair; previous matrices and previousCameraPosition exist (optilux/l1.py IRIS_UNIFORMS) [verify in jar].
- About 0.05 ms for one extra half-size RGBA16F read and write, 2 x 16.6 MB at 624 GB/s [inferred, R13]. Not in v1.

### T7 Froxel grid
- Wronski [R7] and Frostbite [R8]. UE: "Volumetric Fog costs 1 millisecond on PlayStation 4 at High settings", 3 ms on a GTX 970 at Epic with "eight times more voxels"; the cost "is primarily controlled by the volume texture resolution" [R5]. Wronski: "a fixed cost of around 1.1ms on both Sony PlayStation 4 and Microsoft Xbox One", shadow-map downsampling and the apply pass included [R7].
- Iris needs compute or image load/store:
  - FeatureFlags gates COMPUTE_SHADERS on IrisRenderSystem.supportsCompute (glDispatchCompute non-null) and CUSTOM_IMAGES on supportsImageLoadStore (glBindImageTexture, GL 4.2, or ARB/EXT_shader_image_load_store with ARB_buffer_storage) [R3]; the docs say compute needs GL 4.3, images GL 4.2 [R4];
  - 26.3's context is 3.3.0 core (docs/shader.md#facts); whether this driver exposes those entry points there is open [verify in jar and in game];
  - Unbound's only compute stage, shadowcomp, is #version 430 compatibility and runs only with colored lighting on [R1]: no evidence from this machine;
  - L0 refuses compute programs today (docs/offline.md#levels).
- Fallback without compute: slices tiled in an absolute-size 2D colortex, filled by fragment passes [inferred]. Needs its own history (T6).
- Cost at the same voxel count: UE's 1 ms on PS4 scaled by FP32 rate (1.84 TFLOPS [R15] vs 18.7 = 3,840 x 2 x 2.43 GHz [R13], no dual issue) and by bandwidth (176 vs 624 GB/s) gives 0.1-0.3 ms, plus 0.05-0.1 ms to apply at 4K [inferred]. D72 input only.

### T8 Screen-space scattering
- Radial blur of an occluder pre-pass toward the light's screen position; facing perpendicular to the light, that position "can tend toward infinity", and off-screen occluders make the shafts flicker [R11].
- Epipolar sampling places march samples along epipolar lines and interpolates between them [R12]; complex for a fragment-only port [inferred]. D72 input only.

## For Optilux
- One Iris-free include holds T1-T4, with one glue file per backend. Opaque fog in the lighting pass (E2 decides where), translucents in their forward program at their own depth (as Unbound does), clouds at the cloud depth; the sky gets no fog, but the T2 colour matches it.
- End beams: one composite at 0.5 x 0.5 into premultiplied RGBA16F (rgb inscatter, alpha transmittance), upsampled in the next composite; the beam map from a deferred pass at an absolute size.
- No fogStart or fogEnd in either build, except for vanilla-only states (lava, powder snow, blindness, darkness) with BENCH_DETERMINISTIC off; the perf and played builds then fog alike, and the define's cost row (docs/measurement.md#session) holds no fog change [inferred].
- Options (the edge fade always on):

  | Option | Levels | Dimension |
  |---|---|---|
  | FOG_ATMOSPHERIC | Off, On, High | overworld |
  | FOG_WATER | On, Off (15 % fade kept) | all |
  | FOG_NETHER | Off, On | Nether |
  | FOG_END | Off, On | End |
  | END_BEAMS | Off, Low 8, Medium 12, High 16 steps | End |

- Budget hypothesis, fog plus volumetrics at 4K [inferred]:

  | Views | Budget |
  |---|---|
  | forest_noon, ocean_sunset, rain, night, cave, entities | 0.08 ms |
  | underwater | 0.08 ms |
  | nether_crimson, nether_soul | 0.05 ms |
  | end_dragon, end_city | 0.5 ms at Medium (Unbound about 3.4-5.6 at end_dragon; none for end_city) |

- What would confirm each claim: a feature cost row per option on every view of its dimension (docs/measurement.md#verdicts-and-cost-rows; an analytic fog may land inside the 0.5 % floor, which is then the answer); END_BEAMS rows at both End views; a full-resolution beam variant against the half-resolution one, expected close; every feature at review against Unbound's played frames (docs/measurement.md#visual-protocol); later optimizations identical or near on TAA-off frames; a TAA-off capture with beams on identical across two launches, TAA on through A12; the live pass: beam motion, rain fog, entering water, cave mouths.
- Dependencies: sky (fog and edge colour, End flash); lighting (sun and ambient uniforms); water (shared absorption); clouds (fog at cloud depth, shared march and upsample); taa (cycle, flush, N_conv); shadows (shafts, shadowed beams); post (output dither); bloom (bloom fog); reflections (fog on reflected samples); iris (the capabilities above); next-gen (froxels on Aperture compute).
- L3 golden tests (docs/offline.md#levels):
  1. T1 against a float64 4096-step midpoint sum over 10^4 rays, |dy| down to 1e-6: relative error 1e-4 or less, continuous across the series switch (near |b dy s| = 0.02, where the dropped term is under 1e-4 [inferred]).
  2. The energy-conserving step equal at N = 1, 4, 16 and 64 in a homogeneous, uniformly lit medium.
  3. T2 at far 32, 64, 512 and 1024 (bands 4, 6.4, 51.2, 64) equals the hello pack's.
  4. Dither: period equal to the cycle, values in [0, 1), cycle mean 0.5 +- 0.1, no jump at the 720720 wrap.
  5. Upsample: rep(h) = 2h + 1 returns its own value, a constant field stays constant, nothing bleeds across a depth step over 3 %.
  6. Beer-Lambert: T(0) = 1, monotone.
  7. Beam map: one world position gives one density after the map recentres.
- L4: per-pass golden images of the beams at both End views; replay A/B of each step count against a no-op replacement, in shares (predict; docs/offline.md#decision-powers).
- D72 input (not-yet list):
  - Light shafts: T5 with one shadowtex tap per step, 0.2-0.6 ms at half size [inferred]; TAA-reliant.
  - Border fog: analytic, about 0.02 ms or less, deterministic.
  - Cave fog: analytic, about 0.02 ms or less; raw eyeBrightness or the fragment's sky light (as Photon's air fog uses, R2) replaces Unbound's smoothed eye brightness.

## Open questions
- Does 1.11.7 on this 3.3 core context expose COMPUTE_SHADERS and CUSTOM_IMAGES? Decided by javap of FeatureFlags and IrisRenderSystem plus a dump's IRIS_FEATURE_* and MC_GL_ARB_compute_shader / MC_GL_ARB_shader_image_load_store macros.
- Does worldTime read the End's own clock in 26.3, and hold under /tick freeze? The 26.3 branch returns the level's getDefaultClockTime() mod 24000 in the End (WorldTimeUniforms, R3); whether that is the clock the End views' functions set is open. Decided by javap and an end_dragon dump run.
- Is the edge fade in the sky colour still edge fog, or border fog? The user decides at D72.
- Are shadowed End beams (Unbound marches the shadow map in the End; Photon's End fog also takes shadow taps, end_fog_vl.glsl) part of the kept beams, or light shafts? The user decides at D72, with a cost row.
- The Nether fog's density and look: decided by D72's look target and review at both Nether views.
- Is bloom fog kept, and who owns it? The bloom topic and the user decide.
- Is rainStrength bit-stable under freeze, partial ticks included? Decided by a TAA-off rain capture identical across two launches.
- A procedural beam map or a shipped noise texture? Decided by L3 and review against Unbound.
