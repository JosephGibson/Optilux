# Handoff
Status: the latest stop: M3.P10 at its named stop, the user's go for the calibration hours after the driver call (D66); the identity the calibrations will carry checked, nothing launched. Next: M3.P10 step 3 after the go.

## Contents
Outcome · The identity · The driver · The hours · Checks · Open questions · Commits and time · Next

## Outcome
Last phase: M3.P09
- M3.P10 step 1 done (13:55-14:01 ADT, 2026-10-23): `run <calibrate's quick session spec> --check --json` ok, nothing launched, no groups (quick mode is one launch), calibration null; identity sha256 4edbb05a97ab879a7dae07e42c003a8067817e310897f608a8121d4976b51d40, full mode's check the same, its groups 11 of one view.
- Step 2, the stop the prompt names: the user's go for about 4.5 h of machine time, the machine left alone throughout, and D66's driver call.

## The identity
From this session's `run --check --json` (the spec calibrate writes: kind calibration, mode quick, Unbound r5.9.3 with the played profile, set deterministic):
- platform 3bc69860..., tier bench; launchSpec mc-26.3.launch.json de7fdff0...; mods 4 jars;
- world snapshots/bench_263, tree 33a4074d..., 128 files; views bench_263.json c1e7046e...;
- resourcePacks deterministic: Faithful 64x Release 15 (bc534dfb...) under optilux-static-textures (ff44b3cc...), options.txt's line vanilla, Faithful, static;
- settings 24 written keys, no overrides, the token, Sodium's options bf6988db..., 4 iris keys, 174 unwritten;
- suite 7ba0cc9d...; java jdk-25.0.4.1+1, release 86e5e516..., heap 6144/6144 MiB, no args;
- system AMD Radeon RX 7800 XT, hags true, 3840x2160, exclusive fullscreen, build 26200;
- harness 18 modules and PresentMon-2.6.0-x64.exe b2a706bc... with its arguments.
- Against M2's 95d96878...: launchSpec, mods[0] (the helper), world, views, resourcePacks.set, settings' resourcePacks line, suite and harness (acceptance.py) differ, so every M2 threshold is void here (P18).
- From the first calibration session the identity is frozen (plans/m3.md section 4). A moved cap (step 3) changes suite and so the hash; the identity is re-checked before the first session.

## The driver
- As found: 32.0.31041.1004 (Win32_VideoController, dated 2026-08-16), the driver every M3 record names since m3-hello-1 (15 records); M2's 197 records name 32.0.31041.3013. It changed outside these sessions between 2026-10-15 and 2026-10-20 (643f270's handoff).
- So D66's budget run comes first whichever the call: m3-diag-alone-1, m2-diag-alone-1's spec on the deterministic set (its `run --check` holds: full, heap true, calibration null, the baseline alone at forest_noon, 19 rounds), D43's rule over it at the heap 6144 MiB and the 2 twins a session kept (budget.py rule).
- A moved cap goes to suite.json capture.reloadCap with its `why`, read by the reviewer agent, committed with the record before any calibration session; a cap under 20 would leave quick mode without its 2 twins, section 7's cap cut that needs a decision.

## The hours
calibrate's sessions (statistics.calibration: 10 a mode, 2 twins each), at the cap as found (20):
- the budget run: 1 launch, about 5 min (m2-diag-alone-1: 4.9 min);
- quick: cal-quick-4edbb05a97ab-1 to -10, 1 launch each (3 views, R 1, 2 + 3 + 3 x 5 = 20 reloads): 10 launches, about 0.5 h (M2: 27.6 min);
- full: cal-full-4edbb05a97ab-1 to -10, 11 launches each (one view, R 2, 2 + 1 + 9 = 12): 110 launches, about 3.4 h (M2: 121 in 223.8 min);
- the known positive, SHADOW_QUALITY -1 over the baseline beside the twin: quick 1 launch (about 3 min), full 11 launches (about 20 min);
- in all 133 launches, about 4.5 h, each announced; a twin beyond the threshold adds a mode's shadows run once.
- A moved cap holds 2 views a full launch at 30 (6 a session: 60 calibration launches), 3 at 40 (4: 40), so about 0.5-0.75 h less.
- The machine left alone throughout: D42 waits for 30 s without input and no other 3D load before each launch; a message to this session counts as input; NoMachine disconnected (it composed m2's -5-p9: memory), check-ins from another device. The displays held on by calibrate's and run's request and a scratch hold between commands.

## Checks
- Start (13:55 ADT): branch m3 clean at de68869; 1024 passed; verify docs 35 files, 0 violations.

## Open questions
- The perf settle (capture.settleS afterReload 1.5 s, M3.P09's open question), the user's call before the freeze: M2's full calibration at 1.5 s read each view's mean second-half GPUBusy change within -0.84 to +0.04 % (110 valid captures a view, nether_soul 100; rain the largest), the four views still re-meshing at 1-2 s at -0.23 to -0.02 %, so no sign of terrain arriving inside a window; keeping it is the recommendation.
- Carried from M3.P09's handoff (de68869): the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the beacon beam and clouds; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; D72; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Commits and time
- This stop's handoff, after de68869.
- M3.P10 so far: about 0.1 h active from 13:55 ADT; machine: none.

## Next
The user's go and driver call; then the budget run (step 3), `uv run optilux calibrate --mode quick`, then `--mode full` (step 4), resumed by a rerun if one stops.
