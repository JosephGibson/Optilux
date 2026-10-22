# Handoff
Status: the latest stop: M3.P08 closed out: the dump kind, `check L1` (its audit's uniform -> reader included) and `check L2` built and run on m3-dump-1, its closure spot-checked live by m3-closure-1, and what M3.P09 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P08
- The exit holds, shown in this session (2026-10-22, ADT), each launch announced and run with the machine left alone:
  - m3-dump-1 (18:49:19-18:50:36): a dump run on bench_263 (world 33a4074d...) of the hello pack at HEAD 34ebd37 with BENCH_DETERMINISTIC on (`head`, zip sha512 d86371b7...) and off (`off`), and the working tree's change (`change`, 5e7f2673...).
    - It ended ok: 9 of 9 dumps whole (254 files each, 182 stages); 2 distinct manifests, the same in all three dimensions; 104,852 bytes.
    - The change: lib/fog.glsl's environment fog inside `#ifndef BENCH_DETERMINISTIC`, `fogRamp(...)` to `0.5 * fogRamp(...)`. It was never committed and was reverted after the runs.
  - `check L1 m3-dump-1`:
    - The define changes 139 files in each dimension: the .vsh and .fsh of 69 gbuffers programs (basic ... weather, terrain and sodium_terrain, entities, hand, sky, text) and preprocessed.properties. final's stages are equal.
    - `change`: dump-equal in overworld, the_nether and the_end. CLOSED (L1 dump equality): no effect, its manifest f4d735f6... equal to head's in each.
    - Its premise holds: withFog is defined in 414 dumped stages and reached from main in 207 (69 per dimension).
    - The impact matrix: lib/fog.glsl -> 14 program files -> the 7 gbuffers passes -> 11 views; option BENCH_DETERMINISTIC -> the same 7 passes.
    - The audit: 0 problems. The record's offline field agrees.
    - Its uniform -> reader (the close-out, d322d67): head's prints read entityId, far and fogColor, off's far, fogColor, fogStart and fogEnd, each Iris's; the pack's other five declared uniforms (modelViewMatrix, projectionMatrix, chunkOffset, textureMatrix, alphaTestRef) are replaced by Iris's transformers and read in no print. The record's own audit field predates the check (records are never edited); `check L1` prints it now.
  - m3-closure-1 (18:51:25-18:52:59): a visual run of `change` against `head` on quick mode's views, the live spot check (offline.md#rules). It ended ok, 6 of 6 valid, no pair moving.
    - `compare` tiers `change` against `head` identical at forest_noon, nether_crimson and end_dragon.
  - `check L2 m3-dump-1` (RGA 2.15.0.30, gfx1101): 38 distinct programs, 364 stages each with its VGPRs, 0 known offline failures, 1.57 s.
    - With the define on: fragment stages 2-19 VGPRs (2 where it discards: particles, weather, lightning, clouds), vertex stages 9-37.
    - Examples: final.vsh 9 and .fsh 4; basic 17/12; textured 22/16; terrain_solid 34/19 (off: 29/19); entities_cutout 37/19 (off: 33/19); sodium_terrain_solid 32/19; particles 11/2 (off: 29/19).
    - The define on costs the lit programs' vertex stages VGPRs (terrain_solid 34 against 29, entities_cutout 37 against 33; basic's 17 against 19). L2 explains only: likely its resting block light, which lib/light.glsl computes in the vertex stage.
- An L1 finding: Iris's properties preprocessor defines an enabled boolean option as 1, so with BENCH_DETERMINISTIC on, shaders.properties' `screen = BENCH_DETERMINISTIC` reads `screen = 1` (preprocessed.properties). The pack's settings screen then names no real option. It does not touch the bench (Open questions).

