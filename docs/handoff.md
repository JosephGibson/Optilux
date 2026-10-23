# Handoff
Status: the latest stop: M3.P09 done: A5 judged over 33 waits (failed, 17 of 33, so the visual settle stays the floor), the visual settle lengthened by section 7's one fix, the hello pack identical across two full-mode sessions on all 11 views, and the A/A twin first among the Ci.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P09
- The exit holds, shown in this session (2026-10-23, ADT), each launch announced and run with the machine left alone:
  - A5's records judged (D68): m3-a5-1 (07:27:52-07:30:55, waits 1-18, its entry waiting) and m3-a5-2 (07:32:39-07:35:32, waits 19-33, naming it by `remeasures`), one identity, the hello pack at HEAD (zip sha512 d86371b7...).
    - `compare m3-a5-2`: A5 FAIL: 17 of 33 waits' first frame after the predicate equal to its reference (decoded pixels); rate 0.5152 (17 equal of the 33 waits judged); the record's own verdict the same.
    - Per view: forest_noon, cave, rain, nether_crimson 3/3; nether_soul, end_dragon 2/3; night 1/3; ocean_sunset, underwater, entities, end_city 0/3.
    - Every miss is unbuilt terrain (the frames side by side, scratchpad): distant chunks missing at the first frame after the predicate, 0.02-0.95 s after the reload, all of them there 3 s later; the predicate held with limitedBy graph. D68's miss path: the settle stays the visual floor, the rate recorded; m3-a5-2 ended failed on "items failed: A5".
  - m3-determinism-1 (07:39:07-07:41:12), full mode, the old settle (1.0 s, underwater 2.0): ok, 11 of 11 valid, pairs moving at ocean_sunset, underwater, entities and end_city: their first frames still re-meshing (end_city: 16,490 pixels at the horizon).
    - Diagnosis (section 7: readiness): at every view the late frames (A5's three references, 3.1-6.9 s after the reload, and this session's second frames, 3.0 s, underwater 4.0) carry one sha256 across all three launches; the first frames match it at 7 views and miss at the 4 moving ones.
    - The one fix (5f47025): suite.json capture.visualSettleS default 4.0 s, underwater 5.0 (the earliest final frame plus a second), the dimension change's addition 3.0 kept; visualSettleWhy cites the records.
  - m3-determinism-2 (07:45:22-07:47:59) and m3-determinism-3 (07:48:05-07:50:43), full mode's 11 perf views, the new settle: each ok, 11 of 11 valid, no pair moving.
    - `compare m3-determinism-3 --against m3-determinism-2`: identical on every view (forest_noon, ocean_sunset, cave, night, underwater, entities, rain, nether_crimson, nether_soul, end_dragon, end_city), each pair identical too.
    - Every frame of both equals, by sha256, the late frames of the three launches before: the same bits across five launches.
  - The measured schedule's test puts the twin first: test_the_schedule_brackets_each_candidate_between_two_baselines_the_twin_first and test_a_calibration_sessions_schedule_is_unchanged_by_the_twin_first passed.
- Facts (section 9): hello pack zip d86371b7... (unchanged since M3.P08); bench_263 snapshot 33a4074d... (128 files); static-textures pack ff44b3cc...; glslang 16.6.0, RGA 2.15 unchanged; the suite identity now 7ba0cc9d... (capture changed); no calibration of the deterministic set yet (M3.P10).

## What changed
- d0702e5: A5 as a runnable acceptance item (record.RUNNABLE).
  - record.a5_waits: three laps of the perf views, each ordered as a measured pass (lap, the ramped weather first).
  - record.a5_share: a launch takes the waits the cap leaves (2 + 18); a second names the first by `remeasures` and takes the rest; a first is continued once; the name `-` is refused.
  - measure.a5_body and a5_wait: arrive, a reload, one frames.capture (ready 10 frames and minSeconds 0, aligned on the pack's cycle, the reference the view's visual settle plus 2 s after the first frame); each wait's entry in A5's evidence.
  - run: A5's portion of the acceptance body, the view functions checked, the second held to the first's identity and zip (a5_same), A5 judged after the record's status (judge_a5) by `compare -` in a child process, so visual.py stays out of `harness`.
  - compare: A5 records, by name or on stdin: both launches' waits, each frame held to its sha256, decoded pixels (visual.difference); session.record_status: a waiting item (pass null) never fails; the launch announcement and `run --check` name A5's waits.
- 2f18aae: D65, measure.schedule takes the twins first among the Ci (a calibration session keeps its order); suite.json statistics.schedule's text, measurement.md#session step 7, CHANGELOG.
- ffb226c: compare's rate line counts the equal waits of those judged.
- 5f47025: the visual settle's fix (suite.json, measurement.md#readiness, shader.md's water-vision line).
- b17f0da: the five records; mod.md 7 and 12 (A5 failed, 17 of 33), measurement.md#visual-protocol (the hello pack bit-identical on 11/11), CHANGELOG 0.4.0 (A5, the determinism result).

