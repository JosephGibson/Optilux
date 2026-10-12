# Handoff
Status: the latest stop: M2.P03, the per-pass GPU timers, and what M2.P04 starts from.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P03
- The helper's own per-pass timers (D53): mixins at the HEAD of Iris's static GLDebug.pushGroup and popGroup (read in the pinned jar first: both only delegate to the debug state; setPhase, beginLevelRendering's "Clear textures", CompositeRenderer.renderAll per renderer and pass, FinalPassRenderer's "final", ShadowRenderer's "shadowcomp" and Iris's own MixinGui "GUI" call them, none behind a debug option). On the render thread a pooled GL_TIMESTAMP query at each push and pop; a frame is read maxPending frames after it ends if all its stamps are in, else dropped late; a query returns to the pool only once its result is in. `timers.start {perPass, maxPending, maxFrames}`, `timers.read`, `timers.stop`, the `timers.dropped` event; commands.json, the client methods, the fake.
- Exit held: one announced bench launch on world spike with Unbound (pid 9180, joined in 14.2 s, quit exit code 0), driven by a scratchpad script through launch.py and modclient.py inside one PresentMon recording (optilux-m2-p03-exit, 1,637 rows, one swap chain, CTRL_BREAK_EVENT exit 0); `state` read 3840x2160.
  - `timers.start {maxPending: 3, maxFrames: 1000}` at frame 1385; `window.measure {after: now, skipSeconds: 0.5, seconds: 2.0}`: frames 1428-1591, 163 frames, 2.0115 s; `timers.read` 205 frames, `timers.stop` 8: frames 1386-1598, 213, contiguous.
  - Every one of the window's 163 frames: the same 31 passes in one order, every stage in it: Clear textures, begin, Shadow Terrain solid, Shadow Entities, Shadow Terrain translucent, shadowcomp, prepare, the sky phases, Terrain solid, Particles, deferred (deferred1), Rain snow, World border, composite (composite, composite1, composite3-7), final, GUI.
  - Dropped: late 0, full 0, overflow 0, lost 0 at maxPending 3; unmatchedPops 852 (4 per frame), cutPasses 0.
  - The frames' top-level sums: median 11.207 ms (p5 10.676, p95 12.479), below the 163 cut rows' median GPUBusy 12.172 ms (FrameTime 12.125 ms).
- The jar: optilux-helper-0.1.0.jar sha512 8654d88f..., in the store.

## What changed
- mod: core/Timers.java (new: the stack, the ring, the session handoff, the handlers); mixin/GLDebugMixin.java and GlQueries.java (LWJGL GL15C/GL33C) new; Hooks: the group entry points, a failure reported once per run; State.onReleased, so the timers stop with their resource (timers.stop's answer, a disconnect, a world leave, an undelivered start); Session wires them; commands.json: the timers' defaults, ranges and result fields.
- Choices no plan or prompt names, taken here:
  - perPass false times the depth-0 groups only; maxPending default 3 (1-16), maxFrames default 1000 (at most 10,000), at most 512 groups a frame (more: dropped overflow);
  - timers.start needs a world (`not-ready`); read and stop answer `not-ready` with no timers; start echoes its settings;
  - a read waits for the frames that ended before it (2 s at most); a stop keeps the frame in progress and waits for its frames (5 s at most; the rest counted `lost`);
  - the counts (dropped late, full, overflow, lost; unmatchedPops; cutPasses) run from the start; `timers.dropped` once per start or read, naming the oldest frame dropped;
  - a GL call that throws, or a group call off the render thread, fails the timers: nothing more issued, their unread frames lost, read answers `failed`, stop still frees the resource; a read or stop whose resource a disconnect or world leave frees answers `failed`;
  - a dropped frame's queries wait in a late list until their results are in; the pool is deleted once nothing is in flight.
- harness: modclient's timers_start, timers_read, timers_stop (waits: the mod's bounds plus MARGIN), check_timers, top_level_nanos; modfake's timers model (FAKE_PASSES, named as the game names them; its first full drop pushed as timers.dropped; read and stop answer maxPending + 1 frames later) and `_free` given the answer's real ok.
- Docs: mod.md (Status, 4, 11, 14; cut first: the window paragraph mod-protocol.md holds, the flush's R6 sentence platform.md holds, a run narrative and a dated build time: margin 206 to 79 bytes), mod-protocol.md (Status, not-ready, Events, the timers row, Choreography's timed capture), platform.md#mod-adapter-surface's timers row, CHANGELOG's 0.3.0 entry.

