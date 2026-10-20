# Handoff
Status: the latest stop: M3.P03 done, the hello pack and pipeline spec v0 built and loaded on bench_263 through `run`'s new Optilux variants, and what M3.P04 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P03
- The exit holds, shown by m3-hello-1 (2026-10-20, 13:44:40 to 13:47:52 ADT), an announced acceptance run of A2 and A10 on bench_263's eleven views with the hello pack built from 6687dab (`optilux@HEAD`):
  - `optilux run: ok; results/records/m3-hello-1.json: A2 pass, A10 pass`. A2 passed on its first attempt at all eleven views; A10's five checks passed.
  - The pack loaded with no compile error or fallback. The start-of-run reload answered optilux-6687dab1ff5a.zip on IrisRenderingPipeline in 0.180 s. latest.log shows "Creating pipeline for dimension" for the overworld (13:45:11), the Nether (13:46:33, 13:47:17) and the End (13:46:45, 13:47:38), with no WARN or ERROR after the switch. The record holds hookFailures 0, irisOutsideReload 0, the read-back ok and one option read back (BENCH_DETERMINISTIC true).
- The hello pack's zip, from 3427e24 on: 25 entries, sha512 d86371b78b24b77ff53a2e072f1ab39e419287475ee9a7944a09c29d1683fb154197740afc8eef2e30476084b11e02a22f2e666e547f9e478ed5199c085636d4. `run --check`, `pack build --ref HEAD` and `pack build` of the clean tree gave these bytes.
- A2's frames (each view's F2 screenshot, read at 1280x720). "n of 24" counts the distinct frames among the 24 captured over about 2.4 s; Unbound gave 24 of 24 at every view (m2-acceptance-2).
  - forest_noon (1 of 24): a birch and oak forest from above at noon, water and hills beyond, the far terrain fading into the pale edge fog; no clouds; the leaves cut out cleanly.
  - ocean_sunset (1): a shallow sea with seagrass seen through the water and a sand beach; an orange sunset band; the sun a white square; a pale fog band on the horizon.
  - cave (1): a lava lake full-bright, the stone around it lit by its block light and fading to dark.
  - rain (1): a birch forest and beach under a dark grey thunder sky, dimmed; no rain or lightning drawn.
  - nether_crimson (1): a crimson forest over a lava sea, shroomlights glowing; no Nether fog, no spores.
  - end_dragon (1): the obsidian pillars with fire and two iron cages at their tops, and no end crystal on any: the entityId discard holds. The End's sky texture.
  - night (1): stars, a dark beach and trees, a dark blue sea; no clouds.
  - underwater (9): a dark seabed of seagrass and kelp, the surface and a far island above. The band of rows 0-372 brightened by up to 31 levels during the capture, its mean blue 109.3 to 113.1, then held (frames 22 to 24 equal). This is the water fog colour following the player's water vision (Open questions).
  - nether_soul (1): a soul sand valley over a lava sea, basalt pillars, the teal fog colour in the distance.
  - entities (1): the posed cow, horse, sheep, villager, llama, chicken and a pig on its side in the plains village; flat-lit (the pack applies no per-face shading); no GUI (A2's hideGui).
  - end_city (1): End city towers, an End ship and chorus plants under the End sky.
  - Water, lava and fire held still for 2.4 s at every view (/tick freeze); the static-textures pack (M3.P06) still sets their frame across launches.
- One bench launch. runtime/ written only by `run` (the zip and its settings file in shaderpacks/, both gone after the quit), its world restore and the game. No system setting. reference/ read only by `verify similarity` and the pre-commit hook, never by a model.

## What changed
- The hello pack (shader/shaders/), `#version 330 core`:
  - lib/surface_vertex.glsl and lib/surface_fragment.glsl, the one gbuffers stage pair, set per program by valued switches (SURFACE_TEXTURE, SURFACE_LIGHT, SURFACE_NOT_IN_BENCH, SURFACE_HIDES_CRYSTALS: no Iris option); lib/fog.glsl, lib/light.glsl, lib/options.glsl (BENCH_DETERMINISTIC, on).
  - gbuffers_basic, textured and textured_lit; particles, weather, lightning and clouds, which discard under the option; final copies colortex0, opaque; entity.properties (entity.1, the end crystal); shaders.properties (the screen).
  - Each stage compiled and each pair linked with glslang 16.6.0, the option on and off: 48 runs, 0 failures. With the option on, glslang's reflection lists no fogStart, fogEnd or textureMatrix.
- config/pipeline.json v0 and tests/test_pipeline.py (11 tests): the passes equal the program files, each pass's declared samplers and uniforms (default build), its RENDERTARGETS, the option that changes its code, every view of its dimensions, and no input that moves between frames (cycle 1).
- `run` admits `optilux` (the working tree) and `optilux@<ref>` (the commit resolved at the check) in acceptance runs. optilux/packzip.py now holds the zip writer, out of verbs/pack.py, so the measured closure gains packzip alone. `pack build --ref` zips the commit's tree; `--ref` and `--version` combine. `prepare` builds the zip, so `--check` refuses one that cannot build and prints its sha512. `run` writes it (and its part file, journaled), names it in iris.properties with an empty settings file before the start-of-run reload, records `build` and sha512, and deletes them after the quit. A4 is refused with it. An acceptance run now fails on files it could not delete.
- Docs: shader.md (Status, Pipeline spec v0, Determinism and TAA, Facts), design.md#4-architecture's pipeline.json, run-record.md (Record, Run spec), AGENTS.md's shader line, CHANGELOG.md's 0.4.0 entry (three bullets).

## Review
- The pack (reviewer agent, against D56 and shader.md#determinism-and-taa): 9 findings, each read at its source.
  - Fixed:
    - 1 (high, verified in 26.3's bytecode): fogStart and fogEnd carry AtmosphericFogEnvironment's rain fog multiplier, eased by each frame's wall-clock length under /tick freeze too (getGameTimeDeltaTicks counts Util.getMillis(); one instance across views). My premise of a per-tick smoothing was wrong. Under the option the pack now reads neither and draws the edge fog alone.
    - 6: cycle 1's premise is now tested.
    - 7: options are counted from #ifdef/#ifndef only, as OptionAnnotatedSource does.
    - 8: textureMatrix, fogStart and fogEnd are declared only with the option off.
    - 4: the textured header now says only the separate glint draw falls back to it.
  - Reported:
    - 2: verified; the water fog colour, seen live (Open questions).
    - 3: refuted. MixinModelSubmit keeps the id with each deferred submit and MixinModelFeatureRenderer sets it at the draw; end_dragon shows no crystal.
    - 5: the sky takes the world's fog, not vanilla's sky fog; look only.
    - 9: dropped items' random bob; coverage only (M3.P07).
- The variants (reviewer agent, correctness): 9 low findings.
  - Fixed: 2 (`--check` built nothing), 5 (`--ref` with `--version`), 6 (refs resolved once), 7 (the part file journaled), 8 (four tests: a moved ref, F4 on the variant, a refused launch, the empty settings file and the journal), 9 (run-record.md#record); and 4 in part, by a test that shader/ holds only LF files and nothing git ignores.
  - Reported:
    - 1: A9 on the hello pack may fail its half-frame bound (unverified; M3.P05 runs A9 on the reference pack).
    - 3: CI's PR artifact now zips the PR head's tree, equal to the merge's under this flow.

## Choices
Neither the prompt nor the plan names these:
- BENCH_DETERMINISTIC beyond D56's list, each from 26.3's bytecode:
  - the lightmap's flickering block light, rebuilt at rest from the block-0 column;
  - the texture matrix (the glint's wall clock), not applied;
  - the environmental fog, not drawn.
  - Off, each draws vanilla's.
- The crystal test sits in textured_lit, no gbuffers_entities. Lightning and clouds draw their vertex colour with the option off.
- The variant joins on the reference pack, as launch writes it, and switches at the start-of-run reload, as measured runs switch packs. So A10's reload runs on the reference pack.
- Zip names: optilux.zip and optilux-<sha 12>.zip. The exit used `optilux@HEAD`, so the record names its commit.
- P23's "`pack build --ref` builds a commit's shader/" was not so as found (it read VERSION alone); built here.
- pipeline.json v0: views are every view of a pass's dimensions; inputs are the default build's declarations; the screen's format is null.

## Checks
- Start (12:14 ADT): branch m3 clean at 7de5779; 825 passed; verify docs 0 violations.
- Before each commit: 836 (the pack's), then 851 passed; ruff, ruff format and pyright clean; verify docs 0 violations; verify similarity 0 matches of 72 tokens (21 GLSL files, 629 tokens). verify records: 224 records, 0 violations, m3-hello-1 reported at 200,732 bytes (an acceptance record).
- CI green on 3427e24, 6687dab and 3801070, each watched to its end before the next push.

## Open questions
- Driver: m3-hello-1 records 32.0.31041.1004; every M2 run recorded 32.0.31041.3013. It changed outside these sessions between 2026-10-15 and 2026-10-20, so M3.P10 starts with D66's budget run.
- Water fog colour (M3.P06, M3.P09): in water, fogColor follows the player's water vision, which players gain under /tick freeze too. It is the one moving input the pack still reads under the option, and Iris clears colortex0 to it. At underwater it still moved 2.4 s after the 2.0 s settle, longer than a spectator's 60-tick counter predicts (unexplained). Either the view's settle covers the ramp, or the pack holds the colour in water.
- D72 (look); D66 (driver, above); the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- The resting block light approximates vanilla's: no brightness curve on the block part; the default tint.
- The pack ignores single-pass glint (mc_sampleGlint) and the dragon's dissolve; entities are flat-lit.
- Sodium's cutout alpha reference was not read offline; the leaves cut out cleanly in the frames.
- Margins: AGENTS.md 26 bytes; measurement.md 23; platform.md 56; workflow.md 199.

## Commits and time
- 3427e24: the pack, pipeline.json and its test. 6687dab: the variants and their tests. 3801070: m3-hello-1. Then this handoff.
- 2026-10-20 12:14 to about 14:05 ADT: M3.P03 took about 1.9 h against 2.5 h. Tripwire: actuals about 50.4 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.8, M3.P02 about 0.8, M3.P03 about 1.9); the trip is at 174.6 h.

## Next
/optilux-next prints M3.P04's prompt: check L0 and the iso profile v1, 2 h (M), no launch. The variants' zips are built from here; `check L0` gates them before a launch.
