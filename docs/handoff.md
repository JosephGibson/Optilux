# Handoff
Status: the latest stop: M3 closed and released as v0.4.0, then on branch m4 the shader research before M4's plan (roadmap.md#decisions D73, D74), committed and pushed. M4.P00 is next.

## Contents
Outcome · The milestone · Review · Choices · Checks · Open questions · Weak points · Commits and time · Research step · Next

## Outcome
Last phase: M3.P11
- The exit holds, shown in this session (2026-10-24, ADT): `uv run optilux status` prints the Release prompt (run after this file's commit).
- The docs as built: design.md (Status; install, run, world prep, compare / report and pack rows), shader.md, offline.md, measurement.md (session step 9 per D67: the define's cost row from M4's pack, none in 0.4.0), mod.md, run-record.md, workflow.md (Testing), platform.md (the bench tier's two resource packs) and AGENTS.md's layout (seven modules added, `pipeline` no longer planned). Errors found against the code: run-record.md gave acceptance runs "the standard set" (record.check_spec refuses all but record.PACK_SET); measurement.md named PSNR, which visual.py never computes, and put 1,440 fps on the five cut views (m2-survey-1, -2: their cut passthrough captures 1,849-2,061 fps; 1,440 was end_city's, a view with a valid one).
- Cut first where near the cap; margins after, against before: measurement.md 63 (65), platform.md 18 (7), mod.md 30 (15), AGENTS.md 41 (16), run-record.md 101 (9), workflow.md 74 (199).
- CHANGELOG.md's 0.4.0 entry: `report` on a visual run; no BENCH_DETERMINISTIC cost in 0.4.0 (D67). roadmap.md#findings-assigned: F17 and F18 landed in M3.P05 (m3-capture-2: A9 in 1.515 s for 120 frames), F26 in M3.P09 (the twin first), F27 in M3.P10 (driver 32.0.31041.1004; m3-diag-alone-1 580.3 MiB of GPU memory a reload, the cap 20), F25 in M3.P11 with its row in M4; each read in its phase's handoff (7e4536b, de68869, 33a09d0) and its record.
- `check L0` on the hello pack, run here: 48 builds, 16 compiled, 48 glslang runs in 0.31 s, similarity 0 matches, both profiles ok; pass.

## The milestone
- Passed, against plans/m3.md section 1: `verify similarity`, `check L0|L1|L2`, `run`'s visual and dump kinds, `compare`'s tiers and review.html; the hook on staged shader changes; the hello pack with BENCH_DETERMINISTIC and pipeline.json v0 through `check L0` and `verify similarity`; iso v1 through L0's profile check; the static-textures pack in the deterministic set; the coverage views and the snapshot; two visual sessions identical on the 11 perf views (m3-determinism-2, -3); quick and full calibrations on the deterministic set, each mode's twin inside and shadows off beyond. Left for the Release prompt: CI on the PR, the user's rebase merge, release v0.4.0.
- Failed and kept: A5, 17 of 33 waits (m3-a5-1, -2), so the visual settle stays the floor (D68), lengthened to 4 s (5 s underwater, +3 s after a dimension change). Deferred: D67's cost row (M4), the uniform-work scan (D70, M4).
- Records (ok unless named): m3-hello-1; m3-capture-1 (failed: displays off), -2; m3-visual-1 (failed: its option files did not read back), -2; m3-coverage-1 to -3; m3-dump-1; m3-closure-1; m3-a5-1, -2 (A5's miss); m3-determinism-1 to -3; m3-diag-alone-1 (a budget run, stopped by F4's guard); cal-quick-4edbb05a97ab-1 to -10; cal-full-4edbb05a97ab-1 to -11 in parts (-1 passed over); m3-shadows-quick-1; m3-shadows-full-1.
- Pins: glslang 16.6.0 (sha256 82bf434e...), RGA 2.15 (1dd6fc63..., prints 2.15.0.30); similarity k 20, t 72, controls Unbound 129 of 129 flagged, Wisdom Shaders Build3300's longest run 71; optilux-static-textures.zip sha512 ff44b3cc...; the hello pack's zip sha512 d86371b78b24...; the coverage site near (314, 1069), a floor at y 100 over x 306..322, z 1061..1077; snapshots/bench_263 tree sha256 33a4074d... (128 files).
- Calibrations: quick-4edbb05a... and full-4edbb05a... (identity 4edbb05a97ab879a7dae07e42c003a8067817e310897f608a8121d4976b51d40), every threshold the 0.5 % floor; shadows off -10.7570 % quick, -12.2216 % full; twins +0.1782, -0.0130 %.

## Review
Two reviewer agents on the changed docs, against the code and the records (set A: AGENTS.md, design, shader, offline, measurement, mod; set B: run-record, workflow, platform, roadmap's findings, CHANGELOG): 12 findings, 2 medium and 10 low, each read at its source; 11 fixed, 1 left.
- Medium, fixed: measurement.md step 7's cut moved "R 2" onto quick mode, whose rounds are 1 (suite.json modes.quick); run-record.md's new Status said every "As built" names its phase, five did not, and the cut dropped M2.P04 and 0.01.08-0.01.13: the phase list is back.
- Low, fixed: acceptance.py holds M1's items only; step 9's "captures cut" now says on five views; the 1,440 fps (above), in measurement.md, CHANGELOG and F25; offline.md's Status claimed all of L2 (the uniform-work scan waits for M4) and called L5 spec (it runs in a dev session); PSNR; dump records carry L1 closures (`offline`), not `verdicts`; the static-textures pack is built by `install`, not pinned in the platform file; the passthrough bounded the CPU's share, never measured it.
- Left: the 0.3.0 entry's "1,000 to 2,000 frames a second" against 0.4.0's 2,060: released text, rounded (the survey's fastest 2,061). D67 (plans/m3.md, closed) keeps "five views at 1,440-2,060 fps"; reported, not edited.

## Choices
Neither the prompt nor the plan names these:
- Docs-only: the stale help strings (`check`, optilux/verbs/check.py: L0 only; `run`, optilux/verbs/run.py: acceptance or measured only) and record.check_spec's docstring ("the standard resource-pack set") left as code; run.py and record.py are in `harness`, so their fix waits for a change that recalibrates anyway.
- M3's actuals count M3.P00, as M2's close counted M2.P00; the world-prep launches' minutes (no record) estimated from their raw folders.

## Checks
- Start (2026-10-24, 20:48 ADT): branch m3 clean at 33a09d0; 1024 passed; verify docs 0 violations.
- Before the commits, on the working tree (the code unchanged since 33a09d0): ruff, ruff format and pyright clean; verify docs 0 violations; verify records 0 violations (394 records). Tests: one parallel run gave 1 failed, 1023 passed, its name not captured; five runs since passed 1024 (`optilux test`, three `pytest -n auto`, `optilux test --serial`).
- CI green on 950ede9 and 7f4b2a6, each watched to its end before the next push.

## Open questions
- The one test that failed once in parallel (above): unnamed; a timing-sensitive test, as no code changed.
- The help strings and the docstring (Choices), for the next change to run.py or record.py.
- The quick twin's +0.1782 % lies inside the 0.5 % floor but above every quick null's geo-mean (largest 0.12 %); the twin monitor (0 of 1 beyond) watches it.
- Carried from M3.P10 and M3.P09 (git 33a09d0's and de68869's handoffs): the available memory at the budget run; the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the beacon beam and clouds; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; D72 (M4's plan); spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- The review read the changed lines and their sections; gpu-iris.md, mod-protocol.md, lessons.md and playbook.md were outside the prompt's list and unread here.
- Margins stay thin: platform.md 18 bytes, mod.md 30, AGENTS.md 41, measurement.md 63.

## Commits and time
- 950ede9 (the docs), 7f4b2a6 (CHANGELOG and the findings); then this handoff.
- M3.P11: about 1.0 h against 1 h (2026-10-24 20:48 to about 21:06, the session's restart between, then 23:07 to about 23:50 ADT); machine none.
- M3: about 19.3 h against 25 h (P00 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1, P07 2.1, P08 1.8, P09 1.4, P10 2.1, P11 1.0; 17.3 h without P00). Machine apart: 162 launches against about 146, about 5.2 h: 159 recorded (300.7 min: P03 1, P05 2, P06 2, P07 3, P08 2, P09 5, P10 144) and P07's 3 world-prep launches (about 9 min).
- Tripwire: actuals about 64.2 h (M0 3.3, M1 20.3, M2 about 21.3, M3 about 19.3) against M0-M3's 87.3 h; the trip at 174.6 h.

## Research step
Outside the phase numbering, 2026-10-26, on m4 (D73), before M4.P00; no launch, machine none.
- docs/research/: 13 topic docs and synthesis.md, each topic by a read-only researcher and an adversarial verifier (27 agents, 932 claims confirmed at their sources, 290 corrected, 14 removed, 31 left [unverified]); a targeted pass (9 agents): programs.md (the coverage programs no topic held, the base cost), next-gen.md's other not-yet items, the topic docs aligned with the synthesis; then gpt-6.1-sol critiques of synthesis, lighting, taa and iris: 16 findings, 15 folded in, the NoAI one reworded (the entities view was identical across launches, m3-determinism-2, -3).
- What the critiques changed: the overlay split into mod, emit and trans, their depth writes premise 17; TAA resolves in HDR before bloom and the tonemap (D74), post-tonemap the option; the budget a per-view ledger whose upper ends pass Unbound at entities, night and cave, a target, not a prediction; Iris's fixed costs 0.4-1.1 ms; a periodic flush makes the cycle its period; the Slang mul() rule.
- D74 (user): Unbound a springboard, not a template.
- For M4.P00: VERSION 0.5.0 and `## 0.5.0 Shader base` are in (16b9033: the hook refuses any m4 commit without them), so step 2 is left with M3's roadmap line and step 7's first commit is taken; the goal paragraph may be rewritten from the approved plan. Read synthesis.md first: Premises for M4's plan (17), D72 input with nine look questions, Milestones (an M5 split proposed).
- Weak points: every Iris fact [verify in jar]; costs [inferred], about 2x; synthesis.md's margin 110 bytes.
- Commits: 16b9033 (the version, and by mistake D73 and the Plan prompt's reading list, left staged by a refused commit: pushed, no force push), 3d7f8b4, 1dad62c (CI's first attempt failed on test_logman_lists_sessions_on_this_machine, `logman query -ets` exiting 2147946600 on the runner; the rerun passed), 21ba028, cee6cef, then this handoff; each pushed after the last one's CI ended green.

## Next
/optilux-next prints M4.P00 Plan M4 (docs/prompts/standing.md#plan), which now reads docs/research/; Fable 5.1 xHigh suggested, in a fresh session.
