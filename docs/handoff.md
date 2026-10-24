# Handoff
Status: the latest stop: M3.P10 done: both modes recalibrated on the deterministic set, every threshold the 0.5 % floor, shadows off accepted beyond it in both modes beside a twin inside it, an M2 record refused live naming resourcePacks; the reload cap unmoved under the new driver.

## Contents
Outcome · Calibrations · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P10
- The exit holds, shown in this session (2026-10-23 and -24, ADT), each launch announced:
  - config/calibrations/ holds quick-4edbb05a97ab879a7dae07e42c003a8067817e310897f608a8121d4976b51d40 and full-4edbb05a97ab879a7dae07e42c003a8067817e310897f608a8121d4976b51d40 (identity 4edbb05a..., the deterministic set).
  - m3-shadows-quick-1 (17:10-17:13 ADT, 2026-10-24): `compare`: session ok, twin +0.1782 % inside; shadows-off accept, geo-mean -10.7570 % (forest_noon -16.51, nether_crimson -0.37, end_dragon -14.55 %); 18 of 18 captures valid; the record's own verdicts the same.
  - m3-shadows-full-1 (17:14-17:34 ADT, 11 parts): twin -0.0130 % inside; shadows-off accept, geo-mean -12.2216 %, 10 views beyond (nether_soul -0.43 % not); 110 of 110 valid; the same.
  - `compare m2-shadows-quick-1 --calibration quick-4edbb05a...` refused (exit 1) on launchSpec.sha256, mods[0], world.treeSha256, views.sha256, resourcePacks.set, settings.options.resourcePacks, suite.sha256 and harness.modules["optilux/acceptance.py"].
  - `report` on both: report.html under results/raw/<run>/.
- The go (2026-10-23, 14:08 ADT, user): the driver as found, 32.0.31041.1004 (D66); capture.settleS kept at 1.5 s before the freeze.
- m3-diag-alone-1 (D66's budget run): D43's rule gives heap 6144 MiB, cap 20 (heap 230, private 20, drift 20: onset reload 22, as m2-diag-alone-1); the leak holds, 594.7 MiB of private bytes and 580.3 MiB of GPU memory a reload; failed on F4's 2 GiB guard at capture 37, 36 of 36 valid. The cap unmoved, so no suite change and no reviewer pass.
- No section 7 stop: no threshold above 2 %, no twin beyond, no launch invalid on focus, D42 never refused, no fault in a measured module (1024 passed).

## Calibrations
| Mode | Id | Sessions | Thresholds (k 1 of 20) | Largest null |delta| |
|---|---|---|---|---|
| quick | quick-4edbb05a... | cal-quick-4edbb05a97ab-1 to -10 | 0.5 % floor, per view and geo-mean | per view 0.34 % (nether_crimson), geo-mean 0.12 % |
| full | full-4edbb05a... | cal-full-4edbb05a97ab-2 to -11 | 0.5 % floor, per view and geo-mean | per view 0.45 % (end_city), geo-mean 0.07 % |
- cal-full-4edbb05a97ab-1 does not count: its underwater part (-1-p5, 2026-10-23 15:09-15:11 ADT) presented every capture Composed: Flip (flag presentMode); input reached the bench PC at about 15:09:27 (p6's D42 read 105.8 s idle), the minute of the user's halt. calibrate passed it over; its 12 records are committed with the rest.

## Review
The reviewer agent on both calibration files and the two runs' verdicts (correctness against measurement.md#calibration): 1 finding, low, read at its source and fixed here:
- Low: 423babd's handoff said full session -1's parts p1-p6 would count after the resume, but -1-p5's 10 captures were all invalid (presentMode), so the session could never count; the resume spent five launches (p7-p11, 2026-10-24 13:35-13:44 ADT) before calibrate passed it over. Calibrations and verdicts unaffected.
- Its clean reads, recomputed from the records: the nulls from exactly the listed sessions (2 twins, every view), k 1 of 20, every stored threshold; about 30 null ratios from the captures (full-7's end_city 1.0044819 the largest); the identity equal across all 155 records and both files; both runs' twin and shadows-off deltas, accept, the twin first, no capture flagged, no view unjudged; the twin monitor's window starting over.
- Its open item closed here: each file's identityHash equals record.identity_hash of its identity, and both load (`load_calibration`).
- Its observation: full mode's night nulls lean positive (16 of 20, mean +0.10 %), inside the floor.

## Choices
Neither the prompt nor the plan names these:
- The budget run's name m3-diag-alone-1, its spec m2-diag-alone-1's with resourcePacks deterministic; the shadows runs m3-shadows-quick-1 and -full-1, M2's specs with the set and the new ids.
- The user's halt (2026-10-23, 15:13 ADT) after quick and six full parts; calibrate resumed the next day (13:35), then rerun past the composed session (13:47).
- measurement.md#calibration's M2 figures replaced by M3.P10's (git keeps them); suite.json's capture.why, which names driver 32.0.31041.3013, left as frozen (section 4), m3-diag-alone-1 cited here instead.

## Checks
- Start (2026-10-23, 13:55 ADT): branch m3 clean at de68869; 1024 passed; verify docs 0 violations. Resume (2026-10-24, 13:33): clean at 423babd, 1024 passed, the identity equal to quick's calibration key by key.
- Before each commit, on the working tree (each commit's code the same, its other files records and docs): 1024 passed; ruff, ruff format and pyright clean at the end; verify docs 0 violations; verify records 0 violations (394 records with the last runs).
- CI green on every push, each watched to its end before the next.

## Open questions
- The quick twin's +0.1782 % lies inside the 0.5 % floor but above every quick null's geo-mean (largest 0.12 %); the twin monitor (0 of 1 beyond) watches it.
- Available memory 6.8 GiB below M2's at the budget run's start; nxplayer.bin at 2.7 % of the 3D engine before it (under 2 % at launch).
- roadmap.md's F27 (the leak under 32.0.31041.3013): the cap holds under 32.0.31041.1004 too, for M3.P11's findings pass.
- Carried from M3.P09's handoff (de68869): the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the beacon beam and clouds; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; D72; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- One known positive per mode; the slot bias D65 moved shows only through the twin monitor from here.
- Margins: measurement.md 65 bytes, run-record.md 9, platform.md 7, mod.md 15, AGENTS.md 16, workflow.md 199.

## Commits and time
- 5dc7848, 3a97916, 7e541c1, 108a35d, 423babd, ec6c33f (the full calibration with its 126 records), 03e6a66 (the shadows-off runs with measurement.md and CHANGELOG.md); then this handoff.
- M3.P10: about 2.1 h active against 1.5 h (2026-10-23 13:55-14:27 and 14:56-15:30; 2026-10-24 13:33-13:48 and 17:10-17:55 ADT), the halt overnight between; machine 144 launches, about 4.8 h (budget 1 in 4.5 min; quick 10 in 35.2; full 121, the passed-over session's 11 included, in 224.6; shadows quick 1 in 2.8, full 11 in 20.4).
- Tripwire: actuals about 63.2 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1, P07 2.1, P08 1.8, P09 1.4, P10 2.1); the trip at 174.6 h.

## Next
/optilux-next prints M3.P11's prompt: the close (the docs as built, CHANGELOG's 0.4.0 completed, the findings marked landed), then the Release prompt.
