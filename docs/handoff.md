# Handoff
Status: the latest stop: M2.P10 done: A8 passed (m2-a8-2), A11 failed at underwater (m2-a11-1), so the helper's per-pass timers are dropped from use (D53), the jar kept as calibrated; E3 reopens in M4 with Viewfinder. Next: M2.P11.

## Contents
Outcome · A8 · A11 · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P10
- Exit holds: m2-a8-1, m2-a8-2 and m2-a11-1 are acceptance records holding A8 and A11 with their evidence, judged by full-95d96878...; E3's outcome is in design.md#8-open-decisions.
- `run --check` before the first session: m2-a8-1's and m2-a11-1's identities hash to 95d9687847308453839250cc292ce01bde79b39bc4f4103eac593f5155a5463e, the full calibration's, 0 keys differing; no measured module changed (D36).
- No section 7 stop: 154 timer captures, 0 frames missing, 0 dropped (late, full, overflow, lost), every pass list with its stages (the shadow passes and shadowcomp but in shadows off, the gbuffers phases, deferred, composite, final); no launch invalid on focus; D42 never refused.
- A choice no plan names, taken here: m2-a8-1's A8 waits on forest_noon unjudged, not on a view beyond, which `remeasures` does not cover (check_remeasures refuses it); a fresh first session, m2-a8-2, was run, its outcome final, m2-a8-1 kept as evidence. So 3 sessions, not 2.

## A8
The baseline with timers off against itself with them on, beside the twin (timers off); thresholds all 0.5 % (the floor).

| Run | Twin | Geo-mean | Per view | A8 |
|---|---|---|---|---|
| m2-a8-1 | unjudged | unjudged | forest_noon unjudged (all 10 captures Composed: Flip); the other ten +0.03 (nether_crimson) to +0.46 % (underwater) | waits |
| m2-a8-2 | -0.0018 %, inside | +0.1821 % | forest_noon +0.26, ocean_sunset +0.18, cave +0.05, night +0.14, underwater +0.27, entities +0.29, rain +0.33, nether_crimson +0.18, nether_soul +0.11, end_dragon +0.22, end_city -0.04; none beyond | pass |

- The timers' own cost: 20 of the 21 judged views read positive, about +0.2 % (up to +0.03 ms), inside the floor: a steady cost, not noise, too small for A8's rule.
- m2-a8-1-p1 (11:58 ADT): every row Composed: Flip. Input at the machine from before the run until about 12:10 (D42 waited 237 s before p1, 612 s before p2); NoMachine's player and tray monitor (nxplayer.bin, nxrunner.bin) were running and pid 2228 read 0.27-0.79 % of the 3D engine in both waits; all three gone by 12:30; nxservice stopped throughout (no one could connect in). D42 passed p1 all the same: it reads neither an overlay nor the composition.