## Checks
- At the start: 476 passed, mod test 96 passed, verify docs 0 violations.
- At the end: `optilux test` 488 passed; `mod test` 117 passed in 20 classes, the tested jar equal to the store's; ruff and pyright clean; verify docs 0 violations. The first commit alone: 476 passed, ruff, pyright and verify docs clean.
- JUnit added: TimersTest (19, on a fake GPU that fails a GL call off the render thread, a query reissued or deleted while pending, availability asked of one never issued, a result read before it is in; a 60 s timeout per test), MixinTargetTest (GLDebug's two targets, a static handler for a static target, Iris's six callers and no debug option asked), HooksTest (a failing group call reported once per run).
- Mutation checks, each restored by hash: the late list skipped, the start's live check and the read's wait (7 tests failed, the 3 targeted among them); the overflow's count, the late drain's restore and the oldest-frame event (exactly the 3 targeted failed).
- Python added: the timers against the fake (busy both ways, not-ready, maxFrames, perPass, a disconnect), the waits pinned to Timers.java's bounds, 8 malformed answers refused, a start answering other settings stopped first.

## Review
The reviewer agent four times: the jar's render thread (7: 1 medium, 6 low), its correctness (7: 2 medium, 5 low), the client against the mod (11: 1 medium, 10 low), then the fixes again (9: 1 medium, 8 low); each read at its source.
- Fixed: a throw in a group call reported per group and leaking names, and a throw mid-push, -pop or -head leaving the stack or the ring inconsistent (now any throw fails the timers at once); a group call off the render thread passing silently; a start publishing its session after its request was answered (a disconnect then left timers running with nothing held); a stop past its drain losing frames silently (`lost`); an overflowed frame counted again as lost; the event naming a newer frame; frames read as soon as in where the plan says maxPending frames later (drops the same either way); a missed notify; the client's start leaving timers running when it refused them; its waits not pinned; its check passing a non-list or a negative gpuNanos; the fake's names, clock, event and a reconnect race in its test.
- Confirmed by the exit: Iris's phase groups carry spaces ("Terrain solid"), as the client reviewer said; the jar's `ldc " "` was misread as "" at first.
- Left: below.

## Open questions
- PresentMon read "Composed: Flip" (DXGI, AllowsTearing 0) on all 1,637 rows, where M2.P02's exit read Hardware: Independent Flip; options.txt held fullscreen and exclusiveFullscreen true. Cause unknown (an overlay or a window over the game composes it); not this exit's, but measurement.md#validity invalidates such captures: M2.P05's runner must refuse them and name it.
- unmatchedPops ran 4 a frame: setPhase pops unconditionally after phases that push no group (NONE, cutout, tripwire); cutPasses 0, so no group crossed a frame head.
- The main pass groups no entities, translucent terrain or hand: GPUBusy minus the top-level sum, about 0.96 ms at the median, holds that and Iris's copies (A11's residual, M2.P10).
- Carried: game/config/'s sodium-mixins.properties and iris-excluded.json in no key (M2.P05); the display's rate and count recorded, not matched; machine state beyond the five system facts; P9 (M2.P04); F10's startup call (M2.P05); window 1's start frame 2.37 ms after its swap (M2.P02).

## Left alone
- A release lands mid-frame: that frame's groups still issue queries; the timers stop at the next head.
- A name whose glQueryCounter throws is leaked (the timers fail at the first such throw).
- The stop tests order the stop before the next head by a 200 ms wait after its handler entered: a stall longer than that on the machine running `mod test` fails them (they run locally only).
- The fake models no late, overflow or lost drop and no unmatched pop; its every-command test relies on no mutating command between timers.start and timers.stop in the table (it fails loudly otherwise).
- Session's wiring (State.onReleased to Timers.released, Hooks.Groups) and GlQueries run only in game: the exit is their test.

## Weak points
- One launch, one view, one window of 163 frames at about 82 fps, GPU-bound; maxPending 3's margin over the GPU's latency was not stressed.
- The exit is a scratch script, not a run record: its CSV, request log and answers stay in the session's scratchpad; M2.P05 puts timers into the runner with a record.

## Commits and time
- 22211ae feat(mod): time each Iris pass with GL timestamp queries; e037c6e feat: add the timers client and the fake's timers model; this handoff. Each pushed after the previous one's CI ended.
- M2.P03: 15:56 to about 17:45 ADT, about 1.8 h against 3.5 h.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 30.3 h (M0 3.3, M1 20.3, M2.P00 about 3.5, M2.P01 about 0.6, M2.P02 about 0.8, M2.P03 about 1.8).

## Next
/optilux-next prints M2.P04's prompt: the world verbs and bench_263's preparation, 3 h (L), `install` (Chunky's jar) and 1-2 launches.
