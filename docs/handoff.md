# Handoff
Status: the latest stop: M3.P05 done, the jar's aligned, ready-triggered and image-less captures built and accepted (m3-capture-2), A9 on stamps alone, and what M3.P06 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P05
- The exit holds, shown in this session (2026-10-20, ADT):
  - `mod test` (17:10): 125 passed, the tested jar optilux-helper-0.1.0.jar sha512 ed1f2a39e4300fec8adf94b0bc06d8fea4ae7bcf6efeeed6f568ed601d21157052897afecf5fa0bfe5cfab2d74ea245fb3f352a395dfaba5464486dbe1ac86a5 (174,481 bytes) equal to the store's, which `mod build` put there.
  - m3-capture-2 (18:04-18:08, announced, the machine left alone): status ok, A2 pass, A9 pass, A10 pass, on bench_263's eleven views with ComplementaryUnbound_r5.9.3.zip at its defaults.
  - A9 at forest_noon: 120 stamps matched to 120 rows in the span (frames 3858-3977, consecutive); swap offset median -0.1686 ms, max size 0.586 ms; head offset median -0.0654 ms, max size 0.4385 ms; the shortest frame 12.36 ms, the limit 1 ms. Its capture on stamps alone: 1.515 s for 120 frames (F17: 44.5 s with PNGs), complete, none dropped, images false, attempt-001 holding capture.json alone.
  - A10: selftest pass in 6.94 s; its capture took frame 486, sinceReload 365 = 486 - reloadFrame 121, phase 1 of 4; ready held at frame 486 after 4.21 s (limitedBy graph, 358 frames judged; Sodium's check held at 0.47 s with 108 gap frames).
  - A2: each of the 11 views passed at its first attempt.
- m3-capture-1 (17:11) failed before it: the displays were off (3,594 s idle against the 600 s timeout), PresentMon wrote 0 rows in 30 s, and the session ended before A2; A10 passed there too (frame 420, sinceReload 285 = 420 - 135). The rerun came at the user's go with the displays on (18:04, 38 s idle).
- runtime/ written only by `mod build`, the runs' world restores, launches and the game; no system setting.

## What changed
- The jar (077ebc4): frames.capture's `align {cycle, phase}` (core/Capture.Align: a cycle dividing 720720, phase below it, judged at the capture point on Iris's counter, which Iris advances at GameRenderer.render HEAD and resets in preparePipeline, read in the pinned jar with javap), `ready {stableFrames, minSeconds}` (core/Capture.readiness: minSeconds from the request; the "capture" frame poll judges RendererAdapter.reading() until the predicate holds, and the frame whose head found it is the first taken; the report plus that frameIndex in the answer and capture.json) and `images` (default true; false: stamps only, no readback, PNG or capture.frame); flush and after `unsupported` (M5); the capture point and the poll skip a capture whose request was answered; selftest's capture ready-triggered (10 stable frames) and aligned (4, 1), its counter checked against the reload check's reloadFrame, bounded at 60 s; commands.json without shaders.dump. JUnit 117 to 125.
- The client (8fa6ebb): frames_capture's align, ready and images; verify_manifest for image-less captures and the ready report; check_schedule (an aligned frame off its phase, a ready-triggered first frame not the first after the predicate: section 7's stops); the fake mirrors the mod (its refusal order, ready on 7 ms frames, the clock at the last frame taken); A9 on stamps alone (a9_capture, A9_CAPTURE_TIMEOUT 30 s, the capture's seconds and images in its evidence). Tests 903 to 908.
- Docs: mod-protocol.md (Status, Commands, capture layout, Choreography's static capture), mod.md (Status, 6, 8, 11, 12; 298 bytes of duplicates cut first, 62 left), offline.md's L1 row (D60), CHANGELOG.md's 0.4.0 entry (one bullet).

## Review
Three reviewer agents, each finding read at its source.
- Jar, correctness: 6 (1 high, 5 low). The high (the doc table behind commands.json) was read before the docs were written, fixed in the same commit. Fixed: selftest's aligned check judged the capture's own filter (now against reloadFrame); its capture had no bound of its own; `ready: null`'s presence untested; align with ready, every and an interval, and readiness's parsed values untested; a test race.
- Jar, concurrency: 5 low. Fixed: 1 the gate could open and frames be taken between the early answer and the interrupt (the request's liveness checked); 2 a stopped capture's gate still read the renderer; 3 the test's 0.3 s timeout and sampling race, plus a world-leave case and the window's busy. Reported: 4 and 5 (Weak points).
- Client, fake and A9: 5 low. Fixed: 1 the fake's ready ignored minSeconds; 2 the ready report not compared with capture.json; 3 the fake's refusal order; 4 the fake took `after: 0` (it predates); 5 the images guard tested. Reported: a9()'s PresentMon flow is tested live only.

## Choices
Neither the prompt nor the plan names these:
- Commit 077ebc4 carries the fake's `ready: null` so the suite stays green on the jar's commit; A9's sentences in mod.md and the CHANGELOG land with A9 (8fa6ebb).
- The exit's variant: ComplementaryUnbound_r5.9.3.zip at its defaults (profile null), as m1-acceptance-10's A9.
- The ready report names the frame whose head found the predicate held (`frameIndex`); capture.json records align, ready and images; every request states images.
- Selftest: stableFrames 10 (the session start's), align (4, 1), 60 s inside session.py's 120 s.
- A second launch (m3-capture-2) at the user's go after m3-capture-1, its record committed too (501d67f).

## Checks
- Start (16:12 ADT): branch m3 clean at f90192a; 903 passed; mod test 117; verify docs 0 violations.
- Before each commit, on a tree equal to it: 903, 908, 908, 908 passed; ruff, ruff format, pyright clean; verify docs 0 violations; mod test 125; verify records 226 records, 0 violations (m3-capture-2's 260,655 bytes reported over the budget, as acceptance records are).
- CI green on 077ebc4, 8fa6ebb, 501d67f and 64531fb, each watched to its end before the next push; 6c2063d's watched before this handoff's push.

## Open questions
- The display guard for A9 (user's call): `run` holds the displays on and refuses them off only for a spec with a mode (optilux/verbs/run.py), so m3-capture-1 launched with them off. Recommended: the same hold and refusal for a spec whose items need PresentMon (A9), a change to a measured module, so before M3.P10's calibration; until then a session with A9 checks the idle time before its launch.
- Carried: Nether fog and the features on neither list (M3.P04's review findings 1 and 4); the water fog colour (M3.P06, M3.P09); D66, the driver 32.0.31041.1004 since 2026-10-20; D72; the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- Concurrency 4: an image-less capture writes capture.json on the render thread at its last frame, under the capture's lock, after every stamp it records.
- Concurrency 5 (predates): a capture whose worker stalls before `run` across a world leave and rejoin could take a newer capture's slot; not reachable in practice.
- A9's flow is tested live only; the fake's ready is a model on 7 ms frames.
- Margins: AGENTS.md 26 bytes; measurement.md 23; platform.md 56; mod.md 62; workflow.md 199.

## Commits and time
- 077ebc4: the jar with its JUnit tests, commands.json and docs. 8fa6ebb: the client, the fake and A9 with their tests. 501d67f: m3-capture-1's record. 64531fb: the stop's handoff. 6c2063d: m3-capture-2's record and A9's time in the CHANGELOG. Then this handoff.
- 2026-10-20 16:12 to about 18:15 ADT, 2.0 h elapsed, of which about 0.65 h waited for the user's go (17:25-18:04): M3.P05 took about 1.4 h against 3 h. Tripwire: actuals about 53.7 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.8, M3.P02 about 0.8, M3.P03 about 1.9, M3.P04 about 1.9, M3.P05 about 1.4); the trip at 174.6 h.

## Next
/optilux-next prints M3.P06's prompt: the deterministic set and visual runs, 3.5 h, one launch; the visual kind's captures use frames.capture's ready and align as built here.
