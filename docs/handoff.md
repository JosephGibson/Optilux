# Handoff
Status: the latest stop: M2.P09 done: quick and full mode calibrated on bench_263, every threshold the 0.5 % floor, shadows off accepted beyond it in both modes beside a twin inside it, and `compare` refusing m1-acceptance-10 live on identity keys. Next: M2.P10.

## Contents
Outcome · The calibrations · The known positive · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P09
- Exit holds: config/calibrations/ holds quick-95d96878... and full-95d96878...; m2-shadows-quick-1's twin +0.0258 % and m2-shadows-full-1's +0.0048 % lie inside the 0.5 % geo-mean threshold, shadows off reads -10.6851 % and -12.3303 %, accept (`compare` re-judging both: the record's own verdicts, the same); `compare m1-acceptance-10 --calibration quick-...` refused, naming platform.sha256, mods[0], world.snapshot, views.file, settings.iris.shaderPack, suite.sha256, java.release and harness.
- No section 7 stop: no geo-mean threshold above 2 %, no twin beyond, no launch invalid on focus, D42 never refused.
- The user's go (10:47 ADT, 2026-10-15), after the stop at step 2 (de372df); a pause asked by the user (13:24-13:42 ADT), taken while part 2 of cal-full-...-7 waited on D42, no game running.

## The calibrations
Identity 95d9687847308453839250cc292ce01bde79b39bc4f4103eac593f5155a5463e (`run --check` before the first session and after the last commit's test fix, equal); snapshot bench_263 65e7ae73... (116 files); heap 6144 MiB, capture.reloadCap 20; 2 twins a session, 10 sessions a mode; driver 32.0.31041.3013 recorded.

| Mode | Id | Sessions | Thresholds (k 1 of 20) | Largest null |delta| |
|---|---|---|---|---|
| quick | quick-95d9687847308453839250cc292ce01bde79b39bc4f4103eac593f5155a5463e | cal-quick-95d968784730-1 to -10, 1 launch each | geo-mean 0.5, forest_noon, nether_crimson, end_dragon 0.5 (the floor) | geo-mean 0.19; views 0.19, 0.35, 0.45 |
| full | full-95d9687847308453839250cc292ce01bde79b39bc4f4103eac593f5155a5463e | cal-full-95d968784730-1 to -4, -6 to -11, 11 launches each | geo-mean 0.5, every view 0.5 (the floor) | geo-mean 0.09; views 0.16 (ocean_sunset) to 0.42 (nether_crimson) |

- cal-full-...-5 does not count: its nether_soul part (-5-p9, 12:54-12:56 ADT) presented every capture as Composed: Flip (flag presentMode) while the user was at the machine through NoMachine (nxplayer.bin at 2.4 % of the 3D engine in D42's wait after it); calibrate stopped, and its rerun passed it over and ran -6 to -11. Its 12 records are committed with the rest (every launch keeps its record).

## The known positive
SHADOW_QUALITY -1 over the baseline (Unbound r5.9.3, played profile, D35) beside the twin (P18):

| Run | Twin geo-mean | Shadows off geo-mean | Per view |
|---|---|---|---|
| m2-shadows-quick-1 (1 launch) | +0.0258 % | -10.6851 %, accept | forest_noon -16.73, nether_crimson -0.14 (inside), end_dragon -14.32 |
| m2-shadows-full-1 (11 launches) | +0.0048 % | -12.3303 %, accept, no confirm | underwater -25.22 to entities -10.37 on the overworld and End views; nether_crimson -0.55 (beyond), nether_soul -0.36 (inside) |

- Reports: results/raw/m2-shadows-quick-1/report.html and results/raw/m2-shadows-full-1/report.html (ignored). The twin monitor: 1 twin under each calibration, none beyond.

## What changed
- 3647806: the tests' fake roots copy config/ without config/calibrations/ (conftest.copy_config): test_calibrate_announces_its_count_then_resumes_after_a_stop failed once the real calibrations existed (`assert not (root / record.CALIBRATIONS).exists()`), and passes with the fixture's copy.
- b3af943: both calibrations and their 142 session records.
- 7ad28e1: the shadows-off runs (13 records); measurement.md#calibration's results and its Status line, cuts of text that suite.json and plans/m2.md hold (step 4's D47 numbers, step 5's `/return` reason, step 7's budget citations, the 4.2 h estimate); CHANGELOG.md's calibrations.
- Choices no plan or prompt names, taken here: m2-shadows-quick-1 ran right after the quick calibration, before the full one (a quick miss would have stopped before 3.7 h of launches); a scratch process held the displays on (SetThreadExecutionState's display request, no setting changed) from 10:48 to 15:41 so the gaps between commands never met the 600 s timeout; the stopped calibrate was resumed twice (after -5, after the user's pause).

## Checks
- Start (02:55 ADT): branch m2 clean at 11ab7ed; 790 passed; verify docs 0 violations; CI green on de372df (run 38689596734).
- After the fix: 790 passed, ruff, ruff format and pyright clean; verify docs 32 files, 0 violations (measurement.md 24,566 of 24,576 bytes); verify records 184 records, 0 violations (three acceptance records over 200 KB, reported); CI green on 3647806 (run 38788285532) and b3af943 (run 38789083297).
- The displays stayed on past the 600 s timeout: cal-quick-...-10 launched 1,583 s after the last input, m2-shadows-full-1-p1 1,036 s, every window with its rows; the scratch hold ran beside the harness's own request throughout, so this shows the two together, not `run`'s alone.

## Review
The reviewer agent on both calibration files and both runs' verdicts (correctness against measurement.md#calibration): 0 high, 2 medium, 1 low; each read at its source.
- Clean, by its recomputation: k 1 of 20 in both files, the stored thresholds from the stored nulls, the nulls from exactly the listed sessions (2 twins, every view; -5 absent), eight ratios from the captures, every per-view delta, `beyond`, ms value and both verdicts; the identity's stats.py hash equal in all 155 records.
- Reported (1), medium, confirmed: in quick mode the first Ci slot reads slow against the last. Each view's first measured baseline follows a dimension change (settleS 4.0, the rest 1.5) and reads 0.13-0.16 % below the second (8-9 of 10 sessions per view), so twin-1 (slot 1) reads +0.198 % at end_dragon in 10 of 10 sessions (twin-2 -0.055 %), +0.085 % on the geo-mean. A quick candidate always sits in slot 1, the twin and the monitor in the last, which never see it. Inside the 0.5 % floor today (the largest slot-1 geo-mean null 0.19 %); full mode, one view a launch, shows no such slot difference (at most 0.05 %). Not fixed: the schedule is a measured module, frozen (plans/m2.md section 4).
- Reported (2), medium, cause unknown: the baseline's GPUBusy level fell about 1.7 % between cal-full-...-5-p8 (12:52 ADT) and -6-p1 (13:02): forest_noon 7.99 ms in every quick session, m2-shadows-quick-1 and full -1 to -5, 7.85-7.86 ms in -6 to -11 and m2-shadows-full-1; end_dragon and nether_soul alike. `recorded` and D42's GPU readings (at most 0.49 %) do not tell the two apart; AMD's own PresentMon ran in both; the event logs show nothing; nxservice (NoMachine) is installed, stopped now. The quick calibration and its known positive lie wholly in the slower level, the full calibration across both (nulls -0.047 % on the geo-mean in -1 to -4, -0.010 % in -6 to -11, a like spread).
- (3), low, stale: placeholders in measurement.md, read before the full run's numbers were written; none left.

## Open questions
- The level drop (Review 2): what ran on the machine before about 12:55 ADT and not after (the user's NoMachine session, a browser, another load)? D42 reads only the 3D engine. The twin monitor over the next quick runs says whether quick's thresholds hold at the new level.
- The quick slot bias (Review 1): for M3's recalibration, e.g. one discarded baseline after a dimension change, or the twin's slot rotated so the monitor sees slot 1.
- The reload leak (researched with the user, 2026-10-15): the driver went from 32.0.32015.2008 (Adrenalin 26.9.2, 2026-09-29; M1's 46 MiB of private bytes a reload) to 32.0.31041.3013 (26.9.1, 2026-09-03; 616 MiB a reload, GPU memory about 573 MiB) at 2026-10-10 00:17 ADT through an AMD installer, not Windows Update (driver store u0203731.inf; AMDRyzenMasterDriverV32 installed the same minute). The version mapping is from search snippets of AMD's notes, backed by three driver sites; M1's run also differed in world and helper jar. Test, the user's call, best before M3's recalibration: 26.9.2 or newer, then one budget run of m2-diag-alone-1's spec; a flat GPU memory would let the cap rise (fewer launches a full session, more candidates).
- Carried from M2.P08's handoff (git d160287, 11ab7ed): D43's closed "no warm-up pass" and section 7's 2-view text against D47; a pack near 1 ms a frame meets PresentMon's row loss; the queue sign; nxplayer.bin; orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- measurement.md: 10 bytes left; the next addition there needs a cut first.
- results/raw/ of every calibration session and both runs (ignored).

## Weak points
- The quick calibration rests on one GPU level that ended mid-run (Review 2); the full calibration's 20 nulls span both.
- The slot bias (Review 1) is inside the floor by 0.31 %; a quick accept near the threshold reads it against itself.
- Twins within a launch share its state: the 20 nulls are not independent (measurement.md#calibration, a target, not a bound).

## Commits and time
- de372df (the stop), 3647806, b3af943, 7ad28e1, and this one.
- M2.P09: about 1.1 h active against 1.5 h (02:55-02:58 ADT; then from the go at 10:47 to about 16:05, with a 7.8 h wait for the go and the user's 0.3 h pause outside); machine about 4.6 h: 143 launches against 132 (quick 10 in 27.6 min; m2-shadows-quick-1 1 in 2.8 min; full 121, the passed-over session's 11 included, in 223.8 min; m2-shadows-full-1 11 in 20.0 min).
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 42.0 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4, the re-plan 0.35, P07 2.1 active, P08 3.0, P09 1.1).

## Next
M2.P10's prompt from docs/prompts/m2.md (A8 and A11): 2-3 full-mode sessions of 11 launches against full-95d96878..., about 1.2 h of machine, the machine left alone; `run --check`'s identity equal to the full calibration's first.
