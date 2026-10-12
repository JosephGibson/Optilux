# Handoff
Status: the latest stop: M2.P02, `window.measure`, `state`'s framebuffer and F23's jar rows, and what M2.P03 starts from.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P02
- `window.measure {after: reload | now, skipSeconds, seconds}` on the window resource: the skip counted from the last reload's completion inside the mod or from the request, the window from the first frame HEAD past it to the first `seconds` or more later; start and end marks (frameIndex, sinceReload, qpcNs, swapQpcNs), frames (end minus start), seconds and skippedSeconds in the answer and in window.start and window.end; `failed` on a reload, a dimension change, a join or leave, or a falling sinceReload inside; skipFrames, frames and `after: path` answer `unsupported`. `state` gains framebuffer (the main render target); `run` ends a session whose framebuffer differs from the display mode or suite.json (D38). F23: conc2, conc5 and the game adapter's forwarders done.
- Exit held: one announced bench launch on world spike (pid 13356, 51.7 s, quit exit code 0), a scratchpad script driving launch.py and modclient.py inside one PresentMon recording (optilux-m2-p02-exit, 1,440 rows, one swap chain, CTRL_BREAK_EVENT exit 0); each window `{after: reload, skipSeconds: 1.5, seconds: 2.5}` after its own reload:
  - 1: frames 867-1103, 236 frames, 2.5032 s, skipped 1.5028 s; 236 rows cut by CPUStartQPCTime between the HEAD stamps; start edge +1, end edge +1;
  - 2: frames 1260-1492, 232, 2.5039 s, skipped 1.5093 s; 232 rows; +1, +1;
  - 3: frames 1639-1871, 232, 2.5099 s, skipped 1.5020 s; 232 rows; +1, +1.
- The edges: each frame's row found by its swap stamp (0.14-0.19 ms after it, A9's mapping), one row per frame (236, 232, 232); the cut's first row is frame start + 1's and its last frame end's, the constant one-frame shift of plans/m1.md D26, so rows equal frames. All 700 cut rows Hardware: Independent Flip; `state` read 3840x2160. Every mark's sinceReload equalled frameIndex minus the reload's reloadFrame.
- The jar: optilux-helper-0.1.0.jar sha512 809df216..., in the store; identity from M2.P09's first calibration session.