## Review
The reviewer agent on A5 and the schedule (correctness; identity): 8 findings, 1 medium and 7 low, each read at its source and fixed before d0702e5:
- Medium: a first launch could be continued by more than one second, so a rerun half could replace a judged miss. record.a5_continued now refuses it, and compare_a5 checks it again.
- Low:
  - A5 was judged before the record's status. It now waits until the status is known, as a measured run's items do.
  - `compare` refused judged misses. A judged record is now re-judged.
  - The rate counted flagged waits. It now covers the waits judged.
  - A first launch could leave more waits than one more launch holds. It is refused.
  - The announcement left A5 out.
  - judge_a5 dropped the child's stderr. Its last line is kept.
  - `-` was a legal run name. It is refused.
- Its clean reads: nothing pulls compare.py or visual.py into run.py's closure (`--check` lists 18 modules, neither among them); the schedule change leaves stats' bracketing, split_groups, planned_reloads and calibrate unchanged.

## Choices
Neither the prompt nor the plan names these:
- The second launch names the first with `remeasures`, the key A8's second session uses, rather than a new one.
- A wait's two frames come from one frames.capture, so the reference lies at least the settle plus 2 s after the first frame, later than after the reload.
- A flagged wait (event, incomplete) is judged neither way and blocks a pass; none was flagged.
- After m3-determinism-1's moving pairs, section 7's trigger, the unchanged second session was not run: the fix went in, then both sessions ran again. So five launches against the plan's four.
- The fix's figures, 4.0 and 5.0 s, are the earliest final frames seen plus a second.
- The displays read off (idle since 06:40) through all five launches. Acceptance and visual runs read no PresentMon, and m3-capture-1 had shown frames render with them off.

## Checks
- Start (06:40 ADT): branch m3 clean at 69d8155; 1016 passed; verify docs 0 violations.
- Before each commit, on a tree equal to it: 1023 (d0702e5), then 1024 passed at 2f18aae, ffb226c, 5f47025 and b17f0da; ruff, ruff format and pyright clean; verify docs 0 violations; verify records 0 violations (238 records at b17f0da).
- CI green on d0702e5, 2f18aae, ffb226c and 5f47025, each watched to its end before the next push; b17f0da's and this handoff's watched before the report.

## Open questions
- The readiness predicate after a reload: in A5 it held 0.02-0.95 s after `shaders.reload` (limitedBy graph), before Sodium's re-mesh showed in any term read, 16 times in 33. A mod change that sees the re-mesh, then A5 again, could make the predicate the floor. Whose phase is the user's call; the settle covers it now.
- Perf windows start 1.5 s after a reload (capture.settleS). At ocean_sunset, underwater, entities and end_city frames were still re-meshing at 1.0-2.0 s, so a window there may open on terrain still arriving. The bracketing and the halves check bound it; whether to lengthen settleS before M3.P10 freezes the identity is the user's call (no evidence on GPUBusy yet).
- Settled here: the water fog colour (its 3 s ramp lies inside underwater's 5.0 s settle; underwater identical across sessions).
- Carried:
  - `screen = BENCH_DETERMINISTIC` reading `screen = 1` (M3.P08);
  - the beacon beam and clouds across launches (P22; the perf views show neither);
  - the moving coverage items (D64); Unbound's missing coverage-mob shadows; the hello pack's olive End stone; whether 26.3 animates textures on frozen ticks;
  - the display guard for A9; Nether fog and the features on neither list;
  - D66, the driver; D72; spider eyes and the world's difficulty (M4);
  - M2's carried list (git 7dfc2fa's handoff).

## Weak points
- The settle's margin rests on the late frames seen: one session's second frames at 3.0 s (4.0 underwater) and A5's references; a slower re-mesh on another day would show as a moving pair.
- A5 judged one predicate setting (10 stable frames); its misses say when the predicate held, not how long the re-mesh takes.
- Margins: measurement.md 3 bytes, run-record.md 9, platform.md 7, mod.md 15, AGENTS.md 16, workflow.md 199.

## Commits and time
- d0702e5, 2f18aae, ffb226c, 5f47025, b17f0da; then this handoff.
- 2026-10-23, 06:40-08:05 ADT: about 1.4 h against 2.5 h; machine five launches, about 13 min. Tripwire: actuals about 61.1 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1, P07 2.1, P08 1.8, P09 1.4); the trip at 174.6 h.

## Next
/optilux-next prints M3.P10's prompt: the recalibration on the deterministic set, after the user's driver call and go (D66); the perf settle above is an open question before it.
