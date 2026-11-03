# Handoff
Status: the latest stop: M4.P07 every other program done on branch m4, committed and pushed: every program Iris draws is the pack's own (34 per lit dimension), lit forward after deferred or kept for it in D76's overlays, with the eight options, `weather=false false` under BENCH_DETERMINISTIC and the exit's runs. M4.P08 is next.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P07
- The Exit of M4.P07 (docs/plans/m4.md) held in this session (2026-11-03, AST), shown:
  - m4-programs-visual-2, a visual run of `optilux@HEAD` at 73be07b (sha512 547d31fb...) and its BENCH_DETERMINISTIC false variant on the coverage views, one launch, 16:40:01 to 16:42:24: "optilux run: ok; ... 6 of 6 captures valid, pairs moving: coverage_items/pack-define-off, coverage_mobs/pack-define-off, coverage_beacon/pack-define-off" (the define off draws particles, the glint and the flicker); latest.log: every reload of the pack "(IrisRenderingPipeline)", no WARN or ERROR after the selftest's;
  - `check L4` on m4-programs-capture-2 (debug, the coverage views, `optilux@HEAD` at 84026b6, 17:18:41 to 17:21:16: "3 of 3 captures valid, 3 .rdc hashed, 742.7 MiB"): the labels drawn are beacon, clouds, composite, deferred, entities_cutout_diffuse, entities_cutout_glint, entities_solid, final, hand_cutout_diffuse, particles, particles_trans, shadow_entities_cutout, shadow_sodium_terrain_cutout, _solid and _translucent, sky_basic, sky_textured, sodium_terrain_cutout, _solid and _translucent, text_be; each is an Iris shader key whose ProgramId (ShaderKey, javap) has a file of the pack's own, so no draw falls back; the four unlabelled programs are no Iris program: Program 445 the frame's first draw (event 108/121, Iris's draws from 213/226), 364, 704 and 303 after final at coverage_beacon alone (its HUD);
  - m4-weather-discard-1 (`optilux@73be07b`, the discard) and m4-weather-directive-1 (`optilux@0d592a9`, `weather=false false`), full mode, 16:48:04 to 16:51:22 and 16:51:30 to 16:54:46, each "11 of 11 captures valid, pairs moving: none"; `compare m4-weather-directive-1 --against m4-weather-discard-1`: "identical" at rain, and on all 11 perf views.
- m4-programs-capture-1 (73be07b's programs, 17:10:39 to 17:13:10) showed shadow_entities_cutout and shadow_sodium_terrain_translucent drawn through Iris's fallback to the shadow root (ShadowEntities and ShadowWater had no file): 84026b6 adds shadow_entities, shadow_block and shadow_water, the same body, and capture-2 is the exit's.

## What was built
- 73be07b: the forward programs (program/forward.*.glsl, one include): water (FORWARD_TERRAIN: Sodium's vertex alpha as AO), entities_translucent, block_translucent, hand_water, particles_translucent, line, spidereyes, beaconbeam, armor_glint, damagedblock, lightning, clouds, weather, basic, textured, textured_lit; lit by scene.glsl's shadeSurface (the one shading deferred and LIGHT_PATH 0 call), each with its own normal (or facing the camera), levels and Low shadow tap, written with vanilla's blend. D76 as built: a program that may draw before deferred writes the same value into its blend's overlay (trans: block_translucent, entities_translucent; mod: damagedblock, applied to the finished colour; emit: armor_glint, its square root, unfogged) or, for an opaque depth-writing part, the G-buffer (the beam's core as MATERIAL_EMISSIVE, leashes through basic); entities, block, hand and particles write the overlays' neutral values. Off the define mc_sampleGlint() (vec3, declared in every stage by GlintTransformer, javap) into emit or the scene. shadow_lightning discards under the define. The options: SHADOWS [0 1], HELD_LIGHT, BLOCK_FLICKER [0 1 2 3] (default 1; shaders.properties' blockFlicker over lib/flicker.glsl, clock 0 under the define), SUN_SPECULAR (lib/lighting.glsl's GGX), FOLIAGE_TRANSLUCENCY (block.properties' block.10, 82 names, each a 26.3 blockstate; MATERIAL_FOLIAGE), DITHER, dev SCENE_FORMAT [0 1] and OVERLAYS. pipeline.json v1 for every pass (generated with test_pipeline's readers). L0 compiles stages on Iris's glint stubs (glslang preamble) and its rule refuses textureMatrix and mc_sampleGlint under the define. L3: lighting's surfaceLight, foliageFacing and sunSpecular, flicker.py, uniforms.py (blockFlicker at the rest and at each level off the define, e2Load).
- 0d592a9: `weather = false false` under `#ifdef BENCH_DETERMINISTIC` in shaders.properties; weather's discard gone.
- 84026b6: shadow_entities, shadow_block, shadow_water.
- Docs: shader.md (Status, Look and scope's options as built, Pipeline spec's blended draws, Determinism and TAA, Facts: the glint, L4's labels), offline.md (L0's rule and glint stubs, the M4 pack's matrix), research/programs.md (the beam, sign text, lightning's shadow), CHANGELOG.md's 0.5.0 bullet.

## Review
The reviewer agent on the programs against D76, D79 and P11-P19 (correctness): 3 low, each read at its source, all fixed before 73be07b: mod multiplied only the albedo (now the finished colour, as after deferred); a pre-deferred glint was fogged twice (emit now unfogged); the lightning bolt reached the shadow map under the define (shadow_lightning). Not checkable there: which draws Iris keys straight to basic, textured or textured_lit (capture-2 shows none at the coverage views).

## Checks
- Start (15:48 AST): branch m4 clean at 8c9022a; 1127 passed; verify docs 0 violations.
- Before each commit: `optilux test` green (1131 passed), ruff and pyright clean, verify docs 0 violations; `check L0` pass (34 programs x 3 dimensions x 16 variants = 1520 builds, 0 determinism refusals), `check L3` pass ("10 of 12 includes tested, 39 functions over 105,535 cases, 7 uniform tests over 772 cases"), verify similarity 0 matches; verify records 0 violations (410 records); no mod change. CI green on 73be07b, 0d592a9 and 84026b6 before the next push.

## Deferred and logged
- Commits: the prompt splits "the options and pipeline.json" from the programs, after the directive; they landed with the programs in 73be07b, as the programs test the options throughout and no test-green split existed without writing them twice.
- D76's text (sign text alpha-tested into the G-buffer, blend.<program>, renderStage's neutral value) is not as built: vanilla's own blends serve both targets, so no blend.<program> and no renderStage; sign text goes through trans at alpha 1 (block_translucent also draws banner patterns). D76 is not edited; research/programs.md and shader.md say it as built.
- Six launches against four: m4-programs-visual-1 failed at its define-off variant, the option written "false" where an on/off option takes a boolean (a spec fault); m4-programs-capture-2 after capture-1's fallback. The capture run first refused: the displays off (input 4404 s ago, timeout 600 s); at the user's request ("Can you wake the screens for me?") a one-pixel SendInput mouse move and back woke them (17:09), and a scratch hold (SetThreadExecutionState, scratchpad hold.py) ran over both capture runs.
- The coverage visual run is of 73be07b; since then the weather directive (no weather at the coverage views) and the shadow programs (the shadow root's body) only; not rerun.
- Water and glass are not split by block id (research/water.md's first version): one translucent program, no water feature.
- BLOCK_FLICKER's default Low, the roughnesses (0.7 opaque, 0.15 translucent terrain) and EMISSIVE_STRENGTH 2.0 are Claude's look choices (D86).

## Open questions
- The look (D86): the beacon beam's core and glow, the sun's highlight on terrain, foliage's wrap, the flicker's amplitude; the Nether's saturation, the End's sky box brightness; the user's review.
- From the last handoffs: E3 (the timers' spans); RenderDoc's target-control server blocked inbound on Public networks; pinning gamma, Smooth Lighting and See-Through Leaves (the user's); M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- Program 445 as vanilla's lightmap pass is inferred from its place (the frame's first draw, ungrouped, 0.03 %); only its not being Iris's is read.
- pipeline.json's options are textual: an include's unused function or the targets' comment counts (SCENE_FORMAT on every program including targets.glsl).
- No coverage view draws line, spidereyes, damagedblock, armor_glint, lightning, hand_water, entities_translucent or weather in game (M4.P08's content and waivers, D83); L0 builds each.
- GLYPH and position-colour formats carry no normal: entities_translucent's text and basic take Iris's defaults.
- A blended draw before deferred that writes depth (sign text, if it does) has deferred light the surface under it at its own depth (research/lighting.md#d-thin-g-buffer-deferred-opaque-forward-translucent); unread, no perf view draws one.
- tests/test_launch.py::test_logman_lists_sessions_on_this_machine failed once in a parallel run, passed alone and in every later run.
- From the last handoffs: P22's list bounded by moderngl's candidates; renderStage read per pass; sky.glsl without an L3 test; LIGHT_PATH 0 against 1 unmeasured until M4.P10.

## Commits and time
- 73be07b (the programs, the options, their tests, pipeline.json, the docs), 0d592a9 (the weather directive), 84026b6 (the shadow programs), 7d9743f (the six runs' records, shader.md's A/B and L4 facts), then this handoff; CI green on each.
- M4.P07: about 1.8 h of work against 4 h (2026-11-03 15:48 to about 17:35 AST). Machine: 6 launches, about 15 min.
- Tripwire: actuals about 77.5 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 13.3: P00 3.8, P01 0.6, P02 0.7, P03 0.9, P04 2.1, P05 1.8, P06 1.6, P07 1.8) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P08 Coverage and determinism (docs/prompts/m4.md), in a fresh session: the coverage content (D83: a named NoAI mob, the off-hand translucent item, a gradient banner, enchanted trimmed armour, the creative pose with the outline in reach), the snapshot retaken, capture runs filling the coverage list, two visual runs identical on the 11 perf views; it launches about 8 times and sends input, so the machine left alone with the displays awake.
