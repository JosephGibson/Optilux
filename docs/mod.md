# Helper mod (optilux-helper)
Status: rough spec, 2026-10-05, built through M1; full redesign and rewrite (user decision), wire contract in mod-protocol.md. As built: the inert gate (5) and build and test (11), 0.01.04; the pipe, the protocol core and the state owner (4, 5), 0.01.05; the MC 26.3 game adapter, ticks, poses, input and HUD (4, 6, 9), 0.01.06; the Sodium and Iris adapters, readiness, capture and selftest (6-8, 11), 0.01.07; the rest is still spec.

## Contents
1 Stance · 2 Consumers · 3 Non-goals · 4 Architecture · 5 Safety · 6 Time and determinism · 7 Readiness · 8 Capture · 9 Input and HUD · 10 Adapter surface · 11 Build and test · 12 Acceptance · 13 Lessons · 14 Open questions

## 1. Stance
- Rewrite from scratch, from this spec and lessons.md alone. No ALC code is read (user, 2026-10-06).
- Keep ALC's proven design: a pure-Java core (transport, protocol, camera math, capture, readiness, timing) with game access in one thin layer; a strict protocol (bounded lines, strict JSON, coded errors); a layered inert gate (no token -> no pipe, no thread, no mixin); mixin-target tests against the pinned jars; capture tests through an independent PNG decoder.
- Fix ALC's gaps: no push events, head-of-line blocking without cancel, no clock shared with PresentMon, `/tp` semantics re-implemented in PowerShell, keystrokes still needed, static state never reset, a world-readable pipe without client authentication, patch-exact coupling to private Iris/Sodium fields, no test of game-facing code.
- What ALC proved in game: lessons.md#mod; what it never ran: lessons.md#open-at-alc-close. Treat those parts (timers, the compile-error path, the sway) and perf through the mod as unproven.

## 2. Consumers
Session start, perf capture, static and motion visuals, coverage views, the live pass, option variants, debugging, world prep and the JVM track: each need maps to a command in mod-protocol.md#commands, whose Phase column says which milestone first needs it.

## 3. Non-goals
- Keystrokes or OS input.
- Player simulation beyond camera poses and a server-side flight path.
- Any network listener, except E1's loopback TCP fallback if the pipe fails acceptance (design.md#8-open-decisions).
- Several clients at once.
- Running without a token.
- UI.
- Writing Iris settings files (the harness writes them; the mod reloads and reads back).

