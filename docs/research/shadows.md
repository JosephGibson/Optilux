# Shadows
Status: research on Optilux's sun and moon shadows (Iris's shadow pass, filtering, coloured and entity shadows, bias and leaks, cost), from sources and Unbound r5.9.3. None of it is measured in Optilux's own pack yet; the only Optilux numbers are Unbound's shadows-off rows.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
- R1 Microsoft, "Common Techniques to Improve Shadow Depth Maps" (vendor doc, 2018): https://learn.microsoft.com/en-us/windows/win32/dxtecharts/common-techniques-to-improve-shadow-depth-maps
- R2 I. Castano, "Shadow Mapping Summary - Part 1" (developer blog, The Witness, 2013): http://the-witness.net/news/2013/09/shadow-mapping-summary-part-1/
- R3 R. Fernando, "Percentage-Closer Soft Shadows" (NVIDIA, SIGGRAPH 2005 sketch): https://developer.download.nvidia.com/shaderlibrary/docs/shadow_PCSS.pdf; it does not render here, its 75 fps figure was read on a copy: https://www.scribd.com/document/449172201/shadow-PCSS
- R4 J. Jimenez, "Next Generation Post Processing in Call of Duty: Advanced Warfare" (SIGGRAPH 2014 Advances course): https://www.iryoku.com/next-generation-post-processing-in-call-of-duty-advanced-warfare
- R5 K. McAllister, "Inside Bend: Screen Space Shadows" (studio blog on G. Aldridge's technique, undated; SIGGRAPH 2023 talk and code linked, license not stated): https://www.bendstudio.com/blog/inside-bend-screen-space-shadows/
- R6 Iris docs (vendor doc, current), https://shaders.properties/current/reference/: shadowtex, shadowcolor, shadow programs, shadowDistance, shadowDistanceRenderMul, shadowIntervalSize and shadow mipmap constants, rendering and flags pages
- R7 Iris source, branch 26.3 (the pinned jar stays the authority), https://github.com/IrisShaders/Iris/tree/26.3: PackShadowDirectives, ShaderProperties, PackDirectives, ShadowRenderer, ShadowMatrices, IrisRenderingPipeline, FeatureFlags
- R8 Aperture migration guide (vendor doc, headed "This guide is currently extremely outdated"): https://shaders.properties/aperture/migration/
- R9 Photon (pack source, Photon Shaders License Agreement, custom): shaders/include/lighting/shadows/pcss.glsl, distortion.glsl, https://github.com/sixthsurge/photon
- R10 Unbound r5.9.3 (pack source, Complementary License Agreement 1.7), reference/complementary-unbound-r5.9.3/shaders/: program/shadow.glsl, gbuffers_basic.glsl; lib/lighting/; lib/atmospherics/volumetricLight/volumetricLight.glsl; lib/materials/specificMaterials/terrain/leaves.glsl; lib/common.glsl, pipelineSettings.glsl, uniforms.glsl; shaders.properties
- R11 Optilux: results/records/m3-shadows-full-1.json, variant shadows-off (SHADOW_QUALITY -1 over Unbound played; 26.3, 3840x2160, RX 7800 XT, full mode, 2 rounds) [m]; config/profiles/complementary-unbound-played.json ablations (ALC, 1.21.11) [m]
- R12 AMD, RX 7800 XT spec page (vendor doc, 2023, via a search extract): 240 texture units, 583 GT/s peak: https://www.amd.com/en/products/graphics/desktops/radeon/7000-series/amd-radeon-rx-7800-xt.html

## Unbound r5.9.3
Read in R10, described in our words.
- Played: a 2048^2 map (lib/common.glsl gives 4096 only to sharper smoothing or the top level), shadowDistance 96, culling at that distance, hardware filtering, entity shadows to an eighth of it (lib/pipelineSettings.glsl); ENTITY_SHADOW -1 turns entity and block-entity shadows off but keeps the player's (shaders.properties).
- Mapping: a radial distortion whose divisor is linear in the clip-space radius, in the shadow vertex stage and again in every lookup. Its strength follows shadowDistance, so the centre keeps 40 texels per block and the edge gets 2.8 radial texels per block at 2048 and 96 [inferred, computed from lib/common.glsl].
- One `shadow` program serves all geometry in all three worlds. Every fragment, solid included, writes shadowcolor0 (translucent tint, stored at a tenth so water can exceed 1) and shadowcolor1 (light-shaft colour). At played, water's tint takes four caustic fetches animated by frameTimeCounter, its shaft colour two noise fetches animated by world time. Entity shadows fade out by a Bayer-dithered discard.
- Lookups are forward, in the overworld and End gbuffers lighting (mainLighting.glsl), skipped past the map and where the shading's N.L term is 0 (side shading widens it to N.L above about -0.4; foliage and particles always look up). A tap compares shadowtex0; where not fully lit, shadowtex1, and if a translucent lies between it fetches shadowcolor0: up to three dependent fetches.
- Filter: Medium (played) takes two opposite pairs on a spiral rotated by interleaved gradient noise plus a golden-ratio step of frameCounter mod 3600, so it leans on TAA. Entities, hand and particles get twice the taps with static noise. Low is a 5-tap cross, Very Low 4 depth-only taps. Rain widens the kernel.
- Bias and leaks: a world-space normal offset growing with distance^1.5 and at grazing light. Terrain samples are pulled toward the block centre where sky light or vertex AO is low (the cave leak fix); foliage has its own offsets. Shadows end near 0.92 x shadowDistance, after a 16-block blend into a steep power of the sky light.
- SHADOW_QUALITY -1 disables the shadow program in every world, so nothing samples the map, and changes the time-angle formula and foliage lighting: the ablation prices the whole feature. The End's volumetric march runs at every level (LIGHTSHAFTS_ACTIVE, lib/common.glsl) but reads the map only above -1 (volumetricLight.glsl), so the End rows include those reads.
- Nether: gbuffers_basic samples the map in a never-taken branch only with ACT on, a hook its comment says activates the Nether's shadow map; at played the Nether likely has no shadow pass [inferred].
- Shadows off against played (R11), ms and % of GPUBusy:

  | view | ms | % |
  |---|---|---|
  | forest_noon | -1.35 | -16.5 |
  | ocean_sunset | -0.93 | -12.6 |
  | rain | -1.16 | -15.2 |
  | night | -0.63 | -11.5 |
  | cave | -0.62 | -11.6 |
  | underwater | -1.86 | -24.9 |
  | entities | -0.52 | -9.7 |
  | end_dragon, end_city | -1.18 | -14.4 |
  | nether_crimson | -0.03 | -0.55 |
  | nether_soul | -0.03 | -0.43 (inside 0.5 %) |

  Mean 0.86 ms over 11 views, 1.05 over the 9 outside the Nether; geo-mean -12.22 % full, -10.76 % quick (docs/measurement.md#calibration). ALC's 1.21.11 row: mean 0.667, worst rain 1.120 (R11).
- Where the time goes [inferred]: 1.21.11 replay shares put the shadow pass at 4 % (docs/shader.md#method) to 6 % (docs/playbook.md#3-workflow) of Unbound's frame, 0.2-0.5 ms of 26.3's 5.4-8.2 ms; the rest is forward lookups times overdraw, plus the End march's reads. Underwater every tap below the surface runs the full chain.

## Techniques
### Distorted single map, culled
- Claim: Iris renders one orthographic map around the camera with half-size shadowDistance, snapped every shadowIntervalSize blocks (default 2), lit by the moon at night; in the End, endFlashShadows=true (default false) aims it along the End flash without sunPathRotation (R6; R7 ShadowMatrices, ShaderProperties). No cascades: a distortion stands in (R10 radial; R9 quartic, so diagonals are compressed less [inferred]).
- Culling: a positive shadowDistanceRenderMul "will apply culling" at that multiple (R6); at the default -1 the user's max shadow distance applies, 32 chunks in R11, past the render distance (R7). shadow.culling unset or true also drops casters that cannot reach the view frustum (unset: not for a voxelizing pack); false culls by distance only; reversed (safe_zone in R7) never culls within voxelDistance (R6, R7).
- Programs: shadow_solid, _cutout, _water, _entities and _block fall back to shadow (R6, Iris 1.8+). Solid without discard is a design default (docs/playbook.md#4-design-defaults; CONFLICT in docs/gpu-iris.md#depth-and-discard). 26.3's core path injects no alpha test (docs/shader.md#facts): shadow_cutout tests alphaTestRef, shadow_solid samples no texture. Colour is read only where a translucent lies before the opaque depth, so only shadow_water need write shadowcolor0, and nothing shadowcolor1 while light shafts are not-yet [inferred].
- Cost [inferred]: 0.2-0.5 ms at 2048^2 and 96 blocks (the share above), less without Unbound's two colour writes per fragment (an RGBA8 2048^2 target is 16 MB per full write); 4096^2 quadruples raster and colour traffic, not vertex work. Quality: 2048 at Low and Medium, 4096 at High; the distance is its own option.
- Determinism: outside the End the matrices depend only on the shadow angle, sunPathRotation and the camera (R7), all held by the session; End angles follow the End's clock, which the views set [inferred]. Under BENCH_DETERMINISTIC no shadow program reads frameTimeCounter (caustics, waving).
- Iris [verify in jar]: directives and defaults; whether a shadow program may declare no colour output. Per R7 the shadow renderer exists when shadow targets do and shadow.enabled is not false; targets are made up front only when it is true, else for the first program sampling a shadow sampler. No dimension macro exists (docs/offline.md#levels), so a Nether without a pass needs world-1 programs that sample none.
- Aperture: four cascades in array textures, shadowMap and solidShadowMap (R8: "Aperture makes use of cascaded shadow maps"). One Iris-free include maps (distort, or pick a cascade; return uv, depth, the texel's world size); every filter takes its output.

### Noise-free hardware PCF
- Claim: a compare sampler gives a bilinear 2x2 PCF in one fetch (R6: "very little to no performance impact"). Taps at derived offsets and weights build a smooth kernel from few fetches: R2 covers 6x6 texels with 9 taps, measured "between 10 and 20% faster than the Gather4 method" (GTX 480, HD 4000), and dropped rotated Poisson taps for their noise. 4 taps cover 4x4 the same way [inferred].
- Cost [inferred]: Medium is 4 compares on shadowtex1, one on shadowtex0 and at most one colour fetch: 6 fetches a pixel, 50 M at 4K, 0.09 ms at R12's peak, so 0.15-0.35 ms allowing 2-4x for misses and dependent chains, against Unbound's 0.3-1.4 ms of forward lookups. Issue the compares before any dependent fetch (docs/gpu-iris.md#latency). Quality: Low 1 tap, Medium 4, High 9.
- Determinism: no frame-varying term, so nothing needs accumulating: each TAA-off frame is final, and identical or near tiers hold under E4's fallback; TAA-on frames rest on A12 like every pass.
- Iris: shadowHardwareFiltering makes the shadowtex samplers compare samplers (sampler2DShadow; texture() is core 3.3) [verify in jar]. Aperture: shadowMapFiltered, a sampler2DArrayShadow with the cascade in z (R8).

### Rotated disk, rotated per frame
- Claim: a few taps on a spiral or Vogel disk, rotated per pixel and per frame, turn banding into noise that TAA averages. R4: "a 8-tap filter with a special per-pixel noise A.K.A. "Interleaved Gradient Noise"". R10 uses 4 taps; R9 rotates a Vogel disk per frame and returns early when its first 4 taps agree.
- Cost: the same per tap, so it pays only if fewer taps give the same look [inferred]; half the pairs with per-frame rotation is a PB candidate [PB b] (docs/playbook.md#54-sample-count-and-precision-trades).
- Determinism: rotate by frameCounter % C, C being config/pipeline.json's cycle (1 now; the TAA topic sets it; 8 and 16 divide 720720). A mod-3600 term like Unbound's would become the cycle (docs/shader.md#determinism-and-taa). It relies on TAA: review tier only under E4's fallback, whose TAA-off frames show the raw noise.
- Iris: frameCounter [ALC v] (docs/gpu-iris.md#frame-counters-and-reload); the tap count from an int custom uniform (docs/gpu-iris.md#custom-uniforms). Aperture: the same include, given the frame index.

### PCSS
- Claim: a blocker search averages occluder depth, the penumbra grows with (receiver - blocker) / blocker, then PCF runs at that width (R3); R3's unoptimised version ran about 75 fps on a GeForce 7800 GTX. R9 takes 3 blocker taps, an adaptive PCF count and early exits.
- Iris: raw depth beside the compare samplers needs the SEPARATE_HARDWARE_SAMPLERS flag (required for use), adding shadowtex0HW and shadowtex1HW (R6; in R7's FeatureFlags) [verify in jar]. Aperture: raw and filtered samplers both exist (R8).
- Cost [inferred]: 0.15-0.4 ms over Medium at 4K; High only. Determinism: few noisy taps, so it relies on TAA: review tier under E4.

### One tap past a distance
- Claim: one hardware-filtered tap past ~48 blocks, with a dithered switch [PB b] (docs/playbook.md#54-sample-count-and-precision-trades). At the played mapping and 4K a shadow texel covers ~7 screen pixels at 5 blocks and ~3 radially from 20 to 48 [inferred: light overhead, 90-degree vertical FOV from suite.json's fov 0.5], so a 2x2 tap keeps a similar edge far away.
- Cost: 3 of Medium's 4 compares saved past the switch [inferred]. Iris and Aperture: as above. Determinism: the dithered switch relies on TAA; a fixed band evaluating both kernels does not [inferred].

### Coloured translucent shadows
- Claim: shadowtex0 "includes all geometry" and shadowtex1 "excludes transparent geometry" (R6). The tint applies where the receiver is lit in shadowtex1 but not in shadowtex0; shadowcolor0 holds the nearest translucent's tint [inferred]. Unbound fetches the colour at every tap (R10); one fetch per pixel, only when a tap saw a translucent, shortens the chain [inferred; review tier].
- shadowcolor0 defaults to RGBA ("RGBA8 on most systems"), is cleared to white each frame, and its mip chains "will _not_ be generated" (R6); each shadowcolor is two buffers, flipped by shadowcomp passes (R6). Skipping the clear is exact only with texelFetch reads [inferred].
- Determinism: tint from texture and vertex colour only; caustics belong to the water topic. Aperture: solidShadowMap stands for shadowtex1; shadowcolor buffers become array textures (R8).

### Bias, acne, peter-panning, leaks
- Claim: acne comes from depth quantised over a texel and from grazing light; slope-scaled bias fixes it, and "Peter Panning results when the depth offset used is too large" (R1). R2 scales the normal offset with the sine of the N-L angle, the slope bias with its tangent.
- A distorted texel's world size grows with radius, so the offset should scale with the mapping include's texel size [inferred]. Unbound uses distance^1.5 (R10); Photon a clamped linear form credited to Complementary Reimagined (R9 distortion.glsl). Thick blocks keep peter-panning small; thin geometry (panes, plants, carpets) shows it [inferred]; R1 advises giving narrow objects backs.
- Leaks: Unbound pulls the sample toward the block centre where sky light is low (R10). Skipping the lookup at sky light 0 also saves the cave's lookups [inferred], as Unbound's Leaf Shadow Optimization (off at played) does for dark leaves (leaves.glsl); a slanted shaft can light sky-light-0 blocks, so a visual compare decides. Past the map, blend to a sky-light term (R10: over 16 blocks), owned by lighting. All static: deterministic and portable.

### Entity and block-entity shadows
- Claim: Iris defaults shadowEntities and shadowBlockEntities to true, shadowPlayer and shadowLightBlockEntities to false (R7). An entityShadowDistanceMul neither 1 nor negative gets its own frustum at shadowDistanceRenderMul times it, so it shortens only with a positive multiplier [inferred from R7]. R7 never draws a spectator player; played keeps the player's shadow, so the creative player at entities casts one [inferred].
- Unbound's static Bayer fade is deterministic but a visible dither; with TAA, index it by the cycle. Cost: unknown; the entities view's cost row decides. Determinism: the hello pack (no shadows) gave identical TAA-off frames on all 11 views, entities included (docs/measurement.md#visual-protocol); re-check with shadows.

### Contact shadows
- Claim: screen-space shadows "complement shadow maps by capturing small details", shipped for sunlight in Days Gone (R5).
- Cost [inferred]: 8-16 depth reads a pixel, 0.2-0.5 ms at 4K, less at half resolution with a depth-aware upsample (docs/playbook.md#51-structural); a jittered start relies on TAA. A fragment march over depthtex fits Iris and Aperture; R5's code is a compute dispatch [unverified], compute on the 3.3 context [verify in jar].

### Not recommended
- Variance shadow maps (Donnelly and Lauritzen 2006, in R1's references): float targets, blurs, and leaks where casters overlap, as Minecraft's do everywhere [inferred]. Cascades emulated by duplicating geometry add vertex work to a heavy pass; view-dependent warps change shadows with yaw on motion paths [inferred].

## For Optilux
First version: M4 lands the programs for the coverage list and a Low lookup; M5 adds the filters.
- Iris-free includes for the mapping (radial distortion, centre density matched to Unbound's played map, the texel's world size) and the filters, with thin per-backend glue (docs/shader.md#pipeline-spec).
- Programs: shadow_solid depth-only without discard; shadow_cutout testing alphaTestRef; shadow_water writing the tint; shadow_entities, shadow_block. shadowDistanceRenderMul 1, no shadowcolor1, no Nether pass.
- One lookup per pixel in deferred if E2 makes terrain deferred (docs/design.md#8-open-decisions), else forward; translucents and entities do their own. Default filter: noise-free hardware PCF; rotation and PCSS wait for A12.
- Options: SHADOWS Off/Low/Medium/High; shadowDistance 64/96/128/160 (default 96, as in the iso profile); ENTITY_SHADOWS on/off.

| level | map | taps | colour | extra |
|---|---|---|---|---|
| Off | none | 0 | no | sky-light term; shadow.enabled false |
| Low | 2048 | 1 | no | translucents cast none [inferred] |
| Medium | 2048 | 4 | yes | one tap past ~48 blocks, blend band |
| High | 4096 | 9 | yes | PCSS or contact shadows after A12 |

Budget hypothesis at Medium with entity shadows on, ms [inferred, against R11]:

| views | Unbound played | Optilux |
|---|---|---|
| forest_noon, ocean_sunset, rain | 0.93-1.35 | <= 0.8 |
| night | 0.63 | <= 0.6 |
| cave | 0.62 | <= 0.35 (pass only) |
| underwater | 1.86 | <= 0.9 |
| end_dragon, end_city | 1.18 (with march reads) | <= 0.8 + beam reads |
| entities | 0.52 (player only) | <= 0.7 |
| Nether | 0.03 | inside threshold |

What confirms it:
- A feature cost row per level, full mode (docs/measurement.md#verdicts-and-cost-rows), against the table; until timer rows exist (E3), the pass-versus-lookup split from a debug-tier replay share (docs/offline.md#levels).
- Exact trims as A/B verdicts at the identical tier with L4 per-pass golden images: depth-only solid, batched taps, the dropped clear with texelFetch. The sky-light-0 gate, the far tap and the single colour fetch: near, else review.
- The feature: review against Unbound's frames; the TAA-off determinism check with shadows on (A12 or E4's fallback); the live pass for shimmer at each 2-block snap and the sun-to-moon switch. Nether: a cost row inside the threshold and no pass in a replay or Iris's debug text, which says when a pack uses no shadow map (R7) [verify in jar].

L3 golden tests (docs/offline.md#levels): mapping and inverse round-trip, texel size against finite differences, centre density at 2048 and 96; bias offsets for chosen normals, N.L and radii; filter weights summing to 1, a step edge's profile, all levels equal where fully lit or shadowed; the coloured composition; the rotation index equal at f and f + C; the fade band continuous at both ends; the light vector and tap count in Iris's engine (docs/gpu-iris.md#custom-uniforms).

Dependencies: lighting (consumes the term; owns the sky-light fallback, sun-to-moon fade, sunPathRotation, foliage); taa (the cycle C, flush, N_conv); water (tint, caustics; underwater costs most); clouds (cloud shadows multiply the term); fog-volumetrics (End beams and shafts read the map); ao (shared deferred reads); iris (per-dimension programs, the pass rule, 26.3's shadow programs, endFlashShadows); next-gen (voxel shadows, LOD).

## Open questions
- Can a 1.11.7 shadow program write no colour? javap on the pinned jar and an L1 dump.
- Does Unbound's Nether render a shadow pass (its 0.03 ms row; the ACT-only hook suggests not), and does Optilux's world-1 set avoid one? A replay in nether_crimson and IrisRenderingPipeline in the jar.
- Forward or deferred lookup? E2's cost rows on forest_noon.
- Noise-free 4 taps or 2 rotated taps with TAA, at the same look? An A/B cost row and review, after A12.
- shadowtex depth format ("hardware/driver dependent", R6) and ortho planes (R7: -100.05 and 156)? javap.
- Does the 2-block snap shimmer, as the distortion moves texels by fractions where R1 snaps whole texels [inferred]? The live pass.
- Is the sky-light-0 gate identical on all eleven views? A visual compare.
- Is ARB_gpu_shader5 (compare gather) exposed on the 3.3 context? MC_GL_ARB_gpu_shader5 in an L1 dump; Unbound's #version 400 shadow vertex stage running here hints yes [inferred].
- Entity shadow cost and range: the entities view's cost row.
