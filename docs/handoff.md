# Handoff
Status: the latest stop: M4.P02 check L3 and L0's determinism rule done on branch m4, committed and pushed: the pack's functions and custom uniforms tested before any launch, and L0 refusing a moving read under BENCH_DETERMINISTIC. M4.P03 is next.

## Contents
Outcome · What was built · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P02
- The Exit of M4.P02 (docs/plans/m4.md) held in one session (2026-10-27, ADT), each item shown:
  - `uv run optilux check L3` on shader/: "pass: 2 of 5 includes tested, 14 functions over 29,578 cases, 0 uniform tests over 0 cases", exit 0, on "AMD Radeon RX 7800 XT, 3.3.0 Core Profile Context 26.8.1.260810";
  - on a broken copy (fog.glsl's `abs(fromCamera.y)` made `fromCamera.y`, in the scratchpad): exit 1, "FAIL shaders/lib/fog.glsl: fogDistances(fromCamera (-335.51904, -866.62384, -561.1632)) = (1085.5939, 653.8174), golden (1085.5939, 866.62384), off by 212.80646 ...", 542 of 4094 cases;
  - `check L0` on a copy of the hello pack whose shared fragment stage reads frameTimeCounter under `#ifdef BENCH_DETERMINISTIC`: exit 1, "7 refusals", each "FAIL gbuffers_<program>, its fragment stage ... (determinism), at BENCH_DETERMINISTIC true" with "shaders/lib/surface_fragment.glsl:50: reads frameTimeCounter, seconds on the wall clock (SystemTimeUniforms), under BENCH_DETERMINISTIC"; the define-off variant not refused;
  - the hello pack passes L0 with the rule ("1 of 2 variants under BENCH_DETERMINISTIC ...: 0 refusals").

## What was built
- optilux/l3.py and `check L3 [<pack>]`: per include under shaders/lib/ its test file tests/l3/<path>.py (Python, a TESTS list of l3.Function), each function compiled by moderngl after the include expanded as L0 expands it at the test's options under Iris's macros, called once per case from an RGBA32F case texture into an RGBA32F target, held to its numpy golden; a failure names the include, the function, the input and the options, a compile error the include's line (offline.md#levels, L3 as built).
- Custom uniforms: tests/l3/uniforms.py's l3.Uniform entries; shaders.properties read as Iris's PropertiesPreprocessor reads it (javap: JCPP over the 8 conditional and define commands of its 15, other lines verbatim, then Properties), each uniform evaluated by M4.P01's runner after the definitions it reads (ordered by reference, as the last handoff left to this phase), its GLSL on the GPU with the same inputs; every uniform at the defaults needs a test. The hello pack defines none, so only the fixtures exercise it.
- L0's determinism rule (D79), in offline.py: each stage after glslang -E and each custom definition at every variant with BENCH_DETERMINISTIC on.
- First goldens: tests/l3/lib/fog.py (fogDistances, fogRamp, withFog at far 32, 256 and 1024, both define states) and tests/l3/lib/light.py (restingBlockLight over 0-240 and between, surfaceLight on a synthetic lightmap). Worst differences: 6e-08 to 1.2e-07 on the ramp and the fog, 2.4e-07 and 3.0e-07 on the light curves (values up to 1.4), 1.2e-04 on fog distances near 2,000 (6e-08 relative).

## Checks
- Start (13:02 ADT): branch m4 clean at ed5bb7f; 1030 passed; verify docs 0 violations.
- Before each commit: `optilux test` 1040, 1050, then 1068 passed; ruff and pyright clean; verify docs 0 violations; `check L0` pass; every new file LF without BOM.
- CI green on 9f99435 (1025 passed, 15 skipped: test_l3's GL tests skip there, "....ssssss") 4023f02 (1033 passed, 17 skipped) and 079908d (1050 passed, 18 skipped), each watched to its end before the next push; this commit's watched the same way.
- run's module closure: 18 modules, each equal to the 4edbb05a calibrations' (P4); l3.py, offline.py and check.py lie outside it.

## Deferred and logged
- Logged (no prompt names it): L3's test files live in tests/l3/, mirroring shaders/ paths, not in shader/: `pack build` zips all of shader/, and packzip.py is in run's closure (P4), so they stay out of the release zip without touching it.
- Logged: the rule refuses more than P18's names, as D79's "wall-clock and smoothed ones": fogStart and fogEnd (eased by the wall clock: shader.md#determinism-and-taa), randomInt() beside random(), and Iris's 16 hard-coded uniforms on a SmoothedFloat (HardcodedCustomUniforms, read with javap today: rainStrengthS, rainStrengthShiningStars, rainStrengthS2, rainFactor, isDry, isRainy, isSnowy, isEyeInCave, starter, frameTimeSmooth, eyeBrightnessM, isPrecipitationRain, touchmybody, sneakSmooth, burningSmooth, effectStrength). velocity (a camera tracker, no SmoothedFloat) is not refused; whether it divides by frame time is unread.
- Logged: the frameCounter part is per line: on a line that reads frameCounter every %, & and mod() divisor must be a literal dividing 720720 (a non-literal refused as unverifiable); a read without a modulus (`frameCounter < 2`, the history-valid uniform's first frames) passes. A read is static, after -E: an uncalled function's read is refused too.
- L3's first run found lib/light.glsl testing BENCH_DETERMINISTIC without including options.glsl (it saw the define only through its includer); it now includes it, guarded, so the programs compile as before (L0 pass, verify similarity 0 matches).
- AGENTS.md (17 bytes free) names l1.py-l3.py and tests/l3/ but still not expressions.py or IrisExpressions.java; workflow.md#testing (74 bytes free) does not list L3's tests: both for M4.P12's docs as built.
- install.py's docstring: still M4.P03's (P4), as the last handoff says.

## Open questions
- The plan's open premises, each decided in its phase: P22's extension list and P23's RGBA16UI readback and renderStage (M4.P06), F12 through SendInput (M4.P04).
- Pinning gamma, Smooth Lighting and See-Through Leaves (research/lighting.md#open-questions): the user's.
- M5's split (research/synthesis.md#milestones): M5's plan.
- Carried from M3's handoff (git 78ea8b3): the one test that failed once in parallel, unnamed; the quick twin's +0.1782 % under the twin monitor; the available memory at the budget run; the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; M2's carried list (git 7dfc2fa's handoff). The help strings and the docstring go in M4.P03.

## Weak points
- The properties model is javap-read, not yet held to a print: the first dump run of a pack with custom uniforms (M4.P06 on) can compare offline.customs with its preprocessed.properties.
- The custom-uniform check has run only on fixtures (the hello pack has none); M4.P06's pack is its first real use.
- Tolerances rest on GLSL's stated precision (division 2.5 ulp, inversesqrt 2 ulp), not on AMD's documented one; the largest hello-pack difference, 3.0e-07 (surfaceLight), sat well inside its 1e-06 relative tolerance.

## Commits and time
- 9f99435 (check L3, the fog and light goldens, light.glsl's include, its docs), 4023f02 (the custom-uniform check and the properties reader), 079908d (L0's determinism rule), then this handoff.
- M4.P02: about 0.7 h against 3 h (13:02 to about 13:45 ADT); machine: none, no launch.
- Tripwire: actuals about 69.3 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 5.1: P00 3.8, P01 0.6, P02 0.7) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P03 Measured runs of the Optilux pack (docs/prompts/m4.md), in a fresh session.