## 4. Architecture
- Layers, top to bottom:
  1. transport: pipe server, framing;
  2. protocol core: envelope, dispatcher, errors, events, request registry, cancel;
  3. state owner: the single owner of mod state (connection, jobs, active window/capture/path/timers); no global statics. Leaving the world resets it. On disconnect, state survives and work does not:
     - running requests are cancelled;
     - a capture stops, its manifest marked incomplete;
     - a path and timers stop;
     - input blocking is released if no client says `hello` within 10 s. That is long enough for a client restart, and a crashed harness must not leave the game locked.
     - A reconnecting `hello` reports `resumed` and the cancelled request ids.
     - As built (0.01.05): the state owner holds the exclusive resources and their holders, the input-block flag with its release timer and the resume facts; a world leave (Fabric's play disconnect) answers the requests holding a resource `failed` and frees everything.
  4. services: camera, capture, readiness, reload, input, hud, timers, metrics; pure Java, unit-testable;
  5. adapters, one set per platform:
     - game (MC 26.3);
     - renderer (Sodium 0.9.2);
     - shader loader (Iris 1.11.7; Aperture later).
- Threads:

  | Thread | Runs |
  |---|---|
  | pipe I/O | reads and writes only, on one overlapped handle: a synchronous one serializes a pending read against every write |
  | request workers | small pool (up to 40 threads, at most 32 requests running); a long request never blocks a short one |
  | timer | request timeouts, the 10 s input release |
  | render thread | frame hooks and `Minecraft.execute` tasks |
  | server thread | commands and ticks |
  | writer pool | PNG |

- As built (0.01.06), the MC 26.3 game adapter: game state is read and changed only on its thread (the render thread through Minecraft.execute, the server thread through the integrated server's), the worker waits; Fabric's ClientPlayConnectionEvents JOIN and DISCONNECT, ClientLevelEvents.AFTER_CLIENT_LEVEL_CHANGE and ServerTickEvents.END_SERVER_TICK; the frame hook polls focus (Minecraft.isWindowActive), screens (Gui.screen(), Gui.overlay()) and the in-world frames; a poll that throws never breaks the frame: the first failure of a run is logged and sent as `hook.error`. `world.wait` answers at the second frame head in the world with no level-loading screen, so the frame between rendered it (Iris builds its pipeline inside the first, 3 s on Unbound). `command` runs as the player at OWNER (`withPermission(LevelBasedPermissionSet.OWNER)`) with the mod's own CommandSource and result callback: failures are sendFailure's lines (its red empty-literal wrapper), and it succeeded when no failure came, at least one context reported a result and every result was a success.
- An Error in any task becomes a coded response and never kills a thread. ALC's did, once.
- Timed-out game-thread work is not cancelled, but a task whose request was already answered `timeout` or `cancelled` skips its mutation when it runs and logs `skipped-late`. While a window, capture, path or timers are active, every mutating command answers `busy` (mod-protocol.md#envelope). Only repeat-safe work may use short waits; a long one is cancelled cooperatively through `cancel`.
- Prefer Fabric API events (join and leave, client and server ticks) over mixins where their timing fits. Mixins only for:
  - frame boundaries and the capture point;
  - input;
  - renderer and shader-loader internals.

## 5. Safety
- Inert gate:
  - `-Doptilux.token` (32-128 chars `[A-Za-z0-9_-]`), fresh per launch, passed on the JVM command line only, never written to a file; the harness redacts it from its request log (mod-protocol.md#client-rules).
  - Without it there is no pipe, no thread and no mixin; a mixin config plugin decides.
  - A test pins the metadata: one entrypoint, no access widener, no nested jars.
- Pipe:
  - name derived from SHA-256 of the token;
  - FIRST_PIPE_INSTANCE (a squatter fails) and REJECT_REMOTE_CLIENTS;
  - an explicit DACL for the current user only (ALC's default descriptor was world-readable).
- Both ends check each other. The client checks the server PID (`GetNamedPipeServerProcessId`); the mod checks the client process's owner, and `hello` carries the token. With the user-only DACL, that is enough.
- As built (0.01.05): the DACL holds one ACE, GENERIC_ALL for the process token's user, from jna-platform's Advapi32 (plans/m1.md D21); the mod drops a client whose process token's user differs (GetNamedPipeClientProcessId, OpenProcessToken); `launch` reads the DACL back through its handle, checks the server PID and that a second server instance is refused, and its pipe test does the same in JUnit.
- Bounded input: lines at most 1 MiB, strict JSON (Gson's STRICT reader, duplicate keys and lone surrogates refused, nesting at most 64), capped counts (32 running requests) and timeouts. Errors are coded, never free text only.
- The game never starts from Gradle: a task graph holding one of Loom's run tasks (`runClient`) fails before any task runs. The mod is never installed outside runtime/<platform>.

## 6. Time and determinism
- Clocks: every result, event and frame stamp carries `frameIndex` (frames since mod start), `sinceReload` and `qpcNs`. Frame stamps are taken at the HEAD of the frame hook; `window.measure` and the capture manifest carry that stamp.
  - `sinceReload` = frames since the last pipeline creation (reload, dimension change, join). This equals Iris's own frameCounter, which resets then and wraps at 720720 (gpu-iris.md#frame-counters-and-reload), so mod and shader agree on phase; cycles must divide 720720 so phase survives the wrap. ALC's mod held the reload frame but never exposed it.
  - `qpcNs` = QueryPerformanceCounter ticks x 1e9 / QueryPerformanceFrequency, read through the JNA the game ships (the pipe already uses it). Not `System.nanoTime()` (origin unspecified).
  - This is PresentMon's clock: run with `--qpc_time_ms`, PresentMon writes CPUStartQPCTime as absolute QPC milliseconds, so qpcNs = CPUStartQPCTime x 1e6 (measurement.md#tools).
  - As built (0.01.07): a frame stamp also carries swapQpcNs, the previous frame's swap return (after `GpuSurface.present` in Minecraft.renderFrame; 26.3 has no Window.updateDisplay), for D26 (plans/m1.md); sinceReload is SystemTimeUniforms.COUNTER.
  - The harness cuts PresentMon rows by the mod's window stamps instead of sleeping around an assumed 150 ms PresentMon start. A9 checks the mapping on real frames.
- Measurement windows: `window.measure` waits a settle after a trigger (reload done, path started), then marks start and end in frameIndex + qpcNs. Settle and window are in seconds on the QPC clock (frames optional).
- Determinism support:
  - `frames.index` reports Iris's frameCounter next to the mod's index;
  - alignment, history flush and capture are scheduled together inside the mod: `frames.capture` takes `align` and `flush`; `camera.path` carries its own capture. Never across a request round trip: rendering advances during one;
  - phase = sinceReload mod cycle;
  - flush: sessions run with hideGUI true (`hud.set` at session start); the mod sets it false for exactly one frame on the render thread, and BENCH_DETERMINISTIC treats TAA history as invalid in any frame where the hideGUI uniform reads 0. Verified on Iris 1.11.7 (spike R6): hideGUI is a PER_FRAME uniform read from Hud.isHidden() when beginLevelRendering runs updateNotifier.onNewFrame(), so a toggle on the render thread before that point lands in the same frame;
  - `camera.path` sets the pose at the top of each rendered frame from frames since the path start;
  - a reload clears every buffer (TAA history included) and re-meshes all chunks (Iris 1.10.7 bytecode; re-verified in the spike, R5).
- Ticks: `ticks.step n` answers after n server ticks have run (`/tick step` feedback comes before the ticks; ALC slept instead). As built (0.01.06): on the server thread it refuses ticks not frozen (`failed`) or a step already running (`busy`), registers a counter, then calls ServerTickRateManager.stepGameIfPaused(n), the same call `/tick step` makes; a tick counts when runsNormally() holds at END_SERVER_TICK (tickServer runs the tick-rate manager's tick() before the levels).
- Poses (as built, 0.01.06): `camera.place` needs a spectator or flying player (`not-ready` otherwise: gravity would move the pose first) and sets the exact pose server-side with ServerPlayer.teleportTo(level, x, y, z, no relatives, yaw, pitch); another dimension first through `/execute in <dim> run tp @s` in the same server task; it answers once the client holds the pose exactly (doubles and floats equal) and then sets the previous-tick position, rotation, head, body and bob to it, so no frame interpolates; leaving the world ends the wait `failed`. `tpSemantics` applies `/tp`'s rules, implemented once (core/TpSemantics): +0.5 on x and z written as integer literals (never y), both angles cast to float and wrapped to [-180, 180), the pitch then clamped to [-90, 90] as Entity.setXRot does; without it a pitch outside -90..90 is refused rather than clamped.
- Reload ordering: anything that should start after a reload uses the reload's completion inside the mod, never a harness sleep (ALC's sway started late).

## 7. Readiness
- Predicate, all of:
  - in a world, no screen or overlay open;
  - renderer has sections;
  - build queue empty; no busy builder threads; no pending uploads;
  - no section with a running job (expected arrivals); task lists empty;
  - section graph clean;
  - all of the above for `stableFrames` consecutive renderer frames.
- Why not Sodium's own check: `isTerrainRenderComplete()` reads only the queue. A worker holds a dequeued job before it counts as busy (found by disassembling Sodium 0.8.12).
- A held predicate is not a final frame: in ALC, 2 of 34 first frames were not final.
  - Static captures add the determinism check (measurement.md#visual-protocol).
  - The calibrated settle stays the floor until A5 shows predicate-ready -> frame-final (the predicate-ready frame equals a later settled reference) over at least 30 waits.
- Report: seconds, predicateSeconds, limitedBy, and the renderer's own check side by side (it found ALC's gap).
- Re-read every Sodium 0.9.2 field and method by disassembly before relying on it.
- As built (0.01.07), read on the render thread at each frame head while a wait runs: getTotalSections; the builder's queue and busy count; buildResults; each loaded section's runningJobs (a worker dequeues a job before it counts busy); taskLists (absent before the first cull); the tasks the last updateChunks submitted; needsGraphUpdate and the cull task. importantTasks is left out: it keeps sections the render tree does not show. limitedBy: minSeconds, the term that failed last, or stableFrames; the renderer's check reports its own seconds and gapFrames, the frames it held while the predicate did not.

## 8. Capture
- Point: after the world render returns and before the GUI (ALC: after `renderLevel` in `GameRenderer.render`). Iris's final pass is done by then.
- Path: the same screenshot readback and PNG writer F2 uses, so equal pixels give equal bytes.
- Files are written on a writer pool. Images may arrive frames later, so in-flight frames are tracked.
- Accumulation (per-pixel sums for a temporal metric) is not built until such a metric passes its positive control (measurement.md#visual-protocol; user, 2026-10-06). ALC's uint16 sums wrapped above 257 frames, so it would use uint32.
- Manifest: capture.json per capture, with every frame's name, sha256, frameIndex, sinceReload and qpcNs, and the dropped frames. The response carries the same data, so the harness need not re-read it to proceed.
- Retry-safe: each attempt writes to a new subfolder. ALC's refused non-empty folders and a late frame could land in a cleared one.
- Live pass: a low-stall mode (readback queued, written later). Measure its frame-time cost before relying on it.
- As built (0.01.07): the point is right after GameRenderer.render's applyPostEffects call (frames that render the level); Screenshot.takeScreenshot's readback arrives on the render thread frames later and 4 writers write it with NativeImage.writeToFile, F2's writer; at the cap the render thread waits only while a writer holds a frame, as a readback in flight needs the render thread. Layout: mod-protocol.md#commands.
- Limits: at most 4096 frames per capture (ALC), one capture at a time (`busy`). F2 itself takes at most 64 frames per capture. Pending readbacks: at most 16 (CaptureAdapter.MAX_PENDING, in the jar; ~530 MB at 4K). At the cap a deterministic capture stalls the render thread until a writer frees a slot (time, not correctness); the live pass drops the frame and lists it under `dropped`. On cancel or disconnect, pending frames are still written and the manifest marked incomplete.

## 9. Input and HUD
- `input.block`: cancel mouse movement and button and key handling in the game while on. Include raw mouse input: ALC's OS lock missed raw input.
  - pauseOnLostFocus is written false by the harness; the mod also refuses the pause screen while blocked.
- `hud.set`: hide GUI (F1) through Hud.toggle() and isHidden() (26.3 has no hideGui option) and the debug overlay (F3), not keystrokes.
- Events for focus lost and screen opened, so a session can mark captures invalid instead of guessing.
- As built (0.01.06): SDL3 hands every mouse event to MouseHandler.onMove (the grabbed relative motion and the absolute cursor alike), onButton and onScroll, and every key to KeyboardHandler.keyPress, textInput and textEditing; `input.block` cancels all six at HEAD and Minecraft.pauseGame, the pause screen's one door, and releases held keys (KeyMapping.releaseAll) when it turns on; it changes the flag only while its request is live, under the state owner's lock, so a disconnect cannot leave a block without its 10 s release. The game turns the camera from mouse motion only while the mouse is grabbed (MouseHandler.handleAccumulatedMovement); grabMouse does nothing while the window is inactive, and only a click (onButton) or a closing screen calls it. In the 0.01.06 launch the first SendInput nudge, `focused` true, moved nothing; after one click the same 300 counts turned the yaw 45.0 degrees, so the grab was missing (inferred: `state` does not report it). `hud.set` toggles Gui.hud when its flag differs; F3 is no option on 26.3 but DebugScreenEntryList's overlay flag (`debugEntries.setOverlayVisible`).

## 10. Adapter surface
What each platform's adapter must provide, and where ALC hooked it: platform.md#mod-adapter-surface.

## 11. Build and test
- MC 26.x is unobfuscated:
  - Loom plugin `net.fabricmc.fabric-loom` 1.18.2 (non-remapping: `implementation`, `jar`), Mojang names, no refmap [S1][S2];
  - Java 25 throughout (`options.release 25`, Gradle's JVM the bench Temurin), which removes ALC's Loom-vs-Java-21 conflict.
- Gradle: only through `optilux mod build|test`:
  - the wrapper 9.7.1, pinned with distributionSha256Sum; its jar equals Gradle's published sha256;
  - JAVA_HOME and org.gradle.java.home set to the Temurin `install` unpacked under runtime/java/ (gradlew.bat needs JAVA_HOME); JDK detection and auto-download off in mod/gradle.properties;
  - `--no-daemon`: org.gradle.jvmargs forks a single-use daemon that stops with the build;
  - refused while the launch gate is closed (a process from runtime/<platform>/ or an optilux-* ETW session), so never started beside a session; `launch` does not look for Gradle.
  - The first build here took 41 s on a Gradle cache filled on 2026-10-05; ALC estimated 1-2 GB of downloads from empty.
- Inputs: the verb writes mod/build/optilux/inputs.json from the platform file and the hash-checked pinned jars, and Gradle reads nothing else under config/ or runtime/:
  - the versions Loom resolves (minecraft, fabric-loader; fabric-api from Fabric's Maven);
  - `depends`;
  - Iris and Sodium compile-only from the store, by sha512, re-checked by Gradle;
  - the jars holding mixin targets (the client jar by the spec's sha1, Iris, Sodium).
- fabric.mod.json is generated by Gradle: id optilux-helper, environment client, one client entrypoint, one mixin config, no access widener, no nested jars, no sources jar. `depends` uses "=" on minecraft and fabricloader at the platform file's versions and on each bench mod at the version its pinned jar declares, so the mod refuses other versions; Fabric's comparison ignores the +build suffix, so `launch`'s sha512 pins are the exact check.
- The same sources give the same jar: archives carry no timestamps, in a fixed order. `mod build` copies mod/build/libs/optilux-helper-<version>.jar into the store runtime/<platform>/files/, removing any other helper jar; `launch` places it.
- The jar sha512 is part of run identity: one frozen jar per calibration; a rebuild that changes it means recalibrating. The version in mod/gradle.properties is a label.
- Tests (`mod test` runs JUnit, counts its reports and compares the tested jar's sha512 with the store's):
  - core unit tests (no game): the token rule, the mixin config plugin with and without a token, the frame clock, strict JSON, the framing, the protocol core (envelope, codes, out-of-order answers, cancel, timeout, busy, the state reset, a reconnect), every answer against commands.json; a real-pipe test (the DACL read back, a second instance refused);
  - metadata test: reads the built jar; `depends` is derived on its own from the platform file and the pinned jars;
  - mixin-target test: ASM reads every target class, injected method (name and descriptor), INVOKE and accessor field (name and type) from the hash-checked pinned jars, and each call the adapters make into Sodium and Iris; a mixin annotation it does not read fails it;
  - capture: the decoded PNG equals the read-back pixels;
  - commands.json, the command table in machine-readable form (args, results, phase). The mod's argument checks, the Python client and the protocol fake are generated or checked against it, and a test keeps mod-protocol.md's table in step;
  - in-game `selftest` (0.01.07: the clock and swap stamps, a renderer reading, a real reload, one frame to a temp folder, the input mixins);
  - acceptance launches (12).
- Tests write only under mod/build/ (working folder build/test-work/, java.io.tmpdir inside it; ALC's test JVM wrote logs/ into mod/). `.npy` fixtures are marked binary in .gitattributes.

## 12. Acceptance
Each item is recorded in an acceptance run record (run-record.md#record); design.md#6-milestones says which milestone exits on which items.
- A1 inert: no token -> no pipe, no thread, no mixin applied.
- A2 parity: with `hud.set {hideGui: true}` and no screen or chat open, `frames.capture` bytes equal a vanilla F2 screenshot of the same pose; the F2 press comes from the harness (SendInput through ctypes, `input.block off` for it) or from the user in an attended step, and the harness compares the newest file in screenshots/. M1: three provisional views, one per dimension.
- A3 placement: `camera.place` with `/tp` semantics equals `/tp`'s pose on every acceptance view (angles wrapped, +0.5 centre correction).
- A4 compile error: a deliberately broken pack -> `iris-compile-error` with the message; recovery reload works.
- A5 readiness: over >= 30 waits on the hello pack (TAA off), the first frame after predicate-ready equals a reference taken after the view's calibrated visual settle plus 2 s (decoded pixels), 30 of 30; only then may the predicate replace the settle as the visual floor (section 7); any miss keeps the settle and reports the rate. It runs in M3, on a deterministic pack.
- A6 motion: one `camera.path` sequence identical across 2 sessions (hello pack, TAA on, flushed).
- A7 input: mouse (raw on and off) and keys move nothing and open nothing while blocked.
- A8 overhead: in one session, the same variant with per-pass timers on vs off, judged by the in-session threshold; pass = no effect beyond it. The mod sits in both arms of every verdict, so additive cost cancels. The presence arm (mod present vs no jar, launch-level bracketing) and the known-effect arm (the shadows-off ratio through the mod equals a mod-free one) move to the JVM track's J1, where launch-level bracketing exists (jvm.md#build-order; user, 2026-10-06).
- A9 clocks: PresentMon's CPUStartQPCTime x 1e6 (the previous Present's return) against both frame stamps (section 6), matched by order over one capture: the swap-return stamp differs by under 1 ms at the median and the maximum, under half the shortest frame, so each frame maps to one row; the HEAD stamp's offset is reported beside it (plans/m1.md D26; measurement.md#tools).
- A10 `selftest` passes at every session start, after `world.wait` (mod-protocol.md#choreography).
- A11 timers: on GPU-bound captures, the residual GPUBusy minus pass sum (median over the window) moves by less than the view's calibrated threshold between the variants of one session (the sum never equals GPUBusy: Iris's depth copies and non-pack draws lie outside pack passes), and the shadows-off delta from timers matches the GPUBusy delta within the same threshold. Only then, and per pass after the submission control, may timers carry cost rows below the CPU floor (measurement.md#verdicts-and-cost-rows); otherwise they are dropped.
- A12 TAA on: two flush + capture cycles in one session are identical, and so are two sessions. If the flush fails, design.md E4's fallback replaces A6 and A12.

## 13. Lessons
Mod-specific lessons from ALC (reload semantics, `/tp` parsing, pipe bugs, estimates) live in lessons.md#mod.

## 14. Open questions
- Per-frame pose vs Minecraft's partial-tick camera interpolation: set the pose after interpolation each frame.
- Per-pass timers: design.md E3. Viewfinder is MIT: its Iris hooks may be studied (keep its notice if code is reused).

Sources:
- [S1] https://fabricmc.net/2026/03/14/261.html
- [S2] https://docs.fabricmc.net/develop/loom/
