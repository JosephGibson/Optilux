# Water
Status: research on Optilux's water (gbuffers_water surface, waves, Fresnel, absorption, refraction, reflections, underwater) from external sources and Unbound r5.9.3's code. Nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
- R1 Complementary Unbound r5.9.3, pack source, Complementary License Agreement 1.7 (redistribution only on its terms): reference/complementary-unbound-r5.9.3/License.txt; files under shaders/.
- R2 ALC ablations of Unbound, RX 7800 XT, 3840x2160, MC 1.21.11, Iris 1.10.7 (docs/gpu-iris.md#sources-and-tags) [m]: config/profiles/complementary-unbound-played.json, ms saved, mean over valid views (worst).
- R3 M. Finch, Effective Water Simulation from Physical Models, GPU Gems ch. 1, book, 2004: https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects/chapter-1-effective-water-simulation-physical-models
- R4 T. Sousa, Generic Refraction Simulation, GPU Gems 2 ch. 19, book, 2005: https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-19-generic-refraction-simulation
- R5 M. McGuire, M. Mara, Efficient GPU Screen-Space Ray Tracing, JCGT 3(4), paper, 2014: https://jcgt.org/published/0003/04/04/ ; timings from McGuire's post, 2014: https://casual-effects.blogspot.com/2014/08/screen-space-ray-tracing.html
- R6 AMD FidelityFX SSSR, vendor doc, v1.1.4 (2025): https://gpuopen.com/fidelityfx-sssr/
- R7 R. Pope, E. Fry, Absorption spectrum (380-700 nm) of pure water II, Applied Optics, paper, 1997; data in 1/cm: https://omlc.org/spectra/water/data/pope97.txt
- R8 LearnOpenGL, PBR Theory, tutorial, undated: https://learnopengl.com/PBR/Theory
- R9 A. Kaplanyan et al., Filtering Distributions of Normals for Shading Antialiasing, HPG, paper, 2016 (abstract): https://research.nvidia.com/publication/filtering-distributions-normals-shading-antialiasing
- R10 Iris docs (shaders.properties), vendor doc, current: https://shaders.properties/current/reference/overview/ and its buffers, constants, rendering, uniforms and programs/gbuffers pages.
- R11 Iris source, IrisRenderingPipeline, branch 26.3 (head 1.11.6; jar 1.11.7: docs/platform.md#mc-263-verified): https://github.com/IrisShaders/Iris/blob/26.3/common/src/main/java/net/irisshaders/iris/pipeline/IrisRenderingPipeline.java
- R12 Photon (sixthsurge), pack source, Photon Shaders License Agreement (custom: study allowed, modification personal only): https://github.com/sixthsurge/photon , shaders/include/surface/water_normal.glsl
- R13 RX 7800 XT: 3,840 stream processors, 2.43 GHz, 624 GB/s, 64 MB Infinity Cache, 37.3 TFLOPS FP32 (aggregator citing AMD, 2023): https://flopper.io/gpu/amd-radeon-rx-7800-xt-16gb ; 3,840 x 2 x 2.43 GHz = 18.7 TFLOPS, so 37.3 counts dual issue [inferred].
- R14 Khronos refract page, vendor doc (zero vector when k < 0): https://registry.khronos.org/OpenGL-Refpages/gl4/html/refract.xhtml

## Unbound r5.9.3
In Optilux's words; paths under reference/complementary-unbound-r5.9.3/shaders/ (R1).
- Layout: every translucent runs program/gbuffers_water.glsl; a block id selects lib/materials/specificMaterials/translucents/water.glsl; a second target's per-channel tint feeds only program/composite1.glsl's effects behind translucents (volumetrics, rainbows, improved rain).
- Played: SHADER_STYLE 4 sets WATER_STYLE 3; WATER_REFLECT_QUALITY 1 is Potato; DETAIL_QUALITY 2 leaves refraction off, on from 3, which also enables sky-effect reflections by default (lib/common.glsl). ALC's played settings never ran the SSR march (docs/lessons.md#gpu).
- Waves: a bundled tiling texture (bilinear, wrapping by its .mcmeta) read at four scales scrolling apart, after a parallax loop of 4 iterations of 2 fetches; bump rises with sky light, falls at grazing angles; normals whose reflection points into the water are pulled to the face normal (water.glsl). Clock: frameTimeCounter.
- Vertex waves, on by default: two sines lower the top surface by a few hundredths of a block, faded where sky light is low, skipping whole-block heights; the shadow pass does the same (lib/materials/materialMethods/wavingBlocks.glsl).
- Fresnel: a cubic in 1 + N.V over a 15 % floor (gbuffers_water.glsl), mixed in gamma-encoded colour that composite1 raises to 2.2 later; R8 gives water's F0 as 0.02 linear, 0.15 sRGB, so the floor matches F0 in that encoding [inferred].
- Opacity: exponential in the view-ray gap to depthtex1 (e-folding near 13 blocks) from a 25 % floor, toward 1 at grazing angles; one channel (water.glsl).
- Copy: program/deferred1.glsl writes every frame, at any WATER_REFLECT_QUALITY, the lit opaque terrain before fog, square-root-encoded in RGBA8 (lib/pipelineSettings.glsl); sky pixels stay black unless sky-effect reflections are on.
- Reflections (lib/materials/materialMethods/reflections.glsl, reflectionBackground.glsl): Potato projects the reflected direction once, nudged by a fraction of the view position, reading one depthtex1 depth and one copy colour; Medium marches 30 doubling steps, up to 6 refinements, on depthtex1. Misses take a low-quality (Potato) or full (Medium) sky plus a GGX sun highlight; the dither moves per frame under TAA (docs/shader.md#determinism-and-taa).
- Refraction (composite1, lib/materials/materialMethods/refraction.glsl): a noise offset scaled by FOV over distance and by thickness up to one block, kept only where the offset pixel is water too (R4's guard), on the blended image. Clock: frameTimeCounter.
- Underwater: composite1 tints by fixed factors; fog e-folds over 32 blocks at played settings (lib/atmospherics/fog/waterFog.glsl); program/final.glsl wobbles the screen by a sine of frameTimeCounter. From below, reflection is halved, transmission cut by a Fresnel power (water.glsl).
- Foam on top faces near the floor, its threshold scrolling noise (water.glsl); caustics in water's shadow colour (program/shadow.glsl).
- Workarounds [pack source, not checked in game]: a normal facing away is flipped (an Iris fix); water's sky light +7 % for an Iris/Sodium inconsistency; from 26.1 cauldron water has its own id (gbuffers_water.glsl, water.glsl).
- Cost: water is 4 % of Unbound's frame (docs/shader.md#method). WATER_REFLECT_QUALITY -1 against played's 1 saved 0.192 ms mean, 0.321 at ocean_sunset (R2) [m, ALC]: gbuffers_water's reflection path only (lookup, low-quality sky, GGX), as deferred1 writes the copy either way. Medium SSR and refraction were never timed.
- All animation reads frameTimeCounter: Unbound stays a look reference (docs/measurement.md#visual-protocol).

## Techniques
4K is 8.3 M pixels; water at ocean_sunset taken as ~40 %, ~3.3 M pixels [inferred]; ALU at single issue, 3,840 lanes x 2.43 GHz (R13). D determinism, I Iris 1.11.7, A Aperture.

### Wave normals
- Finch: 4 geometric and about 15 texture waves; "the fine waves in our water texture dominate the realism of our simulation" (R3). Photon: noise-perturbed procedural waves turned by the golden angle, a finite-difference normal, quarter-step parallax (R12).
- Optilux: N directional waves turned by the golden angle (R12), analytic normal (R3); each wave's slope fades to 0 as its wavelength nears two pixel footprints (fwidth of world xz): band-limiting instead of mips, less distant shimmer before TAA [inferred]. No parallax in V1.
- Cost: 8 sin/cos pairs at quarter rate (docs/gpu-iris.md#transcendentals), ~150 lane-ops a pixel: 3.3 M x 150 / (3,840 x 2.43 GHz) = 0.05 ms at full issue, 0.05-0.1 ms with occupancy and overdraw [inferred]; a texture variant, 2-4 bilinear fetches. Ladder: Off flat, Low 4 waves, Medium 8, High 8 plus a noise-phase fetch.
- D: a uniform clock, constant under BENCH_DETERMINISTIC (frozen phase, cycle 1, same instructions, so the perf row holds live); live, frameTimeCounter, which "resets after 3600s" (R10), so every period divides 3600 s or the waves jump hourly [inferred]. No TAA dependence.
- I: vaPosition, chunkOffset (docs/shader.md#facts), cameraPosition (docs/gpu-iris.md#custom-uniforms), frameTimeCounter (docs/gpu-iris.md#frame-counters-and-reload) [verify in jar]. A texture variant needs texture.<stage>.<buffer> (OptiFine syntax, as Unbound) or Iris-only customTexture; PNGs load RGBA8, nearest and wrapping unless a .mcmeta says otherwise; mips undocumented (R10).
- A: a pure function of world xz, time and footprint in an Iris-free include.

### Vertex waves (D72 input)
- Not on the scope list (docs/shader.md#look-and-scope). Finch filters out geometric waves "too short" for the mesh (R3); Sodium meshes about one quad per water face [inferred], so wavelengths under ~3 blocks facet.
- Cost: ~250 k water vertices at render distance 16 (config/suite.json), under 0.01 ms [inferred]; the shadow pass must displace the same (shadows topic).
- D, I, A: as wave normals; vaPosition + chunkOffset is camera-relative (docs/shader.md#facts). Unbound's iso keeps them on, its default: M6's ratio.

### Fresnel and Snell's window
- Schlick, F0 0.02 for water (R8). From below, total internal reflection past asin(1/1.333) = 48.6 deg; refract() returns a zero vector there (R14): reflection only.
- Cost: a few ALU. D: none. I: isEyeInWater, 0 none, 1 water, 2 lava, 3 powdered snow (R10) [verify in jar]. A: include.

### Absorption and in-scatter
- Beer-Lambert per channel. Pure water absorbs 0.34 /m at 650 nm, 0.057 at 550, 0.0092 at 450 (R7): over 16 m red keeps 0.4 %, green 40 %, blue 86 %. Minecraft water reads murkier, so the coefficients are look parameters keeping that ratio [inferred]. In-scatter in closed form, no march: (1 - T) x scatter colour x ambient (sky light x a sky-colour custom uniform) [inferred].
- Thickness: fragment depth against depthtex1 at the refracted pixel, both linearized through gbufferProjectionInverse; depth is forward (docs/platform.md#mc-263). Pitfall: far is the render distance (docs/shader.md#facts), "not the far clipping plane distance, which is roughly far * 4.0" (R10).
- Cost: one texelFetch, three exp, under 0.03 ms [inferred]. D: no frame term. I: depthtex1 "excludes transparent geometry" (R10), copied in beginTranslucents before the deferred passes (R11) [verify in jar]. A: depths as arguments; Aperture's solidDepthTex is the analogue (docs/platform.md#renderer-transition).
- The medium's constants are shared with underwater fog (fog topic).

### Refraction from a scene copy
- The scene without refractive meshes goes to a texture; the lookup is offset by the normal map's xy and kept only where it lands on the refractive object, so foreground objects do not leak in (R4).
- Optilux: the deferred lighting pass also writes the lit opaque scene (sky and clouds in) to a copy; gbuffers_water samples it at the offset, drops the offset where depthtex1 there is nearer than the fragment, and writes refracted x T + in-scatter at alpha 1: per-channel absorption, no extra target. It draws into the scene target, hence the copy [inferred]. Limit: glass under water is overwritten [inferred].
- Cost: R11F_G11F_B10F, 4 bytes, 33 MB a frame on every view: 0.05 ms of writes at 624 GB/s (R13; docs/gpu-iris.md#bandwidth), ~0.05-0.1 ms in all [inferred]; 2-3 fetches a water pixel. Ladder: Off (blending, one-channel opacity), On.
- D: none. I: gbuffers_water is among "the only programs that render after deferred" (R10) and sees deferred's flips (R11's flippedAfterTranslucent; Unbound relies on it) [verify in jar]; R11F_G11F_B10F is listed, Iris 1.8+ (R10) [verify in jar]. A: an explicit texture, no flipping.

### Reflections
- Sky (in scope): the sky topic's function on the reflected direction x sky light.
- Low: one projected sample, Unbound's Potato (R1): 1 depth and 1 copy fetch; wrong where the reflected object is far from the assumed distance. Unbound's whole Potato path (lookup, low-quality sky, GGX) cost 0.192 ms mean, 0.321 at ocean_sunset (R2) [m].
- Medium: perspective-correct screen-space DDA, finite thickness (R5), on depthtex1: 16 steps and 4 bisections, count from an int custom uniform (docs/playbook.md#4-design-defaults), static dither from a cheap hash (docs/playbook.md#53-exact-trims), sky on a miss. Basis: "25 iterations for every pixel on the screen at 1920x1080 in less than 1 ms" on a GeForce Titan (R5); x1.6 pixels, x0.8 iterations, a GPU assumed 2-3x faster: under 0.45-0.65 ms, 0.3-0.8 ms with forward-pass divergence [inferred].
- High: 24-32 steps, the start jittered by frameCounter mod the TAA cycle.
- Hi-Z traversal with a multi-frame denoiser (R6) targets D3D12 and Vulkan, its depth hierarchy built by SPD: Aperture-era [inferred].
- D: Sky, Low, Medium have no frame term (cycle 1); High denoises through TAA, rests on A12 (docs/design.md#8-open-decisions E4) and gets review-tier verdicts only under E4's fallback.
- I: half-resolution SSR must be a composite: "Any buffer whose size is changed cannot be rendered to by a gbuffers pass" (R10). The march sets gbuffers_water's VGPR step for every translucent (docs/gpu-iris.md#occupancy); PB moved water from 84 to 72 with custom uniforms (docs/playbook.md#4-design-defaults).
- A: one ssr include shared with block reflections (reflections topic).

### Sun glint and specular antialiasing
- Filtering the NDF over a region estimated from the pixel footprint is "temporally stable, and compatible with deferred shading, normal maps" (R9); taking the region from screen-space derivatives of the wave normal is Optilux's version [inferred]. Unbound flattens its wave-shaped highlight toward a constant as a mip-level estimate grows (R1 water.glsl, lib/util/miplevel.glsl).
- Cost: derivatives and a few ALU [inferred]. D: none; fewer fireflies for TAA. I: derivatives only, core GLSL 3.30. A: include.

### Underwater fog and distortion
- Fog: Beer-Lambert over view distance with the absorption constants, opaque in deferred, translucents forward (fog topic). Under BENCH_DETERMINISTIC fogColor in water settles after 3 s and fogEnd is not read (docs/shader.md#determinism-and-taa); own constants avoid both.
- Distortion (in scope): a small sine UV wobble in the last pass, after TAA, so history never sees it; frozen phase under BENCH_DETERMINISTIC; ~0 ms in an existing pass [inferred]. I: isEyeInWater (R10) [verify in jar]. A: the wobble in an include.

### Foam, caustics, ripples (D72 input)
- Foam: Unbound's shoreline band from the depth gap on top faces (R1); reuses the thickness fetch, 0.01-0.03 ms [inferred]; static under BENCH_DETERMINISTIC.
- Caustics: an animated pattern in water's shadow colour (R1 shadow.glsl); cost in shadow-map texels; needs the shadows topic's coloured shadows; constant phase under BENCH_DETERMINISTIC.
- Rain ripples: wetness eases by its half-life (R10), a smoothing that moves under /tick freeze (docs/measurement.md#visual-protocol); rainStrength is interpolated across weather changes (R10) [verify in jar]. Not V1.
- Sky-effect and world-space reflections are not-yet (docs/shader.md#dropped-features). With sky and clouds in the copy, a miss can read the copy where the reflected direction projects, inside the frame only [inferred]; Unbound's copy has no sky.

## For Optilux
### First version
- M4 (docs/shader.md#coverage-list): gbuffers_water as a lit translucent surface (texture x vertex colour x the lighting topic's light, fog); water and glass split by block id. No water feature.
- M5, in gbuffers_water: waves, Fresnel and Snell's window, thickness at the refracted pixel, refraction from the copy with the leak guard, per-channel absorption and in-scatter, Sky, Low or Medium reflection, footprint-filtered glint, then fog. Underwater fog opaque in deferred, translucents forward (fog topic); distortion in the last pass.
- The copy: scene-lit, the R11F_G11F_B10F output of the deferred lighting pass, one pre-fog copy shared with block SSR (docs/research/synthesis.md#pass-order-iris-gl).
- Includes: water_waves, water_optics (Fresnel, Snell, Beer-Lambert, in-scatter, constants), ssr; gbuffers_water and the deferred resolve pass are glue.
- No water-owned history: TAA's flush covers water. High SSR waits for TAA and A12.

### Options
- WATER_WAVES Off, Low, Medium, High; WATER_REFLECT Off (glint only), Sky, Low, Medium, High; WATER_REFRACT Off, On; UNDERWATER_DISTORTION Off, On.

### Budget hypothesis
ms at 4K, water's shadowed lighting excluded; every cell [inferred] from the costs above.

| Views | Sky, no refraction | Low + refraction | Medium + refraction |
|---|---|---|---|
| ocean_sunset, night | 0.1-0.25 | 0.35-0.55 | 0.6-1.1 |
| rain | 0.03-0.1 | 0.1-0.2 | 0.15-0.4 |
| underwater | 0.05-0.2 | 0.1-0.3 | 0.15-0.4 |
| no water: forest_noon, cave, Nether, End, entities | ~0 | 0.05-0.1 | 0.05-0.1 |

Unbound's water: 4 % of 4.6-7.7 ms frames, 0.18-0.31 ms (docs/shader.md#method) [inferred: a replay share applied to the range].

### Dependencies
- lighting (light function; the deferred pass writes the copy), sky and clouds (a sky function on custom uniforms; both in the copy before water), fog-volumetrics (fog on water; underwater fog on shared constants), shadows (shadow_water; vertex waves and caustics if taken back).
- taa (water history weight, glint fireflies, distortion after TAA, High's jitter cycle), reflections (shared ssr include, sky fallback), tonemap and post (HDR copy; glint into bloom), iris (the [verify in jar] items), next-gen (world-space reflections, compute oceans).

### Confirmation
- Cost rows per level, off vs on (docs/measurement.md#verdicts-and-cost-rows), in full mode: quick mode's views (forest_noon, nether_crimson, end_dragon: config/suite.json) hold none of the water views ocean_sunset, night, underwater, rain (config/views/bench_263.json).
- Timers cannot isolate water: Iris's debug groups show no translucent terrain (docs/platform.md#mod-adapter-surface); L4 attribution maps events by program (docs/offline.md#tools).
- Visual: features go to review (docs/measurement.md#visual-protocol): TAA-off captures at the water views, a coverage frame with glass under water and waterlogged blocks, the live pass for animation and smear; an optimization (half-res SSR, fewer waves) needs identical or near.
- L2 (docs/offline.md#levels): gbuffers_water's VGPR step with and without the march; a step up moves SSR to a composite.

### L3 golden tests
1. Waves: analytic normal vs central differences within 1e-3 at 64 points; unit length; frozen-phase values; slope 0 past the footprint.
2. Fresnel: F(1) = 0.0204 for n 1.333, F(0) = 1; from below, F = 1 past 48.6 deg.
3. Transmittance: T(0) = 1; per channel at 1, 4 and 16 blocks.
4. Depth: linearization from a dumped projection matrix; view z round trip at 0.05 (near: R10), 1, 16 and 256 blocks within 1e-4 relative.
5. SSR on a synthetic floor and wall: the hit pixel; a miss flags the sky; steps within the uniform.
6. Leak guard: a foreground occluder rejects the offset.
7. Clock: constant phase under BENCH_DETERMINISTIC; High's jitter cycle divides 720720.

## Open questions
1. SSR in gbuffers_water or half-res in a composite? Cost rows at ocean_sunset and night, L2's VGPR map.
2. Analytic waves or a generated tiling normal texture? L2, a cost row, a shimmer review; whether a generated PNG is a shipped texture asset (docs/shader.md#look-and-scope) is the user's call.
3. Do custom textures, or colortex mips (built "directly before the program" that asks for them: R10), reach gbuffers_water with mips? The jar.
4. 26.3's exact far plane (R10: roughly far x 4)? The jar, then test 4; only formulas built on far care.
5. Does mc_Entity reach gbuffers_water on Sodium 0.9.2, and does waterlogged water map to minecraft:water? The jar, a coverage frame.
6. Unbound iso once water lands: WATER_REFLECT_QUALITY 2 and DETAIL_QUALITY 3 (other details move too) or played's? The user, for M6's ratio (config/profiles/complementary-unbound-iso.json).
7. The 0.192 ms is a mean over all valid views, yet the switch changes only gbuffers_water: how much falls on views without water? A per-view Unbound row, full mode.
8. Is losing glass behind refracted water acceptable? A coverage-frame review.
9. A lower TAA history weight on water? The taa topic's positive controls and the live pass.
