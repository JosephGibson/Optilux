# Handoff
Status: the latest stop: M4.P08 coverage and determinism done on branch m4, committed and pushed: the coverage content (a named mob, a gradient banner, enchanted trimmed armour, the off-hand glass, a creative view with the outline), the snapshot retaken, every pass's views or waiver from frame captures, the M4 pack identical across launches on the 11 perf views, the look runs beside Unbound. M4.P09 is next.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P08
- The Exit of M4.P08 (docs/plans/m4.md) held, shown in this session (2026-11-03 and 2026-11-20, AST):
  - `world prep bench_263` (prep-bench_263-20261103-222654, 18:26:54 to 18:32:22): "optilux world prep: ok; 15 views prepared, snapshot 31830e4397eadfc3f5387eea48bedc6b26558cad99f8f4b48538ea4c029be4ba (129 files)"; after the sweep each of the 8 content entities "Test passed. Count: 1" (named mob and armor stand counted only as built: name, trim and enchantment in their nbt filters), every block "Test passed", the sign "Optilux", the banner "minecraft:gradient";
  - m4-determinism-1 (15:40:45 to 15:43:56) and m4-determinism-2 (15:44:04 to 15:47:15), full mode, `optilux@HEAD` at 06d56f6 (zip sha512 8c02119b...), each "11 of 11 captures valid, pairs moving: none"; `compare m4-determinism-2 --against m4-determinism-1`: "identical" on all 11 perf views;
  - every pass has views or a waiver: tests/test_pipeline.py (16 passed) holds config/pipeline.json to tests/fixtures/l4/coverage.json, the labels `check L4` read from m4-coverage-capture-1 ("11 of 11 captures valid, 11 .rdc hashed, 3632.1 MiB", 15:29:47 to 15:32:31) and m4-coverage-capture-2 ("16 of 16 captures valid, 16 .rdc hashed, 4762.4 MiB", 15:34:15 to 15:37:29), each held to its record's .rdc sha256.
- Waivers (pipeline.json, shader.md#coverage-list): D83's lightning (gbuffers_lightning, shadow_lightning), the damaged block, spider eyes and snow (weather: none under the define, D79's directive; rain at rain off it, defineOff); beyond D83, no capture drew a key Iris gives shadow_block, the shadow root, basic (leashes among them) or textured, and textured_lit is a fallback only. 25 dimension waivers: what the Nether's (15) and End's (10) views lack for a pass drawn elsewhere.

## What was built
- 06d56f6: `world prep`'s coverage step: a NoAI cow named Optilux (CustomNameVisible) at (321.5, 101, 1068.8), a white banner with a blue gradient at (319, 101, 1073) read back by `data get`, the armor stand's diamond chestplate trimmed (sentry, gold) and enchanted (protection 1), counted by both; session.OFFHAND (light-blue stained glass) set at a coverage view with `hand` on arriving and emptied before spectator (measure.arrive, leave_gui; world.prepare_view, before the snapshot); the views file's coverage_hand (317.5, 102, 1069.5, yaw -90, pitch 40, hand): the crosshair on floor block (320, 100, 1069) 4.08 m from the eye, inside survival's 4.5. 26.3 draws name tags and the outline only with the GUI shown (LivingEntityRenderer.shouldShowName and GameRenderer.shouldRenderBlockOutline read Hud.isHidden, javap), so the cow stands where only coverage_hand frames it (placed by projecting into each view at FOV 90 and 99); measurement.md#baseline-suite; suite.json coverageViews.
- 092fac6: pipeline.json's views (views drawn at the defaults), defineOff, waiver and dimensionWaivers per pass; tests/fixtures/l4/coverage.json (27 captures' labels, Iris 1.11.7's 90 ShaderKeys and its ProgramIds' files and fallbacks, javap); four new tests; shader.md#coverage-list and Pipeline spec; research/programs.md's views; suite.json's mover; CHANGELOG.md's 0.5.0 bullets.
- 5ba059a: the launch spec re-pinned on Mojang's sixth 26.3 JSON (the asset index alone: 917ff6d7... to 331e5c80..., +95,884 bytes), its fixture and test.
- The look (D86): results/raw/m4-look-1/review.html and m4-look-2/review.html (15 views, the pack beside Unbound played); results/raw/m4-coverage-capture-2/tonemaps/index.html: per capture-2 capture the HDR scene (colortex0 after its last writer before composite) at the pack's exposure and grade through the Lottes-like curve, AgX, Hable and PBR Neutral (their published forms), beside the game's frame; the page's own path matches the game's frame within 1 level (the dither) on all 16.

