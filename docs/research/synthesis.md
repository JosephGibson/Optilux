# Shader research synthesis
Status: The synthesis of the 13 verified topic docs in docs/research/ for M4's plan and the user's D72; recommendations only. Nothing here is measured in Optilux, and every Iris fact was read on branches or docs, not the pinned jar (docs/roadmap.md#findings-assigned F9).

## Contents
Index · Architecture · Temporal · Iris gates · Budget · D72 input · Milestones · Premises for M4's plan · Risks · Gaps

## Index
Tags: [inferred] reasoning, [m] measured, [verify in jar] not yet read in the pinned jar. D72 is the user's (docs/roadmap.md#decisions), E2 is decided by measurement, closed decisions stand.
- docs/research/lighting.md: deferred (D) on a 64-bit integer G-buffer, translucents forward through the same include; forward (F) a dev option until E2.
- docs/research/tonemap.md: R11G11B10F scene; one pass ends HDR (bloom mix, grade, fixed exposure, a Lottes-like curve) into gamma-encoded RGB10_A2.
- docs/research/taa.md: after the tonemap; Halton(2,3) over 16 phases, Catmull-Rom history, w 0.9; a v0 first for the flush.
- docs/research/shadows.md: one distorted 2048^2 map, depth-only solid and cutout programs, noise-free hardware PCF, no Nether pass.
- docs/research/ao.md: GTAO-style at half resolution, a spatial filter, indirect light only, no AO history.
- docs/research/sky.md: deferred sky; a gradient in M4; Hillaire LUTs rebuilt each frame in prepare passes in M5.
- docs/research/clouds.md: half-resolution overworld slab, ~16 steps, a worldDay/worldTime clock, TAA the only denoiser.
- docs/research/fog-volumetrics.md: analytic fogs in one include; only the End beams march, at half resolution.
- docs/research/water.md: everything in gbuffers_water; refraction from a pre-fog copy; Sky/Low/Medium reflections.
- docs/research/reflections.md: single-frame screen-space block reflections with mip roughness; puddles on raw rainStrength.
- docs/research/post.md: mip-tile bloom with a Karis prefilter; RCAS-style sharpening after TAA; a static dither last.
- docs/research/next-gen.md: integer floodfill colored light and half-res shafts if a probe and cost rows allow; path tracing not.
- docs/research/iris.md: fragment programs only in M4; compute, SSBO and images after one probe; nothing smoothed under BENCH_DETERMINISTIC.

## Architecture
### Lighting path (E2's candidates)
- D: opaque gbuffers (terrain_solid without discard, terrain_cutout on alphaTestRef, entities, block, hand, opaque particles via particles.ordering=mixed) write `gbuf` RGBA16UI: albedo 3x8, octahedral normal 2x7, block and sky light 7 each, vanilla AO 6, material 6. Blended draws before deferred (spider eyes, damaged block, beacon beam, glint, translucent entities) write `overlay` RGBA8 with a mode in alpha; an R8 `mask` serves TAA. Every later pass reads only these and depth.
- F (LIGHT_PATH, dev): the include per fragment; it still exports normal and material for AO and SSR [inferred].
- M4 draws a shadow pass: the coverage list holds `shadow` (docs/shader.md#coverage-list) and M4 builds every coverage-list program (docs/roadmap.md#m1-to-m6). So E2 can time a real 1-tap lookup plus E2_LOAD, which corrects lighting's "M4 has no shadows" and may lift separateAo's shadow-pass caveat.

### Pass order (iris-gl)
Rules: what gbuffers_water samples sits at colortex4+ (colortex0-3 "are only able to be sampled from fullscreen passes", docs/research/iris.md); one size per pass; no pass reads what it writes (docs/shader.md#pipeline-spec). Scale 1 unless marked.

| Pass (program) | M | Reads | Writes |
|---|---|---|---|
| shadow (shadow_solid, _cutout, _water, _entities, _block) | 4 | alphaTestRef | shadowtex0/1 2048^2; shadowcolor0 RGBA8 tint (M5) |
| sky-lut (prepare-prepare2, overworld) | 5 | uniforms | 256x64, 32x32 RGBA16F; skyview 192x108 R11G11B10F |
| maps (prepare3) | 5 | worldTime | nebula 512x256 RGBA16F; End beam map |
| surface (opaque gbuffers) | 4 | gtexture, vaUV2, mc_Entity | gbuf RGBA16UI; mask R8 |
| overlay (blended, before deferred) | 4 | as surface | overlay RGBA8 |
| ao (deferred, deferred1) | 5 | depth, gbuf | RG16F (AO, 1/viewZ), 0.5 |
| clouds (deferred2) | 5 | skyview, noise | RGBA16F + RG16F, 0.5 |
| light (deferred3) | 4 | gbuf, overlay, shadowtex, ao, clouds, skyview | scene-lit R11G11B10F: lit, sky, clouds, no fog |
| ssr (deferred4, mips of scene-lit) | 5 | scene-lit, gbuf, depthtex1 | refl RGBA16F, confidence in alpha, 0.5 |
| resolve (deferred5) | 4 | scene-lit, refl, gbuf | scene R11G11B10F: reflections, opaque fog |
| forward (water, hand_water, weather, translucent particles) | 4 | depthtex1, scene-lit, skyview | blends into scene |
| beams (composite, End) | 5 | beam map, depth | RGBA16F, 0.5 |
| bloom (composite1-2) | 5 | scene, beams | P R11G11B10F 0.5 mipmapped; tile atlas |
| tonemap (composite3) | 4 | scene, beams, atlas | ldr RGB10_A2, gamma-encoded |
| taa (composite4) | 5 | ldr, history, depth, mask | history RGBA16F, an explicit pair |
| present (final) | 4 | history, or ldr | screen: distortion, RCAS, dither |

- One pre-fog copy (scene-lit) serves refraction and SSR, as Unbound's deferred1 copy does; R11G11B10F settles water's format against reflections' RGBA16F. M4 may fuse light and resolve.
- Fog sits where its doc puts it: opaque in deferred, translucents forward at their own depth; no fog composite. Beams join the bloom prefilter at its matching half size and the scene in the tonemap pass [inferred].
- pipeline.json v1 adds resource names, a history flag per output and budgets (docs/research/iris.md).

### Shared infrastructure
- Half-resolution march and depth-aware upsample (docs/playbook.md#51-structural): one include and one half-size 1/viewZ for AO, clouds, End beams and Medium SSR; AO and clouds could share a pass [inferred].
- Noise: arithmetic (IGN, hashes); for AO a 4x4 set of 16 rotations offset per frame settles ao's IGN-against-tile question at C = 16 [inferred]. Shipped noise waits on the texture-asset question.
- LUTs: sky, nebula, End beam map, an optional cloud-shadow map. Mip chains: scene-lit and P, 0.06-0.1 ms each.
- Every algorithm in an Iris-free include; uniform-only terms in one custom-uniform table per backend.

## Temporal
- TAA denoises: TAA itself, AO's rotation, clouds' dither and LOD switches, the End beams, High SSR; later rotated PCF, PCSS, shafts, SSGI, stochastic SSR, path tracing. Their TAA-off frames stay deterministic (rotation 0, static dither). Nothing else accumulates.
- No state outside TAA in v1: AO, cloud and reflection histories are rejected (a 0.965 weight needs 156 frames). An fp16 floodfill needs the flush and 100-200 frames; the integer form converges within 15 steps, no flush [inferred].
- C = 16: Halton(2,3) indices 1-16 minus their mean, phase frameCounter mod 16; every frame term uses 16 or a divisor. 720720 = 2^4 x 3^2 x 5 x 7 x 11 x 13, so 32, 64, 600 and 3600 fail. pipeline.json's cycle becomes 16 with TAA on.
- N_conv = 53 (smallest n with 0.9^n <= 1/255). Sharpening adds ceil(ln G / ln(1/0.9)) frames for weight sum G, 11 at G = 3 [inferred]: capture 64 frames after an aligned flush, at phase 0. History sticks up to 5 steps off, so only the flush makes frames repeat.
- Flush: hideGUI 0 for one frame invalidates every Clear=false buffer through one history-valid uniform. F12 (docs/roadmap.md#findings-assigned): at entities and coverage views with `hand`, hideGUI reads 0 every frame. Options: a flush at frameCounter mod K (K a multiple of 16 dividing 720720, e.g. 240), an invisible option-driven uniform, or the hand shown another way; the user's, in M5.
- E4's fallback (docs/design.md#8-open-decisions): TAA, its masks and ladder get review and the live pass only; AO, clouds and beams keep identical or near verdicts for optimizations on TAA-off frames, their converged look goes to review; sharpening is under-represented with TAA off; High SSR and the later TAA-denoised items are review only; TAAU, leaving no TAA-off frame, waits on A12; nothing else loses.

## Iris gates
Every row is [verify in jar] by its class (under net.irisshaders.iris); state as read on branches or docs.

| Capability | State | Class |
|---|---|---|
| Sodium keys to terrain_solid (no alpha test), _cutout, water; shadow_solid, _cutout, _water | yes | ShaderKey, ProgramId |
| the pack applies alphaTestRef; entityId per vertex; MC_HAND_DEPTH 0.125 | read in jar (docs/shader.md#facts) | StandardMacros |
| deferred between opaque and translucent gbuffers; particles.ordering=mixed | yes | IrisRenderingPipeline |
| RGBA16UI; its clear; never blended | format yes, clear open | InternalTextureFormat, BlendModeOverride |
| R11F_G11F_B10F, RGB10_A2, RGBA16F, RG16F | yes | InternalTextureFormat |
| colortex0-3 unsampleable in gbuffers | yes | IrisSamplers |
| size.buffer, one size a pass; scale.<pass>; mip flags per program | yes; program lists conflict | ShaderProperties, CompositeRenderer |
| flips toggle; frame-end copy of flipped Clear=false buffers | yes | BufferFlipper, FinalPassRenderer |
| previous matrices (per program, identity first), previousCameraPosition | yes | MatrixUniforms, CameraUniforms |
| custom uniforms on frameCounter, viewWidth, matrices, sunAngle, worldTime, worldDay, eyeBrightness, rainStrength, held light | yes | kroppeb.stareval Parser, CustomUniforms |
| smooth(), wetness, eyeBrightnessSmooth on the wall clock (docs say ticks; source holds) | yes, barred | SmoothFloat, SmoothedFloat |
| rainStrength PER_TICK; sun at the tick delta; the End's worldTime; hideGUI per frame | yes; still under freeze open | CommonUniforms, CelestialUniforms, WorldTimeUniforms |
| separateAo (maybe needing a shadow pass), oldLighting, oldHandLight | yes | WorldRenderingSettings, IdMapUniforms |
| mc_Entity, at_midBlock.w in core terrain; mc_sampleGlint's clock | open | TransformPatcher |
| shadow directives, compare samplers, SEPARATE_HARDWARE_SAMPLERS, a colourless shadow program, endFlashShadows | yes; colourless open | PackShadowDirectives, ShadowRenderer |
| sky, stars, sun, moon, clouds, weather directives; prepare; program.<world>/<name>.enabled | yes; 26.3 open | ShaderProperties, ProgramSet |
| raw TEXTURE_3D custom textures; noisetex from Random(0) | yes | CustomTextureData, NativeImageBackedNoiseTexture |
| depthtex1 copied before deferred; gbuffers_water sees deferred's flips | yes | RenderTargets |
| textureGather select, bitCount (ARB_gpu_shader5) | open | StandardMacros |
| compute, custom images (ARB_clear_texture), SSBO | unlikely: ARB_compute_shader "OpenGL 4.2 is required" | FeatureFlags, IrisRenderSystem, GlImage |
| final target format, RGBA8 assumed | open | FinalPassRenderer |

## Budget
- 26.3 baseline [m], Unbound played GPUBusy (results/records/m3-shadows-full-1.json): forest_noon 8.20, end_city 8.18, end_dragon 8.16, rain 7.60, underwater 7.46, ocean_sunset 7.38, nether_soul 6.50, nether_crimson 5.91, night 5.51, cave 5.39, entities 5.38 ms; shadows off -0.86 mean. ALC's 1.21.11 ablations are context (config/profiles/complementary-unbound-played.json): TAA 0.579, clouds 0.302, water reflection 0.192, SSAO 0.138, bloom 0.128 ms.
- Medium per feature [inferred]: lighting 0.25-0.65; tonemap 0.1-0.25; TAA 0.3-0.45, +0.1-0.3 if history flips; shadows 0.35-0.9 (0 Nether); AO 0.08-0.25; sky to 0.12; clouds 0.05-0.33; fog to 0.08; End beams 0.3-0.55; water 0.35-0.55 on open water, else 0.05-0.1; reflections to 0.1, rain 0.2-0.8; bloom 0.1-0.2; sharpening 0.02-0.05.

| View type | Unbound ms | Optilux features ms |
|---|---|---|
| day (forest_noon, ocean_sunset, entities) | 5.4-8.2 | 1.5-3.6 |
| night | 5.5 | 1.7-3.3 |
| rain | 7.6 | 1.7-3.7 |
| underwater | 7.5 | 1.5-3.2 |
| cave | 5.4 | 1.2-2.5 |
| Nether | 5.9-6.5 | 1.0-2.0 |
| End | 8.2 | 1.5-3.5 |

- Outside the sums: the base (raster, exports, entities), which no doc estimates; Iris copies and mips, under 0.5 ms.
- End: 73 % of the record's 8.16 ms is about 6 ms for Unbound's march [inferred, a 1.21.11 share], which puts fog's Medium beams at 0.44 ms plus the upsample, at their 0.5 ms budget.
- ALU rates mix 2.124 and 2.43 GHz (14 %); water's dual-issue 37.3 TFLOPS was corrected and no other doc used it.
- Proposal: per-feature budgets at Medium's upper ends in pipeline.json; the default profile under Unbound played on every perf view and under 8.3 ms (120 fps); a Low profile toward 4.17 ms, the panel's 240 Hz (docs/platform.md#mc-263-verified); taken-back features under 1.5 ms mean.

## D72 input
| Candidate | ms [inferred] | Determinism | Aperture | Rec |
|---|---|---|---|---|
| colored light, integer floodfill, 8 chunks | 0.25-0.9, weak basis; ~150 MB | own state, 15 steps, no flush | images fit | later: after the probe and Unbound's COLORED_LIGHTING row; shadowDistance >= 128 |
| its extras | unmeasured | - | - | later |
| light shafts | 0.2-1.2 at half size | A12 | yes | later, on the End-beam march |
| sky-effect reflections | 0.01-0.04 as a panorama | no TAA | yes | later, after clouds |
| world-space reflections | 0.5-2, 200-810 MB SSBO | own history | yes | not for 1.0 |
| ray or path tracing | 7.7-17 | wholly A12 | ray queries unknown | not; with Aperture |
| SSGI (new) | 0.6-2 | A12 | yes | later, AO's High |
| voxel block-light shadows | 0.5-2 | exact if all lights traced | yes | later |
| aurora map | to 0.05 | cycle 1 | yes | later; needs a coverage view |
| border and cave fog | to 0.02 | static | yes | now if the look wants |
| vignette, chromatic aberration | 0-0.03 | static | yes | now if the look wants |
| emissive extras (ores, amethyst) | ~0 | static | yes | a look call |
| lens flare, motion blur, DOF | 0.1-0.6 | not as Unbound writes them | yes | later |
| FXAA | 0.1-0.3 | static | yes | not |
| custom PBR, POM, IPBR | 0.2-0.6 | exact | yes | not (Faithful 64x) |
| TAAU (outside scope) | saves 1-2 | no TAA-off frame | yes | after A12 |

Look-target questions:
1. Reference: Unbound played only, or a third Unbound profile with the taken-back features? Unbound is the only reference pack (docs/design.md#7-decisions-taken-user-2026-10-05).
2. The budget's rate: 120 fps, 240 Hz, or per view against Unbound.
3. Operator (Lottes-like, AgX, Hable, PBR Neutral) from L4 HDR captures re-tonemapped offline; eye adaptation in or out.
4. A physical LUT sky or an art-directed gradient; sun and moon style.
5. Bloom fog; the edge fade in sky colour or border fog; shadowed End beams kept or counted as shafts.
6. Smooth blocks in the material map; puddles on leaves.
7. Pinning gamma, Smooth Lighting and See-Through Leaves: identity, so recalibration.
8. Is generated noise a shipped texture asset (docs/shader.md#look-and-scope)?
9. M6's ratio narrowed to shared features; block SSR needs Unbound's IPBR, so a cost row only.

## Milestones
- D73 stands (user, 2026-10-26): M4 and M5 keep their cut; merged, the plan would be about twice the 40,960-byte cap (docs/roadmap.md#decisions).
- M4 (docs/roadmap.md#m1-to-m6): D72 first; every coverage-list program, shadow included; lighting; tonemap and final; the gradient sky; edge fog; E2; cost and timer rows; L3-L4. M5: shadow filters, sky, clouds, water, fogs, AO, bloom, full TAA, the flush, A6, A12, controls, live pass.
- Unnamed in-scope features: the material map, held-item light and flicker in M4 with lighting; vanilla weather in M4 (coverage list; discarded under BENCH_DETERMINISTIC); block reflections and rain puddles in M5 with water (one ssr include); image sharpening with TAA and underwater distortion in final, M5; entity shadows in M5 with shadows; End beams in M5 with fog; the End flash's light term in M4, its glow in M5 with sky.
- M5 split: M5a the temporal proof, then TAA-free features: TAA v0, `camera.path`, the flush with F12's answer, A6, A12, so E4 closes early; shadows, sky, fogs, water to Medium, reflections, puddles, bloom. M5b the TAA-denoised features and gates: TAA's ladder and masks, AO, clouds, End beams, sharpening, High SSR, positive controls, live pass. It avoids ALC's M3 case (docs/design.md#6-milestones).

## Premises for M4's plan
M4.P00 verifies each at its source, or marks it open:
1. Sodium's terrain keys reach terrain_solid (no alpha test), terrain_cutout and water; shadow keys likewise.
2. Deferred runs between opaque and translucent gbuffers; particles.ordering=mixed works.
3. RGBA16UI allocates, clears or leaves sky to depth, never blends; the float formats load.
4. separateAo fills vaColor.a on Sodium 0.9.2, with or without a shadow pass.
5. mc_Entity and at_midBlock.w reach core terrain and gbuffers_water.
6. oldLighting=false drops face shade; oldHandLight=false; held light at every view.
7. Custom-uniform inputs and the matrix element order (m.<row>.<column> or .x a column).
8. colortex0-3 unsampleable in gbuffers; size.buffer, scale and mip flags as read; the flip copy.
9. mc_sampleGlint() and the wall clock.
10. A colourless shadow program; compare samplers; no Nether pass without a shadow sampler.
11. sky=, stars=, sun=, moon=, clouds=off on 26.3; the End sky's program.
12. Tick-delta and PER_TICK uniforms still under /tick freeze: the TAA-off check on the M4 base.
13. The driver's MC_GL_ARB_* extensions in an L1 dump; Unbound's world0/shadow.vsh, "#version 400 compatibility", ran in m3-shadows-full-1, a hint GLSL 4.00 compiles here [Iris keeping 400 inferred].
14. The final target's format, which sets the dither step.
15. Iris 1.11.7 against branches 26.3 (head 1.11.6), 26.1, 1.21.9 and multiloader-new (F9).

## Risks
- Compute and SSBOs are likely absent; Iris builds computes unchecked, so a refused one fails the load, and an unsupported bufferObject throws: colored light, world-space reflections, Hi-Z and froxels each need a fragment path.
- F12 open voids entities' TAA-on rows.
- The portable history pair costs Iris a copy plus a write; image parity waits on the probe.
- Tick-delta uniforms are untested: the hello pack reads none.
- E2's tier: near only under one 8-bit step of quantization, else close (user sign-off); the bench lacks MoreCulling (played tier), so it sees more leaf overdraw.
- ~20 resources against colortex0-15 verified (docs/gpu-iris.md#passes-and-buffers), 32 in source; dimensions can reuse indices [inferred].
- SSR in gbuffers_water raises every translucent's VGPRs.
- Bloom pulsing and AO shimmer at leaves: the live pass.
- Lottes constants solved as Unbound writes them may trip verify similarity (docs/shader.md#policy).
- Costs scaled from other GPUs and shares carry about 2x; the 0.5 % floor is 0.01-0.04 ms, so small features need timer rows (E3).

## Gaps
- The base (raster, exports, entities): no estimate.
- Coverage programs with no topic: particles, weather, beacon beam, lines, text, lightning, translucent sorting.
- Unassessed not-yet items: rainbows, Nether storm, weather styles, outline styles, hand sway, light-level overlay, armor trims, distant light bokeh.
- Unread primaries: Hillaire 2020 timings, GTAO's body, Lottes 2016, Reinhard, Uchimura, Wronski 2014, Hillaire 2015, Schneider, Bauer, the CoD bloom slides, Pedersen, Frostbite translucency (a 404).
- Weak sources: spec aggregators and search extracts (RX 7800 XT), a Scribd copy (PCSS), slide-text timings (SSSR), Modrinth listings.
- No AMD-measured AO, SSR, cloud, LUT or TAA cost; no Unbound row for ACT, shafts, WSR, Medium SSR or refraction.
- Uncovered: Voxy, Aperture past an outdated guide, VGPRs per pass, off-bench lava and darkness fogs.
