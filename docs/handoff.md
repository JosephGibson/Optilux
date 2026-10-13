# Handoff
Status: the latest stop: M2.P06, the reload budget, done: heap 6144 MiB and a cap of 20 reloads a launch (user, 2026-10-13: the driver kept, sessions over the cap split); the split needs a re-plan before M2.P07.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P06
- M2.P06's Exit holds: the five budget records carry heap tables; config/java/bench.json (6144 MiB, unchanged, so no third run) and suite.json (capture.reloadCap 20; statistics.calibration twinsPerSession 2, minSessionsPerMode 10) are set from them by D43's rule, each `why` citing them; section 7's stop does not fire under D43 as amended: a 2-view launch without the warm-up pass holds the twin and one candidate at R 2 in 2 + 2 x 9 = 20 reloads.
- The user's decisions (2026-10-13): the diagnosis first (the last stop's option 1), then the defaults run (option 1 again), then option 2: keep AMD's driver 32.0.31041.3013 and cap a launch at 20 reloads, sessions over it split into launches of views without the warm-up pass (plans/m2.md D43 and section 7 amended, e24925e).
- The records, all announced, status ok, calibration null, Xmx 6144 MiB: m2-budget-full-1 and m2-budget-overworld-1 (the pair, the last session), m2-diag-alone-1 (the baseline alone with windows), m2-diag-switches-1 (the pair's switches without windows), m2-diag-defaults-1 (Unbound at its defaults, alone, without windows); the last three at forest_noon, 42-44 reloads, the GPU memory read after every reload.
- Heap after GC / private bytes (MiB) at reload 20: 1,189.6 / 20,923.9, 986.6 / 21,133.2, 904.5 / 22,382.4, 904.2 / 22,054.0, 958.1 / 22,632.6; private growth over reloads 2-20: 510.2, 523.0, 592.0, 559.7 and 602.7 a reload. At reload 30 every record is over 75 % of physical memory (24,518.25 of 32,691 MiB).
- The leak: every pipeline reload leaves about 0.5 GiB of GPU memory, with or without a pack switch, a window or the played profile (alone: dedicated 3,770.9 at reload 3 to 14,110.5 at 21, then shared 334.9 to 12,487.4 by 42). The 16 GB card fills near reload 21; the baseline then slows: drift onsets 23, 24 and 22, up to +473.7 % (+351.4 % among valid captures). Every M1 record ran on driver 32.0.32015.2008 and grew 50-76 MiB over reloads 0-20; every M2 record runs on 32.0.31041.3013 (the driver store's only display package, dated 2026-09-02). The helper jar, the other change, allocates no GL memory with timers off (read in its source, not run).
- D43's rule (optilux/budget.py) over all five: 6144 and 7168 MiB cap 20 (the pair alone to 9216), 8192 and up 10 or less; the smallest kept. Private bytes and the drift each bind at 20; the heap after GC at 120 to 230.

## What changed
- plans/m2.md: M2.P06's diagnosis and D43's drift limit (62f63a9), then D43's split and section 7's stop per 2-view launch (e24925e); 40,954 of 40,960 bytes.
- record.py and measure.py: a budget run's `keepViews`, `alone` and `windows` false (flag `noWindow`); a heap run stops before a reload under 2 GiB available; the GPU memory after every capture and in each heap row (perReload `gpuMiB`); a budget run (measurement, heap true, calibration null) passes capture.reloadCap, which refuses others naming the split; session.py's RunHost.gpu_memory.
- optilux/budget.py: D43 as a pure function, holds_twin_and_one and calibration_fit with or without the warm-up pass.
- config/suite.json, config/java/bench.json as above; measurement.md#session's budget (20, the leak, the split, budget runs) and #calibration (2 twins, 10 sessions, about 3.5 h); run-record.md; CHANGELOG's 0.3.0 entry gains the cap.
- Choices no plan or prompt names, taken here: the diagnosis as budget runs through `run`; forest_noon; F4's 2 GiB guard; the rule reads the rows, not the mean slope; a tie goes to the smallest heap; a run without windows sets no drift cap; budget runs pass the cap (else no leak could be measured past 20 again), acceptance runs do not (F4's 50 reloads are refused at 20).

## Checks
- At the start: 610 passed, verify docs 0 violations, tree clean on m2.
- 02bc5a5: 641 passed; ruff, ruff format and pyright clean; verify docs 0 violations; CI green on each pushed commit before the next push, 365646b's on its rerun (the runner's own `logman query -ets` failed with a WMI error).
- Tests added (31): the budget keys' refusals, the diagnosis runs on the fake, the guard, the typeperf parser on a real sample, the rule's 13 over the pair's rows, the cap of 20 (quick mode's 20 passes, one over a cap of 19 refused, full mode's 112 refused naming the split, a budget run passing).

