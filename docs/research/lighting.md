# Lighting architecture
Status: research for M4 and M5 on forward or deferred lighting (E2), the G-buffer and the light model for a basic resource pack. Nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
[verify in jar]: an Iris fact read in docs or branch source, held until read in the pinned 1.11.7 jar. [inferred]: reasoning, not a read.
- R1 shaders.properties, the Iris pack reference (community doc, current): programs/gbuffers, shadersproperties/ordering, features, flags, buffers/image_format, uniforms/overview, macros/mc_hand_depth; https://shaders.properties/current/reference/
- R2 Iris source, branch multiloader-new, not the pinned jar (mod source, read 2026-10-26): pipeline/programs/SodiumPrograms.java, uniforms/CommonUniforms.java, uniforms/IdMapUniforms.java; https://github.com/IrisShaders/Iris/tree/multiloader-new/common/src/main/java/net/irisshaders/iris
- R3 AMD GPUOpen, RDNA Performance Guide (vendor doc): https://gpuopen.com/learn/rdna-performance-guide/
- R4 KitGuru, RX 7800 XT review (review, 2023): 60 CUs, 96 ROPs, "a memory bandwidth of 624 GB/s", 64 MB Infinity Cache, 2124 MHz game clock; https://www.kitguru.net/components/graphic-cards/dominic-moass/amd-rx-7800-xt-review/
- R5 Burns, Hunt, The Visibility Buffer (paper, JCGT 2013; abstract read): https://jcgt.org/published/0002/02/04/
- R6 Cigolle et al., A Survey of Efficient Representations for Independent Unit Vectors (paper, JCGT 2014; abstract read): https://jcgt.org/published/0003/02/01/
- R7 Google Filament, PBR documentation (vendor doc, living): https://google.github.io/filament/main/filament.html
- R8 Jimenez et al., Practical Realtime Strategies for Accurate Indirect Occlusion (paper, Activision ATVI-TR-16-01, 2016; abstract read): https://research.activision.com/publications/archives/atvi-tr-16-01practical-realtime-strategies-for-accurate-indirect-occlusion
- R9 Barre-Brisebois, Bouchard, Approximating Translucency (talk, GDC 2011): not read; frostbite.com's page now redirects to a 404 [unverified].
- R10 Khronos GLSL refpages, packUnorm and bitfieldInsert (spec doc): https://registry.khronos.org/OpenGL-Refpages/gl4/html/packUnorm.xhtml
- R11 Photon by SixthSurge (pack source, Photon Shaders License Agreement, 2021-2025): shaders/program/gbuffers_all_solid.fsh, d4_deferred_shading.fsh; https://github.com/sixthsurge/photon
- R12 Complementary Unbound r5.9.3 (pack source, Complementary License Agreement 1.7, studied as docs/shader.md#policy allows) under reference/complementary-unbound-r5.9.3/shaders/.
- R13 minecraft.wiki, Options (wiki, current): https://minecraft.wiki/w/Options
- R14 results/records/m3-shadows-full-1.json [m]: Unbound played on 26.3, full mode.

## Unbound r5.9.3
- Forward: each gbuffers program lights its own fragments. Terrain is one program for solid and cutout, discarding at alpha 0.5 or below, so solid terrain carries a reachable discard too (program/gbuffers_terrain.glsl; world0/ has no gbuffers_terrain_solid).
- lib/lighting/mainLighting.glsl, per fragment, so once per overdraw layer:
  - sun: N.L with a side-shadowing offset; PCF with more samples at higher quality and for near foliage; a normal-offset bias growing with distance; the lookup pulled to the block centre where sky light and vanilla AO are low; a fade to a sky-light estimate before the shadow distance;
  - block light: its own curve on the lightmap coordinates, never vanilla's lightmap texture; the optional flicker (BLOCKLIGHT_FLICKERING, off by default) reads noisetex at a frameTimeCounter coordinate, one value per frame;
  - held light (lib/lighting/heldLighting.glsl): both hands' heldBlockLightValue, the lava bucket forced by item id, distance from the player's head (playerPos + relativeEyePosition), a steep falloff, added to block light in quadrature;
  - vanilla AO from the vertex alpha (separateAo = true, shaders.properties), reshaped by N.U and the scene light, multiplying the diffuse sum but not emission; a cave minimum (lib/lighting/minimumLighting.glsl) and per-axis face shading;
  - sun highlight (lib/lighting/ggx.glsl): GGX, a Schlick-type Fresnel, Horizon Zero Dawn's sphere-light approximation at WATER_REFLECT_QUALITY 2 or more (played: 1);
  - foliage: with shadows on, plants and leaves skip N.L, shaded by the shadow map plus a view-toward-light highlight; only at SHADOW_QUALITY -1 are plants lit as if facing up and leaves pulled toward N.L = 1.
- Light and ambient colours (lib/colors/lightAndAmbientColors.glsl) are global initializers from skyColor, time-of-day factors and rainFactor, run per pixel (docs/gpu-iris.md#uniform-math). rainFactor and the End flash intensity are smooth() custom uniforms (shaders.properties).
- Outputs (lib/pipelineSettings.glsl): colortex0 R11F_G11F_B10F lit colour; colortex6 RGB8 smoothness, material mask, sky-light factor: 8 B per fragment [inferred: RGB8 padded]. Terrain adds colortex4 RGBA8_SNORM normals only at BLOCK_REFLECT_QUALITY 2 or more with RP_MODE not 0 (played: 1 and 0).
- deferred1 multiplies the lit colour by SSAO, sun and emission included (program/deferred1.glsl).
- Cost: forest_noon 8.20 ms GPUBusy; SHADOW_QUALITY=-1 takes 1.35 ms (-16.5 %): shadow pass, lookups and shadow-only branches [m, R14]. Shadow's share is ~6 % in PB's forest replay (cutout terrain ~30 %, solid ~19 %; docs/playbook.md#3-workflow, 1.21.11) and 4 % in ALC's weighting (docs/shader.md#method), leaving 0.85-1.0 ms for per-fragment lookups [inferred].

## Techniques
Defaults unless a technique says otherwise. Det: no frame-varying term, no accumulation, so TAA-off captures judge it, under E4's fallback too. Iris: gbuffers and deferred programs and colortex formats; no compute, SSBO, images, custom textures, mipmaps, flipping, previous-frame or extra shadow data [verify in jar]. Aperture: the algorithm in an Iris-free include (docs/shader.md#pipeline-spec); no pass reads what it writes.

### D: thin G-buffer, deferred opaque, forward translucent
- Opaque programs write surface data; one deferred pass lights each visible pixel once; programs after deferred light forward with the same include. Overdraw then costs a texture fetch, the alpha test and an export, not lighting and shadow lookups. PB: deferred lighting is "the only real fix for leaf overdraw" (docs/playbook.md#6-did-not-work). Photon's deferred pass is "Shade terrain and entities, draw sky", its shadow lookups there on the flat normal (R11).
- Order: "By default, gbuffers_weather, gbuffers_water, and gbuffers_hand_water are the only programs that render after deferred" (R1 gbuffers); separateEntityDraws "may not work at all" in newer Iris. With a deferred program particles default to `after`; particles.ordering=mixed (Unbound's) draws opaque ones before deferred (R1 ordering).
- Iris: RGBA16UI and RG32UI exist (R1 image_format); the hand's depth multiplier comes through the projection matrix, undone in NDC (R1 mc_hand_depth). Aperture: deferred writes a new scene target, not colortex0, so nothing flips.
- Cost [inferred, R4]: export 8 B per shaded fragment (66 MB per full-screen layer, as Unbound's). The pass reads G-buffer 8 B, depth 4 B, sky target 4 B, overlay 4 B and writes 4-8 B: 200-230 MB, 0.32-0.37 ms at the 624 GB/s peak, less with compression and the 64 MB Infinity Cache, more with ALU: 0.2-0.45 ms. M5's deferred sky, AO and fog share the reads. AMD: "Use a compute shader for full-screen passes", up to 2 % (R3); Iris compute here is [verify in game].
- A visibility buffer (triangle and instance ids, attributes refetched, R5) needs Sodium's vertices in a full-screen pass, which Iris does not give, and cutout needs its albedo fetch for the alpha test anyway: not available [inferred].

### F: forward with split programs
- Lighting stays in gbuffers, paid per shaded fragment. F-v computes the unshadowed terms per vertex (as the hello pack reads light, shader/shaders/lib/surface_vertex.glsl); shadow and specular stay per pixel.
- Cost [inferred]: 60-100 VALU per fragment at 3840 lanes x 2.124 GHz is 0.06-0.1 ms per full-screen layer, dual issue and stalls ignored. M5's lookups would cost F what they cost Unbound, 0.85-1.0 ms at forest_noon.
- E2's crux: M4 has only a 1-tap shadow lookup, so per-fragment cost is lowest when E2 is decided. D can lose 0.1-0.3 ms on low-overdraw views in M4 and still win at forest_noon in M5 [inferred].

### Discard-free solid programs
- "Any reachable `discard` defers depth writes until after the shader, even if it never fires" (docs/gpu-iris.md#depth-and-discard). AMD: "Avoid `discard` in long running shaders when there are other paths" (R3); its Z-prepass alternative needs a pass Iris does not offer [inferred].
- Iris maps Sodium's TERRAIN to TerrainSolid with AlphaTest.ALWAYS and TERRAIN_CUTOUT to TerrainCutout with ONE_TENTH_ALPHA (R2 SodiumPrograms); PB read cutout `> 0.5` on 1.10.7 (docs/gpu-iris.md#programs-and-alpha-tests): CONFLICT. A core program applies alphaTestRef itself (docs/shader.md#facts). gbuffers_terrain_solid falls back to gbuffers_terrain (R1 gbuffers).
- Today every hello-pack program shares a fragment stage with a reachable discard (shader/shaders/lib/surface_fragment.glsl); terrain falls back to gbuffers_textured_lit.
- ALC's slower route was Iris's injected alpha test, which core programs do not get; the split program is unmeasured (CONFLICT, docs/gpu-iris.md#depth-and-discard). Cost: sign unknown; an A/B with identical frames decides.

### G-buffer packing
- Later topics read albedo (texture x vertex colour), normal, block and sky level, vanilla AO and material id: 72 bits at 8 each. Proposed: 64 bits in one RGBA16UI or RG32UI target: albedo 3x8, octahedral normal (R6) 2x7, block 7, sky 7, AO 6, material 6.
  - Signed octahedral codes with an exact zero keep the six axis normals, all of terrain's, exact [inferred; L3]. A 7-bit level is 1/8 of a light level; 6-bit AO steps 1.6 % [inferred].
  - Photon packs 8-bit fields in pairs, dithers its light levels before packing and multiplies vanilla AO into terrain albedo (R11), leaving no AO to merge with SSAO. A fixed spatial dither stays deterministic; a per-frame one needs TAA [inferred].
- #version 330 lacks packUnorm4x8 and bitfieldInsert (GLSL 4.00, R10): shifts and masks, which port to Slang.
- Integer targets are not blended [inferred; L3 on this driver]; a UNORM G-buffer needs blend.<program>.<buffer>=off wherever Iris blends (Unbound sets some) [verify in jar].
- AMD: "put highly correlated bits in the Most Significant Bits"; "partial writes will disable compression" (R3).
- Cost: 8 B per fragment; 12 B adds ~0.05 ms per full-screen layer (33 MB at 624 GB/s) [inferred].

### Overlay target
- Blended draws before deferred (spider eyes, damaged block, beacon beam, the glint draw, translucent entities and block entities) cannot write an integer target: they write an RGBA8 overlay that deferred composites; translucent entities light forward with the shared include.
- 26.3 draws an item's glint with its entity or the hand, reaching a core program only through mc_sampleGlint() (docs/shader.md#facts): those programs write it to the overlay too.
- Photon's overlay carries a type in alpha: glint adds, damage multiplies albedo, before lighting (R11 d4_deferred_shading). A premultiplied over cannot multiply, so the overlay needs a mode field. Photon puts beacon beams (alpha-tested) and spider eyes in its G-buffer (R11).
- Pitfalls [inferred]: an opaque draw after an overlay write at a pixel (the hand) must clear it (L4 order); forward-lit translucent entities clip at 1 and band in RGBA8: a scale or RGBA16F (66 MB). Cost: a 33 MB clear plus the overlay pixels.

### Light model on levels and custom uniforms
- Block and sky light come from vaUV2 / 240 through Optilux's curves, not vanilla's lightmap, so vanilla's tick flicker never enters and the hello pack's lightmap special case (docs/shader.md#determinism-and-taa) goes away. What the lightmap also carried returns from uniforms: nightVision, darknessLightFactor, screenBrightness (PER_FRAME, R2 CommonUniforms), the End flash.
- Sun: "a simple Lambertian BRDF" (R7) times the shadow (1-tap in M4, filtered in M5). Sky: a hemisphere blend on N.U times the sky curve. oldLighting is false by default (R1 features): the pack supplies the face shade [verify in jar: Sodium's shade off]. Specular: GGX, Schlick Fresnel (R7), sun only, smoothness from the material map (docs/shader.md#look-and-scope), skipped where shadowed (docs/playbook.md#53-exact-trims).
- Uniform-only math is custom uniforms (docs/playbook.md#4-design-defaults; PB: terrain 72 -> 60 VGPRs): vectors, day factors, colours, held-light terms, flicker. Det: rainStrength is PER_TICK, wetness and eyeBrightnessSmooth smoothed (R2); smooth() is barred (docs/measurement.md#visual-protocol), so the bench reads rainStrength and endFlashIntensity raw where Unbound smooths them.
- Iris: custom-uniform inputs [verify in jar]; at_midBlock.w carries block emission (BLOCK_EMISSION_ATTRIBUTE, R1 flags) [verify in jar]. Aperture: uniforms are ap.* structs (docs/platform.md#renderer-transition), so each custom uniform is re-expressed per backend from one table [inferred]. Cost: once per pixel in D, 0.06-0.1 ms [inferred].

### Held-item light
- heldBlockLightValue and heldBlockLightValue2 come from each item's getLightEmission, PER_FRAME (R2 IdMapUniforms). oldHandLight, true by default (R1 features), raises the main hand's value to the higher hand's and keeps the off hand's, so summing both double-counts: set it false, as Unbound does.
- Distance from the player's head, playerPos + relativeEyePosition ("World space offset from the player head to the camera", R1 uniforms); falloff and merge (max or quadrature) are look choices; a scalar branch gates it (docs/gpu-iris.md#uniform-math).
- Det: fixed pose and inventory. The entities view holds a torch (docs/design.md#7-decisions-taken-user-2026-10-05 D11), and world prep leaves the spectator holding one (docs/measurement.md#baseline-suite): held light is probably on at every view [inferred], so the gate saves nothing on the bench. Cost: ~0.02 ms in D [inferred].

### Block-light flicker
- One value per frame, so a custom uniform. Off-bench, a sum of sines of frameTimeCounter, which wraps at 3600 (docs/gpu-iris.md#frame-counters-and-reload): it jumps hourly unless its periods divide 3600 s [inferred]; the live pass checks it. Under BENCH_DETERMINISTIC, a function of frameCounter % C, C dividing pipeline.json's cycle (1 today): the multiply stays live, the frame still. Iris: both counters as custom-uniform inputs [verify in jar]. Cost: one multiply per pixel.

### Foliage and entities
- Foliage (by material id): wrapped diffuse plus a view-toward-light transmission term (R9 [unverified]; Unbound's highlight in lib/lighting/mainLighting.glsl); bias and shadows are the shadows topic's.
- Entities and the hand use the same model on vaNormal; the entity overlay colour is mixed into albedo in gbuffers (as Photon, R11); hand positions are rebuilt with MC_HAND_DEPTH.
- The material id travels as a smooth float varying, rounded in the fragment stage: flat varyings in terrain measured +1.36 % in the Nether for ALC, neutral for PB (docs/gpu-iris.md#uniform-math) [inferred for this use]. Iris: mc_Entity in core terrain [verify in jar].

### Vanilla AO and SSAO
- separateAo puts vanilla AO in the vertex alpha, but R1 features warns of a bug that "prevents separateAo from functioning unless the shadow pass is enabled"; M4 draws a shadow pass, which may lift it [verify in jar].
- Filament: "the ambient occlusion term is only applied to indirect lighting", and against over-darkening it takes Lagarde's min() of medium- and large-scale occlusion (R7). GTAO adds a multi-bounce fit and specular occlusion (R8). Unbound multiplies everything.
- Proposed: vanilla AO on ambient and block light, softened on direct light until shadows land; with SSAO, min(vanilla, SSAO) (R7), not the product; review tier. Det: vanilla AO is static; SSAO noise is the ao topic's.

## For Optilux
### First version (M4)
- D is the base path; F a dev option over the same include until E2 closes.
- G-buffer: terrain_solid (no discard), terrain_cutout, entities, block, hand, opaque particles (mixed). Overlay: spidereyes, damagedblock, beaconbeam, armor_glint, entities_translucent, block_translucent, the inline glint. Deferred: lighting and the deferred sky into a new scene target; then water, hand_water, weather and translucent particles forward into it.
- Iris-free includes (docs/shader.md#pipeline-spec): the lighting core (struct in, radiance out), the codec, the curves.
- Options: HELD_LIGHT Off/On; BLOCK_FLICKER Off/Low/Medium/High; FOLIAGE_TRANSLUCENCY Off/On; SUN_SPECULAR Off/On. Dev: LIGHT_PATH forward/deferred; E2_LOAD 0/4/8/16 extra fetches per lit fragment from an int custom uniform, standing in for M5's lookups.

### Cost hypothesis, M4, shadows excluded [inferred]
| View type | F ms | D ms |
|---|---|---|
| forest_noon | 0.12-0.4 | 0.3-0.65 |
| cave, night, nether_* | 0.06-0.15 | 0.25-0.5 |
| ocean_sunset, underwater, rain | 0.08-0.2 | 0.25-0.5 |
| end_* | 0.05-0.1 | 0.2-0.45 |
| held light, all views | +0.02 | +0.02 |

D: its pass plus 4 B more export per fragment than F, low ends assuming compression and cache hits. In M5 F adds 0.85-1.0 ms of lookups at forest_noon; D pays them once per pixel.

### Measurements and tiers
- E2: cost rows for F and D, full mode, every perf view, E2_LOAD 0/4/8/16. F against D is near (max |d| <= 1, config/suite.json fidelity) only if quantization stays under one step (L3 test 6); else close, which needs the user's sign-off (docs/measurement.md#visual-protocol).
- Discard-free solid: optimization A/B, identical expected. Custom uniforms: L2 live-register map, A/B, near (1-2 ulp, docs/gpu-iris.md#custom-uniforms).
- Overdraw: L4 at forest_noon, shaded fragments per pixel in the cutout events, gbuffers and deferred shares.
- Held light, flicker: cost rows at entities and cave; every perf view identical across 2 sessions; off-bench flicker in the live pass. Look: review tier beside Unbound's reference frames.
- Thresholds: the 0.5 % floor (docs/measurement.md#calibration), 0.005-0.01 ms on a 1-2 ms frame.

### L3 golden tests
1. Codec: each field round-trips over its domain; no bit crosses fields.
2. Octahedral 2x7: axis normals exact; max error over 10^6 random vectors under a stated bound.
3. Curves: endpoints, monotonic, a golden table for 0-240.
4. Held light: 0 at level 0, monotonic in distance.
5. Custom uniforms in Iris's engine against the reference; the bench flicker constant over frames.
6. F against D: the include on exact inputs vs the decoded G-buffer, max 8-bit difference.
7. moderngl on this driver: blending and glClear on an RGBA16UI target.

### Dependencies
- taa: deferred rebuilds position from depth with the jitter removed, as Unbound's gbuffers_terrain does; the tonemap's output is TAA's input. tonemap: its format and the light scale.
- shadows: lookups in deferred from depth and the flat normal, foliage and entity flags; their cost moves E2; separateAo may need the shadow pass. ao: normals and depth in, applied to ambient, min() with vanilla AO.
- sky: in the lighting pass, one uniform table for sun, moon and ambient. water: the forward include; refraction copies the scene target. clouds, fog, reflections, post and next-gen read the scene target or G-buffer. iris: every [verify in jar].

## Open questions
- E2: does D lead at forest_noon by E2_LOAD 4, and with M5's real lookups? The E2 cost rows, rerun on the M5 pack; L4 for overdraw and Sodium's draw order (front to back assumed [inferred]).
- MoreCulling, which cuts leaf geometry, is played tier, not bench (docs/platform.md#mod-tiers): E2 is judged on more leaf overdraw than the user plays with. A played-tier look at forest_noon sizes the gap, never as evidence.
- separateAo without a shadow pass on 1.11.7: the jar, or a coverage frame with and without a shadow program.
- Do 7-bit levels and 6-bit AO band, with or without a fixed dither? L3 test 6 and coverage frames, review tier; if so, 12 B and its cost row.
- Integer colortex clear and blend in Iris: the jar and L3 test 7; sky pixels come from depth either way.
- Overlay clears, and where gbuffers_line and damagedblock draw (before deferred by R1's default): L4 order.
- Does mc_sampleGlint() read the wall-clock glint transform (docs/shader.md#determinism-and-taa)? The jar; the bench needs it still.
- Held light at every view: heldBlockLightValue in an L1 dump at a non-entities view.
- Smooth lighting and See-Through Leaves (R13) move vanilla AO and leaf cutout. Not pinned in suite.json's optionsTxt, they are identity already (docs/run-record.md#identity: every options.txt key as the game reads it); pinning them is the user's.
- Non-block light items (Unbound forces the lava bucket): IrisItemLightProvider in the jar. Custom-uniform inputs such as sunPosition: L3 in Iris's engine.
