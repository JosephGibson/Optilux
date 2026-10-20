# Handoff
Status: the latest stop: M3.P05 stopped at its exit, the jar's aligned, ready-triggered and image-less captures built, reviewed and committed, the exit run failed on A9 with the displays off; what the rerun of the exit starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P04
- Stopped (prompt: a Done-when not met; one launch allowed, no rerun unasked): m3-capture-1 (results/records/m3-capture-1.json, committed) ended `failed`: A10 pass, A9 FAIL, A2 FAIL (not run).
  - A9: PresentMon (2.6.0, session optilux-m3-capture-1) wrote 0 rows within FIRST_ROW_TIMEOUT 30 s, before A9's capture began; the session ended there (WM_CLOSE, exit 0), so A2 never ran.
  - Cause: the displays were off. GetLastInputInfo read 3,594 s idle at 17:14:29 ADT (the launch 17:11), the AC display timeout 600 s (powercfg 0x258), so they went off near 16:24 while the code was written; displays off give 0 rows (memory, f402c8c). `run` holds the displays on and refuses them off only for a spec with a mode (optilux/verbs/run.py, the runner's `spec.mode is None` branch), so an acceptance spec with A9 launches unguarded. AMD's PresentMon (RSXTraceSession) ran after the join as in m1-acceptance-10 and m2-a8-2-p1, whose rows came, so it is not the cause.
  - A10 in game, the new selftest (record: session start, selftest): pass in 5.80 s; capture: frame 420, sinceReload 285 = 420 - reloadFrame 135, at phase 1 of 4; ready held at frame 418 after 3.30 s (limitedBy graph, 277 frames judged; Sodium's check held at 2.51 s with 81 gap frames), 420 the first frame at the phase from it; 3840x2160 decoded at the target's size.
- The jar: optilux-helper-0.1.0.jar sha512 ed1f2a39e4300fec8adf94b0bc06d8fea4ae7bcf6efeeed6f568ed601d21157052897afecf5fa0bfe5cfab2d74ea245fb3f352a395dfaba5464486dbe1ac86a5 (174,481 bytes), `mod build` into the store, `mod test` 125 passed against it; the run's identity carries it.
- Not shown: A9's offsets and its capture time on stamps alone (F17's figure), A2 on the new jar. runtime/ written only by `mod build`, the run's world restore, launch and the game; no system setting.

## What changed
- The jar (077ebc4): frames.capture's `align {cycle, phase}` (core/Capture.Align: a cycle dividing 720720, phase below it, judged at the capture point on Iris's counter, which Iris advances at GameRenderer.render HEAD and resets in preparePipeline, read in the pinned jar with javap), `ready {stableFrames, minSeconds}` (core/Capture.readiness: a Readiness from the request's time, judged by the new "capture" frame poll on RendererAdapter.reading(); the gate opens at the frame head where it holds and that frame is the first taken; its report plus that frameIndex in the answer and capture.json) and `images` (default true; false: stamps only, no readback, PNG or capture.frame, the manifest written at the last take); flush and after `unsupported` (M5); the capture point and the poll skip a capture whose request was answered; selftest's capture ready-triggered (10 stable frames) and aligned (4, 1), its counter checked against the reload check's reloadFrame, bounded at 60 s; commands.json without shaders.dump, frames.capture with ready, images and the `ready` result. JUnit 117 to 125.
- The client (8fa6ebb): frames_capture's align, ready and images; verify_manifest for image-less captures and the ready report; check_schedule (an aligned frame off its phase, a ready-triggered first frame not the first after the predicate: plans/m3.md section 7's stops); the fake mirrors the mod (its refusals in the mod's order, ready modelled on 7 ms frames, the clock at the last frame taken); A9 on stamps alone (a9_capture, A9_CAPTURE_TIMEOUT 30 s, the capture's seconds and images in its evidence, the PNG deletion gone). Tests 903 to 908.
- Docs: mod-protocol.md (Status, Commands, capture layout, Choreography's static capture), mod.md (Status, 6, 8, 11, 12; 298 bytes of duplicates cut first, 62 left), offline.md's L1 row (D60), CHANGELOG.md's 0.4.0 entry.

## Review
Three reviewer agents, each finding read at its source.
- Jar, correctness: 6 (1 high, 5 low). The high (the doc table behind commands.json) was read before the docs were written; fixed in the same commit. Fixed: selftest's aligned check judged the capture's own filter (now against reloadFrame); selftest's capture had no bound of its own; no test of `ready: null` present; untested align with ready, every and an interval, and readiness's parsed values; a test race.
- Jar, concurrency: 5 low. Fixed: 1 the gate could open and frames be taken between the early answer and the interrupt (the request's liveness checked); 2 a stopped capture's gate still read the renderer; 3 the test's 0.3 s timeout and sampling race, plus a world-leave case and the window's busy. Reported: 4 and 5 (Weak points).
- Client, fake and A9: 5 low. Fixed: 1 the fake's ready report ignored minSeconds; 2 the ready report not compared with capture.json; 3 the fake's refusal order; 4 the fake took `after: 0` (it predates); 5 the images guard tested. Reported: a9()'s PresentMon flow has no offline test.

## Choices
Neither the prompt nor the plan names these:
- Commit 077ebc4 carries the fake's `ready: null` so the suite stays green on the jar's commit; A9's sentences in mod.md and the CHANGELOG land with A9 (8fa6ebb).
- The exit's variant: ComplementaryUnbound_r5.9.3.zip at its defaults (profile null), as m1-acceptance-10's A9.
- The ready report names the frame whose head found the predicate held (`frameIndex`); capture.json records align, ready and images; every request states images.
- Selftest: stableFrames 10 (the session start's), align (4, 1), 60 s inside session.py's 120 s.

## Checks
- Start (16:12 ADT): branch m3 clean at f90192a; 903 passed; mod test 117 passed, the store's jar equal; verify docs 0 violations.
- Before each commit, on a tree equal to it: 903, 908, 908 passed; ruff, ruff format, pyright clean; verify docs 0 violations; mod test 125; verify records 225 records, 0 violations.
- CI green on 077ebc4, 8fa6ebb and 501d67f, each watched to its end before the next push.

## Open questions
- The display guard for A9 (user's call): `run` could hold the displays on and refuse them off for a spec whose items need PresentMon (A9, as for a mode), so a run like m3-capture-1 is refused with nothing launched. Recommended: yes, a change to run.py, a measured module (harness identity), so before M3.P10's calibration. Without it the rerun's session takes a display hold from its start.
- Carried: Nether fog and the features on neither list (M3.P04's review findings 1 and 4); the water fog colour (M3.P06, M3.P09); D66, the driver 32.0.31041.1004 since 2026-10-20; D72; the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- Concurrency 4: an image-less capture writes capture.json on the render thread at its last frame, under the capture's lock, after every stamp it records.
- Concurrency 5 (predates): a capture whose worker stalls before `run` across a world leave and rejoin could take a newer capture's slot; not reachable in practice.
- A9's flow is tested live only; the fake's ready is a model on 7 ms frames.
- Margins: AGENTS.md 26 bytes; measurement.md 23; platform.md 56; mod.md 62; workflow.md 199.

## Commits and time
- 077ebc4: the jar with its JUnit tests, commands.json and docs. 8fa6ebb: the client, the fake and A9 with their tests. 501d67f: m3-capture-1's record. Then this handoff.
- 2026-10-20 16:12 to about 17:25 ADT: M3.P05 took about 1.2 h of its 3 h so far, the exit undone. Tripwire: actuals about 53.5 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.8, M3.P02 about 0.8, M3.P03 about 1.9, M3.P04 about 1.9, M3.P05 about 1.2); the trip at 174.6 h.

## Next
/optilux-next prints M3.P05's prompt again. Its steps 1-4, 6 and 7 are done and committed; what is left is step 5's exit (an announced acceptance run of A2, A9 and A10 on bench_263, the next name m3-capture-2, with the displays on: the guard above, or a display hold from the session's start), then steps 8 and 9 and this handoff with `Last phase: M3.P05`.
