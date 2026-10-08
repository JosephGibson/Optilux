# Lessons from ALC
Status: carried 2026-10-05 from AlaCarteShaders 0.5 (ALC: MC 1.21.11, Iris 1.10.7, Sodium 0.8.12). ALC is retired and separate: this file is all Optilux takes from it (user, 2026-10-06).

## Contents
Tags · Outcomes · Game control · Iris and Sodium · Determinism · Tools · Windows · Statistics · GPU · Java · Mod · Open at ALC close

## Tags
- [MC]: re-verify on each platform.
- [HW]: this machine.
- [ALC]: context only.
Each item reads "fact -> technique". Brackets name the ALC record a fact came from (ALC's own docs/measurement.md when none): citations only, never looked up.

## Outcomes
[ALC] Read this first.
- In 9 days ALC shipped 7 accepted exact changes.
  - 15 candidates measured, 7 accepted; 7 more closed offline.
  - The five-change stack measured -5.4 % geo-mean on 4.6-7.7 ms frames; a later stack -8.1 % (it included rejected changes). [ledger]
- Wins: removing unread work (mip chains, copy passes, unread passes) and hoisting invariant math. Micro-arithmetic and occupancy work measured zero or slower. [ledger]
- Effort: 2.4 MB of tooling, 1.5 MB of docs, 838 tests, against ~130 shader marker lines. M0-M3 produced no shader change. -> Optilux core rule (design.md#3-core-rule).
- The project's own verdict: "Machine time is not the constraint. Agent time is, by one to two orders of magnitude." [agent-workflow-plan]

## Game control
- `/tick` needs permission level 3; datapack functions run at level 2. -> Send it through the mod's `command` (OWNER level). Command feedback is not completion. [MC] 26.3: verified by reading (allowCommands=1 gives the owner OWNER); Viewfinder's control_ticks froze ticks in the spike.
- Weather ramps only while ticking. -> `/tick step 120`, only on an overworld weather change, only while frozen. [MC] 26.3: the step ran in M1 after each session's first weather set (clear, m1-acceptance-10); a change to rain or thunder waits for M2.
- `/tp` adds 0.5 to integer coordinates and wraps yaw (180 -> -180). A mod that set yaw 180 changed frames on 4 views. -> The mod copies both behaviors, implemented once in the mod, never in the harness. [m3-run-plan-1] [MC] 26.3: verified in M1 for x and z, never y (A3, m1-acceptance-10; mod.md#6-time-and-determinism).
- Keystrokes were lost behind loading screens; a resent `/tick freeze` landed in open chat. -> No keystrokes. Confirm commands from latest.log, gate on readiness. [_archive/harness-plan] [MC] 26.3: M1 confirms each command by the mod's `command` answer (mod-protocol.md#commands), not latest.log, and gates on `ready`.
- F2 screenshots include the GUI and chat. -> Capture in the mod right after `renderLevel` with the vanilla screenshot writer (byte-identical to F2 on 8/8). F2 takes at most 64 frames per capture. [m3-run-plan-1] [MC] 26.3: the mod captures after `applyPostEffects` instead (mod.md#8-capture), byte-identical to F2 in M1 (A2, m1-acceptance-10); the spike's PrintWindow and Viewfinder captures show the HUD toast.
- 1.21.11 gamerules are snake_case (`advance_time`, `advance_weather`, `spawn_mobs`, `random_tick_speed`); datapack format [94,1]. -> Read both from the platform. [MC] 26.3: names unchanged, formats data 121.0 and resource 97.1 (verified).
- Setup function: spectator; kill non-player entities except the dragon; time 6000; weather clear. [tools/bench/datapack]
- World load: `--quickPlaySingleplayer <world>`. [MC] 26.3: verified (L1, 18.4 s to the world).
- Direct launch:
  - Fabric KnotClient, 84 pinned jars, offline session (`--accessToken 0` and `--offlineDeveloperMode`; any token value passes);
  - every classpath jar and the asset index hashed against the pinned launch spec before each launch;
  - join took 29.9 s direct against 39.0 s through Prism in one pair, with no gain in another pair. [m3-run-plan-1] [MC] 26.3: verified (82 jars, flags accepted, join 18.4 s).
- Prism: avoid.
  - `--help` opens a dialog;
  - JvmArgs backslashes get escaped;
  - it rewrites instance.cfg on every launch;
  - it needs the network and shows an updater prompt. [environment, m3-run-plan-2]
- Fabric's client gametest API is unusable for this: it resets options and pauses between waits. [_archive/harness-plan-2]
- World snapshot:
  - restore + hash check ~2.2 s before every launch; sessions refuse a world with missing region files;
  - pre-generation only during preparation;
  - move LOD databases out of the world (Voxy's was 393 MB). [environment]
- Datapack hygiene: prune stale functions, write LF. [_archive/audit-report]

## Iris and Sodium
Shader-pack facts are in gpu-iris.md.
- Reload: 0.5-1.9 s, or 3.2-5.3 s for a copy's first reload. A reload longer than the settle puts its stall in the window. -> Record the answer time. [environment, m3-run-plan-1] [MC] 26.3: 0.54-0.61 s warm, 1.72 s after a settings change, dev tier (spike V1, V3).
- Iris reload leak (issue #1569): +10.4 MB per reload, GPU time flat over 288 reloads. -> Cap 288 per session. [_archive/harness-plan] [MC] 26.3: refuted as a number: 20.6 MiB heap and 320 MiB private bytes per reload on the dev tier with debug options (spike V3); on the bench tier 33.16 MiB heap and 46.3 MiB private per reload in the full session (m1-acceptance-10; about 20 MiB heap in -5 to -7, roadmap.md#findings-assigned F14), so M2 sets the cap (roadmap.md#findings-assigned F4).
- `Iris.reload()` builds synchronously; a failed pipeline falls back to vanilla. -> Read the compile result. [m3-run-plan-1] [MC] 26.3: verified by reading; in a world the error goes to chat, not to getStoredError (spike R4).
- Sodium rebuilds terrain shaders lazily. -> Wait >= 2 frames after a reload. [MC] 26.3: verified by reading (PipelineManager's versionCounterForSodiumShaderReload).
- Sodium's `isTerrainRenderComplete()` reads the queue size only. -> Full predicate in mod.md#7-readiness. [MC] 26.3: verified (`getBuilder().isBuildQueueEmpty()`).
- A held predicate is not a final frame (2 of 34). -> The calibrated settle stays the floor.
- Meshing is client-side and cannot be pre-done. The Nether still meshed at 2 s (12.7 % drift). -> 4 s settle after a dimension change.
- First pipeline compile at launch ~4 s; with enableDebugOptions Iris writes patched_shaders on every build. [_archive/harness-plan-2]
- `BIOME_SULFUR_CAVES` was unknown on 1.21.11: a harmless 40-line warning per pipeline. [runbooks/troubleshooting] [MC] 26.3: gone (no such warning in the spike's logs).

## Determinism
ALC's recipe for bit-identical frames across launches:
- `frameCounter` and `frameTimeCounter` constant;
- 17 wall-clock `smooth()` half-lives at 0.001 s;
- TAA off (path-dependent rounding of +-1-2 levels; see the 2026-09-28 diagnosis below);
- the End flash pinned (a random vanilla event);
- the rain texture discarded (it scrolls on client ticks);
- static textures (62 animated textures held on frame 1);
- minimal particles.
-> Optilux builds this into BENCH_DETERMINISTIC instead of patching copies.

Further facts:
- Natural copies with TAA live had floors 3.7-5.4x looser. Two-session floors were too low: pristine upstream failed itself on 7 of 8 views.
- Open: End terrain shifted up to 3 levels between launches; cause undiagnosed. An in-session reference removes it.
- A driver update moved ALC's stored deterministic frames on 8/8 views. -> Optilux judges inside one session; stored references are recaptured when they stop matching. Drivers are never part of identity (user, 2026-10-05).
- A sentinel's first frame after a dimension change differed; its retake matched. -> Keep the rejected frame, retake once.
- Iris resets frameCounter and frameTimeCounter at every pipeline creation (reload, dimension change, join), and frameTimeCounter is wall-clock (gpu-iris.md#frame-counters-and-reload). ALC's "runs from game start" wording was imprecise; its pin of frameTimeCounter was still right. [MC] 26.3: verified (spike R5).
- A reload clears every colortex and re-meshes all chunks, so TAA history is built from still-meshing frames. It forgets them only up to fp16 rounding: ALC's "path-dependent rounding". [MC] 26.3: verified (spike R5; the re-mesh now starts in the new pipeline's first frame and runs asynchronously after it).
- 2026-09-28 diagnosis, same pack, two passes each: TAA on differed on 9/9 views; TAA off matched on 7/9 (the two others became the End-flash and rain pins). The "up to 11 % of pixels" figure has no surviving source.
- Bit-identical frames under live TAA did occur incidentally (end_dragon series across reloads), unexplained.

## Tools
- Offline methods, ranked by ALC's record and with what each may decide: offline.md.
- PresentMon 2.6 (fields and flags in measurement.md#tools):
  - the old field names (`TimeInMs`) broke the analyzer;
  - the console output is UTF-16 with a BOM;
  - `--qpc_time_ms` gives absolute QPC ms. -> Optilux compares it with the mod's qpcNs directly (mod.md#6-time-and-determinism).
- Two concurrent PresentMon sessions print the same presents microseconds apart: only 24 of 419 GPUBusy values were identical. -> Never match sessions by printed values; run one session. [m3-run-plan-2]
- A topmost popup over the game forces composition and changes the present mode. -> No overlays during sessions. [_archive/harness-plan-2]
- RGA:
  - treats every pixel shader as wave64; gfx1101 allocates VGPRs in steps of 12; the live wave size is unobservable;
  - gbuffers_terrain does not build offline. [amd-rdna3, ledger] [HW]
- CPU headroom at 4K: none of 2,124 captures was CPU-limited. [HW]
  - The lightest (3.6 ms, cave, TAA off) still read GPUBusy/FrameTime 1.00, with ~2.7 frames queued (GPULatency).
  - The GPU stayed power-limited at ~2.5 GHz with no downclock at light load.
  - PresentMon's CPUBusy tracks FrameTime (the render thread blocks in GL calls), so it cannot show headroom.
- ADL telemetry (50 ms) is diagnostic only. The GPU is power-limited at 310-315 W, hotspot 92-96 C, and its clock follows the load regime. [HW]

## Windows
- `SetForegroundWindow` is refused when the game is behind another window. The attached-thread-input request works. Windows grants activation through a one-shot right. Open: why two launches got none. [_archive/phase2-status]
- Windows 11 Notepad starts through a windowless stub, so it is a bad focus test; use charmap.exe.
- ALC's OS input lock: low-level hooks, started before the game, released by Escape x3. Raw mouse input bypassed it (971 events blocked, camera still turned). -> Optilux blocks input in the mod (`input.block`), raw motion included. [MC] 26.3: the rawMouseInput option is gone (deprecated.json lists it removed; InputConstants.grabMouse uses SDL3's relative mouse mode), so the suite writes no such key (user, 2026-10-06).
- Task Manager or qrenderdoc opening mid-session stole focus. `GetLastInputInfo` also counts the harness's own input. -> Idle check before a session; validity catches the rest.
- HAGS on (registry value 2); present mode Independent Flip in exclusive fullscreen (borderless: Composed: Copy with GPU GDI, measurement.md#validity); GPUBusy/FrameTime 0.995-1.005. [HW] [MC]

## Statistics
- GPU time has +-1 % regimes lasting 10-40 s. ABBA blocks were noisier (0.52 % rms) than bracketing each candidate between two A captures (0.33 %). Calibrated R=2 gave 0.21 %.
- Threshold history: twice the worst A/A deviation, floor 0.5 %, on only 9 comparisons per view ("few for a worst case"). -> Optilux uses null-candidate calibration (measurement.md#calibration).
- Tail: pooled p95. p99 swung up to 39.5 % between identical captures. -> Optilux uses the median of per-capture p95s, which the committed record can re-judge.
- A sentinel view that could not be measured once passed silently (fixed 2026-10-02). -> Missing = fail.
- Known-positive control: a retired change rerun as a new one reproduced on 7/7 views. -> It tells a blind harness from a working one.
- ALC closed candidates offline on unchanged ISA and on replay predictions. -> Optilux lets each offline method use only the power its record earned: offline.md#decision-powers.
- Calibration context hashes (snapshot, views, settings, mods, Java) must match. -> The identity in Optilux's run record.
- Natural mode and the flicker gate never flagged a change, and the deviation ratio flagged pure noise. -> No automated temporal gate without a positive control.

## GPU
RDNA3; full list, merged with the user's playbook, in gpu-iris.md.
- Compiled code depends on settings: at ALC's played settings, the SSR march never ran, the reflection blur was not built and colortex8 was unallocated. 7 backlog items closed offline after reading the dumps. [roadmap]

## Java
- ALC: Oracle GraalVM 21.0.12; bench heap 4096-10240 MiB. One JSON source for runtimes and flags; the started process was checked against it.
- Played flags (candidate set for jvm.md):
  - unlock: `UnlockExperimentalVMOptions`, `UnlockDiagnosticVMOptions`, `AlwaysActAsServerClassMachine`;
  - memory and misc: `AlwaysPreTouch`, `DisableExplicitGC`, `UseNUMA`, `PerfDisableSharedMem`, `UseFastUnorderedTimeStamps`;
  - code cache: `ReservedCodeCacheSize=400M`, `NonNMethodCodeHeapSize=12M`, `ProfiledCodeHeapSize=194M`, `NonProfiledCodeHeapSize=194M`, `-DontCompileHugeMethods`;
  - threads and prefetch: `UseCriticalJavaThreadPriority`, `ThreadPriorityPolicy=1`, `AllocatePrefetchStyle=3`;
  - Graal: `EagerJVMCI`, `-Dgraal.TuneInlinerExploration=1`;
  - G1: `MaxGCPauseMillis=37`, `G1HeapRegionSize=16M`, `G1NewSizePercent=23`, `G1ReservePercent=20`, `SurvivorRatio=32`, `G1MixedGCCountTarget=3`, `G1HeapWastePercent=20`, `InitiatingHeapOccupancyPercent=10`, `G1RSetUpdatingPauseTimePercent=0`, `MaxTenuringThreshold=1`, `G1SATBBufferEnqueueingThresholdPercent=30`, `G1ConcMarkStepDurationMillis=5.0`, `GCTimeRatio=99`.
- Mod build: Fabric Loom 1.18.x needs Java 25, so ALC pinned 1.17.21 on Java 21. 26.x requires Java 25 anyway.

## Mod
From ALC's alc-harness; the rewrite's spec is mod.md.
- Read every third-party mechanism at the pinned version (disassemble) before designing on it. ALC found 3 false premises this way, late ("a control described rather than read").
- `/tp`, `/tick` and reload behaviour: see Game control and Iris and Sodium above.
- Proven in game (launches 1 and B): frames byte-equal to F2 on 8/8 views; mod frames equal keystroke frames 8/8; accumulation equals compare.py on 16/16; inert without token; 40 reloads and 32 captures.
- Pipe bugs fixed in ALC review:
  - a client that left before the first wait broke `ConnectNamedPipe` (ERROR_NO_DATA) for the whole game; disconnect and continue;
  - errors were read with the wrong GetLastError;
  - a malformed line failed only after the request timeout instead of at once.
- `camera.pan` drifted when a late sway was still running. -> Starting a path stops any running path, inside the session.
- ALC's mod ran about 3x its line estimate (2,954 lines main + 1,565 tests against ~1,000 estimated), and launch 1 about 2x its time estimate (mod waits and ingest were not counted).
- A label is not enforcement. In Optilux the mod is part of the bench tier, so no tooling-session exception exists.

## Open at ALC close
- Unresolved:
  - the cause of the focus-lost launches;
  - whether AMD's own PresentMon session ran during ALC's calibration: answered by the spike, AMD Software starts PresentMon-x64.exe (RSXTraceSession) with every game;
  - the End terrain shift;
- Never exercised in game: per-pass GL timers, the mod-driven sway, the compile-error probe.