## What changed
- mod: core/Window.java (new); IrisAdapter sets the anchor at Iris.reload's return, drops it on a failed one; GameAdapter: stateAnswer with framebuffer, a pipeline-lost listener on the join, the leave and a dimension change, the five forwarders to Tasks removed (call sites use Tasks); Session wires the window's frame poll first; commands.json: state's framebuffer, window.measure's result, `excludes` (a window and a capture keep each other out) and a commandKeys note; Commands reads `excludes`, Protocol.dispatch refuses on it; State: hello(live) (conc2) and a release token; CaptureAdapter: a stopped capture drains its pending frames, at most 30 s, before its resource goes (conc5), `active` cleared by compare-and-set.
- harness: modclient.window_measure (its wait the skip, the window and 5 s; the marks and frames checked); modfake: window.measure on 7 ms frames, state's framebuffer, the anchor (set by a reload or selftest, dropped by a dimension change or a refused reload, sinceReload restarted), busy for an exclusive request while a delayed mutating one runs and by `excludes`; session.framebuffer_refusal and session_start(mode, resolution); run passes the identity's resolution and suite.json's.
- Docs: mod-protocol.md (Status, Envelope, not-ready, Events, the state and window.measure rows, Choreography); mod.md (Status, 4, 6, 8, 11; cut first, text platform.md, measurement.md#tools and mod-protocol.md hold: margin 110 to 206 bytes); run-record.md#identity (D38); CHANGELOG's 0.3.0 entry.

## Checks
- At the start: branch m2 held the user's estimate amendment uncommitted; asked, it went in as its own commit (fb1d0c3, CI green); then 467 passed, mod test 82 passed, verify docs 0 violations.
- At the end: `optilux test` 476 passed; `mod test` 96 passed in 19 classes, the tested jar equal to the store's; ruff and pyright clean; verify docs 0 violations. CI green on e129db7 and ed94496.
- JUnit added: WindowTest (the skip from the reload, `now` from the request, the length, the anchor and what drops it, the wrap, a failure inside, a failed reload's restart, the answer and its events, the unbuilt arguments, busy both ways with a mutation and with a capture, a cancel), ProtocolTest (conc2, the release token, conc5, `state`'s field). conc2's and conc5's tests failed with their fixes switched off (2 of 93), then passed restored.
- Python added: the window against the fake, the client refusing marks that disagree (4 cases), the wait, the fake's busy rules, D38's refusal through session_start.
- A flake: tests/test_launch.py::test_logman_lists_sessions_on_this_machine failed once (`logman query -ets`: "The GUID passed was not recognized as valid by a WMI data provider"), then passed 3 of 3 alone and in all four full runs after; inferred: an ETW session changed during the query.

## Review
The reviewer agent three times: the jar's correctness (4 findings, low), its concurrency (7: 1 medium, 6 low), the client against the mod (5: 1 medium, 4 low); each read at its source.
- Fixed: a window could overlap a capture or a stopped capture's drain (medium): `excludes`, both ways; the fake started a window over a running mutation, which the mod refuses (medium); a cancelled window still sent its events; the 10 s release could still fire after a hello at its moment (older than this change): the token; an ending capture could clear the next one's `active` after a world leave; a failed reload's restarted counter could fail a later window; the cancel test passed without `close`; the fake's refused reload kept its anchor, its selftest set none, its dimension change kept sinceReload counting, its window events carried the frame before; the client tests pinned neither the wait nor the end mark; not-ready's row lacked the window's case.
- Not held: the marks' sinceReload one frame behind Iris's counter (live: equal to frameIndex minus reloadFrame).
- Left: below.

## Open questions
- Carried: game/config/'s sodium-mixins.properties and iris-excluded.json in no key (M2.P05 the natural phase); the display's rate and count recorded, not matched; machine state beyond the five system facts; P9 (M2.P04); F10's startup call (M2.P05).
- Window 1's start frame came 2.37 ms after its swap, the other marks 0.15-0.22 ms: a frame's own work, not the cut's (its row still matched by the swap stamp); M2.P05's summaries will show whether a window's first frames run long.

## Left alone
- A mutation's game work can outlive its handler (a timed-out ticks.step keeps stepping, mod.md#4-architecture), so a window could start over it; session.step ends the run on any ModError, so no caller goes on (older than this change).
- The drain's bound: a stopped capture whose readbacks never arrive frees its resource after 30 s with no manifest (logged).
- Capture.settle writes capture.json under the capture's lock, which the render thread's wants() takes: one long frame at a capture's end (older); `excludes` keeps it out of any window.
- The fake's event envelope's qpcNs is perf_counter_ns while its marks are frames x 7 ms (older, every event).
- A pipeline creation seen at the next frame head fails a window opened in the few ms before that head: the safe side.
- window.measure takes no timeoutSeconds (the plan's arguments); the client's wait covers the skip and the window and cancels after it.

## Weak points
- An Iris pipeline creation outside shaders.reload and the game's join, leave and dimension events is seen only through the counter falling at a frame head.
- The exit is a scratch script, not a run record: its CSV, request log and facts stay in the session's scratchpad; M2.P05 puts the cut into the runner with a record.
- The per-edge check rests on A9's swap mapping; one launch, three windows, one view.

## Commits and time
- fb1d0c3 docs: raise the timers, session and statistics phases to 3.5 h (the user's amendment); e129db7 feat(mod): add window.measure and fix the release and capture races; ed94496 feat: add the window client and refuse a framebuffer off the display; this handoff. Each pushed after the previous one's CI ended.
- M2.P02: 15:06 to about 15:52 ADT, about 0.8 h against 2.5 h.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 28.5 h (M0 3.3, M1 20.3, M2.P00 about 3.5, M2.P01 about 0.6, M2.P02 about 0.8).

## Next
/optilux-next prints M2.P03's prompt: the per-pass timers, 3.5 h (XL), 1 launch.