## What changed
- b4f4165: the dump kind.
  - record.DUMP, check_dump_spec, dump_views (per dimension the views file's first view), record.dump_manifest.
  - launch.iris_properties' `debug` (enableDebugOptions true).
  - measure.dump_body and dump_capture: the print's places emptied before each reload, the print copied under raw/<run>/dumps/<dimension>/<variant>/ and re-hashed; compared_sha256 drops Properties.store's date line.
  - run.py's dump branch: zips kept under raw/<run>/packs/, `dumps` deduplicated by manifest, the read-back of the flag.
  - The orphan's record; verify's dump_problems; the fake's Iris print.
- fe0f6fd: `check L1` (optilux/l1.py; check.py).
  - Dump equality and took-effect, the premise check, the impact matrix and the audit.
  - The record's `offline` from `check L1 -` in a child process; verify re-judges it.
- 04ca9ce: `check L2` (optilux/l2.py; check.py), RGA's output fixtures from the hello pack's final program.
- 1a111b5 and 34ebd37: the reviews' fixes (Review).
- 2a0f3cb: the two records.
- The close-out, at the user's request after the first handoff ("Can you fix what's not fixed if it's in the scope P8 and close out P8?"):
  - 357dc1f: config/tools.json's rga pin names what its exe prints (`printed` 2.15.0.30); check L2 holds it exactly.
  - d322d67: the audit's uniform -> reader: l1.IRIS_UNIFORMS (195 names), pack_uniforms, read_uniforms, uniform_problems; check.iris_pinned refuses another Iris jar.
- Docs:
  - offline.md: L1 and L2 as built, the dumps' print and Iris's transform cache.
  - design.md's check row; run-record.md: the dump kind, its spec, the `offline` field.
  - CHANGELOG.md 0.4.0: dump runs, `check L1`, `check L2`.

## Review
The reviewer agent on L1 (correctness): 13 findings, 2 high, 4 medium and 7 low. Each was read at its source and all are fixed (34ebd37):
- High:
  - A continued #define's body was read as code and `for` passed as a function name, a false "not compiled". Continuations are now joined, directives kept in place, keywords refused.
  - A premise verdict closed whatever the options and the prints said. Now it closes only at the baseline's options, dumped in every dimension: not compiled where the prints are equal, not executed where every differing stage differs in dead changed functions alone (l1.dead_only).
- Medium:
  - A changed texture or .mcmeta could be closed by dump equality; a file no print shows now blocks it.
  - impact failed on a pack that maps its dimensions; the error is now caught.
  - A one-variant record failed; it now has no candidate to judge.
  - `check L1` judged records that were not ok; it now refuses them.
- Low:
  - Directive moves: kept in place.
  - An empty print: counted by stage files.
  - verify now re-derives every expected closure.
  - Closures come after the final status.
  - The orphan keeps its `packs`.
  - Files are compared by bytes.
  - The audit covers only Optilux variants; agreement leaves the audit out.
- Its open points, settled at the source:
  - Iris keeps user function names and main (the spike's print; withFog found in 414 stages).
  - TransformPatcher caches each transform (LRUCache 400, no flag in the key, never cleared: javap), so the run turns the flag on from its start-of-run reload.
- The reviewer agent on L2 (correctness): 12 findings, 4 medium and 8 low, each read at its source. 11 are fixed (1a111b5):
  - each print's own program names;
  - known offline failures apart from tool failures (RGA not running fails the verb);
  - a duplicate stage refused;
  - each run's folder emptied;
  - every stage lacking a figure named;
  - compute stages listed;
  - an ok record required;
  - run_l2 tested.
- The twelfth, the version check accepting any 2.15.x, is fixed in the close-out (357dc1f).

## Choices
Neither the prompt nor the plan names these:
- One dump run carries both exit items (head, off, change: 11 reloads), so the phase took its 2 launches.
- Each dimension's dump is taken at the views file's first view there.
- Before each reload the run empties patched_shaders/ and game/'s two properties files, so no file is stale; Iris's own clear spares *.properties. The old Unbound print from 2026-10-07 went at the first print.
- The flag is on from the start-of-run reload (measure.TRANSFORM_CACHE). D60 names each dump's reload; the plan is not edited.
- `dumps` holds each manifest's files once (2 of 9 here; 9 distinct would near the 200 KB budget).
- The audit's uniform -> reader (D69's audit, shader.md#pipeline-spec):
  - Its list comes from the pinned jar with javap (scratchpad uniform_scan.py, not committed): the String constant each of UniformHolder's 16 registering calls receives (174 names), MatrixUniforms' 8 recipes over ModelView and Projection (13), ExternallyManagedUniforms' helpers' names.
  - It reads the uniforms the pack's own GLSL declares, as its prints still read them: Iris's own programs (the shadow_* keys) read Iris-internal names (AlphaTestValue, FogDensity, FogIsExp2) that are not the pack's.
  - Samplers and images are left to the buffer pairs and Iris's sampler binding.
- The exit's change lived only in the working tree and is reverted; both records say dirty true and name it in `notes`.

## Checks
- Start (17:44 ADT): branch m3 clean at ac45c84; 977 passed; verify docs 0 violations.
- Before each commit, on a tree equal to it: 986, 1002, 1006, 1007, 1012, 1012, then 1014 and 1016 passed; ruff, ruff format and pyright clean; verify docs 0 violations; verify records 0 violations (233 records at the end).
- CI green on b4f4165, fe0f6fd, 04ca9ce, 1a111b5, 34ebd37, 2a0f3cb, 9dfad33, 357dc1f and d322d67, each watched to its end before the next push.

## Open questions
- `screen = BENCH_DETERMINISTIC` reads `screen = 1` with the option on (Outcome): a pack fix, such as an option list that names no macro. Whose phase is the user's call; it changes no frame.
- Settled in the close-out:
  - RGA 2.15 names its geometry and tessellation outputs geom, tesc and tese (a vert-geom-frag and a vert-tesc-tese-frag program of Claude's own, built 2026-10-22; a needs_rga test keeps the geom case).
  - Iris.setDebug is called by duringRenderSystemInit, and IrisConfig.load() calls no Iris method (javap), so a reload under the flag never makes the KHR debug context (P13, D60).
- Carried:
  - the beacon beam and clouds across launches (P22), for M3.P09's diagnosis;
  - the moving coverage items (D64);
  - Unbound's missing coverage-mob shadows;
  - the hello pack's olive End stone; whether 26.3 animates textures on frozen ticks;
  - the display guard for A9; Nether fog and the features on neither list; the water fog colour (M3.P09);
  - D66, the driver; D72; spider eyes and the world's difficulty (M4);
  - M2's carried list (git 7dfc2fa's handoff).

## Weak points
- The premise check reads GLSL by tokens, not with a parser; it closes only under its guards, and on m3-dump-1 nothing closed by it.
- The fake prints sources verbatim. Real prints were read once, in m3-dump-1.
- M3.P07's unnamed flaky test: 12 full runs this session, all passed.
- IRIS_UNIFORMS is a superset in one way: a name registered under a condition (a DH or a feature flag) counts as defined everywhere.
- Margins: run-record.md 32 bytes; measurement.md 20; platform.md 7; AGENTS.md 16; mod.md 62; workflow.md 199.

## Commits and time
- b4f4165, fe0f6fd, 04ca9ce, 1a111b5, 34ebd37, 2a0f3cb, 9dfad33 (the first handoff); 357dc1f and d322d67; then this handoff.
- 2026-10-22, 17:44-19:00 ADT, then the close-out after 19:05 to 19:32: at most about 1.8 h against 3 h. Tripwire: actuals about 59.7 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1, P07 2.1, P08 1.8); the trip at 174.6 h.

## Next
/optilux-next prints M3.P09's prompt: A5 and the determinism exit, 2.5 h, 4 launches.