## A11
Every variant timed: the baseline, its twin, shadows off (SHADOW_QUALITY -1). Per view the threshold in ms (0.5 % of the baseline's median GPUBusy); the residual's move against the baseline's; shadows off's delta from the timers against GPUBusy's, bracketed, in ms.

| View | Limit | Residual: shadows off, twin | Shadows off: timers, GPUBusy, apart |
|---|---|---|---|
| forest_noon | 0.0393 | +0.0055, -0.0005 | -1.2959, -1.2916, -0.0044 |
| ocean_sunset | 0.0355 | -0.0044, +0.0019 | -0.9108, -0.9144, +0.0036 |
| cave | 0.0260 | +0.0132, -0.0011 | -0.6319, -0.6182, -0.0137 |
| night | 0.0266 | +0.0145, -0.0025 | -0.6185, -0.6058, -0.0127 |
| underwater | 0.0359 | -0.0484, +0.0007 | -1.7546, -1.8055, +0.0509 |
| entities | 0.0261 | -0.0135, +0.0009 | -0.5514, -0.5635, +0.0121 |
| rain | 0.0363 | +0.0034, +0.0030 | -1.0912, -1.0914, +0.0002 |
| nether_crimson | 0.0285 | +0.0004, 0.0000 | -0.0345, -0.0337, -0.0008 |
| nether_soul | 0.0313 | -0.0003, +0.0006 | -0.0068, -0.0066, -0.0002 |
| end_dragon | 0.0390 | +0.0028, +0.0010 | -1.1225, -1.1167, -0.0058 |
| end_city | 0.0391 | +0.0095, -0.0015 | -1.1448, -1.1325, -0.0123 |

- Fail at underwater only, systematic: the baseline's residual 0.528-0.531 ms in all five measured captures, shadows off's 0.4812 and 0.4813 in both rounds; shadows off removes 0.048 ms of GPU work no timed group holds.
- The session: twin -0.0246 % (inside), shadows off -12.3450 % accept with every variant timed (m2-shadows-full-1: -12.3303 %); the known positive shows at ten views (all but nether_soul).
- Re-derived here with compare's steps (record.session_captures, stats.judge_items): the same entry as the record's.

## What changed
- 0083015: the 36 records (three sessions, 11 parts each); design.md#8-open-decisions E3's outcome and E5; mod.md#12-acceptance A8 and A11 as found, section 14's answered timers line cut; measurement.md's timer rows "none yet" (cut: pyproject.toml's two deps, suite.json's exclusiveFullscreen history); CHANGELOG.md's timers verdict.
- No code changed. Reports: results/raw/m2-a8-1, m2-a8-2, m2-a11-1/report.html (ignored).
- A scratch process held the displays on from 11:54:53 to 13:12:44 (the same request `run` holds, no setting changed), over the gaps between the three commands.

## Checks
- Start (11:46 ADT): branch m2 clean at 16be571, pushed; 790 passed; verify docs 0 violations.
- Before the commit: 790 passed (the 10 A8 and A11 verdict tests of tests/test_stats.py among them); ruff, ruff format and pyright clean; verify docs 32 files, 0 violations (measurement.md 21 bytes left, mod.md 52); verify records 220 records, 0 violations (the three acceptance records over 200 KB, reported).
- CI green on 0083015 (run 38930536945).
- `compare m2-a8-2`: A8 pass, twin -0.0018 %; `compare m2-a8-1`: A8 waits; `compare m2-a11-1` refused (Open questions).

## Review
The reviewer agent on both specs, before any launch (correctness against plans/m2.md M2.P10): specs clean; 3 low findings, each read at its source, none fixable here (stats.py and record.py are measured modules, D36):
- (1) a8_verdict re-judges the geo-mean in a second session, before reading `first`; stricter than one reading of the plan, never looser; untested branch. Reported.
- (2) check_remeasures does not refuse a second re-measure of one first session: nothing stops redrawing until a pass. Reported; here no re-measure ran.
- (3) A11's twin runs timers on, judged against timers-off nulls, and a session whose item failed leaves the twin monitor (judged_twin reads ok records only): m2-a11-1's twin is not counted. Reported; the monitor reads 0 of 2 (m2-shadows-full-1, m2-a8-2).

## Open questions
- Underwater's untimed work: which GPU work shadows off removes outside Iris's GLDebug groups (a shadow clear, copy or mipmap outside them?); Viewfinder hooks the same groups (P19), so it is M4's first E3 question.
- A11 has no guard for 11 views against one threshold each, which A8's second session has; here the failure is systematic, but M4's A11 may want one.
- `compare` refuses an A8 or A11 record whose item failed: run.py records a failed item as a problem, status failed, and compare judges ok records only. compare.py is outside the harness hash, so a fix needs no recalibration; the user's call.
- m2-a8-1-p1's composition: NoMachine's player, pid 2228 or the input; D42 cannot see it. Ask for no NoMachine window during runs (memory: remote viewer).
- forest_noon's baseline reads 7.85 ms today, the lower GPU level of M2.P09's Review 2; quick's thresholds rest on the higher one.
- Timer unmatched pops: about 2,200 a timers-on capture since its timers.start (underwater), counted as mod-protocol.md#commands says; cause unread.
- Carried from M2.P09: the level drop's cause, the quick slot bias, the reload leak and the driver test (git 16be571's handoff), and M2.P08's list.

## Left alone
- The timers in the jar (D53: kept as calibrated, unused); measurement.md (21 bytes) and mod.md (52) need a cut before they grow.

## Weak points
- A11 rests on one session; its failure is one view of eleven, reproducible within it, not across sessions.
- A8 judged on one complete session (m2-a8-2); m2-a8-1's ten views agree with it.

## Commits and time
- 0083015 and this one.
- M2.P10: about 1.6 h against 1 h (11:46-13:22 ADT), the machine inside it about 1.25 h against 1.2 h: 33 launches (m2-a8-1 34.9 min, 15.4 of it D42's waits; m2-a8-2 20.0; m2-a11-1 20.2).
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 43.6 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4, the re-plan 0.35, P07 2.1 active, P08 3.0, P09 1.1, P10 1.6).

## Next
M2.P11's prompt from docs/prompts/m2.md (optilux-bench and the close): the skill by workflow.md#skills, three evals, CHANGELOG's 0.3.0 entry completed, the findings marked landed; 1-2 launches.
