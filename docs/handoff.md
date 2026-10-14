# Handoff
Status: the latest stop: M2.P08 done: two surveys, every baseline capture valid and GPU-bound, the floors bounded from above, D47 keeping the warm-up pass in every launch, and A2, A3 and A10 passed on the eleven views. Next: M2.P09.

## Contents
Outcome · What changed · Checks · Review · The surveys · Acceptance · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P08
- Exit holds: the jar read agrees with P17 (12079c5); m2-survey-1 and m2-survey-2 ok, 88 of 88 baseline captures valid and GPU-bound (the lowest 0.9973 of FrameTime); the floors written to measurement.md#validity as upper bounds (the user's go, 2026-10-14: no view's passthrough was CPU-limited); m2-acceptance-2 ok, A2, A3 and A10 passed on all eleven views.
- D47 (the user's rule, fixed before m2-survey-2 ran, 2026-10-14): entities' warm-up capture again beyond 0.5 % in the same direction (-1.50 %, then -1.28 %), so the pass is kept: suite.json capture.warmupPass true, every launch runs it, full mode's twin and one candidate at R 2 take 11 launches of one view (two views plan 22, over the cap 20).
- The display request (f402c8c): shown live past the timeout only by a scratch hold of the same request (the displays read on at 620 s without input); no `run` has yet passed 600 s from the last input (m2-survey-1 ended about 599 s after it, m2-survey-2 about 474 s).

## What changed
- f402c8c: `run` and `calibrate` hold the displays on through a measured session (measure.displays_on; refused when they read off; the last handoff's review).
- fc85e9a: m2-survey-2's records.
- a153abf: launch.quit_mod reads to the pipe's end (QUIT_DRAIN 2 s, modclient.Client.wait_closed) before closing the client's end; the quit facts gain `pipeEnded`. fc85e9a's first CI run failed test_the_games_own_screens_never_end_the_session_but_another_screen_does (5 screens counted of 7: the fake's quit screens dropped by the close); its rerun passed; a test delaying them fails without the wait (5 == 7) and passes with it. mod-protocol.md#choreography with it. Its `git add -A` also took both acceptance records, against one logical change a commit; pushed, left so (no rewrite).
- 3a751c4: record.check_spec takes the warm-up pass from suite.json capture.warmupPass (the survey's `warmup` true still forces it); suite.json's whys (estMinutesPerSplitSession 22, the calibration fit's, cpuFloorMs.status); measurement.md steps 4 and 7 and Calibration (11 launches, about 4.2 h), run-record.md#split-sessions (a name of at most 35 characters from ten parts), roadmap.md's M2.P10 machine line, CHANGELOG.md.
- This commit: measurement.md#validity's floors and the queue sign's reading here; CHANGELOG.md's surveyed views and floors; roadmap.md's M2.P09 machine line (the acceptance records went in with a153abf).
- Choices no plan or prompt names, taken here: a 20-minute display request from a scratch process before m2-acceptance-1 (the machine 572 s idle, an acceptance run holds none; stopped after m2-acceptance-2, no process left); m2-acceptance-2 launched only after 30 s without input; the plan's text left as the record of what was planned (below).

## Checks
- This stretch's start (10:43 ADT): branch m2 clean at 750ab48.
- 3a751c4: 788 passed, ruff, ruff format, pyright clean, verify docs 0 violations; a153abf 787 passed, CI green (run 38578416485); fc85e9a's CI green on its rerun (run 38576217124).
- verify records: 0 violations; m2-acceptance-2 (245,837 bytes) and -1 (196,347) are acceptance records, reported over 200 KB as D51 allows.

## Review
- The display change's review is in git 750ab48's handoff.
- Before M2.P09's freeze (the user's go, 2026-10-14), the reviewer agent on a153abf and 3a751c4 (correctness): 0 high, 0 medium, 5 low, each read at its source. Fixed: (1) a quit whose pipe did not end within 2 s, or whose read failed, passed silently (`pipeEnded` read nowhere, a late hook.error unread): wait_closed is true only when the mod closed the pipe, and a measured or acceptance run fails on it (de7e78c); (2) the launch test pinned neither the exit before the drain nor `seconds` at the exit (de7e78c); (3) a warmupPass other than true or false dropped the pass silently: refused (68af3e5); (4) an unsplit session with the pass dropped had no test (68af3e5). Reported: (5) D43's closed text and section 7's 2-view stop against the code (Open questions). Clean, by its reading: the real pipe ends 0.8 s after `quit` (m2-survey-2-p4's request log), so the drain costs a quit nothing; every reader of the warm-up pass agrees with split parts; a calibration and its runs cannot disagree on it (suite.json in the identity).

## The surveys
m2-survey-1 (parts -p1c, -p2, -p3, -p4) and m2-survey-2 (-p1 to -p4): full mode, R 1, calibration null, the baseline, its twin and the passthrough; snapshot 65e7ae73... (116 files); heap 6144 MiB, cap 20.

| View | Baseline GPUBusy ms (survey 1), ratio lowest (1 / 2) | Passthrough, floor bound | D47 delta % (1 / 2) |
|---|---|---|---|
| forest_noon | 7.83, 0.9987 / 0.9994 | <= 0.54 ms | +0.28 / +0.18 |
| ocean_sunset | 7.05, 0.9985 / 0.9988 | <= 0.59 ms | +0.41 / +0.28 |
| cave | 5.19, 0.9993 / 0.9992 | cut twice, 0.50 | +0.13 / +0.00 |
| night | 5.28, 0.9990 / 0.9996 | cut twice, 0.50-0.51 | -0.11 / +0.20 |
| underwater | 7.07, 0.9992 / 0.9985 | <= 0.52 ms | -0.04 / +0.13 |
| entities | 5.19, 0.9991 / 0.9991 | cut twice, 0.53-0.54 | -1.50 / -1.28 |
| rain | 7.20, 0.9981 / 0.9973 | <= 0.93 ms | +0.60 / +0.79 (settles 1.5/4.0 s) |
| nether_crimson | 5.67, 0.9995 / 0.9992 | cut twice, 0.49 | +0.04 / +0.10 |
| nether_soul | 6.25, 0.9992 / 0.9990 | cut twice, 0.51 | +0.05 / +0.28 |
| end_dragon | 7.78, 0.9979 / 0.9985 | <= 0.66 ms | -0.03 / -0.18 |
| end_city | 7.79, 0.9973 / 0.9982 | <= 0.69 ms | -0.14 / -0.12 |

- The passthrough: 1,064-2,061 fps, GPUBusy 0.95-1.05 of FrameTime, GPULatency 1.26-1.76 frames: GPU-bound on every view, so no floor, only bounds; 14 of 22 captures cut invalid, PresentMon 12 to 1,259 rows short of the mod's frames (valid captures at 1,064-1,923 fps, invalid at 1,439-2,061: no clean threshold).
- The baseline's GPULatency 1.03-1.11 frames (ALC: about 2.7): no CPU-limit sign on this machine.
- m2-survey-2-p1: input came about 90 s into it (part 2's D42 read 56 s); it ended ok, no focus.lost, every baseline capture valid.

## Acceptance
- m2-acceptance-1 failed, A2 alone: on its first six views (forest_noon to end_dragon's first attempt) another window held the foreground (pid 5176, ended, unknown; then explorer.exe, then Code.exe) and covered the screen's centre, so F2 never reached the game; once the focus fallback's click landed, every F2 matched a frame. The user was at the machine. A3 and A10 passed.
- m2-acceptance-2 ok (11:03-11:06 ADT): A2 passed on all eleven views at the first attempt; A3 (centre and wrap) on all eleven; A10's selftest.

## Open questions
- Corrected (user, 2026-10-14): a full-mode session is 11 launches: the plan's M2.P09 (about 132 launches, 4.5 h) and M2.P10 (2-3 sessions of 11, 1.2 h) machine lines, prompts/m2.md's M2.P09 and M2.P10, roadmap.md's. Left as planned, the plan 3 bytes under its cap: D43's "no warm-up pass" (closed; D47's outcome supersedes it), section 7's "a 2-view launch holds the twin and one candidate" (met at M2.P06) and section 8's totals (104-113 launches; now about 169-183).
- A pack near 1 ms a frame (M3's hello pack, M4) meets PresentMon's row loss before the 90 % rule: its captures may be cut invalid.
- Carried: measurement.md's queue sign (GPULatency) reads no CPU limit here; nxplayer.bin (NoMachine) held D42 about 4 min with the user at the machine; orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- results/raw/ of the six survey parts and both acceptance runs (ignored); the failed survey parts m2-survey-1-p1 and -p1b (committed before).
- measurement.md: 37 bytes left; the next addition there needs a cut first.

## Weak points
- The floors are bounds from one GPU-bound capture per view per survey; five views have no valid passthrough capture at all.
- D47 rests on two sessions; rain's pairs differ in settle, so rain says nothing either way.
- The display state's off path has met the fakes only.

## Commits and time
- f402c8c, 750ab48 (the stop), fc85e9a, a153abf, 3a751c4, d160287 (the phase's handoff); before M2.P09: de7e78c, 68af3e5 and this one: docs: correct the calibration and timer runs' launch counts.
- M2.P08: about 3.0 h active against 1.5 h (0.7 h on 2026-10-13, 0.9 h that night around a 4.9 h wait for the user, 0.9 h on 2026-10-14 from 10:42 ADT, 0.5 h of fixes before M2.P09 from 12:02 ADT); machine: 10 launches (both surveys' 8, two acceptance runs) and 2 failed before (-p1, -p1b).
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 40.9 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4, the re-plan 0.35, P07 2.1 active, P08 3.0).

## Next
M2.P09's prompt from docs/prompts/m2.md (Calibration and the known positive), with the user's go for its hours: about 132 launches over about 4.5 h.