## Review
- Three reviewer passes (the diagnosis code, the rule, the configs): 24 findings, each read at its source. Fixed: GPU growth past the card's size, windowless captures' settle and flag, unreadable typeperf values, non-text spec items, the rule's mean slope and unread drift, section 7's case named, the exemption narrowed to calibration null, the drift range (13-474 %, not 13-132), M1's span, two refusal texts. Reported: the tie-break; D43's drift reads baseline captures only; the items under Open questions.
- m2-diag-alone-1 and -switches-1 keep `gpuDedicatedMiB` (about half the growth) and switches' noWindow true with flags []: records are append-only.

## Open questions
- For the re-plan (the user's approval), before M2.P07, recommendations first:
  - The split's phase: M2.P07, which already brings `calibrate` and `compare`: `run` and `calibrate` launch a session's view groups, `compare` joins a session's records; its estimate rises. A new phase renumbers the prompts.
  - "Session": AGENTS.md says one launch, while a split full-mode session spans 6 launches; minSessionsPerMode counts the whole split session (2 nulls over all 11 views), and the term follows.
  - The warm-up pass: D43 drops it in split launches, while D47 keeps it pending M2.P08's survey, which plans it in full mode (a 2-view launch with it is 22): the survey at R 1 (2 + 3 + 3 x 5 = 20 a 3-view launch) keeps D47's comparison.
  - Sizes: plans/m2.md section 8 (M2.P09 about 70 launches, not 15), roadmap.md#estimates, suite.json's estMinutesPer5Variants 19 (no 5-variant launch fits 20).
- The driver: kept (user, 2026-10-13). Records note its version; a driver change moves the leak, and nothing checks it before a measured launch.
- Carried: D47; nxplayer.bin's GPU share (3.2-3.3 % before the first diagnosis launch); orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- results/raw/m2-diag-*/ (ignored); the specs and the rule's runs in the session's scratchpad.
- D42 waited 212.6 s, 315.7 s and 3.2 s before the three diagnosis launches.

## Weak points
- One run per diagnosis cell; the driver lead compares M1's records with M2's, between which the jar, the world and the runner's reload path changed too.
- The validity flags passed captures past the drift onset: they judge a window, not a session's drift; the cap keeps sessions before it.
- The plan has 6 bytes left: the re-plan cuts text or splits the milestone.

## Commits and time
- 62f63a9, 0cda0e7, 8717b2f, acd5aaa, 365646b, 1f2a6eb, 1671fae, 79b2531, e24925e docs: split sessions over the reload cap into launches of views; 02bc5a5 feat: cap a launch at 20 reloads and calibrate 2 twins a session; this handoff.
- M2.P06 this session: 04:32-04:45, about 10:15-11:15 and 13:38-14:15 ADT (the rest waiting on the user's answers): about 1.8 h against 1.5 h, 2.4 h with the first stop's 0.6 h.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 35.4 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4).

## Next
The re-plan of M2.P07 to M2.P10 for D43's split (Open questions), plans/m2.md and docs/prompts/m2.md amended with the user's approval; then /optilux-next prints M2.P07's prompt.
