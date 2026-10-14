# Handoff
Status: the latest stop: M2.P08 stopped after its survey: D47 keeps the warm-up pass (entities -1.50 %, rain +0.60 %), the prompt's stop (step 6), and the passthrough gave no floor, only upper bounds; decisions for the user (Open questions). The display request and the survey's records are committed.

## Contents
Outcome · What changed · Checks · Review · The survey · The stop · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P07
- M2.P08's Exit does not hold: the survey record m2-survey-1 is ok, every baseline capture valid and GPU-bound (44 of 44, the lowest 0.9973 of FrameTime); no floor written (none measured, below); no D47 change in suite.json; no acceptance run (step 6 stops before step 7). Steps 1-4 were done in 12079c5.
- The user's answer to the last handoff (2026-10-14): a measured run holds the displays on through a power request (built, f402c8c). m2-survey-1's four launches ran unattended under it, 04:09-04:23 ADT, every window with its rows, the displays read on; but the user's last input came about 04:13:40, so part 4's last window ended about 599 s after it (D42's 486.6 s plus its 112 s after the check): the request's effect past the 600 s timeout is not yet shown.

## What changed
- f402c8c: measure.displays_on: `run` on a measured spec, and `calibrate` once over all its sessions, takes SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED) before its first step and releases it at the end whatever happened; refused when the displays read off or unread (GUID_CONSOLE_DISPLAY_STATE through PowerSettingRegisterNotification, which reports the state at once: read live, 1 = on), a failed call refused as such (RecordError, never the file-lock fix); the record's session.displays holds the request, the state, the AC display timeout (600 s, PowerReadACValueIndex, only read) and the input's seconds. measurement.md#session step 2, run-record.md's `session`, CHANGELOG.md with it.
- Choice no plan or prompt names, taken here: the refusal reads the displays' state, not idle input against the timeout as the question put it: the request holds the displays' own idle timer, so the input-only test refused a measured process after another (calibrate full after quick, M2.P10's sessions) with the displays on (the review's finding 1).

