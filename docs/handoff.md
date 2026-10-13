# Handoff
Status: the latest stop: M2.P06, the reload budget, stopped again on plans/m2.md section 7 after its diagnosis (user, 2026-10-13): every pipeline reload leaks about 0.5 GiB of GPU memory, so a launch holds 20 reloads; the user's decision comes first.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P05
- Stopped: plans/m2.md section 7, "no heap under D43 at which full mode holds the twin and one candidate". D43 as amended (the drift limit) over the four budget records gives heap 6144 MiB, bench.json's own (so no third run), and a cap of 20 reloads; full mode's twin and one candidate plan 112 at R 2 (68 at R 1), and no full calibration session fits one twin. bench.json, capture.reloadCap and statistics.calibration are unchanged; CHANGELOG's reload cap is not written. M2.P06's Exit does not hold.
- The diagnosis (plans/m2.md M2.P06, user 2026-10-13), both announced, both status ok, calibration null, at forest_noon, Xmx 6144 MiB, the game's and the adapter's GPU memory read after every reload (typeperf):
  - m2-diag-alone-1: the baseline alone with its windows, no pack switch, 42 reloads, 40 of 40 captures valid. Heap after GC / private bytes (MiB) at reloads 2: 590.0 / 11,726.4; 10: 730.2 / 16,495.6; 20: 904.5 / 22,382.4; 30: 1,079.4 / 28,656.0; 40: 1,254.4 / 35,134.6 (6,703 MiB still available). The game's dedicated GPU memory 3,770.9 at reload 3 to 14,110.5 at 21 (574 a reload), the adapter's 15,333.6 at 21; then dedicated holds at 14.3-14.8 GB and shared grows 334.9 to 12,487.4 (reloads 22 to 42, 608 a reload). GPUBusy against the warm-up's 7.8588 ms: within 0.39 % to reload 21, +20.3 % at 22, +61.3 to +62.0 % from 23 to 33, +98.0 to +131.7 % from 34 to 42 but +62.6 % at 41.
  - m2-diag-switches-1: the pair's switches (the baseline, shadows off, the twin) without windows, 44 reloads, 42 captures, none valid by design. At 2: 588.8 / 11,979.6; 10: 729.7 / 16,562.3; 20: 904.2 / 22,054.0; 30: 1,077.1 / 27,490.6; 40: 1,250.9 / 33,709.8. Dedicated 4,097.9 at reload 3 to 14,709.5 at 23 (531 a reload), then shared 207.9 at 24 to 11,699.2 at 44 (575 a reload).
