# Handoff
Status: the latest stop: M4.P06 the base pack done on branch m4, committed and pushed: the probe answered P22 and P23 in game, the base pack (G-buffer, deferred lighting, Low shadows, gradient sky, tonemap) loads in all three dimensions and its visual run ended ok. M4.P07 is next.

## Contents
Outcome · The probe · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P06
- The Exit of M4.P06 (docs/plans/m4.md) held in this session (2026-11-03, AST), shown:
  - m4-base-visual-1, a visual run of `optilux@HEAD` (6208da5's zip, sha512 5cb2b68c...) on quick mode's views, one launch, 15:09:54 to 15:11:38: "optilux run: ok; results/records/m4-base-visual-1.json: 3 of 3 captures valid, pairs moving: none"; each reload ran Iris's IrisRenderingPipeline with the pack (latest.log: forest_noon 15:11:06, nether_crimson 15:11:15, end_dragon 15:11:26), no compile error, no fallback; every frame hashed, the pair at each view equal (forest_noon a5cac017...);
  - `check L0`: "20 programs x 3 dimensions x 6 variants (defaults, BENCH_DETERMINISTIC false, E2_LOAD 4, E2_LOAD 8, E2_LOAD 16, LIGHT_PATH 0) = 342 builds", determinism "0 refusals", similarity "0 matches of 72 tokens or more": pass;
  - `check L3`: "pass: 9 of 11 includes tested, 33 functions over 93,247 cases".
- The frames (look, D86's to review): forest_noon lit with the gradient sky and the edge fog into it; nether_crimson very saturated red (exposure 2.2 with the Nether's ambient); end_dragon's sky box, drawn by skytextured at strength 1, a bright lilac noise.

## The probe
A probe build in shader/, never committed (its generator and sources in the session's scratchpad), through m4-probe-dump-3 (bench, 14:06:08-14:07:19, "3 of 3 dumps whole, 1 distinct") and m4-probe-capture-1 (debug, entities, coverage_items, coverage_beacon, 14:10:05-14:12:01, "3 of 3 captures valid, 3 .rdc hashed, 940.8 MiB"); the capture build added a shadow pass (sha512 46fd40f5... dumped, 7cf369ec... captured). Its pass outputs were read by the committed l4replay.py with outputs on (check L4 asks for them only beside a second capture of a view).
- P22: all 296 extensions the driver reports to a 3.3 core context (moderngl 5.13.0, driver 26.8.1.260810) are defined in game as MC_GL_<name>, in each dimension: compute, SSBOs, image load/store, ARB_draw_buffers_blend, ARB_gpu_shader5, ARB_shading_language_packing among them. Controls: MC_OS_WINDOWS, IS_IRIS, MC_GL_VENDOR_ATI and MC_VERSION 260300 defined, MC_GL_VENDOR_AMD and MC_GL_RENDERER_RADEON not. Read as lines of shaders.properties under #ifdef, which the dump's preprocessed.properties keeps: L0 refuses a stage naming MC_GL_* (offline.md#levels), so not tokens of the stages as the prompt says.
- P23, D75: an RGBA16UI target, Clear=false, written whole by every gbuffers program, read back by deferred's texelFetch exactly on every geometry pixel (entities 5,201,664, coverage_items 5,119,234, coverage_beacon 3,652,610 of as many; deferred's own check green on all, red on none); sky pixels hold stale values (2,457, 912 and 77,769 px still matching an old pattern), so the sky skip by depth is needed. D75's fallback is not taken.
- P23, D76: renderStage per pre-deferred pass: SKY (sky), TERRAIN_SOLID (solid and cutout terrain), NONE (entity draws, ungrouped), BLOCK_ENTITIES (sign text, drawn through block_translucent, and the beacon beam), HAND_SOLID; after deferred the beam again at BLOCK_ENTITIES, translucent terrain at RAIN_SNOW or NONE, translucent particles at PARTICLES. renderStage cannot tell a program's draws before deferred from those after: D76's waiver branch for M4.P07.
- Depth (M4.P05's open question): 26.3's main depth is stored reversed; Iris 1.11.7's DepthTransformer rewrites depthtex0/1/2 reads and gl_FragCoord.z to 1 - d and the projections forward, so depthtex0 = 1 - stored on every pixel, the sky exactly 1.0. shadowtex is not rewritten: D32 2048 x 2048 cleared to 1.0, stored equal to the forward reference at the median; a hardware compare gave lit 76-86 %, shadowed 7-9 %, partial 7-15 % of geometry pixels. platform.md#mc-263 corrected (R11 was wrong).

## What was built
- shader/shaders/, written fresh: lib/ (Iris-free: gbuffer codec, octahedral normals, light curves, lighting core, gradient sky, edge fog, shadow mapping, tonemap, sRGB, dither, options), program/ (the Iris glue and program bodies), the root's programs (the overworld), world-1 (the Nether, no shadow programs: no pass, P20) and world1 (the End), each a wrapper defining its dimension; 20 programs: terrain_solid (no discard), terrain_cutout, entities, block, hand and particles into the G-buffer (D75; albedo stored sRGB-encoded); deferred (lighting, D76's three targets applied, the gradient sky with skytextured's sun and moon added, the edge fog into the sky); shadow, shadow_solid, shadow_cutout (D77: 2048, 96 blocks, multiplier 1, depth only, one hardware compare on shadowtex1); composite (exposure per dimension, saturation matrix, a Lottes-form curve solved from midIn and hdrMax, sRGB into RGB10_A2) and final (static triangular IGN dither) (D78); skybasic culled, skytextured into the early target; basic, textured, textured_lit, clouds, weather, lightning forward. Options: BENCH_DETERMINISTIC, LIGHT_PATH (0 forward, 1 deferred, the default) and E2_LOAD (0, 4, 8, 16 compare taps from an int custom uniform) on a DEV screen.
- config/pipeline.json v1: 7 resources (name, buffer, format, clear, history, scale, why) and 20 passes in frame order with options lists; tests/test_pipeline.py rewritten for it (12 tests, its own #if reader).
- L3 tests per include: tests/l3/lib/ gbuffer, normals, curves, lighting, tonemap, srgb, dither, shadow, fog; l3.py takes uint, ivec and uvec arguments and results; check L1's audit takes a target cleared every frame as written (pipeline.json resources), and its impact matrix reads `options`.
- The hello pack, its spec v0 and its L3 tests moved to tests/fixtures/hello/ for the tools' own tests (L0, L1, L2, L3).
- Docs: shader.md (Status, Pipeline spec, Determinism and TAA as built, Facts), offline.md, platform.md, AGENTS.md, CHANGELOG.md's 0.5.0 bullet; research lighting, programs, sky, shadows, tonemap and synthesis corrected where P11-P20 and the probe contradict them (synthesis's premises list cut to a pointer first). A researcher agent listed about 140 claims; the contradictions and the cheap [verify in jar] tags were fixed.

## Review
The reviewer agent on the pack against D75-D79 and P11-P20 (correctness): 1 high, 1 medium, 4 low, each read at its source.
- Fixed before the pack's commit: the Nether's ambient never reached a surface (the sky level is 0 there: 26.3's the_nether has_skylight false, read in the jar; the End has sky light) - sceneLevels takes the Nether's sky level as full; the hand's held light differed between LIGHT_PATHs (now half a block in both); 8-bit linear albedo lost dark texels (sRGB 0-6 stored 0) - the G-buffer stores the sRGB-encoded albedo, deferred linearizes it; entity.properties' comment; the shadow lookup's circular reach dropped the map's corners (the distortion keeps the whole square inside).
- Reported, not fixed: in the End the edge fog fades into END_SKY, not the sky box behind (a seam at the render distance; the box's mean needs a capture: M5's End sky); a pre-deferred draw that writes depth through a forward root (the beacon beam's core, perhaps leashes) leaves deferred decoding a stale G-buffer texel at coverage_beacon (M4.P07's beaconbeam and line programs; no perf view draws one).

## Checks
- Start (2026-11-02 16:18 AST): branch m4 clean at 7c62abd; 1122 passed; verify docs 0 violations.
- Before each commit: `optilux test` green (1127 passed), ruff and pyright clean, verify docs 0 violations, verify similarity 0 matches (140 GLSL files), verify records 0 violations (404 records); no mod change. CI green on 4b4cc66 and 6208da5 before the next push.

## Deferred and logged
- The session ended at 2026-11-02 16:33 with the first dump run's game starting: m4-probe-dump-1 was finished as an orphan (aborted) by the next run; m4-probe-dump-2 failed as 26.3, seeing the unexpected shutdown, reset fullscreen (854x480: "Detected unexpected shutdown during last game startup: resetting fullscreen mode"); m4-probe-dump-3 ran ok. Five launches against the plan's three.
- 4b4cc66 (the probe's records) also carried tests/l3/lib/light.py's deletion, staged earlier by `git rm --cached`: at that commit test_l3's hello-pack test fails on a machine with GL (CI skips it, green); 6208da5 restores it through the fixture.
- skybasic and skytextured written now, not in M4.P07: D78's deferred gradient with vanilla's sun and moon needs skytextured in a target deferred adds at the sky.
- The sky and light colours are computed per pixel from sunPosition and rainStrength, not custom uniforms (T11's chain): M4.P11's uniform-work scan (D70) prices it.
- Not read yet: nightVision, darkness, screenBrightness, the entity overlay colour, a held light's colour. The forward roots light facing up, unshadowed (M4.P07).
- Until M4.P07, translucent entities, block entities, particles and the translucent hand fall back to G-buffer programs and draw nothing after deferred; D76's targets are cleared and read, no program writes them.

## Open questions
- The look (D86): the Nether's saturation, the End's sky box brightness; the user's review.
- From the last handoffs: E3 (the timers' spans; M2's 0.048 ms); RenderDoc's target-control server and runtime's java.exe blocked inbound on Public networks; pinning gamma, Smooth Lighting and See-Through Leaves (the user's); M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- P22's list is bounded by moderngl's 296 candidates: an extension only the game's context reports would not show.
- renderStage is read per pass from the target's snapshots (the first pass a pair shows in), not per draw.
- sky.glsl has no L3 test; LIGHT_PATH 0 against 1 is unmeasured until M4.P10.
- From the last handoffs: replay shares move between replays; a replay A/B candidate that compiles but fails to link (unverified); one capture per press.

## Commits and time
- 4b4cc66 (the probe's records), 6208da5 (the base pack, its L3 tests, pipeline.json v1, the fixture), 00e04b6 (the research corrections), then this handoff with m4-base-visual-1; CI green on each.
- M4.P06: about 1.6 h of work against 4 h (2026-11-02 16:18 to 16:34, 2026-11-03 14:04 to about 15:25 AST). Machine: 5 launches, about 8 min.
- Tripwire: actuals about 75.7 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 11.5: P00 3.8, P01 0.6, P02 0.7, P03 0.9, P04 2.1, P05 1.8, P06 1.6) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P07 Every other program (docs/prompts/m4.md), in a fresh session: the forward programs after deferred, the pre-deferred blended draws into D76's targets (renderStage cannot split a program's two sides), the beacon beam's stale G-buffer (Review), the options; its four launches send input, so the machine left alone.