## Review
The reviewer agent (completeness against the captures): 13 findings, 2 medium, 11 low, each read at its source.
- Fixed: per-dimension files drawn by no view of their dimension (medium: dimensionWaivers and a test); passes the define discards (clouds, particles) listed as drawn (medium: viewsWhy and shader.md say their look is the define-off captures'); the textured_lit, shadow root and shadow_block waivers' wording; shader.md's missing fallbacks, its "all D83" for weather, its end-crystal line (shadow_entities hides them); pipeline.json's stale top-level why; the lightning waivers' reason (no bolt in rain's stepped ticks); D83's waivers now tested to cite D83.
- Not borne out: two unlabelled programs at coverage_beacon draw after final (the HUD), as shader.md#facts says.
- Reported: program/shadow.fsh.glsl's header still credits the root with entities' shadows (left, so the pack stays the zip the runs measured); rain's particles_translucent appears in capture-2 alone (particles vary by launch; views are the union); the basic waiver's leash gap is no D83 item; the waiver texts are tested only for D83's citation.

## Checks
- Start (2026-11-03 17:48 AST): branch m4 clean at 1a31b11; 1131 passed; verify docs 0 violations.
- Before the commits: `optilux test` 1137 passed; ruff and pyright clean; verify docs 0 violations; verify records "416 records, 0 violations"; check L4 on both capture runs (45.75 s, 175.27 s). CI green on 5ba059a and 06d56f6; c42db7a and 092fac6 below.

## Deferred and logged
- Choices: the off-hand glass only at coverage views with `hand`, never in the snapshot, so the entities perf view keeps its torch alone (suite.json's coverage area: out of sight of every perf view); a fourth coverage view rather than moving one; the outline on a floor block; capture-2 with the define off too (weather at rain, the scenes kept with `--keep`); the records committed before the coverage list, whose fixture test reads them.
- Stops met: the first prep refused (the launch spec moved); the user chose the re-pin. m4-coverage-capture-1's first try was refused by D42 after 10 min (mpvnet.exe at 3.5 % of the 3D engine), nothing launched; resumed 2026-11-20 at the user's word, unattended. The scratchpad had been cleared: specs and scripts rewritten. A scratch display hold (SetThreadExecutionState) ran 15:28:59 to 15:55:20.
- Within a launch, the M4 pack's coverage_hand pair moved (m4-look-2: 24,878 pixels along the player's own shadow; a creative player ticks under /tick freeze): named in suite.json coverageViews, out of identical and near.
- results/raw/m4-coverage-capture-2/l4 holds 22 GB of kept targets (disposable; 77 GB free).

## Open questions
- The look (D86), the user's, no stop; Claude's pre-screen of the look runs, suspects: ocean_sunset's sky stays day blue at 12000, the sun a large white square, its highlight on water a hard vertical streak; night draws no moon and no stars; underwater is near black with no water fog, the surface showing the day sky; rain is lit and skied as clear noon; clouds read as dark grey smudges (forest_noon, coverage_hand); the End's sky a flat grainy lavender over bright End stone and black pillars; the Nether strongly saturated, no distance fog; shadows faint on the coverage floor. Tonemaps: AgX desaturates, Hable darkens and flattens, PBR Neutral is brightest and most saturated.
- A leashed mob for basic's leash key (no D83 item); the shadow program's stale comment.
- From the last handoffs: E3; RenderDoc's target control on Public networks; pinning gamma, Smooth Lighting and See-Through Leaves; M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- The coverage fixture holds draws, not visible pixels: an entity just outside a frame still draws (entities_cutout_glint at coverage_hand).
- The Nether's no sky or clouds, the End's no clouds and water never standing in the Nether are game knowledge, unread in the jar this session; the captures show none drawn.
- The tonemap page and the fixture's builders are scratch scripts, not optilux modules; AgX is its common polynomial fit.
- Mojang republishes 26.3's index every week or two: a seventh stops launches again until a re-pin; M4.P09's freeze makes that a stop.
- From the last handoffs: test_logman's parallel flake; P22's list; renderStage per pass; sky.glsl without an L3 test; LIGHT_PATH 0 against 1 unmeasured until M4.P10.

## Commits and time
- 5ba059a (the re-pin), 06d56f6 (the coverage content), c42db7a (the six records), 092fac6 (the coverage list), then this handoff.
- M4.P08: about 2.2 h of work against 3 h (2026-11-03 17:48 to 18:50 and 2026-11-20 15:25 to about 16:35 AST). Machine: 7 launches, about 25 min, and two refusals before a launch.
- Tripwire: actuals about 79.7 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 15.5: P00 3.8, P01 0.6, P02 0.7, P03 0.9, P04 2.1, P05 1.8, P06 1.6, P07 1.8, P08 2.2) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P09 Recalibration (docs/prompts/m4.md) in a fresh session: it freezes identity at the first calibration session and stops for the user's go before about 135 launches over about 5 h, the machine left alone with no remote viewer connected.
