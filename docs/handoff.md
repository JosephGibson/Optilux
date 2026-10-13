# Handoff
Status: the latest stop: M2.P06, the reload budget, stopped on plans/m2.md section 7 (no heap under D43 holds full mode's twin and one candidate); the user's decision comes first.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P05
- Stopped: plans/m2.md section 7, "no heap under D43 at which full mode holds the twin and one candidate". D43's rule over the pair gives 6144 MiB and a cap of 30 reloads; full mode's twin and one candidate plan 112 (a full calibration session of one twin 68). bench.json, capture.reloadCap and statistics.calibration are unchanged; the third run did not happen. M2.P06's Exit does not hold.
- F14's controlled pair, both announced, both status ok, calibration null, the baseline (D35), shadows off (SHADOW_QUALITY -1) and the twin at R 1, Xmx 6144 MiB, physical memory 32,691 MiB:
  - m2-budget-full-1: full mode, 11 views, 68 reloads; 55 of 66 captures valid (11 fewFrames); heap after GC / private bytes / available (MiB) at reloads 2: 589.6 / 11,739.7 / 12,087; 10: 843.7 / 15,910.7 / 11,872; 20: 1,189.6 / 20,923.9 / 11,466; 30: 1,409.6 / 25,500.0 / 7,672; 40: 1,612.8 / 29,396.8 / 3,991; 50: 1,919.6 / 33,835.2 / 364; 60: 2,255.4 / 36,121.5 / 446. Per reload: heap 28.72, private 420.4.
  - m2-budget-overworld-1: the overworld's seven views, no Nether or End visit, 44 reloads; 41 of 42 valid (1 halves); at 2: 590.7 / 11,719.6 / 14,754; 10: 816.2 / 15,890.7 / 14,446; 20: 986.6 / 21,133.2 / 14,217; 30: 1,166.3 / 24,996.0 / 11,079; 40: 1,389.1 / 28,986.4 / 6,976. Per reload: heap 21.01, private 454.4.
- F14 answered: the heap's extra growth follows the dimension visits (28.72 against 21.01 MiB a reload, as M1's 33 against 20), the private bytes do not (420 and 454 MiB a reload in both). M1's F4 table (m1-acceptance-10: one pack reloaded back to back, 2 frames each) grew 46.3 MiB a reload; these sessions switch packs and options and render a 4 s window after each reload. Which of those makes the tenfold growth is unread.
- D43 as written (results/raw/budget-rule/d43.py, local): per heap, the cap by the heap and by private bytes, the worse run's: 6144: 30 (heap 140 and 190, private 30 and 30); 7168 to 10240: 20; 11264 to 14336: 10; 15360 and up: 0 or less. Private bytes bind everywhere: each 1024 MiB of heap commits 1024 MiB more at the start, about 2.4 reloads' growth.
- The baseline drifts with the reloads, inside that cap: every pass-2 baseline lies within 0.9 % of its view's warm-up capture (full) and 0.3 % (overworld) up to reload 22, then 13.3 % (forest_noon, reload 23, full) and 40.6 % (ocean_sunset, reload 24, overworld) above it, rising to +474 % (entities, reload 44, full) and +118 % (underwater, reload 39, overworld). The onset sits near 22 GB of private bytes (20.9 and 21.1 GB at reload 20) with 11.5 and 14.2 GB of physical memory still available; the GPU's dedicated memory was not read. M2.P05's quick run (14 reloads) lies before it.
- Done in the phase: a measurement run with heap true takes `rounds` and `dimensions` (a budget run), the heap table records the physical memory (70a0c8e); the pair's records (7d22628). The rule as a module, its tests, the reviewer pass, the configs, measurement.md's budget and CHANGELOG's reload cap were left at the stop. The budget's refusal one reload over the cap is already tested (tests/test_measure.py: capture.reloadCap 13 refuses a plan of 14).

## What changed
- optilux/record.py: SPEC_OPTIONAL gains `rounds` and `dimensions` (BUDGET), check_budget refusing them outside a measurement run with heap true; Spec.rounds read by the planned reloads, the schedule (measure.py), the announcement and the planned captures (run.py).
- optilux/measure.py: heap_table's physicalMiB; optilux/session.py: RunHost.physical_memory (psutil).
- docs/run-record.md (Record, Run spec): the budget run's fields and physicalMiB.
- Choices no plan or prompt names, taken here: the pair needs R 1 in full mode and an overworld-only view set, which no spec field gave, so the spec gained them for heap runs only (no verdict reads a budget run: calibration null); D43's slopes are each record's perReload (first row to last), its start the first row, the worse run per heap the smaller cap; the overworld half ran after the full half had already shown the stop, being step 1's other half and F14's answer.

## Checks
- At the start: 600 passed, verify docs 0 violations, tree clean on m2.
- 70a0c8e: 610 passed; ruff, ruff format and pyright clean; verify docs 0 violations; CI green. 7d22628: 610 passed.
- Tests added (10): the pair's 68 and 44 reloads and its seven overworld views; eight refusals of rounds and dimensions; a budget run on the fake (full mode, R 1, the Nether's two views, 10 reloads, heap rows at 2 and 10); the heap test also reads physicalMiB.

## Review
None at this stop: the reviewer pass was to read the rule and the configs it writes, and neither was committed.

## Open questions
- For the user (the stop): what a session may hold. Each launch leaks about 420-454 MiB of private bytes a reload under pack switching, and the baseline slows from about reload 23, so no launch measures past about 20 reloads as things stand; full mode plans 112 or more. Options, recommended first:
  1. Name the cause before amending D43: one or two diagnostic launches, the baseline reloaded alone with its windows against pack switches without windows, reading the game's GPU dedicated memory (typeperf's GPU Process Memory, read only) beside the heap; then D43 amended with a drift limit beside the memory one. Costs a phase (about 1.5 h) before M2.P07.
  2. Amend D43 now: a launch holds at most 20 reloads, sessions split across launches (full mode by view groups, calibration by fewer twins and more sessions); M2.P05's runner gains the split. Costs many more launches (full mode's 11 views need several per round) and keeps an unexplained leak in every session.
  3. Drop the warm-up pass (D47) and shrink R: saves 11 reloads in full mode, not enough alone (2 + 11 x 5 = 57 for the twin and one candidate at R 1).
- M2.P08's survey (full mode, Ci 2, 112), M2.P09's calibrations (244 and 38 at 5 twins) and M2.P10 all plan past the onset; they wait on the decision.
- Carried: D47 (pass 1 against pass 2 within 0.26 % in M2.P05's quick run); nxplayer.bin's GPU share; orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- results/raw/budget-rule/ (ignored): d43.py, the rule as run, and the pair's specs.
- D42 waited 294.0 s before the first launch (input inside 30 s, chrome.exe at 2.2-3.0 % of the 3D engine), 30.4 s before the second.

## Weak points
- One run per half; the drift's cause and the leak's are unread; the GPU's memory was never read.
- The overworld half's captures after its onset (reload 24) carry valid flags, as the flags judge a window, not a session's drift.

## Commits and time
- 70a0c8e feat: let a heap run set its rounds and keep some dimensions; 7d22628 chore: record the reload budget pair at the 6144 MiB heap; this handoff. Each pushed after the previous one's CI ended green.
- M2.P06: 23:18 to about 23:55 ADT, about 0.6 h against 1.5 h, stopped.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 33.6 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 0.6).

## Next
The user's decision on the session's reload budget (Open questions), then D43 amended in plans/m2.md; /optilux-next then prints M2.P06's prompt again.
