# Remaining programs and the base cost
Status: The coverage-list programs no topic doc holds, and the base cost of raster and G-buffer export at 3840x2160 under the synthesis's deferred design, per view type. Research, not yet measured in Optilux; Iris facts come from a source branch and docs, not the pinned jar.

## Contents
Sources · Unbound r5.9.3 · Programs · Base cost · For Optilux · Open questions

## Sources
Tags: [m] measured; [inferred] reasoning; [verify in jar] read on a branch or in docs until javap of the pinned 1.11.7 jar reads the named class (docs/roadmap.md#findings-assigned F9).
- R1 Iris, branch 26.3 at adc75283b (head 1.11.6), read 2026-10-26: ProgramId, ShaderKey, IrisRenderingPipeline, MixinLevelRenderer, MixinParticleEngine, TransformPatcher, GlintTransformer, StandardMacros; https://github.com/IrisShaders/Iris/tree/adc75283b
- R2 shaders.properties reference (community doc): programs/gbuffers, shadersproperties/ordering, features, rendering, macros; https://shaders.properties/current/reference/
- R3 The pinned jar by javap: ProgramId's fallbacks (docs/plans/m3.md#3-premises P14), 26.3's jar facts (P22).
- R4 Sodium sorting: douira's notes ("somewhat outdated"), https://hackmd.io/@douira100/sodium-sl-gfni ; Sodium 0.7.0 notes, https://modrinth.com/mod/sodium/version/mc1.21.9-0.7.0-fabric
- R5 AMD RDNA Performance Guide: https://gpuopen.com/learn/rdna-performance-guide/
- R6 RX 7800 XT: 96 ROPs, 624 GB/s, 64 MB Infinity Cache, 2124 MHz game clock (docs/research/lighting.md#sources R4).
- R7 Records [m] in results/records/: m2-survey-1-p*, m2-survey-2-p* (passthrough); m3-determinism-2, -3, m3-coverage-2, -3 (hello pack); m3-shadows-full-1 (Unbound played).
- R8 Repo: shader/shaders/, config/views/bench_263.json, optilux/world.py, config/suite.json.
- R9 Complementary Unbound r5.9.3, studied only (docs/shader.md#policy): shaders.properties, world0/, program/.

## Unbound r5.9.3
In my own words (R9):
- world0 has line, weather, lightning, beaconbeam, armor_glint, spidereyes, damagedblock, hand and both translucent entity programs, no particles, textured_lit or hand_water: particles land in its textured program. Properties: particles.ordering mixed, beacon.beam.depth true, rain.depth false, alpha tests on weather, beam, damage and eyes.
- Particles are lit forward with shadows and fog, tagged to skip SSAO and TAA and dithered behind clouds on frameCounter mod 3600; rain sways by frameTimeCounter; beam and lightning dither; eyes, damage and glint write plain colour. As written these break docs/shader.md#determinism-and-taa.
- Lines: the vertex stage offsets each segment's projected ends sideways by a fixed pixel width, the side from vertex parity, jittered under TAA; the fragment stage spots vanilla's outline by its colour.

## Programs
Each: Iris (program, ShaderKey, fallbacks: [verify in jar: ProgramId, ShaderKey] except R3), draw, slot (gbuf, an overlay target or forward: docs/research/synthesis.md#architecture), D, view, C at 4K. None reads a frame term or needs TAA, so TAA-off frames judge them and E4's fallback (docs/design.md#8-open-decisions) costs them nothing; with TAA on, all but lines take the frameCounter mod 16 jitter (docs/research/synthesis.md#temporal) and rest on A12 [inferred]. None keeps history: each body is an Iris-free include (docs/shader.md#pipeline-spec); Aperture's programs for these draws are unknown.

### Particles
- Iris: gbuffers_particles (PARTICLES), gbuffers_particles_translucent (PARTICLES_TRANS), 0.1 cutoff; translucent -> particles (R1, R2) -> textured_lit (R3). The translucent one "requires particles.ordering=mixed" (R2); with a deferred program the default is after (R1 IrisRenderingPipeline, R2 ordering). MixinParticleEngine only sets the PARTICLES phase (R1): where 26.3 splits opaque from translucent is unread.
- Draw: on the bench only particles alive at /tick freeze or born in stepped ticks: "under /tick freeze particles neither spawn nor age" (docs/platform.md#mc-263-verified V2).
- Slot: opaque into gbuf, translucent forward (synthesis); TAA mask skip (docs/research/taa.md#6-masks-for-what-the-camera-cannot-reproject).
- D: discarded under the define, as built (docs/shader.md#determinism-and-taa). Same frames, cheaper [inferred]: every vertex outside the clip volume, so nothing rasterizes; an identical-tier A/B decides.
- View: coverage_beacon's campfire smoke (config/views/bench_263.json); the define hides its look, so a define-off variant judged within its launch, where frozen particles hold [inferred]. C: a few thousand pixels, about 0 under the define [inferred].

### Weather
- Iris: gbuffers_weather (WEATHER, 0.1 cutoff) -> textured_lit (R3). "gbuffers_weather, gbuffers_water, and gbuffers_hand_water are the only programs that render after deferred" (R2); rain.depth defaults to false (R2 rendering); `weather` "Enables or disables weather (rain & snow) geometry and rain splash particles" (R2 features; R1 IrisRenderingPipeline reads it).
- Draw: vanilla's rain or snow columns, to options.txt weatherRadius 10 (unwritten: R7's settings). Slot: forward, lit from vaUV2 by the shared include, fogged at its own depth (synthesis); rainStrength raw, PER_TICK (docs/research/synthesis.md#iris-gates); TAA mask skip.
- D: discarded as built. Proposed [inferred]: weather=false false (R2 features: weather=<weatherGeometryEnabled> <splashParticlesEnabled>, with the CAN_DISABLE_WEATHER feature flag) inside #ifdef BENCH_DETERMINISTIC in shaders.properties, which Iris preprocesses with the options (docs/gpu-iris.md#properties-and-options; Unbound gates directives on options), so nothing draws; an identical-tier A/B against the discard.
- View: rain (thunder) in a visual run of its mode; no coverage view has weather and none is snowy (config/views/bench_263.json): snow uncovered.
- C: the passthrough read 0.93-0.94 ms at rain, 0.54-0.59 at forest_noon and ocean_sunset [m, R7], rain plus the view's geometry: vanilla rain at most about 0.4 ms [inferred], "pure overdraw, no shader-side fix" (docs/playbook.md#6-did-not-work); Optilux's off the define 0.2-0.5 ms [inferred]. Gated rows keep the define on (docs/measurement.md#session step 9): weather shows only in the define's cost row and M6's ratio.
- Not-yet: weather styles live here (docs/shader.md#dropped-features), D72 input. Aperture's weather switch is unknown; the discard ports.

### Lightning
- Iris: gbuffers_lightning (LIGHTNING: POSITION_COLOR, FULLBRIGHT) -> entities -> textured_lit (R3); also the dragon's death beams; not after deferred (R2). Slot: emit, added and unlit (docs/research/lighting.md#overlay-targets); TAA mask skip.
- D: discarded as built. A bolt struck in rain's 120 stepped ticks (config/suite.json capture.ticksAfterWeatherChange) would freeze into its captures [inferred]; the discard hides the bolt, not a sky flash in a uniform the pack reads [inferred]. m3-determinism-2 and -3 were identical at rain.
- View: none reliably; a summoned lightning_bolt (not a monster) at the site under /tick freeze, clear of the mobs, would be world-prep content, so identity [inferred]. C: about 0 [inferred].

### Beacon beam
- Iris: gbuffers_beaconbeam (BEACON: BLOCK format, no alpha test, per-fragment fog, FULLBRIGHT) -> textured (R1, R3). beacon.beam.depth defaults to false; true means "the inner beacon beam will be treated like opaque geometry" (R2 rendering); Unbound sets it.
- Slot: emit, added (docs/research/lighting.md#overlay-targets). Pitfall [inferred]: without depth, deferred fogs it at the depth behind; fog it in its program, or set beacon.beam.depth and put the inner beam into gbuf as emissive. Photon puts its alpha-tested beams in its G-buffer (docs/research/lighting.md#overlay-targets).
- D: still within a launch (the hello pack's coverage_beacon pair identical, m3-coverage-3), moving across launches: "the beacon beam's turn and scroll (the game time, which the unfrozen ticks before /tick freeze move)" (config/suite.json coverageViews); the coverage rule excludes it, so no discard. View: coverage_beacon. C: a thin column, about 0.01 ms [inferred].

### Lines
- Iris: gbuffers_line (LINES: POSITION_COLOR_NORMAL_LINE_WIDTH) -> basic (R1, R2); leashes take basic. isLines holds only with the pack's own line program (R1 IrisRenderingPipeline) and forces the core transform (R1 TransformPatcher); the outline comes wrapped as iris:is_outline (R1 MixinLevelRenderer).
- Draw: "block outline, fishing line" (R2), the outline in vanilla's colour (docs/shader.md#look-and-scope). Slot: unlit, before deferred by R2's default unless L4 shows otherwise (docs/research/lighting.md#open-questions): trans, premultiplied over (docs/research/lighting.md#overlay-targets) [inferred].
- The vertex stage widens each segment into a screen-space strip, as vanilla does; a fixed pixel width reads thin at 4K [inferred]; the format carries a line width (R1 ShaderKey). TAA: unjittered, skip. D: no frame term; Unbound's rainbow outline reads frameTimeCounter (outline styles: not-yet, D72 input, about 0 ms).
- View: none [inferred; vanilla's outline rule unread]: perf views hide the GUI, and entities and coverage_beacon have nothing in reach; coverage_beacon looks level from about y 103.6 over the beacon at y 101, 7 blocks off (config/views/bench_263.json, optilux/world.py). A pose looking down at a block within 5 blocks, with hand, would draw it: a views change, so identity. C: about 0.

### Text
- Iris (R1 ShaderKey): TEXT, TEXT_INTENSITY, TEXT_BG -> entities_translucent -> entities; TEXT_BE, TEXT_INTENSITY_BE -> block_translucent -> block; hand text -> hand or hand_water. R2 puts sign text in gbuffers_block and name tags in gbuffers_entities: CONFLICT on the first hop, same chain.
- Slot: the translucent programs, so trans, lit forward (docs/research/lighting.md#overlay-targets). Alternative [inferred]: vanilla's bitmap glyphs have alpha 0 or 1, so an alpha-tested gbuf write is exact, but nothing tells a glyph from another translucent draw.
- D: static. View: coverage_items' sign (read back by world prep); no site entity has a custom name (optilux/world.py CONTENT): name tags uncovered. C: about 0.

### Armor glint
- Iris: gbuffers_armor_glint (GLINT) -> textured (R1, R3). Inline, GlintTransformer makes mc_sampleGlint() glintAlpha times glintTexture at iris_glintCoord, the UV through iris_transforms.TextureMat, for a glint draw with an overlay, else a stub returning 0; IRIS_INLINE_GLINT is defined (R1).
- Slot: emit, added (docs/research/lighting.md#overlay-targets), separate or with its entity or hand (docs/shader.md#facts).
- D: TextureMat carries the scroll 26.3's TextureTransform drives by Util.getMillis() (docs/shader.md#determinism-and-taa), so mc_sampleGlint() follows the wall clock [inferred; docs/research/synthesis.md#premises-for-m4s-plan 9]. Under the define the separate draw skips the matrix (as built) and the inline glint is skipped or sampled at the raw UV [inferred].
- View: coverage_items' enchanted golden apple. C: a fetch per glinted pixel, about 0.

### Spider eyes
- Iris: gbuffers_spidereyes (ENTITIES_EYES, _TRANS: FULLBRIGHT) -> textured (R1, R3), blend forced to SRC_ALPHA, ONE for colour and ZERO, ONE for alpha (R1 ProgramId). Draw: "spider/enderman/dragon eyes" (R2).
- Slot: emit, added by that blend (docs/research/lighting.md#overlay-targets); with no mode field the forced blend's alpha no longer matters [inferred]. If the forced blend does not add on emit, set blend.gbuffers_spidereyes.<buffer> (R2 rendering), if a directive beats the override.
- D: static. View: none: SummonCommand refuses monsters in Peaceful (docs/plans/m3.md#3-premises P22); the difficulty is the user's (docs/plans/m3.md#2-scope) and changing it re-hashes the world [inferred], so recalibration (docs/measurement.md#calibration); a written waiver fits docs/shader.md#pipeline-spec. C: 0.

### Damaged block
- Iris: gbuffers_damagedblock (CRUMBLING: 0.1 cutoff, no fog, FULLBRIGHT) -> terrain -> textured_lit (R1, R2). Slot: mod, multiplied into albedo before lighting (docs/research/lighting.md#overlay-targets). D: static.
- View: none [inferred]: spectators cannot mine, creative breaks at once, no command sets progress; a helper-mod call into the client level's destroy progress would (a mod change). C: 0.

### Hand
- Iris: gbuffers_hand -> textured_lit (R3); gbuffers_hand_water -> hand (R1, R2). The solid hand draws before deferred after the depthtex2 copy, the translucent at the level's end (R1 MixinLevelRenderer, IrisRenderingPipeline); MC_HAND_DEPTH 0.125 (docs/research/synthesis.md#iris-gates).
- Slot: hand into gbuf, hand_water forward (synthesis), positions rebuilt with MC_HAND_DEPTH (docs/research/lighting.md#foliage-and-entities); TAA: identity reprojection.
- D: fixed inventory; hideGUI reads 0 every frame where the hand shows (docs/roadmap.md#findings-assigned F12), so the flush waits on F12's answer; TAA-off frames are unaffected.
- View: entities (perf), coverage_beacon; hand_water none, only a torch being held [inferred]. C: under 0.01 ms [inferred]. Not-yet: hand sway, a vertex term (D72 input).

### Translucent entities and block entities
- Iris: gbuffers_entities_translucent -> entities -> textured_lit; gbuffers_block_translucent -> block -> terrain (R1, R2); R2 pairs entities_translucent with the ENTITY_TRANSLUCENT feature flag, which Unbound requests as optional (R9). separateEntityDraws "may not work at all" in newer Iris (R2 ordering): both draw before deferred.
- Draw: translucent entity and block-entity layers and text; which items and mob layers take them is unread. Slot: trans, lit forward by the shared include, RGBA16F as RGBA8 clips and bands; whether these draws write depth is a premise (docs/research/lighting.md#overlay-targets).
- D: static under /tick freeze with NoAI (V2). View: coverage_items, coverage_mobs, entities [inferred]. C: small.

### Translucent sorting
- IRIS_HAS_TRANSLUCENCY_SORTING is defined unconditionally (R1 StandardMacros), "if the currently loaded version of Sodium supports translucency sorting" (R2). Sodium sorts translucent faces per section on the CPU, the order changing only "when the camera crosses the face plane of one of the involved faces" (R4). The bench pins terrain_sorting_enabled true and quad_splitting_mode SAFE (config/suite.json display.sodiumOptionsFile): identity.
- Slot: gbuffers_water's translucents arrive back to front, so forward blending is ordered without OIT, which Iris turns off (docs/platform.md#mc-263) [inferred]. D: fixed at a still pose once the sort lands [inferred]; whether readiness waits for sort tasks is open. C: CPU only; 0.7.0 claims "no measurable performance impact in typical scenarios" for its quad splitting (R4). Aperture runs on Sodium (docs/platform.md#renderer-transition).

## Base cost
Scope: opaque raster (terrain, entities, hand), albedo fetch, alpha test, the gbuf and mask exports and their clears at 3840x2160, which docs/research/synthesis.md#budget leaves out; not lighting, sky, fog or post.

| View | Passthrough GPUBusy ms [m] | Hello pack ms/frame [m] | Unbound GPUBusy ms [m] |
|---|---|---|---|
| forest_noon | 0.54, 0.56 | 1.27, 1.26 | 8.20 |
| ocean_sunset | 0.59, 0.59 | 1.15, 1.15 | 7.38 |
| entities | 0.51, 0.51* | 0.87, 0.86 | 5.38 |
| night | 0.50, 0.51* | 0.81, 0.81 | 5.51 |
| rain | 0.93, 0.94 | 1.48, 1.48 | 7.60 |
| underwater | 0.53, 0.52 | 1.12, 1.12 | 7.46 |
| cave | 0.50, 0.50* | 0.86, 0.86 | 5.39 |
| nether_crimson | 0.49, 0.49* | 1.05, 1.05 | 5.91 |
| nether_soul | 0.53, 0.53* | 0.96, 0.96 | 6.50 |
| end_dragon | 0.66, 0.66 | 0.81, 0.82 | 8.16 |
| end_city | 0.69, 0.69 | 0.80, 0.82 | 8.18 |

- Passthrough: m2-survey-1, -2; "Iris draws it with its fallback programs, no shadow pass and a copy to the screen" (docs/plans/m2.md#6-decisions D46). * only cut captures (docs/measurement.md#validity), values as read. Its identity is not the other columns' (the standard set and launch spec 9bd33805 against the deterministic set and de7fdff0: R7; docs/measurement.md#baseline-suite): context for an estimate, never a comparison.
- Hello pack: pairSeconds over the frameIndex gap of its two PNGs 2 s apart (m3-determinism-2, -3, the define on): wall-clock, so at least its GPU time; no hello-pack record holds GPUBusy. PNG writers run meanwhile (docs/mod.md#8-capture), so night's and the End's 0.80-0.82 may be a CPU floor [inferred]; the gap over the passthrough fits a reachable discard in every hello program (docs/research/lighting.md#discard-free-solid-programs) [inferred].
- Unbound: m3-shadows-full-1's baselines; terrain is 40 % weighted, 54 % at forest_noon (ALC, 1.21.11: docs/shader.md#method, docs/playbook.md#3-workflow), 2.2-3.3 ms of 26.3's day frames and about 4.4 at forest_noon [inferred], forward-lit with shadow lookups (part of its 1.35 ms shadows-off delta at forest_noon: docs/research/lighting.md#unbound-r593) and AF (ALC's 1.21.11 ablation: 0.204 ms mean, forest_noon 0.392: config/profiles/complementary-unbound-played.json).

Arithmetic [inferred]:
- 8,294,400 px: a byte per pixel is 8.3 MB a layer, 0.0133 ms at R6's 624 GB/s. D per shaded fragment: gbuf 8 B, mask 1 B, depth test and write about 8 B: 17 B, 0.23 ms a full layer; the hello pack's RGBA8 and depth, 12 B, 0.16 ms; D adds 0.066 ms a layer. ROPs: 96 x 2.124 GHz, 0.04 ms per 32-bit layer; the 64-bit rate is unread.
- Clears: gbuf 66 MB, mask 8, the overlay targets 33 + 33 + 66, 0.33 ms if written; "Fast clears are designed to be ~100x faster than normal clears", for 0 or 1 values on full images (R5): about 0 if Iris's integer clear qualifies. Iris copies depthtex1 and depthtex2 "unconditionally" (~0.29 ms replayed: docs/gpu-iris.md#passes-and-buffers), so every measured pack holds them.
- Layers per pixel, unmeasured: 2-3 at forest_noon and rain (canopy; PB's cutout terrain ~30 % beside solid ~19 %: docs/playbook.md#3-workflow), 1.1-1.5 elsewhere; sky exports nothing, water draws forward.

| Type | Views | D base ms [inferred] | Basis |
|---|---|---|---|
| day | forest_noon, ocean_sunset, entities | 0.9-1.5 | hello 0.86-1.27, 1-3 layers |
| night | night | 0.6-0.9 | hello 0.81, maybe CPU-bound |
| rain | rain | 1.1-1.7 | hello 1.48, weather discarded |
| underwater | underwater | 0.8-1.3 | hello 1.12, surface forward |
| cave | cave | 0.6-1.0 | hello 0.86 |
| Nether | nether_crimson, nether_soul | 0.7-1.2 | hello 0.96-1.05 |
| End | end_dragon, end_city | 0.7-0.9 | passthrough 0.66-0.69 |

- Low ends: compression, Infinity Cache hits, early depth from the discard-free solid program; high ends: the hello interval plus uncompressed export. Lighting's D row already counts 4 B of the export (docs/research/lighting.md#cost-hypothesis-m4-shadows-excluded-inferred): up to 0.2 ms twice at forest_noon.
- With the synthesis's Medium features, Iris's copies and mips and the TAA history, per view: docs/research/synthesis.md#budget [inferred].
- Measuring it: the base alone sits where PresentMon loses rows (docs/roadmap.md#findings-assigned F25), so take it by difference on M4's whole pack or as timer rows once E3 closes (docs/design.md#8-open-decisions); L4 shares rank, never in ms (docs/offline.md#decision-powers).

## For Optilux
- M4 writes every program above, fallbacks only a safety net; particles.ordering=mixed; beacon.beam.depth default until the beam's fog is settled.
- Under the define: particles and lightning discarded or vertex-culled, weather=false false, glint unscrolled, the beam drawn under the coverage rule.
- Overlay targets: blend.<program>.<buffer> per program, so damage multiplies into mod; glint, spider eyes, the beam and lightning add into emit; translucents, text and lines go over into trans (docs/research/lighting.md#overlay-targets) [verify in jar].
- Coverage gaps: lines, lightning, spider eyes, damaged block, hand_water, name tags, snow: each a written waiver (docs/shader.md#pipeline-spec), or content or a pose that re-hashes the world or views and recalibrates; the user's call.
- A define-off coverage variant, judged within its launch, for particles, weather and lightning.
- Measure: L4 at the coverage views and rain naming each draw's program; weather=false false and the vertex cull against the discard, identical tier; the define's cost row (docs/measurement.md#session step 9).

## Open questions
1. Where does 26.3 split opaque from translucent particles? The jar, L4.
2. Does a pack's own gbuffers_line get an Iris line patch, or expand alone as Unbound's does? The jar, L4.
3. Does blend.<program>.<buffer> beat ProgramId's spidereyes blend? BlendModeOverride in the jar; L3.
4. Does Iris's RGBA16UI clear fast-clear? L4 or a timer row.
5. Does mc_sampleGlint's TextureMat follow the wall clock? The jar, then two captures 2 s apart.
6. Does readiness wait for Sodium's sort tasks? docs/mod.md#7-readiness against Sodium 0.9.2.
7. Which render types reach the translucent entity programs (items, horse markings)? L4.
8. How often does a bolt freeze into rain? Frame equality at rain across sessions.
