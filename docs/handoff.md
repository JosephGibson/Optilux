# Handoff
Status: the latest stop: M3.P10 halted by the user (15:13 ADT) after quick mode's calibration and six parts of full mode's first session; the cap unmoved under the new driver. Next: `calibrate --mode full` resumed at cal-full-4edbb05a97ab-1-p7 after the user's go.

## Contents
Outcome · The halt · Choices · Checks · Open questions · Commits and time · Next

## Outcome
Last phase: M3.P09
- The go (14:08 ADT, 2026-10-23, user): the driver as found, 32.0.31041.1004 (D66); capture.settleS kept at 1.5 s before the freeze (the open question of M3.P09's handoff).
- Step 1: identity 4edbb05a97ab879a7dae07e42c003a8067817e310897f608a8121d4976b51d40 (`run --check --json` on calibrate's quick spec, re-checked equal at 3a97916 before the first session); frozen since 14:26 ADT.
- Step 3, m3-diag-alone-1 (14:16-14:20 ADT): D43's rule (budget.py rule) gives heap 6144 MiB, cap 20: heap 230, private bytes 20, drift 20 (onset reload 22, as m2-diag-alone-1's).
  - The leak holds under 32.0.31041.1004: 594.7 MiB of private bytes and 580.3 MiB of GPU memory a reload; the game's dedicated GPU memory 3,152 MiB at reload 2, 13,205 at 20 (M2: 3,254 and 13,574).
  - Status failed on F4's 2 GiB guard at capture 37, 36 of 36 captures valid; the machine had 11.5 GiB available at reload 2 (M2: 18.3).
  - The cap unmoved: no suite.json change, no reviewer pass (step 3 asks one of a moved cap), the identity kept.
- Step 4, quick: quick-4edbb05a97ab879a7dae07e42c003a8067817e310897f608a8121d4976b51d40 from cal-quick-4edbb05a97ab-1 to -10 (14:26:41-15:01:52 ADT), each ok, 20 nulls.
  - Thresholds (k 1 of 20): every one the 0.5 % floor, per view and geo-mean.
  - Largest null |delta| (recomputed from the file's nulls): forest_noon 0.234 %, nether_crimson 0.338, end_dragon 0.178; geo-mean 0.124 (M2: 0.45 and 0.19).
- Full, halted: cal-full-4edbb05a97ab-1-p1 to -p6 (forest_noon, ocean_sunset, cave, night, underwater, entities), 15:01:57-15:12:59 ADT, each ok; p7 (rain) never launched.
- Not yet run: full's other 104 launches, the shadows-off runs (step 5), the M2 refusal, review, docs (steps 6-10).

## The halt
- A Claude Code restart about 14:55 ADT ended this session's tracking of calibrate's background command, not its processes: the chain (quick, then full once quick exited 0) and the scratch display hold ran on.
- About 14:58 the user asked to finish quick and hold before full's 110 launches. Ending the chain's bash parents, and then a watcher on calibrate's pid, were refused by Claude Code's auto-mode classifier; quick finished and the chain started full at 15:01:52.
- The user's halt (about 15:09): Ctrl+C sent to calibrate's console at 15:10:51 was ignored (its process group has Ctrl+C disabled). A watcher then waited for p6's record and ended calibrate at 15:13:02 in p7's D42 wait, no game running.
- Left clean: no p7 record or raw folder, shaderpacks/ only Unbound's zip, iris.properties as the harness leaves it, no optilux ETW session; the scratch hold released at 15:13:31.
- A rerun of `calibrate --mode full` resumes split session cal-full-4edbb05a97ab-1 at its first part without an ok record (run-record.md#split-sessions), so p1-p6 count.

## Choices
Neither the prompt nor the plan names these:
- The budget run's name m3-diag-alone-1, its spec m2-diag-alone-1's with resourcePacks deterministic.
- Quick committed at the halt with its 10 records; full's six parts in a commit of their own before this handoff.
- A rerun drives one calibrate per background command, never chained, so a hold between modes needs no stop.

## Checks
- Start (13:55 ADT): branch m3 clean at de68869; 1024 passed; verify docs 35 files, 0 violations.
- Before 3a97916 and 7e541c1: 1024 passed; verify records 0 violations (239, then 255 records); CI green on 5dc7848, 3a97916 and 7e541c1, each watched to its end.

## Open questions
- When to resume: full's 104 launches (p7-p11, sessions 2-10), about 3.2 h, then shadows off (1 + 11 launches, about 25 min), the machine left alone.
- Available memory 6.8 GiB below M2's at the budget run's start: what ran beside it? D42 reads only the 3D engine and input; a 12-reload part stays far from F4's guard.
- nxplayer.bin (NoMachine) read 2.7 % of the 3D engine in D42's wait before m3-diag-alone-1, under 2 % before its launch.
- Carried from M3.P09's handoff (de68869): the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the beacon beam and clouds; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; D72; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Commits and time
- 5dc7848 (the stop before the hours), 3a97916 (the budget run), 7e541c1 (quick's calibration and records); then full's six parts, then this handoff.
- M3.P10 so far, 2026-10-23: about 0.8 h active (13:55-14:27, 14:56-15:20 ADT); machine 17 launches, about 51 min (budget 4.5 min, quick 35.2, full's parts 11.0).

## Next
The user's go; then `uv run optilux calibrate --mode full` alone in the background (it resumes at cal-full-4edbb05a97ab-1-p7), then M3.P10 step 5's shadows-off runs and steps 6-11.
