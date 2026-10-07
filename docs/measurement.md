# Measurement
Status: draft; constants live in config/suite.json; nothing calibrated on mc-26.3 yet.

## Contents
Baseline suite · Session · Verdicts and cost rows · Validity · Calibration · Visual protocol · Run record · Readiness · Tools

## Baseline suite
config/suite.json is the source of every value below.
- Views: 11 view roles placed fresh in a new 26.3 world (user, 2026-10-05): ALC's 8 (6 overworld, 1 Nether, 1 End) plus `nether_soul` and `entities` (design.md D10, D11) and `end_city` (user, 2026-10-07; roadmap.md#decisions D29). `entities` is the only role with entities in view: creative mode, a torch in hand, frozen NoAI mobs. Each role names what it stresses and how to pick it.
  - Placement: 1. candidate poses from the role's rule (biomes located in game); 2. in-game check in one dev session (`camera.place` + capture): feature visible, not inside a block (a buried camera shows a black frame: ALC's nylium case), no entities in sight (except the entities role), GPU-bound at 4K, inside the pre-generated area with render-distance margin; 3. poses recorded in config/views/<world-id>.json (committed): id, dim, x, y, z, yaw, pitch, time, weather. Its hash joins the run identity and the datapack functions are generated from it.
  - World: bench_263, seed 263 (suite.json world), created in game; its eleven views in config/views/bench_263.json, flown and kept by the user (0.01.11); snapshot snapshots/bench_263/. Pre-generation and the GPU-bound check of step 2 come in M2.
  - The entities role's mobs and the coverage content carry the tag optilux_bench and PersistenceRequired; the setup function's kill spares them, the ender dragon and the end crystals on end_dragon's pillars, and runs at world preparation only.
