# Clouds
Status: Research on Optilux's clouds (models, noise, lighting, half-resolution march, temporal reuse, cloud shadows, a clock the bench can hold, cost at 4K) for D72 at M4's plan and M5's clouds pass. It is research only: nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
Tags follow docs/gpu-iris.md#sources-and-tags; [inferred] marks this doc's estimates.
- R1 Schneider, "The Real-time Volumetric Cloudscapes of Horizon Zero Dawn", SIGGRAPH 2015 Advances (talk, not read): https://advances.realtimerendering.com/s2015/index.html.
- R2 Guerrilla, Nubis talk page (2017): https://www.guerrilla-games.com/read/nubis-authoring-real-time-volumetric-cloudscapes-with-the-decima-engine. The 2015 prototype "rendered in under 2 milliseconds on the PlayStation 4".
- R3 Schneider, "Nubis, Evolved", SIGGRAPH 2022 Advances (talk): https://www.guerrilla-games.com/read/nubis-evolved. PS5 at 1080p "without the use of temporal upscaling"; no ms.
- R4 Schneider, "Nubis3: Methods (and madness) to model and render immersive real-time voxel-based clouds", SIGGRAPH 2023 Advances (talk): https://advances.realtimerendering.com/s2023/index.html. Voxel clouds with compressed SDFs, "leaving behind the now widely adopted 2.5D methods"; no ms.
- R5 Hillaire, "Physically Based Sky, Atmosphere and Cloud Rendering in Frostbite", SIGGRAPH 2016 PBS course (slides; notes not read): https://www.slideshare.net/DICEStudio/physically-based-sky-atmosphere-and-cloud-rendering-in-frostbite.
- R6 Toft, Bowles, Zimmermann, "Optimisations for Real-Time Volumetric Cloudscapes" (paper, arXiv 1609.05344, 2016): https://ar5iv.labs.arxiv.org/html/1609.05344.
- R7 Wolfe, Morrical, Akenine-Moller, Ramamoorthi, "Spatiotemporal Blue Noise Masks" (paper, EGSR 2022): https://research.nvidia.com/publication/2022-07_spatiotemporal-blue-noise-masks.
- R8 Photon, SixthSurge (pack source; Photon Shaders License Agreement: study allowed, redistribution on its terms only): https://github.com/sixthsurge/photon. Read under shaders/: include/sky/clouds/cumulus.glsl and cirrus.glsl, program/d2_clouds_upscaling.fsh, shaders.properties, settings.glsl.
- R9 Iris source, branch 26.3 (vendor source, head read 2026-10-26; its commit adc75283b matched the pinned jar, docs/platform.md#mc-263-verified): https://github.com/IrisShaders/Iris/tree/26.3. Read: WorldTimeUniforms, IrisExclusiveUniforms, CommonUniforms, MixinLevelRenderer; IrisRenderingPipeline on branch 26.1.
- R10 OptiFine shaders.properties doc (vendor doc; Iris follows it): https://raw.githubusercontent.com/sp614x/optifine/master/OptiFineDoc/doc/shaders.properties.
- R11 shaders.properties wiki, world uniforms (vendor doc): https://shaders.properties/current/reference/uniforms/world/.
- R12 KitGuru, RX 7800 XT review (2023): https://www.kitguru.net/components/graphic-cards/dominic-moass/amd-rx-7800-xt-review/. 60 CUs, 624 GB/s, 64 MB Infinity Cache.
- R13 Complementary Unbound r5.9.3 (pack source; Complementary License Agreement 1.7, reference/complementary-unbound-r5.9.3/License.txt).
- R14 ALC's ablation (RX 7800 XT, 3840x2160, MC 1.21.11, Iris 1.10.7, played settings: Unbound-style clouds, CLOUD_QUALITY 2; config/profiles/complementary-unbound-played.json): CLOUD_QUALITY=0 saves 0.302 ms mean over valid views, 0.649 ms at ocean_sunset [ALC m]. PB, a Reimagined fork on the same GPU: "The Overworld clouds were up to 0.65 ms at 4K" (docs/sources/shader-optimization-playbook.md#41-structural-changes-biggest-wins).
- R15 shaders.properties wiki, custom textures (vendor doc): https://shaders.properties/current/reference/buffers/custom_textures/.

## Unbound r5.9.3
Studied in R13, described in my own words; no code or constants carried over.
- Placement: deferred1 (shaders/program/deferred1.glsl) marches every pixel but the hand [inferred from its depth cutoff] at full resolution, mixes clouds into the scene colour and writes their distance to colortex5's alpha. lib/common.glsl compiles them only under OVERWORLD; shaders.properties sets `clouds=off` unless the Vanilla style is chosen.
- Shape (lib/atmospherics/clouds/unboundClouds.glsl): a thin slab offset from Iris's cloudHeight, NaN-guarded (lib/common.glsl). Density is fBm of 3D noise packed in the 2D noise texture, two bilinear fetches per octave (lib/util/commonFunctions.glsl): four octaves by default, two of 2D noise at Low. It grows in rain through rainFactor, a smooth() of rainStrength (shaders.properties), and falls off from the slab's centre.
- March: fixed-length steps counted from the path through the slab (one or two for a vertical ray, on the order of a hundred for a grazing one [inferred from the step rule]); a dithered start; samples behind terrain skipped unless it fades into the sky; a stop past a horizontal cap of a few thousand blocks, on leaving the slab, or near opacity.
- Light: no light march; shading from height in the slab plus a sun-facing boost, colours from lib/colors/cloudColors.glsl, each sample blended toward a sky colour evaluated per sample.
- Clock: wind from worldTime and worldDay (lib/common.glsl), so played clouds step at 20 Hz; frameTimeCounter only off the default speed. Dither: the noise texture plus a golden-ratio step on frameCounter mod 3600 under TAA (deferred1.glsl); TAA denoises.
- Cloud shadows (lib/lighting/cloudShadows.glsl): CLOUD_SHADOWS is off by default, so played has none. The Unbound style blurs 2D noise at a fixed offset; the Reimagined style projects along the light to its layer.
- Reimagined style (reimaginedClouds.glsl, cloudCoord.glsl): blocky clouds from a 2D map with smoothed texel edges (credited to SixthSurge); first hit only, two light samples in the map.
- Cost: R14; deferred1 (clouds, SSAO, sky fog) is 12 % of Unbound's frame (docs/shader.md#method). Grazing rays marching longest fits ocean_sunset's worst case [inferred].

## Techniques
D = determinism (docs/shader.md#determinism-and-taa), I = Iris 1.11.7 on the 3.3 core context, A = Aperture (docs/shader.md#pipeline-spec).

### T1 A clock the session holds
- Claim: one custom uniform drives all cloud motion: ticks = (worldDay mod P) x 24000 + worldTime. R11: worldTime is "equivalent to the command `time query daytime`"; worldDay "is reset by any `time set` command". R9: both per tick from the level's default clock. Each overworld view's function runs `time set` (optilux/world.py) with time advance off and /tick freeze (config/suite.json setup), so both hold. Unbound (R13) and Photon (R8: world_age) use this form, each wrapping worldDay.
- Rejected: cloudTime (game time mod cloud texture width x 400, plus the partial tick, scaled; 0 with no cloud texture: R9 MixinLevelRenderer), as no command sets the game time (docs/plans/m3.md#3-premises P22); frameCounter, reset at every pipeline creation (docs/gpu-iris.md#frame-counters-and-reload), so dither phase only; frameTimeCounter, wall-clock (P19); smooth(), which fades over seconds (R10: "Default fade time is 1 sec.") [verify in jar].
- Look lost: the bench field is frozen, one per view time and place; only the live pass sees drift. In play the drift steps at 20 Hz, a few pixels per tick overhead [inferred], as Unbound's played clouds do (R13).
- Precision: wrap each octave's offset by its tile period on the CPU (frac) [inferred]. Cost: none per pixel (docs/playbook.md#4-design-defaults).
- D: holds, nothing smoothed. I: custom uniforms read what CommonUniforms.addNonDynamicUniforms registers, WorldTimeUniforms included (R9), with frac (docs/gpu-iris.md#custom-uniforms); worldTime and worldDay are in optilux/l1.py's IRIS_UNIFORMS [verify in jar]. A: the formula in backend glue (Aperture's `ap.*` uniforms, docs/platform.md#renderer-transition).

### T2 Volumetric slab march
- Claim: the common form is a 2.5D layer (R4's term), coverage x height profile x 3D shape noise eroded by finer noise, marched between two altitudes, as R8's cumulus is (coverage map, altitude fraction, two 3D Worley textures). R4's voxel clouds are out of scope.
- R6, GTX 1080 at 1920x1080: 128 steps cost 297.7 ms at full and 128.0 ms at half resolution (43 %, not 25 %); 8 steps at half 2.3 ms; quarter resolution, 8 jittered steps and TAA 2.4 ms; "visually similar results with 1/16 the number of steps" (abstract).
- R5, Xbox One: main view at half resolution per axis (640x360 at 720p) with temporal reprojection, 0.72 ms at 720p, 1.09 ms at 900p (slide 44).
- R8 defaults (settings.glsl): 40 steps at the horizon, 20 at the zenith, 6 light and 2 ambient steps, one fresh ray per 4x4 block a frame; stop below 0.075 transmittance (cumulus.glsl).
- Cost here: half resolution marches a quarter of the rays, but R6's 43 % says cost falls slower, so a quarter to a half of R14 at Unbound's per-ray work [inferred]. Each T4 light sample adds a fetch per step.
- Ladder: Low = T7; Medium ~16 steps, 2 octaves, 1 light sample; High ~24-32 steps, 3 octaves plus erosion, 2-3 light samples [inferred].
- D: deterministic given T1 and T6. I: one deferred fragment pass, sampler3D or packed 2D noise. A: march, density and integration in Iris-free includes.

### T3 Shape noise
- Claim: Photon loads two 64^3 R8 Worley volumes as raw TEXTURE_3D (R8 shaders.properties). R10 documents raw textures (type, internal format, dimensions, pixel format and type); R15 adds Iris's customTexture.<name> (its own sampler) and says raw textures use "bilinear filtering and clamping" by default, so tiling noise needs a .mcmeta with clamp off. PB's packed 2D layout reads both slices in one fetch [PB b] (docs/playbook.md#54-sample-count-and-precision-trades).
- For Optilux: a seeded tileable generator in Python, committed, its data written by `pack build`; nothing derived from Unbound's or Photon's textures (docs/shader.md#policy).
- Cost: one fetch per octave per step; 64^3 R8 is 256 KB against 64 MB of Infinity Cache (R12), likely resident [inferred].
- D: static. I: 3D textures are core GL, so the context is no limit; Iris's raw loader and .mcmeta [verify in jar]. A: a plain texture.

### T4 Lighting
- Scattering per step, integrated analytically: (S - S exp(-sigma_t D)) / sigma_t (R5 slide 29; slide 32: "Energy conservative"). R6: brightness then no longer depends on step length, allowing larger steps. R8 does the same.
- Phase: two Henyey-Greenstein lobes, defaults g0 0.8, g1 -0.5, blend 0.5 (R5 slide 34); constant along a ray, so once per ray.
- Multiple scattering: octaves of scattering, extinction and phase (R5 slides 61-62); R8 runs 8, lowering extinction and anisotropy each. Each octave adds an exp per step at quarter rate (docs/gpu-iris.md#transcendentals): 2-4 at Medium [inferred].
- Sun: Low a height gradient (as Unbound); Medium 1 low-frequency sample toward the light; High 2-3 with growing steps (R8 doubles each).
- Ambient: sky irradiance above, ground bounce below (R8: a planet albedo), as custom uniforms from the sky model.
- Aerial perspective: once, at the transmittance-weighted mean depth (R5 slide 40), not per sample as in Unbound.
- D: no accumulation. I: custom uniforms only. A: include.

### T5 Half resolution, depth-aware upsample
- Claim: docs/playbook.md#51-structural [PB b]: a half-size pass where texel h marches pixel 2h + 1 with its coordinates and dither; upsample at x * 0.5 - 0.5 from 4 texels, bilinear x depth-similarity weights (~3 %) on stored 1/viewZ; premultiplied RGBA16F; cloud depth on the same weights; a 4x4 search for low confidence, never a full-resolution fallback march; the night nebula added at full resolution after.
- Cost: a quarter of the rays (measured drop: T2). The upsample reads ~17 MB of RGBA16F and ~8 MB of RG16F, ~0.04-0.08 ms at 624 GB/s (R12) [inferred]; folded into the consumer it writes nothing extra.
- D: exact mapping. I: `size.buffer.colortexN = 0.5 0.5` draws the pass at that size (docs/gpu-iris.md#passes-and-buffers, PB v) [verify in jar]. A: explicit half-size target, no flipping.

### T6 Dither and temporal reuse
- Dither: a per-pixel start offset from generated spatial blue noise or a hash, plus a golden-ratio step on frameCounter mod c, the TAA cycle (8 or 16). 720720 = 2^4 x 3^2 x 5 x 7 x 11 x 13: 32 and Unbound's 3600 do not divide it. An STBN mask (R7) would be generated with c slices [inferred].
- Pitfall: in R6 per-ray jitter took 8 half-resolution steps from 2.3 to 7.5 ms, which the authors attribute to texture-cache misses; one offset for all rays removed the cost but gave TAA nothing to resolve. Cost: a hash per pixel plus that risk.
- Option a: TAA alone, as in Unbound.
- Option b, a cloud history (R8 d2_clouds_upscaling.fsh): one pixel per k x k block refreshed a frame (frameCounter mod k^2, k 4 by default), blended by age up to a limit; history rejected off-screen, behind nearer terrain, on the hand, on NaN or a clock change; a 3x3 clamp under fast camera motion; history read and written in one pass (flipping); advection by frameTime. R6: R1 updated in a 4x4 pattern, at half resolution (section 2) or quarter (abstract).
- D: a needs TAA-on determinism (A12; docs/design.md#8-open-decisions E4). b adds a second history: the same flush, its own N_conv, k^2 dividing 720720 (k 2, 3, 4, 6 or 12), advection from T1. Under E4's fallback both get review-tier verdicts only.
- I: b needs gbufferPreviousModelView, gbufferPreviousProjection and previousCameraPosition (optilux/l1.py IRIS_UNIFORMS, from the jar). A: b needs explicit ping-pong.

### T7 Layered 2D clouds
- Claim: one analytic plane hit per sky pixel, 2-3 octaves of 2D noise, a phase term and faked thickness; also the main layer's Low [inferred]. R8's cirrus is a shell hit plus a light march (~11 noise fetches per density sample, cirrus.glsl) and its altocumulus is marched (settings.glsl): both cost more.
- Cost: 0.03-0.1 ms at full resolution, a quarter at half [inferred: ~25 M bilinear fetches on 60 CUs at an assumed 4 texture units each, not in R12]. Ladder: off or one layer.
- D: deterministic without TAA when undithered. I and A: core fragment code.

### T8 Step caps and LOD
- Claim: cap far-ray steps, stretch the step and scale opacity to match; skip the finest octave past a dithered distance [PB b] (docs/playbook.md#54-sample-count-and-precision-trades). R6: R1 took longer steps on the base shape alone while density stayed below a threshold. Loop counts from an int custom uniform (docs/gpu-iris.md#occupancy). ALC measured a cloud-march early exit as no win [ALC m] (docs/playbook.md#6-did-not-work).
- Cost: bounds the grazing rays behind ocean_sunset's worst case; its size waits for a cost row. D: dithered switches rely on TAA; tier review. I: int custom uniform [verify in jar]. A: include.

### T9 Cloud shadows on terrain
- Analytic: project the shaded point along the light to the slab's middle and read low-frequency coverage (1-2 fetches), as Unbound's Reimagined style does (lib/lighting/cloudShadows.glsl). Map: R8 renders a 512x512 cloud shadow buffer (size.buffer.colortex8 = 512 512).
- Cost: analytic 0.02-0.06 ms at 4K [inferred: 1-2 fetches per lit pixel]; a 512^2 map has an eighth of the half-resolution pass's pixels, each a coverage read [inferred]. Ladder: off / on.
- D: same clock, no accumulation. I: fixed-size buffers (R10); a map read in gbuffers needs a prepare pass, which R9's 26.1 pipeline runs inside its shadow rendering [verify in jar]. A: include.

## For Optilux
- First version (M5): T1-T5 and T6a; T7 as Low and an optional high layer; T9 analytic.
  - clouds-march: deferred, overworld only (program.<world>/<name>.enabled, docs/gpu-iris.md#passes-and-buffers), half resolution, writing premultiplied RGBA16F and RG16F (1/viewZ, cloud distance). The deferred sky pass upsamples and fades to sky; the lighting include holds the shadow function.
  - `clouds=off` in shaders.properties, as in Unbound and Photon: gbuffers_clouds then draws nothing, so the coverage list needs a waiver or a vanilla mode (docs/shader.md#coverage-list) [verify in jar]. R9's 26.1 pipeline reads the pack's cloud setting.
  - Altitude, coverage and thickness are look constants, so cloudHeight is not read (R9: the CLOUD_HEIGHT environment attribute, not the clouds option). Rain coverage reads rainStrength (R9: per tick, the level's rain level, unsmoothed), never a smooth() of it.
  - Options: CLOUDS Off / Low / Medium / High; CLOUD_SHADOWS on/off. Off disables the pass and its consumer stops reading it (docs/playbook.md#7-pitfalls).
- Budget hypothesis, ms at 4K: Medium at half of Unbound's cost per view, High at Unbound's. R14 gives only the mean and the worst view, on ALC's views of these roles; other rows are [inferred]. Unbound's clouds are not compiled outside the overworld (R13): if R14's mean covers Nether and End views, its overworld mean is higher.

  | View type (views) | Medium | High |
  |---|---|---|
  | grazing sky (ocean_sunset) | 0.15-0.33 | 0.30-0.65 |
  | open sky (night) | 0.10-0.25 | 0.20-0.45 |
  | terrain with sky (forest_noon, rain, entities) | 0.05-0.15 | 0.10-0.30 |
  | no sky (cave, underwater): the pass still writes ~25 MB | 0.02-0.05 | 0.02-0.05 |
  | Nether, End | 0 | 0 |

- Confirm: cost rows of CLOUDS Off against each level per perf view, quick then full, and the dither and resolution variants as A/B rows (docs/measurement.md#verdicts-and-cost-rows); L4 attribution and per-pass golden images, L2 VGPRs of the march, explain only (docs/offline.md#levels); review tier, as for every feature (docs/measurement.md#visual-protocol); the TAA-off static capture identical across two sessions on every overworld view with clouds on, then A12; the live pass for drift steps and ghosting.
- L3 golden tests: slab entry and exit (up, down, grazing, inside); T4's integration equal at 4, 16 and 256 steps on constant density; HG lobes integrate to 1; the generator tiles and is byte-reproducible; packed 2D within 1/255 of two-fetch noise; the clock uniform in Iris's engine equals the GLSL, continuous across the day boundary, exact under the wrap; upsample weights sum to 1, keep a constant field, return a representative's value, give 0 past a 3 % depth step; one dither cycle, no frameCounter read at cycle 1.

## Open questions
- Does 1.11.7 honour `clouds=off` on 26.3? Decided by javap on the jar and an L1 dump run.
- Do worldTime and worldDay hold under the session setup in 1.11.7? Decided by the jar and a TAA-off check across two sessions with clouds on.
- Do rainStrength and thunderStrength (the level's weather at the tick delta, R9; not on P19's list) hold on the rain view under /tick freeze? Decided by the jar and two rain captures.
- Do raw TEXTURE_3D textures and their .mcmeta load on the 3.3 core context? Decided by the jar, L0 and an in-game compile.
- Does "no texture assets ship" (docs/shader.md#look-and-scope) cover generated noise data? Decided by the user.
- Per-pixel or coarser dither on RDNA3, given R6's cache-miss cost? Decided by A/B cost rows at ocean_sunset.
- Does the 20 Hz drift read as judder? Decided by the live pass; Unbound's played clouds step alike.
- Should TAA reproject cloud pixels at the cloud distance? Decided by A6 sequences and the live pass (taa topic).
- Is a cloud history (T6b) worth a second flush? Decided after A12 by a cost row against T6a.
