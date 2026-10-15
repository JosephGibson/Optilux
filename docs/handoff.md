# Handoff
Status: the latest stop: M2.P09 at its named stop, the user's go for the calibration hours; the identity the calibrations will carry checked, nothing launched. Next: M2.P09 step 3 after the go.

## Contents
Outcome · The identity · The hours · Checks · Open questions · Left alone · Commits and time · Next

## Outcome
Last phase: M2.P08
- M2.P09 step 1 done (02:55 ADT, 2026-10-15): `run <a quick-mode calibration spec of the baseline> --check --json` ok, nothing launched, no groups (quick mode is one launch), calibration null; identity sha256 95d9687847308453839250cc292ce01bde79b39bc4f4103eac593f5155a5463e.
- Step 2, the stop the prompt names: the user's go for about 4.6 h of machine time, the machine left alone throughout.

## The identity
From this session's `run --check --json` (the spec in the scratchpad: kind calibration, mode quick, the baseline Unbound r5.9.3 with the played profile, D35):
- platform 3bc69860..., tier bench; launchSpec mc-26.3.launch.json 9bd33805...; mods 4 jars;
- world snapshots/bench_263, tree 65e7ae73..., 116 files; views bench_263.json 9b05721e...;
- resourcePacks standard (Faithful 64x Release 15, bc534dfb...); settings 24 written keys, the overrides, token, Sodium's options, iris and the unwritten keys;
- suite 8fe79f13...; java jdk-25.0.4.1+1, release 86e5e516..., heap 6144/6144 MiB, no args;
- system AMD Radeon RX 7800 XT, hags true, 3840x2160, exclusive fullscreen, build 26200;
- harness 17 modules and PresentMon-2.6.0-x64.exe b2a706bc... with its arguments.
- From the first calibration session the identity is frozen (plans/m2.md section 4): no change to the jar, the measured modules, suite.json, the platform file, bench.json, the world or the views without recalibrating.

## The hours
calibrate's own plan, read without launching (statistics.calibration: 10 sessions a mode, 2 twins a session; D43 with D47's warm-up pass):
- quick: cal-quick-95d968784730-1 to -10, 1 launch each (3 views, R 1, 2 + 3 + 3 x 5 = 20 reloads): 10 launches, about 0.5 h (about 3 min a launch, m2-measurement-1's 2.4 min plus the restore and D42's wait);
- full: cal-full-95d968784730-1 to -10, 11 launches each (one view a launch, R 2, 2 + 1 + 9 = 12 reloads; parts -p1 to -p11): 110 launches, about 3.7 h (about 22 min a session, suite.json estMinutesPerSplitSession);
- then the known positive, SHADOW_QUALITY -1 (P18) over the baseline beside the twin: one quick run (1 launch, about 3 min) and one full session (11 launches, about 22 min);
- in all 132 launches, about 4.6 h, each announced; the machine left alone throughout (D42: 30 s without input and no other 3D load before each launch; a focus.lost ends a session invalid), the displays held on by calibrate's and run's display request.

## Checks
- Start (02:55 ADT): branch m2 clean at 11ab7ed, up to date with origin; 790 passed; verify docs 32 files, 0 violations.

## Open questions
- Carried from M2.P08's handoff (git d160287 and 11ab7ed): D43's closed "no warm-up pass" and section 7's 2-view text against D47; a pack near 1 ms a frame meets PresentMon's row loss; the queue sign; nxplayer.bin; orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- measurement.md: 37 bytes left; its thresholds (step 8) need a cut first.

## Commits and time
- This stop's handoff, after 11ab7ed.
- M2.P09 so far: about 0.1 h active from 02:55 ADT; machine: none.

## Next
The user's go; then `uv run optilux calibrate --mode quick`, then `--mode full` (M2.P09 step 3), resumed by a rerun if one stops.