- Quick set: suite.json modes.quick.views (one per dimension).
- Motion paths: suite.json motionPaths. Yaw sweeps; parameters set in M5. Perf on a path is reported, never a verdict: thresholds are calibrated on views only.
- Coverage views (M3): a frozen area with entities and special renderers, out of sight of the perf views.
- Reference pack: Complementary Unbound r5.9.3, unmodified. Profile `played`: the user's settings; profile `iso`: every dropped feature switched off (shader.md#dropped-features), kept features matched to Optilux as they land; start point: the ALC ablation costs in config/profiles/complementary-unbound-played.json.
- Resource packs: M2 calibrates on Faithful 64x alone. From M3 every session uses the deterministic set (Faithful 64x + optilux-static-textures, animated textures held on frame 1) and M3 recalibrates both modes on it. The run spec names the set; `run` refuses a set the calibration does not cover.
- Display: suite.json display, whose optionsTxt block holds every key the spike wrote and read back; the remaining options the harness writes are fixed in M1 from it (platform.md#install-and-launch).

## Session
1. Restore the world snapshot and hash-check it. One session per run name; run names are single-use.
2. Launch (announced). `optilux-helper` blocks game input; pauseOnLostFocus false. Start on the user's go or when the machine is idle.
3. `ready`, then the start-of-run reload and a 30 s GPU warm-up (mod-protocol.md#choreography).
4. Warm-up pass over all views; kept only if M2 shows pass 1 differs from pass 2.
5. Per view: a generated datapack function sets time and weather (`/function optilux:view/<id>`, written from the views file; LF; stale functions pruned); `camera.place` sets the exact pose; `ticks.step n` (n = suite.json capture.ticksAfterWeatherChange) only when overworld weather changes. The GUI is hidden (`hud.set hideGui`) at every view but entities: hiding it also drops the held item, and entities keeps its torch in frame (0.01.12's frames, handoff.md); captures stop before the GUI, so no frame shows it.
6. Per variant: reload, then read the compile result (a failed pipeline falls back to vanilla, so a compile error invalidates the variant); wait at least 2 frames (Sodium rebuilds terrain shaders lazily); settle: the window's skipSeconds is the largest suite.json settle that applies to anything since the last window (afterReload, afterViewSwitch, afterDimensionChange).
7. Schedule: A, then (Ci, A) pairs, R rounds; the A/A twin is always one Ci. `run` refuses a spec whose planned reloads (start-of-run + warm-up pass + views x (1 + 2 x R x (candidates + 1))) exceed suite.json capture.reloadCap (288, the Iris reload leak; re-measure on the platform): full mode holds at most 5 candidates plus the twin.
8. Capture: PresentMon GPUBusy median (primary), and as the tail the median of per-capture p95 frame times, which the record can re-judge. One PresentMon session at a time, its rows cut by the mod's window stamps (mod-protocol.md#choreography). FPS is shown for humans only. Settle and window are in seconds, timed by the mod on the QPC clock.
9. Perf windows measure the variant with BENCH_DETERMINISTIC on, the build that also gives its frames (user, 2026-10-06). Each release carries a cost row of the define (on vs off) on every view, and the M6 ratio vs Unbound is measured with it off.

## Verdicts and cost rows
- Combining: per view and round, ratio_r = median GPUBusy of the Ci capture / mean of the median GPUBusy of its two adjacent A captures; ratio = mean of ratio_r over R rounds; delta = 100 x (ratio - 1), in %, negative = faster. Thresholds use the same unit; cost rows in ms use the view's threshold x the baseline's median GPUBusy.
- Optimization verdict: one test on the delta of the geo-mean ratio over the mode's views: accept if delta <= -threshold; reject if delta >= +threshold; else inconclusive. Per-view deltas are reported, and a view beyond its own threshold is flagged.
  - A candidate with an invalid or missing capture on any view of the mode, or left GPU-bound on one (Validity), is inconclusive and names the view. The geo-mean is never taken over fewer views than the verdict's set, except views closed offline by dump equality, which are left out and named in the record (Calibration). A Ci capture whose adjacent A is invalid is invalid too. Missing = fail, for candidates as for the twin.
- Confirmation: an accept within 2x threshold is re-measured in a second session before it ships.
- Feature cost row: per-view ms delta, feature off vs on, with its threshold. No accept or reject; rows feed the budget (shader.md#method).
- Timer cost rows, for frames below the CPU floor:
  - per-pass GPU timer medians, only after mod acceptance A11 (mod.md#12-acceptance), and only with no dropped timer frames in the window;
  - thresholds from timer twins: null sessions on the mode's schedule with the chosen timer source on, in the tier whose sessions use the rows (order: calibration, A11, timer twins; design.md E3);
  - the record labels each row as a timer row;
  - submission control: a GL timer also counts GPU idle inside a pass while the CPU is still submitting, so CPU-limited frames can inflate it. Before timer rows are used, the same variant and view run with and without a fixed CPU load on the game's cores. A pass whose timer moves beyond its timer threshold is submission-sensitive, and its rows stay indicative. Fullscreen passes (composite, deferred, final) are expected to pass; geometry passes (gbuffers, shadow) are the risk.
- Indicative rows never feed a verdict or a budget.
- Below threshold in quick mode -> "inconclusive, run full".
- A stack that includes rejected changes is not the shipped set (ALC). Measure the shipped set itself before a release claims a number.

## Validity
- The baseline must be GPU-bound: GPUBusy >= 90 % of FrameTime per capture, else the capture is invalid for GPUBusy verdicts and cost rows. It stays valid for timer rows once A11 and the submission control have passed; the record marks the capture cpuLimited and each of its rows as a timer row.
- A candidate below 90 % is "left GPU-bound": its GPUBusy rows on that view are indicative. Neither Iris nor vanilla has a render scale to escape to. Measure it on a heavier base that stays GPU-bound, or with per-pass GPU timers (A11).
- CPU headroom (ALC, lessons.md#tools): no capture at 4K was CPU-limited. The lightest GPU-bound captures bound the CPU floor from above (suite.json validity.cpuFloorMs.alcUpperBound: cave 3.6 ms, nether_crimson 3.8, underwater 4.0, night 4.4; the rest 4.6 and heavier); the 90 % rule fails at 0.9x the floor, so the invalid edge is at or below ~3.3 ms on cave. M2 measures the real floor per view with a passthrough pack; early Optilux packs (M4) will sit below it, so their cost rows come from per-pass timers.
- A draining GPU queue is a second sign: GPULatency (PresentMon 2.x: time from the frame's CPU start until the GPU started on it) reads several frames with a full queue and under one when the GPU idles (ALC ~2.7 frames; the spike's idle L1 capture read 1.04 at 141 fps). CPUBusy is not a sign: it tracks FrameTime.
- >= 100 frames per capture; the two halves agree within 3 %.
- PresentMode is Hardware: Independent Flip on every row of the window; any other mode invalidates the capture (an overlay forced composition, lessons.md#tools).
- A/A twin beyond the geo-mean threshold -> the whole session is inconclusive. A twin that could not be measured on a view fails, never passes silently.
- Run identity must match the calibration identity, or the result is refused.

## Calibration
- Per mode: complete sessions on that mode's schedule with 5 twins as candidates; at least 4 sessions (>= 20 null candidates). Regime shifts land inside the null distribution. Estimated ~2 h per identity for both modes.
- Thresholds: on |delta| of the null candidates, the level exceeded by <= 5 % of them (with 20, the largest), floor 0.5 %; accept and reject use it with opposite signs. Computed per view, and for the geo-mean over the exact view set a verdict uses: the calibration file stores every null candidate's per-view ratios, and `compare` derives the geo-mean threshold for that subset.
- The thresholds are empirical. Twins in one session share its launch state, so 20 twins are not 20 independent checks and "<= 5 % false accepts" is a target, not a bound; every session's A/A twin is a fresh null result. If more than 2 of the last 20 twins under the current calibration exceed the geo-mean threshold (7.5 % odds by chance at 5 %), recalibrate; the window restarts at each calibration.
- Matched key by key on the identity (run-record.md#identity). The baseline pack is recorded in the calibration file, not matched (user, 2026-10-06): thresholds are relative, and the twin monitor guards a baseline whose noise differs. Calibrations are committed (config/calibrations/<id>.json).
  - Any identity change means recalibration: every key under run-record.md#identity (platform's loaded sections and mod tier, launch spec, mod jars incl. optilux-helper, world snapshot, views file, resource packs, written settings, suite measurement sections and modes, Java, system).
  - Graphics drivers are assumed good and never part of identity (user, 2026-10-05). Every verdict compares variants inside one session, so a driver change between sessions cannot bias one; a change in noise shows in the twin monitor. Stored Optilux reference frames (deterministic) are recaptured whenever they stop matching; Unbound reference frames are look references for side-by-side review and are never matched.
- Known-positive control at every new calibration: shadows off on Complementary must be detected with the right sign.

## Visual protocol
- Determinism rests on Iris facts re-verified in the spike (R5; gpu-iris.md#frame-counters-and-reload): frameCounter and frameTimeCounter reset at every pipeline creation; frameTimeCounter is wall-clock; a reload clears every buffer and re-meshes all chunks, so the first frames after it are not final.
- BENCH_DETERMINISTIC, from Optilux's first commit:
  - frameTimeCounter pinned to a constant (ALC pinned it to 0);
  - every frame-varying term (jitter, dither, noise offsets) derives from frameCounter modulo one cycle;
  - smoothing instant, animation pinned. Wall-clock smoothing otherwise keeps moving under /tick freeze;
  - static textures, rain texture discarded, End flash pinned (ALC).
- Static capture, TAA off (M3): `ready`, then capture at an aligned phase. ALC's recipe: bit-identical across launches on 8/8 views.
- Static capture, TAA on (M5): history built while chunks re-mesh is forgotten only up to fp16 rounding (ALC: TAA on differed on 9/9 views). So:
  1. `ready`;
  2. flush the history at an aligned frame (Terms: flush; the mechanism lives in mod.md#6-time-and-determinism);
  3. capture N_conv frames after the flush, where N_conv is the smallest n with w^n <= 1/255 for history weight w, derived in code.
  - Flush and capture are one request inside the mod (mod-protocol.md#commands, frames.capture).
- Determinism check: two flush + capture cycles in one session must be identical. This replaces "frame n equals frame n + cycle", which a TAA rounding orbit may never satisfy. It also catches a frame that was not yet final (ALC: 2 of 34).
- Motion path (M5): the mod sets the pose per rendered frame from frames since the path start. The path starts at an aligned frame after a flush; path and capture are one request. A/B sequences compare frame by frame.
- Tiers: identical (decoded pixels equal) / near (max |d| <= 1 on every pixel) / close (mean FLIP <= 0.005, p99.9 <= 0.10, SSIM >= 0.995) / review.
- Required tier: an optimization must be identical or near on every view; close or review needs the user's sign-off. A feature always goes to review.
- Review page: side by side (static, sequences, coverage). Claude pre-screens the frames visually and marks suspects; the user decides.
- Live pass: BENCH_DETERMINISTIC off; real-time motion path, animation and weather; frames at fixed wall-clock intervals; visual only, never perf; checklist: ghosting, shimmer, flicker, animation, exposure smoothing; required at the M5 and M6 exits and for any change to time, smoothing or animation code.
- Temporal artifacts: no automated gate until a positive control passes. History rejection off must be flagged as ghosting, and jitter off as aliasing. Candidate metric: ColorVideoVDP (offline.md#tools).
- Complementary unmodified is probably not deterministic (ALC needed modified copies): perf baselines and look references only.

## Run record
The identity contract (every input that can move a measurement), the record's fields, comparison rules and the run spec: run-record.md. Verdicts are re-judged from the record's per-capture summaries alone.

## Readiness
- Predicate: mod.md#7-readiness (Sodium's own isTerrainRenderComplete() reads only the queue size). [MC] 26.3: verified; the 0.9.2 fields are in platform.md#mod-adapter-surface, and M1 rebuilds the predicate on them.
- For visual captures the calibrated settle stays the floor until A5 shows predicate-ready -> frame-final over at least 30 waits (mod.md#12-acceptance); perf windows keep the calibrated settle regardless, because the thresholds were calibrated with it.
- Chunk meshing is client-side and cannot be pre-done; dimension changes need the longer settle.

## Tools
- PresentMon 2.6 (config/tools.json), one continuous session per run:
  - command: `--process_id <pid> --output_file <f> --qpc_time_ms --v2_metrics --session_name optilux-<run> --stop_existing_session --no_console_stats`;
  - fields: CPUStartQPCTime (absolute QPC, ms), FrameTime, GPUBusy, GPULatency, PresentMode;
  - window cut: rows whose CPUStartQPCTime x 1e6 lies between the mod's window.start and window.end qpcNs (mod.md#6-time-and-determinism). Both read one counter; an offset within A9's 1 ms moves at most one frame at each window edge, the same for every variant, and GPUBusy itself is timed on the GPU;
  - the CSV grows during the run and completes at exit; the first row arrives ~4 s after the start (spike L1), so the window cut, never a sleep, defines the capture. Stop it the one way that leaves no ETW session behind: CTRL_BREAK_EVENT through GenerateConsoleCtrlEvent to PresentMon in its own console process group (CTRL_C_EVENT is ignored there: Windows disables Ctrl+C in a CREATE_NEW_PROCESS_GROUP child; spike L1); a killed PresentMon leaves its session running;
  - AMD Software starts its own PresentMon-x64.exe (session RSXTraceSession, v1 metrics to stdout) with every game and stops it after (spike L1); record it, never block on it.
- FLIP (flip-evaluator), LDR, sRGB inputs, ppd from suite.json. SSIM and PSNR via scikit-image.
- RenderDoc 1.46 (debug tier): injected by gfx-debuggers (`-Ddebugger=renderdoc`, forward-slash path); what replay may decide: offline.md#decision-powers.
- Python deps: locked in uv.lock (workflow.md#code-conventions). ALC's set is the start: numpy, pillow, scikit-image, scipy, flip-evaluator, minecraft-launcher-lib, nbtlib.
