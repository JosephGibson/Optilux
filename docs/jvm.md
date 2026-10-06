# JVM track
Status: designed 2026-10-05; built after shader 1.0 (user decision).

## Contents
Goal · Why a separate protocol · Metrics · Scenarios · Axes · Protocol · JVM Expert · Build order · Carried from ALC

## Goal
- Rank Java runtime, JVM flags, heap, GC, runtime mods and renderer backend by measured play quality on the machine that runs it. Report with evidence and confidence.
- Scope is stated in every report: machine, platform, mod tier. "Settle it once and for all" (draft v0) means once per machine and platform. Anyone can run `optilux jvm` on their own machine and get their own report.

## Why a separate protocol
- A JVM change needs a relaunch. Noise between launches dominates, not the in-session noise ALC calibrated.
- CPU-side metrics are noisier than GPUBusy, and GPU-bound shader scenes hide JVM effects.
- Therefore:
  - launch-level bracketing: A, C1, A, C2, A, ...;
  - A/A launches for calibration;
  - more repeats;
  - long runs scheduled while the machine is idle.

## Metrics
Per launch, all into one run record.
- Frame pacing: frame-time p50, p99, p99.9; stutter count (frames over 2x the rolling median). Source: PresentMon.
- GC: pause count, total and max pause, allocation rate. Source: unified logging (`-Xlog:gc*`) or JFR.
- Server tick: integrated-server MSPT mean and p99. Source: the helper mod.
- Chunk generation: chunks/s from a Chunky pre-gen of fixed radius on a fresh copy of a fixed-seed world.
- Flight throughput: chunk load and mesh rate along a fixed camera path at fixed speed through ungenerated terrain.
- Startup: launch to `ready`.
- Memory: heap after GC at steady state; process private bytes.
- Stability: crashes, out-of-memory errors, errors in latest.log.

## Scenarios
- S1 startup + idle: launch, load the world, hold a view for a fixed time.
- S2 flight: fixed path through fresh terrain (fresh world copy, fixed seed).
- S3 pregen: Chunky, fixed radius, fresh world copy.
- S4 played steady: the played tier at a view; pacing only.
- Resolution: run where the GPU is not the bottleneck (the vanilla renderer, or windowed at a lower resolution; neither vanilla nor Iris has a render scale, measurement.md#validity) so JVM effects show. Then once at the play setup for realism.

## Axes
- Runtime: Temurin 25 (reference = config/java/bench.json), GraalVM 25, Zulu 25, Microsoft OpenJDK 25. Java 25 is required on 26.x.
- GC: G1 (default), generational ZGC, generational Shenandoah. Verify flag names on each runtime.
- Heap: fixed Xms = Xmx at 4, 6, 8, 10 GB.
- Flag sets:
  - none (defaults);
  - the user's played set, ported from GraalVM 21 (lessons.md#java); drop flags Java 25 rejects;
  - a community G1 set;
  - Java 25 features: compact object headers, AOT cache for startup. Verify names and status on the chosen runtime.
- Runtime mods (jvm tier): Lithium, C2ME (alpha).
- Renderer backend: OpenGL vs Vulkan, on vanilla only (Iris needs OpenGL on 26.3). The backend is a platform field (platform.md#concept), so this experiment declares the renderer option as its treatment: `compare` lets that written setting alone differ and the record notes the override.
- Design:
  - screen one change at a time against the reference;
  - then combine the winners;
  - no full factorial.

## Protocol
- Fresh world copy per launch for S2 and S3; the same snapshot for S1 and S4.
- Launch order: A, C1, A, C2, A, ... with an A/A twin launch in every batch.
- Calibration per scenario: at least 20 null launch pairs (a null pair is two consecutive A launches of the bracket: n candidate launches give n + 1 A's and n null pairs). Each metric's threshold is the level of |delta| exceeded by at most 5 % of null pairs, applied with opposite signs.
- Machine idle, input blocked by the mod, every launch announced.
- Run identity already carries the JVM fields (run-record.md#identity: java runtime, version, heap, args; the platform's mod tier). Each JVM experiment declares the field it varies as its treatment, so `compare` allows that field alone to differ (run-record.md#comparison).
- Validity:
  - the process completes the scenario;
  - the GC log parses;
  - a crash is a result only in a stability run.

## JVM Expert
`optilux jvm report`:
- per scenario and metric: ratio against the reference, threshold, verdict;
- plots: frame-time histograms, GC pause timelines, chunk throughput;
- ranked recommendations with their evidence;
- the recommended args exported as a profile (config/java/<name>.json) the harness can launch with.

## Build order
Post-1.0, outline only; Phase 0 of that track details it.
- J1: GC-log and frame-pacing parsing; S1 and S3; reference and A/A calibration; the helper mod's presence and known-effect overhead arms (mod.md#12-acceptance, A8).
- J2: S2 flight path; one-at-a-time screening of the axes.
- J3: combinations; report; profile export.
- J4: renderer-backend axis; S4 on the played tier.

## Carried from ALC
- One source for runtimes, heaps and flags (ALC java-runtime.json) -> config/java/*.json. The harness checks the started process's real args against it.
- ALC's played flags (GraalVM 21, G1 tuning, code cache, JVMCI) are listed in lessons.md#java as a candidate set, not a default.
- Observations:
  - AlwaysPreTouch costs ~1 s per start (est.);
  - the first shader pipeline compile is ~4 s at launch;
  - no GC log was ever analysed.
