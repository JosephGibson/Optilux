# Optilux design
Status: Phase 0 closed 2026-10-06; roadmap.md holds the milestones and M0's phases, prompts in docs/prompts/m0.md. Next: M0 (handoff.md).

## Contents
1 Goals · 2 Non-goals · 3 Core rule · 4 Architecture · 5 Interfaces · 6 Milestones · 7 Decisions taken · 8 Open decisions

## 1. Goals
- G1 Optilux shader: an original Iris shader pack with the Complementary Unbound look, leaner and faster than Unbound at matched features. Built, measured and released through Claude Code.
- G2 Runtime report (post-1.0): the best Java runtime, JVM flags and runtime settings for the machine that runs it, from measured frame pacing, GC, chunk generation, tick time, startup and stability (jvm.md).
- G3 One suite for both: one harness, one helper mod, one run-record format. A new Minecraft version or renderer is a new platform file plus an adapter, not a rewrite (platform.md).
- Scope: boutique. One machine (Windows 11, RX 7800 XT, 5800X3D, HAGS on, 3840x2160). One platform at a time (mc-26.3). One developer; others may download releases.
- Quality bar: a strong tool for the user, not a software showcase. Low overhead, cheap to maintain, tests only where cheap and valuable.

## 2. Non-goals
- Several MC versions or machines at once for the shader.
- OptiFine; before 1.0, any shader loader other than the current backend (iris-gl); Aperture follows the renderer transition (platform.md#renderer-transition).
- Every Complementary feature on the user's drop list (shader.md#dropped-features), plus ray and path tracing.
- Driver workarounds, or drivers in run identity: drivers are assumed good.
- Shipping textures: Faithful 64x is the build and test pack; nothing from it ships.
- Extensive test coverage.

## 3. Core rule
Carried from ALC.
- The loop is the product: edit -> hot reload -> mod places the camera -> frames + GPU ms vs baseline in the SAME session -> verdict or cost row + run record.
- Build a component only if it makes the loop faster or its verdicts more trustworthy.
- Trust = in-session bracketing, A/A twin tripwire, thresholds from null calibration, decoded-pixel equality as the only proof of "no visual change" (measurement.md).
  - ALC: rms A/A noise 0.21 %, thresholds 0.5-1.3 % per view; 5 candidates per ~35 min campaign; a known positive reproduced on 7/7 views; a 5-change stack = product of its singles; frames bit-identical 8/8 across launches.
- Agent time is the constraint, not machine time (ALC: ~40 min machine vs 12-24 h agent per batch, est.). Gates, docs and skills are budgeted like GPU ms.
- No milestone closes on dummies: loop milestones exit on real packs. (ALC: M0-M3, 5 of 9 days, 0 shader changes.)
- Wins come from removing work nothing uses and hoisting invariant math; micro-arithmetic measured zero (ALC, lessons.md#outcomes).

## 4. Architecture
```
user / Claude Code --skills--> optilux CLI (Python)
  install, launch      platform file -> runtime/<platform>/ (no launcher)
  run                  run spec -> named pipe (JSON lines) -> optilux-helper mod (Fabric)
                       PresentMon (ETW) -> GPU ms          camera, reload, capture, input.block
  compare, report      run records (results/records/) <- frames, samples, identity
  check, verify        offline levels (offline.md); docs limits, similarity, records
```
- harness: Python package `optilux`, CLI `optilux <verb>`; one `.venv`, pinned requirements.
- helper mod `optilux-helper`: full redesign and rewrite (user, 2026-10-05). Pure-Java core plus one adapter set per platform. Spec in mod.md, wire contract in mod-protocol.md; written from these docs alone, no ALC code (user, 2026-10-06).
- shader pack `optilux`: backend iris-gl; a backend-neutral pipeline spec (shader.md#pipeline-spec) so an Aperture backend can follow.
- platform layer: config/platforms/<id>.json, the mod adapter and the world snapshot (platform.md).
- data:
  - config/: tracked inputs (platforms with their launch specs, suite, profiles, java, tools, views, pipeline.json) and calibrations/ (committed).
  - results/records/: run records, committed (the ledger; per-capture summaries, ~200 KB budget); results/raw/: frame samples and heavy artifacts, ignored and disposable.
    - Records are append-only, so git stores each once, compressed; growth is linear. `verify records` enforces the budget. Past 100 MB of records (~500 sessions, est.), stop and choose an archive for older ones.
  - runtime/: installed games, ignored.
  - snapshots/: worlds, ignored.
  - reference/: Complementary source for study, ignored, never redistributed.
- Experts (draft v0 roles) are bundles, not programs:
  - Shader Expert = main session + optilux-bench and optilux-research skills + read-only researcher agent + `optilux.shader` + Viewfinder's MCP in dev sessions (offline.md).
  - JVM Expert = `optilux.jvm` reporter (rank, graph, recommend) + JVM scenarios (post-1.0).

## 5. Interfaces
- CLI: `optilux <verb>`. This table is the one list of verbs; other docs point here. Exit 0 ok, 1 failed; `--json` where the output is structured.

  | Verb | Does | From |
  |---|---|---|
  | install | Minecraft, Fabric, the tier's mods, Java and tools (config/tools.json) into runtime/, hash-checked; write or check the launch spec | M1 |
  | launch | check the launch spec's hashes, start the game directly (token on the command line) | M1 |
  | run | validate a run spec, run the session, write the run record | M1 |
  | mod build / test | Gradle through the pinned wrapper, no daemon left | M1 |
  | world prep / snapshot / restore | pre-generate, snapshot and hash, restore | M2 |
  | calibrate | null sessions per mode -> config/calibrations/ | M2 |
  | compare / report | verdicts, cost rows, tiers; one page per run | M2 |
  | check L0..L4 | offline levels (offline.md) | M3 (L0-L2), M4 (L3-L4) |
  | verify docs / similarity / records | static checks | M0 (similarity M3, records M2) |
  | pack build / release | the shader zip | M0 |
  | milestone start | cut the milestone branch from origin/main | M0 |
  | status | where things stand, and the next prompt | M0 |
  | test | unit tests | M0 |
  | jvm | JVM scenarios and report | post-1.0 |
- Mod protocol: mod-protocol.md.
  - Named pipe, JSON lines, token-gated.
  - Concurrent requests matched by id; push events.
  - frameIndex + sinceReload + qpcNs on every result and event.
  - The harness adapts to `capabilities`, never to the MC version string.
- Run spec (input) and run record (output): run-record.md.
- Platform file: platform.md, config/platforms/mc-26.3.json.
- Suite and profiles: config/suite.json, config/profiles/*.json.

## 6. Milestones
Sketch; roadmap.md holds the milestones, phases and prompt sets (docs/prompts/). Version 0.MM.PP.N = milestone MM, phase PP, patch N (0 for the phase itself). One commit per phase, one PR and one release per milestone.
- Phase -1: this design set; open decisions closed; runtime spike. Exit: spike passes and its findings are folded into these docs; user approves the set.
- Phase 0: roadmap. Exit: docs/roadmap.md + the prompt set for M0.
- M0 foundation: repo, AGENTS.md, hooks, CI (tests + packaging), release workflow shipping a placeholder pack, `optilux status`, doc-limit test. Exit: a merged PR produces a private release.
- Sizing rule: a milestone whose plan would pass the 40 KB plan cap is split before it starts.
  - Unattended machine time (calibration, the overhead experiment) does not count: agent time is the constraint (section 3).
  - ALC: M1 (9 launches, 53.5 min) and M2 (2 launches) ran to plan.
  - The case to avoid is ALC's M3: it built a new mod and the measuring path that used it together. That took two run plans (118 KB and 57 KB), and the mod ran 3x its estimate.
- Tripwire: if M0-M3 together run past twice their summed estimates, stop and re-plan before building more infrastructure.
- M1 game control: install, launch, the mod's M1 commands (mod-protocol.md#commands). Exit: mod acceptance A1-A4, A7, A9, A10 (mod.md#12-acceptance) on unmodified Complementary, in a provisional world with three views (one per dimension): a copy of the spike's `spike` world placed under snapshots/provisional/ by hand and hashed; its Nether and End views are reached with `camera.place`'s `dimension` argument, then the snapshot is retaken; the `world` verbs replace this in M2. A2 and A3 are re-run on the final views in M2.
- M2 perf loop: the new world with the view roles placed; run, compare, report, run records; calibration per mode. Exit, all of:
  - each mode calibrated on unmodified Complementary;
  - quick + full: twin null, and a known positive (shadows off) detected with the right sign beyond the calibrated threshold. ALC's 0.667 ms is context, not a gate: the platform, pack build and views all differ;
  - the CPU floor measured per view with a passthrough pack (measurement.md#validity);
  - A2 and A3 re-run on the final views;
  - A8 timer overhead, A11 timers kept or dropped;
  - `compare` refuses a mismatched identity.
- M3 visual loop: the static-texture pack, the hello pack (BENCH_DETERMINISTIC, TAA off) with pipeline spec v0, offline levels L0-L2, coverage views, review page, iso-feature profile v1, similarity check; both modes recalibrated on the deterministic resource-pack set (measurement.md#baseline-suite). Exit: every perf view identical across 2 sessions (TAA off, ALC's recipe); A5 readiness.
- M4 shader base: every coverage-list program, lighting, tonemap; cost rows, from per-pass timers where frames sit below the CPU floor; offline levels L3-L4 and debug-tier attribution.
- M5 shader features and temporal: shadows, sky, clouds, water, fog, AO, bloom, full TAA; the history flush; A6 motion and A12 TAA-on determinism, or E4's fallback; temporal positive controls; live pass.
- M6 1.0: ratio vs Unbound iso reported (no gate); live pass; look review; README; release.
- Post-1.0: optimization at full precision; JVM track; lod tier when Voxy ships for the platform; Aperture backend when public.

## 7. Decisions taken (user, 2026-10-05)
- Name: Optilux. Target mc-26.3; the design stays MC-version-independent.
- Renderer: Iris/OpenGL now; backend-neutral pipeline spec; Aperture port later.
- JVM: designed now (jvm.md), built after 1.0.
- LOD: Voxy once it ships for the platform (lod tier).
- Display: 3840x2160 for play and bench.
- Git: rebase merge; one milestone branch at a time.
- License: full rewrite. Complementary's dev team agreed as long as nothing is a 1-1 copy. Source may be studied; Optilux ships MIT.
- Performance: no fixed target; 1.0 reports the ratio.
- Reference packs: Complementary Unbound only.
- Textures: build and test on Faithful 64x; ship nothing from it.
- Mod tiers: bench, played, debug, dev, lod, jvm (platform.md#mod-tiers).
- Home: C:\Projects\Optilux.
- JVM evidence comes from launch-level bracketing, never from a hot reload (jvm.md).
- Commits: Claude commits as the user; no Claude credit anywhere.
- Release notes: CHANGELOG.md.
- Bench Java: Temurin 25, default G1, Xms = Xmx, no extra flags (config/java/bench.json).
- World: a new 26.3 world. ALC's 8 view roles plus nether_soul and entities (D10, D11) are placed fresh (measurement.md#baseline-suite).
- Shader scope: the user's drop list plus a second round (light shafts, border and cave fog, light-level overlay). Kept: held-item light, night sky styles, End beams and flash, entity shadows, block reflections, rain puddles, image sharpening, underwater distortion, block-light flicker. Outline as played (vanilla). See shader.md#look-and-scope; the iso profile is config/profiles/complementary-unbound-iso.json.
- Drivers: assumed good; no workarounds, never part of run identity. Records note the version, so a stored frame that stops matching has its cause at hand (an overnight driver update stopped an ALC run).
- Helper mod: full redesign and rewrite, not a port (mod.md).
- Optimization playbook: the user's playbook is kept verbatim (sources/) and curated into playbook.md and gpu-iris.md. Every technique stays a hypothesis until Optilux measures it.
- The following defaults were applied on the user's instruction (2026-10-05) and confirmed one by one (user, 2026-10-06).
  - D5 FLIP viewing distance: about 70 cm from the 32-inch 4K panel.
  - D6 GitHub: private repo `Optilux`, created at the start of M0; milestone branches `m0`, `m1`, ...
  - D7 Credit, in README and next to the MIT license: "Optilux is inspired by Complementary Shaders by EminGT. It is a full rewrite and contains no Complementary code."
  - D8 Mod list: config/platforms/mc-26.3.json as pinned on 2026-10-05. ScalableLux and C2ME are re-pinned when stable builds land.
  - D10 Views: a second Nether role, `nether_soul` (soul sand valley), joins full mode.
  - D11 Entity costs: an `entities` perf role (creative mode, a torch in hand, frozen NoAI mobs in sun) joins full mode. Its cost rows cover entity shadows and held-item light. It is the one exception to the no-entities rule.
  - Mod transport: the named pipe with an explicit DACL; the TCP fallback only if it fails acceptance (E1).

## 8. Open decisions
Section 7's decisions are closed (D5-D8, D10 and D11 carry labels; the rest are unlabeled). These close by evidence:
- E1 Transport: switch only if the named pipe fails the mod's M1 acceptance (mod.md#12-acceptance).
  - Fallback: loopback TCP (127.0.0.1, ephemeral port; any local process can connect, so the token is the only gate). AF_UNIX is not an option on the harness side: CPython for Windows undefines it (Modules/socketmodule.h), the user's 3.12.10 has no socket.AF_UNIX, and the enabling change (python/cpython issue 77589, PR 137420) is unreleased.
  - ALC's pipe failures were bugs in its own code, fixed in review (lessons.md#mod), not pipe faults. I/O stays off the render thread (mod.md#4-architecture).
- E2 Leaf lighting: forward or deferred lighting for cutout terrain. Decided in M4 by building both on the forest view and comparing cost rows and look (playbook.md#6-did-not-work).
- E3 Per-pass GPU timers: Viewfinder's (dev tier) or optilux-helper's own, whichever passes A11 first (M2). Viewfinder's timings are dev tier, so cost rows can carry them only from dev-tier sessions calibrated with timer twins, the dev tier in the row's identity (platform.md#mod-tiers; measurement.md#verdicts-and-cost-rows); otherwise E3 falls to optilux-helper's timers. Without either, cost rows below the CPU floor need a heavier base.
- E4 TAA-on determinism: the one-frame hideGUI history flush is proposed, not verified (A12, M5). If it fails, the fallback also sets M5's exit:
  - A6 runs with TAA off: one motion sequence identical across 2 sessions;
  - A12 is replaced by M3's TAA-off check (every perf view identical across 2 sessions), re-run on the M5 pack;
  - visual verdicts (required tiers) are judged on TAA-off captures; TAA-on output goes to the review tier on every perf view and motion sequence, with the live pass.
- E5 Viewfinder: adopted for development and diagnostics over MCP (dev tier, offline.md). It counts as measurement evidence only after the A8 timers arm with Viewfinder as the source (the presence check waits for J1, jvm.md#build-order), and after its timings pass A11.