- The cause, as far as read: the leak is per pipeline reload, with or without a pack switch or a window. Private bytes over reloads 2 to 20 grow 510.2 (full), 523.0 (overworld), 592.0 (alone) and 559.7 MiB (switches) a reload; the pair's mean slopes (420.4, 454.4) flatten past reload 30. The drift is the VRAM overflow: the baseline holds while the game's dedicated memory grows and slows from the first reload whose growth lands in shared memory (alone: 22; the pair's onsets 23 and 24). Private bytes follow the GPU memory (its commit) past the physical memory, 35,134.6 MiB in 32,691.
- Unread: why M1's F4 table (m1-acceptance-10: Unbound at its defaults, profile null, world spike, 50 reloads back to back, no settings files written) grew 46.3 MiB private a reload against 510-592 here; its GPU memory was never read.
- D43's rule (optilux/budget.py), caps per heap, the worse run's: the pair alone 6144 to 9216: 20, 10240 to 14336: 10, 15360 and up: 0; with the diagnosis 6144 to 8192: 20, 9216 and up: 10 or less. Private bytes (every record's row at 30 over 75 % of physical memory, 24,518.25 MiB: 25,500.0, 24,996.0, 28,656.0, 27,490.6) and the drift (onsets 23, 24, 22) each cap 6144 at 20; the heap after GC at 120 to 230.
- Calibration within 20: quick mode (3 views, R 1) fits 2 twins a session, 10 sessions for 20 nulls; full mode (11 views, R 2) fits none (one twin plans 68).

## What changed
- plans/m2.md: M2.P06's diagnosis and D43's drift limit, 4-5 launches (28-33 in all), section 10's amendment (user, 2026-10-13); 40,959 of its 40,960 bytes.
- record.py and measure.py: a budget run's `keepViews`, `alone` (the baseline in every slot, no twin) and `windows` false (reload and options only, flag `noWindow`, `settleS` null); a heap run stops before a reload under 2 GiB available; the GPU memory after every capture and in each heap row, perReload `gpuMiB` (dedicated plus shared); an unreadable typeperf value refused; session.py's RunHost.gpu_memory; run.py's plan line and the LUID; run-record.md and measurement.md#validity as built.
- optilux/budget.py: D43 as a pure function (each record's rows to its last, past it the steepest segment, the private bytes shifted by the heap's difference from the run's Xmx, the drift), holds_twin_and_one (section 7), calibration_fit; imported by no measured module, so `harness` is unchanged by it.
- Choices no plan or prompt names, taken here: the diagnosis as budget runs through `run` with spec keys, so each has a record; forest_noon (full mode's first onset), alone at R 19 (42 reloads), switches at R 10 (44); F4's 2 GiB guard; the rule reads the rows, not the first-to-last slope the last stop used (both pair rows at 30 are over the limit that slope held to 30); a tie goes to the smallest heap (D43 names none); a run without windows sets no drift cap, and runs none of which read the drift are refused; D43 over the pair alone and over the pair with the diagnosis, both 6144 MiB and 20.

## Checks
- At the start: 610 passed, verify docs 0 violations, tree clean on m2.
- 0cda0e7: 625 passed; acd5aaa with 365646b: 640 passed; ruff, ruff format and pyright clean; verify docs 0 violations; CI green on each pushed commit before the next push, 365646b's on its rerun: its first run failed test_logman_lists_sessions_on_this_machine on the runner's own `logman query -ets` ("The GUID passed was not recognized as valid by a WMI data provider"), 639 passed.
- Tests added (30): the budget keys' 12 refusals, the diagnosis's 42 and 44 reloads, the alone run and the windowless run on the fake, the guard, the typeperf parser on a real sample (an unread value refused), the heap rows' GPU memory and gpuMiB; the rule's 13 (the pair's own rows, a row over the limit, the steepest segment, the Xmx shift, the drift at 20, 21, 30 and 31, refusals, section 7's 112, the calibration fit).

## Review
- The reviewer on the diagnosis code: 6 findings (1 medium, 5 low), each read at its source and fixed in acd5aaa: perReload's dedicated memory stopping at the card's size; a windowless capture's settle and its valid without a flag; non-text keepViews and dimensions items crashing; an unreadable typeperf value summed as missing; reloadS undocumented. m2-diag-alone-1 and -switches-1 keep gpuDedicatedMiB (302.5, 312.2: about half the growth) and switches' noWindow true with flags [] (records are append-only).
- The reviewer on the rule: 9 findings (1 high, 1 medium, 7 low). Fixed: section 7's case named (holds_twin_and_one); the rows instead of the mean slope; an unread drift kept apart from none; no cap made from no growth; the empty heap table; the drift constant's source; boundary tests. Reported: the tie-break (above); statistics.calibration is one block for both modes while the fit differs per mode; D43's drift reads baseline captures only, while the overworld half's twin at reload 23 already read +11.5 % (the cap is unchanged).

## Open questions
- For the user (the stop): what a session may hold, the leak now named. Options, recommended first:
  1. Find what leaks first: one launch of about 5 min, the baseline at the pack's defaults (profile null), alone, without windows, at forest_noon, 42 reloads; the spec keys exist, no code. Near 46 MiB a reload, the played profile's settings leak (bisect its keys next); near 560, something since M1 does (the jar, the world, the settings files written per reload). A leak in Iris or the pack lies outside the harness; re-pinning Iris is the user's. Costs about 0.5 h before the decision below.
  2. Accept 20 reloads a launch now: capture.reloadCap 20; quick calibration at 2 twins a session, 10 sessions; full mode split across launches by view group, which without the warm-up pass (D47) holds 2 views a launch for the twin and one candidate (2 + 2 x 9 = 20): 6 launches a full-mode session; full calibration at 2 twins a session, 2 views a launch, about 60 launches. M2.P05's runner gains the split; calibration's hours grow several fold.
  3. Narrow full mode instead (fewer views, R 1, no warm-up pass) until a session fits 20; changes the suite's modes, an identity key, and the coverage design.md set.
- M2.P08's survey (112), M2.P09's calibrations and M2.P10 all plan past 20 reloads; they wait on the decision.
- Carried: D47 (pass 1 against pass 2 within 0.26 % in M2.P05's quick run); nxplayer.bin's GPU share (3.2-3.3 % again before the first launch); orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- results/raw/m2-diag-alone-1/ and -switches-1/ (ignored); the specs and the rule's run over the records in the session's scratchpad.
- D42 waited 212.6 s before the first launch (input; nxplayer.bin at 3.2-3.3 % of the 3D engine) and 315.7 s before the second (input).

## Weak points
- One run per diagnosis cell; M1's F4 cell from another identity, its GPU memory unread.
- The diagnosis records differ from the pair's identity in `harness` alone (measure.py, record.py, session.py, run.py); their memory growth is compared, never a frame time.
- The validity flags passed every capture past the drift onset (alone: 40 of 40 valid at +62 to +132 %): flags judge a window, not a session's drift.
- Private bytes are commit, not RAM: D43's private-bytes limit tracks the GPU memory's commit here, not memory pressure.

## Commits and time
- 62f63a9 docs: diagnose the reload leak first and cap the budget at the drift; 0cda0e7 feat: let a budget run read GPU memory, alone or without windows; 8717b2f chore: record the reload leak diagnosis at one view; acd5aaa fix: count shared GPU memory and flag windowless budget captures; 365646b feat: compute the reload budget's heap and cap from budget records; this handoff. Each pushed after the previous one's CI ended green.
- M2.P06 this session: 04:32 to about 04:45 ADT, then the open question until the user's answer (before 10:26, not recorded exactly), then to about 11:15: about 1.1 h of work against 1.5 h (1.7 h with the first stop's 0.6 h); 6.6 h by the clock.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 34.7 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 1.7).

## Next
The user's decision on the session's reload budget (Open questions); then the diagnostic launch, or D43 and the phases amended in plans/m2.md (1 byte left: an amendment cuts text first); /optilux-next then prints M2.P06's prompt again.
