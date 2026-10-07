# Handoff
Status: M1 closed pending merge: 0.01.13.0 (debug, timing and the acceptance re-run) is the last phase on m1, and the milestone PR awaits the user's rebase merge, which creates release v0.01.13.0 (URL pending); /optilux-next prints the Release prompt.

## Contents
Outcome · Runs · Timing · Open questions closed · Debug · Critique · Optimize · F4 for the cap · Choices · Not done · Open questions · Commits and time · Next

## Outcome
- M1's exit (roadmap.md#m1-game-control), as of 0.01.13.0: every M1 verb runs with its tests green; the 17 commands answer as mod-protocol.md specifies; m1-acceptance-10 holds A1, A2, A3, A4, A7, A9 and A10 passed and F4's table on the final jar and configuration; snapshots/provisional/ hashed and config/views/provisional.json committed; dev session 1 done; optilux-plan built; the bench world's seed and views found with the user; the QA pass run as 0.01.12 and 0.01.13. Pending at the commit: CI on this push, the PR, the user's rebase merge, the release.
- Start gate (15:31:59 ADT): m1 at e666b13, equal to origin, clean; 420 tests in 12.4 s; `mod test` 82 passed on jar c971da15... (the store's copy equal); verify docs 0 violations.
- The jar is unchanged (c971da15..., 0.01.12.4); no `mod build`. Six launches, all bench tier, each announced; runtime/ written only by `launch`, `run` and the game, and one file by hand (below); no system setting changed.

## Runs
- m1-acceptance-8 (15:37 ADT): stopped by the user, who was at the computer (focus.lost three times; A2's first attempt missed); the interrupt ended the process tree during A2's retake, so no record was written (raw kept: the request log, a4/, a9/, a2/, the session's latest.log copied after). A4, A7 and A9 had passed in its output. Its A4 copy, left in shaderpacks/, was deleted by hand (the run's own file; `run` refuses to start beside it).
- m1-acceptance-9, the timed run (borderless, the suite's window then): ok, 19:16:36-19:20:01 UTC; A1, A2, A3, A4, A7, A9, A10 passed, F4's table; snapshot 69d23fa3... (73 files) retaken first; harness e666b13, clean.
- m1-acceptance-10, the final configuration (exclusive fullscreen, below): ok, 19:38:09-19:41:36 UTC; snapshot 1b6bc36d5a1fe35b87e06957cd2dc73af3faa1f06a8c7d25a53c9f070d688da9 (73 files), retaken after the probe. A9: 1,196 PresentMon rows, all Hardware: Independent Flip; 120 rows for 120 stamps; swap offset median -0.1623 ms, max size 0.4167 ms (limit 1 ms, shortest frame 9.82 ms); head offset median 13.07 ms; CTRL_BREAK exit 0, no session left, 120 PNGs deleted. A2: each view's F2 screenshot equals one of 24 distinct frames on the first attempt. A3: centre and wrap equal on all three views. A4: iris-compile-error in 0.22 s, recovery 0.339 s, ready 1.34 s, one frame. A7: T opened ChatScreen and (200, 100) turned yaw 135 -> 165; blocked, 160 frames, nothing moved; after, yaw 195. A1: no optilux pipe, the inert line, 9 mixins declined, 0 applied, 73 threads with none of the mod's, WM_CLOSE exit 0 in 4.1 s. A10: selftest passed (2.91 s).
- 0.01.12's paths live in -9 and -10: each session's request log checked (932 lines, the token absent); no stray answer; hook failures and Iris loads outside a reload counted, 0 each; options.txt 24 of 24 keys, iris.properties 5 of 5 and Sodium's flags and text read back; options.txt recorded as the game read it (174 unwritten keys); A2 pressed only with the game's pid in the foreground; A1's three controls saw the mod (pipe listed, 9 mixins, threads optilux-pipe and optilux-worker-1); the driver (32.0.32015.2008) and the other JVM (VS Code's) recorded.

## Timing
m1-acceptance-9, 215 s by the tool's stamps around the verb (205 s between the record's startedAt and endedAt); -10 split the same within 2 s each (218 s). Seconds, from the request log, the record and the tool's stamps:
- 6.0 before the launch (uv, the spec, both tree hashes, the system), 0.3 the gate, hashes and files, 13.2 start to join;
- 3.7 the mod's pipe, hello and frames advancing (3.1 s until the first frame after the join), 3.7 world.wait to the start reload (selftest 2.7);
- 30.0 the GPU warm-up (capture.gpuWarmupS);
- 7.1 the first view (ticks.step 120: 6.0), 3.6 A4, 3.1 A7;
- 50.7 A9: ready 1.0, PresentMon's first rows 2.1, the capture 44.5, stop and match 3.1;
- 41.8 A2 and A3 on three views (each A2 capture 9.0-9.1; each dimension change 1.8 to place, 4.0 to settle);
- 28.3 F4 (50 reloads of 0.47 s median, six memory rows), 1.4 home and quit;
- 17.7 A1's launch (join 13.0, WM_CLOSE 4.0), 4.0 the record and the verb's exit (both ends include a tool call).
- Frame rate: over 30 fps more than a minute in (the request log's stamps): 97 to 171 fps between 98 and 134 s after the connection, outside captures and reloads; the harness's SendInput (A7 at 51 s, A2's F2 presses) counts as input, so the session never went a minute without it. The probe's launch held 100 s with no input at all: 99.7 fps from its first frames.index to its quit (its request log), 98.0 fps from 60 to 75 s and 98.8 from 75 to 105 s after the start (PresentMon).

## Open questions closed
- PresentMode: the window mode. One variable, one launch (the probe, `launch spike --set exclusiveFullscreen=true --quit-after 100`, PresentMon from the join): Hardware: Independent Flip on 8,723 of 8,723 rows, PresentRuntime DXGI, at 3840x2160@240 (the desktop's mode); borderless read Composed: Copy with GPU GDI, PresentRuntime Other, on every row of -8 (1,154) and -9 (1,183). The file Optilux writes (options.txt) caused it, so it is fixed as the row says: suite.json display.window exclusive fullscreen, exclusiveFullscreen true; four tests moved with it; measurement.md#validity carries the evidence; -10 shows the fix live.
- `/function` without `/return`: no success. In the pinned jar's bytecode (javap -c -p), FunctionCommand.queueFunctionsNoReturn hands the source's callback to CallFunction, which makes it the new Frame's returnValueConsumer; only Frame.returnSuccess and returnFailure call that, and only ReturnCommand's executors and FallthroughTask (`return run`) call those. The mod's Feedback needs one success, so `command` answers succeeded false for a function that ends without `/return`. Not read live: no function exists in the client jar, the four bench jars or either world, and runtime/ takes no hand-written file. measurement.md#session's view functions end in `return 1`; M2's prep sees it live with its first function.
- D30's candidate worlds: deleted by the user; saves/ held bench_263 and spike only.

## Debug
Read: the session's latest.log of -8, -9 and -10, A1's, the probe's; the request logs of -8, -9, -10 and the probe; PresentMon's logs.
- From Optilux code: one WARN per session, A4's own (`shaders.reload of optilux-a4-broken-... failed ... iris-compile-error`), with Iris's ERROR and its ShaderCompileException through IrisAdapter.reloadNow; the request log's only error answer is the same iris-compile-error. Expected: A4's evidence.
- Explained, no change (low): the mod's command log line doubles a leading slash (`command //weather clear`, known since 0.01.08; a jar change for a log line would move the jar's identity for nothing); `time set` logs succeeded false for 26.3's "already set" (set_time counts it as done); the selftest's capture sends one capture.frame and no capture.done (the done event belongs to frames.capture's handler; no item reads it).
- Not Optilux code: Iris's refmap and Sodium-mixin warnings, Sodium's AMD workaround, the PerfOS registry note, vanilla's offline chat key, "Requested post effect does not exist: minecraft:end_of_frame", Complementary's block ID map (57 lines, stone_slab variant); PresentMon's note that targeting by name needs elevation (the harness targets the pid).
- Found by the runs, assigned to M2: a run killed from outside writes no record and leaves A4's copy (-8); the next `run` refuses the copy.

## Critique
Reading 2 of D31: gpt-6-astra, xhigh, repo mode, on optilux/record.py and optilux/session.py at e666b13 after the line "What in these two files would make M2's calibration untrustworthy or its loop slower?" (47,185 characters), checked against a `git archive HEAD` copy given its own `git init` (results/, tests/fixtures/, uv.lock, docs/sources/, docs/prompts/, docs/plans/ and docs/templates/ left out; 156 files). Started 18:11 ADT with Codex's 5 h window at 24 % (the one-line check at 16:55: gpt-6.1-sol, effort low, resets 19:41 ADT), not at 10 % or under as D31 says: the user chose to run it now rather than wait (2026-10-07). It ran 225.8 s, 0.63 M tokens in (0.55 M cached), 6,499 out; the window went 24 % to 41 %; no stop at the limit. Five findings, each read at its source; each holds; none is fixed here, as none moves an M1 record (nothing in M1 matches identities; acceptance runs hide the GUI everywhere for A2's parity), so m1-acceptance-10 stays the final record:
- c1, high: session_start hides the GUI for the whole session and settle_view never shows it for entities, whose held torch measurement.md#session keeps. Assigned to M2 already (roadmap.md's "The entities frame showed no hand": M2's session sets it per view).
- c2, medium: identity holds neither the harness nor PresentMon's build and flags. Assigned to M2 already (0.01.12's id3, id4).
- c3, medium: the launch spec and views are hashed after the session, so an edit during a run would be recorded as the run's input. Assigned to M2 already (0.01.12's id7).
- c4, medium: the reference pack is in identity twice, through the platform file's referencePacks (platform_identity hashes every top-level key) and iris.properties' shaderPack in settings, though measurement.md#calibration records the baseline pack and never matches it (user, 2026-10-06): a new pin would force a recalibration. Assigned to M2 with the identity rows.
- c5, medium: a failed selftest (a probe's exception comes back as `pass: false` in a normal answer, Selftest.check) does not stop the session; record_status fails the run at its end. Acceptance runs keep going for each item's evidence; assigned to M2: a calibration or measurement session ends at once.

## Optimize
No change: each gain moves identity or the jar, or shortens acceptance runs only; handed to M2 in roadmap.md#qa-pass-open-questions with the numbers above: A9's 44.5 s is bound by the four PNG writers (about 1.4 s per 4K frame each, 2.8 frames a second; 18.8 ms median between captured frames, 10 ms uncaptured), not the render thread's readback; the warm-up's 30 s; `ticks.step 120`'s 6 s per weather change; A2's 9 s per view; 13-14 s per join.

## F4 for the cap
- -10: heap after GC 739.3 -> 2,397.5 MiB and private bytes 12,888.8 -> 15,205.7 MiB over 50 reloads: 33.16 MiB heap and 46.3 MiB private per reload; reloads 0.464-0.509 s, median 0.477. -9: 33.11 and 44.8 MiB.
- m1-acceptance-7 (0.01.09): 20.05 MiB heap and 72.7 private per reload, median 0.331 s. There F4 ran after the overworld view only; in -9 and -10 after all three dimensions, in the End. Not separated.
- For M2: at 33 MiB a reload from 739 MiB, the 6 GiB heap fills near 160 reloads, so capture.reloadCap's 288 (ALC's) would not hold; the cap comes from the worst case.

## Choices
- F4's 50 reloads in the timed and final specs, as -7 ran.
- The final acceptance run taken before the critique, so exclusive fullscreen met A2, A7 and A9 early; it stays the final record, as nothing in the run path changed after it.
- m1-acceptance-8 keeps no record: none was written by hand.
- The window-mode fix taken as its row says; its alternative, borderless with M2's validity accepting composed copy, stays open to M2.

## Not done
- D31's start rule (10 % or under): reading 2 started at 24 %, by the user's choice.
- The `/function` row's live read (above); the answer comes from the bytecode.
- Pending at the commit: CI on the push, the PR, the merge and the release (the Release prompt).

## Open questions
Each in roadmap.md#qa-pass-open-questions with its phase or milestone:
- A run needs the machine to itself; exclusive fullscreen on two displays minimizes on a click on the other one (M2; when runs happen is the user's).
- A run killed from outside writes no record (M2).
- The session's time split and A9's capture (M2); F4's cap (M2, roadmap.md#findings-assigned F4).
- Reading 2's c4 (the reference pack in identity) and c5 (a failed selftest ending a calibration session), with c1-c3 (M2).
- The live world against its snapshot, Gradle's other downloads, 0.01.12's review rows for M2 (M2).

## Commits and time
- 0.01.13.0: Debug, timing and the acceptance re-run on the final jar; then this close-out (handoff time and CI). Earlier commits and versions: git log.
- 0.01.13: 15:32 ADT to the commit at 18:21: 2.8 h against 2 h. Of it, 1.8 h was waiting on the user: m1-acceptance-8's stop to the go to rerun (15:40-16:14) and the question on D31's start rule (16:55-18:11); the work, launches included, about 1.0 h.
- CI on the phase commit: green, run 37688757828, 1m44s (its serial test step 65 s, pyright 5 s).
- M1: 14.5 h through 0.01.12 (its handoff), 1.3 h for 0.01.12's close-out and patches .1-.5 (14:05-15:24 by the commit log; no handoff gives it), 2.8 h here: about 18.6 h against 28. Tripwire: M0-M3 55.8 h, trip at 111.6 h; actuals about 21.9 h (M0 3.3, M1 18.6).

## Next
/optilux-next prints the Release prompt (/optilux-release): verify docs, the tests and `pack release --check`, the push, the PR `0.01 Game control: <what it delivers>`, its checks; after the user's rebase merge, the release v0.01.13.0 with optilux-0.01.13.0.zip, then the switch block to m2 and M2's Plan prompt.