## Checks
- At the start (22:46 ADT): branch m2 clean at 4e00289, 779 passed, verify docs 0 violations.
- f402c8c: 786 passed (7 added: the hold and release, read order, off, unread, dimmed, failed calls, one hold over a split session and over calibrate's sessions, none for an acceptance run, the real calls on Windows); ruff, ruff format, pyright clean; verify docs 0 violations; CI green (run 38526478779).
- This commit: verify records 22 records, 0 violations (the two over 200 KB are M1's acceptance records, reported).

## Review
- The reviewer agent on the display change (correctness): 7 findings, each read at its source. Fixed before f402c8c, each with a test or a doc line: (1) idle input against the timeout refuses back-to-back measured processes (now the displays' state); (2) a failed power call reached `run` as an OSError with the file-lock fix, a failed release could fail a written record; (3) no test of the read order; (4) calibrate's no-hold branch untested; (5) no test of the real calls; (6) measurement.md placed the hold after D42, the code before step 1; (7) execution_state's docstring said the process holds the request (the thread does).

## The survey
m2-survey-1 (full mode, R 1, calibration null; parts m2-survey-1-p1c, -p2, -p3, -p4, each ok, 18, 18, 18 and 12 captures; snapshot 65e7ae73..., 116 files; heap 6144 MiB, cap 20). Per view: the baseline's median GPUBusy and GPUBusy over FrameTime (median, lowest), GPULatency; the passthrough's FrameTime and validity; D47's delta (warm-up against the measured pass's first baseline) and the measured baselines' spread:

| View | GPUBusy ms | ratio (lowest) | GPULatency ms | passthrough | D47 delta % (spread) |
|---|---|---|---|---|---|
| forest_noon | 7.832 | 0.9991 (0.9987) | 8.148 | 0.5375 ms, valid, GPU-bound | +0.28 (0.06) |
| ocean_sunset | 7.051 | 0.9995 (0.9985) | 7.321 | cut: 522 rows short | +0.41 (0.27) |
| cave | 5.186 | 0.9995 (0.9993) | 5.457 | cut: 274 short | +0.13 (0.18) |
| night | 5.284 | 0.9995 (0.9990) | 5.845 | cut: 1,259 short | -0.11 (0.19) |
| underwater | 7.072 | 0.9996 (0.9992) | 7.322 | cut: 993 short | -0.04 (0.22) |
| entities | 5.187 | 0.9997 (0.9991) | 5.705 | cut: 556 short | -1.50 (0.35) |
| rain | 7.199 | 0.9991 (0.9981) | 7.451 | 0.9329 ms, valid, GPU-bound | +0.60 (0.40), settles 1.5/4.0 s |
| nether_crimson | 5.671 | 0.9996 (0.9995) | 6.061 | cut: 562 short | +0.04 (0.08) |
| nether_soul | 6.245 | 0.9998 (0.9992) | 6.493 | cut: 197 short, halves | +0.05 (0.16) |
| end_dragon | 7.780 | 0.9988 (0.9979) | 8.226 | 0.6578 ms, valid, GPU-bound | -0.03 (0.34), settles 4.0/1.5 s |
| end_city | 7.792 | 0.9987 (0.9973) | 8.249 | cut: 12 short | -0.14 (0.39) |

- The floors (stats.cpu_floors): none. The passthrough ran at 1,440-2,060 fps, GPUBusy over FrameTime 0.96-1.04 and GPULatency 1.26-1.76 frames on all 11 captures: GPU-bound, so its FrameTime bounds the floor from above (forest_noon 0.54 ms, rain 0.93, end_dragon 0.66); on the other 8 PresentMon wrote 12 to 1,259 rows fewer than the mod's frames, so the cut failed. Every other capture's rows equal its frames within the edge's one row.
- The baseline's GPULatency reads 1.03-1.11 frames (ALC: about 2.7).
- D47 (stats.warmup_agreement, within 0.5 %): drop false: entities -1.50 % beyond its measured spread (0.35 %), rain +0.60 % on a pair of different settles (its warm-up after the start, its measured capture after the Nether); the other nine within 0.41 %.

## The stop
- Prompt step 6: D47 keeping the warm-up pass is the user's; the floors are a Done-when not met. Not done: suite.json's D47 change, measurement.md's floors and warm-up, CHANGELOG's views and floors, the acceptance run (A2, A3, A10).
- Nothing else launched; no system setting touched (the power calls only read, and the request is the run's own, released).

## Open questions
- The user's, now: D47. Recommended: a second survey session (m2-survey-2, about 15 min) before deciding, entities' -1.50 % against one capture per view; if it repeats, keep the pass and full mode's launches hold one view each (2 + 1 + 9 = 12 reloads with 2 candidates at R 2; D43's 2-view launch needs 22, over the cap 20), 11 launches a full session against 6, full mode's calibration hours nearly twice; else drop it in suite.json. Dropping now leaves a first visit 1.5 % off at entities inside the first bracket (half of it in that candidate's ratio), above the 0.5 % threshold floor.
- The user's, now: the floor. Recommended: measurement.md#validity states it bounded from above by the survey (at most 0.54-0.93 ms on the three valid views, every passthrough GPU-bound), the 90 % rule out of reach until a frame nears 1 ms; ALC's alcUpperBound superseded. Else a floor read below 4K or with vanilla (identity changes), or PresentMon at 2,000 fps (its row loss unexplained).
- Carried: measurement.md step 4's default against D47's; plans/m2.md section 7 lacks the stop on D47 keeping the pass; nxplayer.bin (NoMachine's player) at 3.7-6.2 % of the 3D engine while the user was at the machine held D42 for about 4 min, under 2 % in its last checks; orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- results/raw/m2-survey-1-p1c/, -p2/, -p3/, -p4/ (ignored); m2-survey-1-p1 and -p1b (failed, committed before).
- The acceptance spec (scratchpad): m2-acceptance-1, kind acceptance, views and world bench_263, the reference pack with profile null, tier bench, resourcePacks standard, items A2, A3 and A10; `run --check` held.
- measurement.md: 56 bytes left; its floors and warm-up wait for the answers.

## Weak points
- D47 rests on one warm-up capture per view; the floors' bounds on three captures.
- The display state's off path has met the fakes only; the on path was read live; the hold past the timeout is unshown (the survey ended about 599 s after the last input): the next unattended measured run past 600 s shows it, or fails at its first window as m2-survey-1-p1 did.

## Commits and time
- f402c8c feat: hold the displays on through a measured session; this handoff with the survey's five records.
- M2.P08 this session: 22:46 to about 22:58 ADT, then 03:49 to about 04:40 ADT after the user's answer (about 4.9 h waiting), about 1.0 h active; the phase about 1.7 h against 1.5 h, stopped.
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 39.6 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4, the re-plan 0.35, P07 2.1 active, P08 1.7 so far).

## Next
The user's answers on D47 and the floor; then M2.P08's prompt again from step 5's outcome (a second survey if chosen), then step 7's acceptance run.
