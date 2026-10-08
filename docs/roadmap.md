# Roadmap
Status: milestones M0-M6, the current one in detail, the findings assigned and the decisions.

## Contents
Rules · M0 foundation · M0 phases · M1 game control · M2 perf loop · M2 phases · M1 to M6 · Findings assigned · Decisions · Estimates

## Rules
- Commits and versions (D33): Conventional Commits, each one logical, test-green change (`optilux test` and `optilux verify docs` pass before it), a phase one or more of them (workflow.md#git); the version in VERSION, a milestone a minor release, one PR and one release per milestone plus patches (workflow.md#release). Phases are M<N>.P<PP>; M0's and M1's are 0.MM.PP.
- Sizing rule (design.md#6-milestones): a milestone whose plan would pass the 40,960-byte plan cap is split before it starts. Unattended machine time (calibration, the overhead experiment) does not count: agent time is the constraint (design.md#3-core-rule).
- Tripwire (design.md#6-milestones): if M0-M3 together run past twice their summed estimates, stop and re-plan before building more infrastructure. Estimates holds the sums; every handoff adds the actuals.
- This file holds the current milestone in detail and the others one line each (workflow.md#doc-ownership). When a milestone closes, its section shrinks to one line and the next one expands from its approved plan; Findings assigned keeps a row until the finding has landed.
- Running a milestone: plan from docs/templates/plan.md, optional /critique, the user's approval, the prompt set, the unattended run, the handoff (workflow.md#running-a-milestone). An unattended run asks nothing mid-run: it takes the recommendation in Decisions or the plan, or logs the question in the handoff.
- No milestone closes on dummies (design.md#3-core-rule). M0 ships a placeholder pack because its exit is the release path, not a pack; M1-M3 exit on real packs.

## M0 foundation
- Closed with release v0.00.06 (2026-10-06): repository, harness skeleton (`test`, `verify docs`, `status`, `milestone start`, `pack build`, `pack release`), hooks, CI, the release workflow, optilux-next, optilux-release, the agents, the placeholder pack; about 3.3 h against 7.8 estimated. Plan: plans/m0.md; prompts: prompts/m0.md; what happened: the 0.00.06 handoff in git history.

## M0 phases
- 0.00.00 to 0.00.06 ran as planned in plans/m0.md section 5; the per-phase table is in the 0.00.06 handoff (git history).

## M1 game control
- Closed with release v0.2.0 (2026-10-08): `install`, `launch`, `run` for acceptance runs, `mod build`, `mod test` and the helper mod's 17 M1 commands, accepted on A1-A4, A7, A9 and A10 (m1-acceptance-10); the bench world bench_263 and its eleven views; optilux-plan; the QA pass; about 20.3 h against 28 estimated. Plan: plans/m1.md; prompts: prompts/m1.md; what happened: the 0.01.13 handoff and the workflow pass's, in git history; its open rows: Findings assigned.

## M2 perf loop
- Goal (plans/m2.md section 1): calibrated sessions on bench_263's views say whether a shader change is faster, slower or inside the noise, with every input that can move the numbers in the record's identity.
- Verbs (design.md#5-interfaces, From = M2): `world prep`, `world snapshot`, `world restore`, `calibrate`, `compare`, `report`, `verify records`, and `run`'s measurement and calibration kinds with `run --check`. Mod: `window.measure`, `timers.start`, `timers.read`, `timers.stop`, `state`'s framebuffer size and F23's rows. Skill: optilux-bench.
- Not in M2 (plans/m2.md section 2): Viewfinder's timers and E5, which stays diagnostic; timer twins and timer cost rows (M4); the hello pack, the deterministic set, A5, `shaders.dump`, visual tiers, `check` and `verify similarity` (M3); `camera.path`, the flush, A6 and A12 (M5); declared treatments and launch-level bracketing (the JVM track, after 1.0); A9's capture path (M3, plans/m2.md D48); Gradle's verification metadata (F24).
- Exit, all of (plans/m2.md section 1): the verbs above run, tests green; bench_263 pre-generated and set up, its snapshot retaken and hashed, every view function answering; the bench heap and capture.reloadCap set from F14's pair; a survey record with every perf view GPU-bound on the baseline and the CPU floor per view; A2, A3 and A10 passed on the eleven views; a quick and a full calibration, in each mode the twin inside the geo-mean threshold and shadows off faster beyond it; `compare` refusing a mismatched identity and naming the field, in a test and live; the helper's per-pass timers judged by A8 and A11 (E3); optilux-bench; CI green on every push and on the PR; the user's rebase merge and release v0.3.0; docs/handoff.md written.
- Branch m2; M2.P00 (the plan) precedes the phases M2.P01 to M2.P11. Plan: plans/m2.md, premises verified 2026-10-08 (P9 open until M2.P04), its decisions D35-D53, approved by the user on 2026-10-08 and amended the same day (its section 10; D34 below). Prompts: prompts/m2.md.

## M2 phases
Change, exit and estimate per phase; files and tests are in plans/m2.md section 5, its decisions D35-D53 in section 6.

### M2.P01 Identity before calibration
- Change: F21's rows before any calibration: the key `harness`, options.txt's unwritten keys in `settings`, HAGS as applied, the reference pack out of identity (plans/m2.md D36-D39); the launch spec, views and Java hashed and the static identity built before the launch; `run <spec> --check`.
- Exit: `run --check --json` on a bench_263 acceptance spec prints the identity with `harness` and `system.hags`, and nothing launches.
- Estimate: 2 h; machine: none.

### M2.P02 window.measure and the jar's M2 rows
- Change (mod): `window.measure`, timed in seconds after a reload or from now, its stamps and frame count, failed when a reload, a dimension change or a world leave falls inside; `state`'s framebuffer size, a run refused unless it equals the display mode and suite.json (plans/m2.md D38); F23's rows.
- Exit: one launch: three windows whose PresentMon rows match their frame counts within one at each edge, every row Independent Flip; `state` reads 3840x2160.
- Estimate: 2.5 h; machine: 1 launch.

### M2.P03 Per-pass timers
- Change (mod): GL_TIMESTAMP queries at Iris's GLDebug group calls on the bench tier, read without stalling the render thread; `timers.start`, `timers.read`, `timers.stop` (D34; plans/m2.md D53).
- Exit: one launch with Unbound: 120 frames, each with every pipeline stage, none dropped at maxPending 3, the median top-level pass sum below the span's median GPUBusy.
- Estimate: 3 h; machine: 1 launch.

### M2.P04 World verbs and bench_263's preparation
- Change: `world snapshot` (F8); `world restore`, before every run (F15; plans/m2.md D44); `world prep`: the gamerules, Chunky's pre-generation (D45), the kill, the torch, the view functions and the reference frames (F16).
- Exit: snapshots/bench_263 retaken and hashed; a restore leaves the live hash equal; each Chunky task's end read as P9 resolves; every view function succeeds; seven tagged mobs and ten end crystals counted; eleven reference frames kept.
- Estimate: 3 h; machine: `install` (Chunky's jar), 1-2 launches, the generation.

### M2.P05 The measured session
- Change: one runner for acceptance and measured runs (F22); the measurement and calibration kinds (plans/m2.md D40); one PresentMon session cut by each window's stamps (F1); the summaries and validity flags; A8 and A11 admitted for M2.P10; the startup call recorded (F10); the machine to itself (F19; D42), orphans (F20; D41), the time split (F17, F18; D48) and the GUI per view (D49).
- Exit: a quick-mode run of the baseline and its twin ends ok, every capture valid, its rows matching its frames; a run killed in a test leaves an aborted record.
- Estimate: 3 h; machine: 1-2 launches. Attended: the machine left alone while it runs.

### M2.P06 Reload budget
- Change: F14's controlled pair as measured sessions; the heap, capture.reloadCap and the calibration's twins and sessions by plans/m2.md D43 (F4, F14).
- Exit: the records with their heap tables; suite.json and bench.json set from them; at a changed heap, the third run's slope within 10 % of the predicted.
- Estimate: 1.5 h; machine: 2-3 launches. Attended: the machine left alone while they run.

### M2.P07 compare, report, calibrate, verify records
- Change: the statistics (thresholds, verdicts, the twin monitor, A8's and A11's verdicts); `compare`, `report` (plans/m2.md D50), `calibrate` with its resume, `verify records` (F13; D51); one critique of the measuring path (D52).
- Exit: tests green; `verify records` passes; `compare` refuses an uncalibrated record, naming `calibrate`; each critique finding handled.
- Estimate: 3 h; machine: none. Attended: the critique's permission prompt (D52), unless allowed.

### M2.P08 The final views: GPU-bound, CPU floor, A2 and A3
- Change: P17's fallback path read in the pinned Iris jar; a full-mode survey of the baseline, its twin and the passthrough pack (plans/m2.md D46, D47); the CPU floor per view with GPULatency (F10) into measurement.md; then A2, A3 and A10 on the eleven views.
- Exit: the jar read agrees with P17; every baseline capture valid and GPU-bound; the floors written; A2, A3 and A10 passed. A view that fails is the user's: the run stops.
- Estimate: 1.5 h; machine: 2 launches, about 20 min. Attended: the machine left alone (A2 injects input).

### M2.P09 Calibration and the known positive
- Change: the quick and full calibrations; per mode, shadows off (SHADOW_QUALITY -1) against the baseline beside its twin; `compare` refusing an M1 record live.
- Exit: both calibrations committed; in each mode the twin inside the geo-mean threshold and shadows off faster beyond it; the refusal names an identity key.
- Estimate: 1.5 h; machine: 3-5 h of sessions, about 15 launches. Attended: the user's go and the machine left alone.

### M2.P10 A8 and A11
- Change: the timers' overhead (A8) and their agreement with GPUBusy (A11) on full mode's schedule, judged by the full calibration through M2.P05's runner and M2.P07's verdicts, no measured module changed; kept for M4's timer rows only if both pass (E3; plans/m2.md D53).
- Exit: an acceptance record with A8 and A11 and their evidence; E3's outcome in design.md.
- Estimate: 1 h; machine: 2-3 sessions, 40-60 min. Attended: the machine left alone.

### M2.P11 optilux-bench and the close
- Change: the optilux-bench skill by the creation rule, with three evals; the docs as built; CHANGELOG's 0.3.0 entry completed; the findings marked landed.
- Exit: the evals pass; `optilux status` prints the Release prompt.
- Estimate: 1.5 h; machine: 1-2 launches. Attended: `claude -p`'s permission prompt, unless allowed; the machine left alone for the run.

## M1 to M6
One line each, from design.md#6-milestones; phase lists are provisional until each plan is approved. F and Q numbers refer to Findings assigned.
- M1 game control: closed (above); exit: design.md#6-milestones M1.
- M2 perf loop: detailed above (M2 perf loop, M2 phases); exit: design.md#6-milestones M2.
- M3 visual loop: the static-texture pack, the hello pack with BENCH_DETERMINISTIC and pipeline spec v0, offline L0-L2 (`check`), `verify similarity`, coverage views, review page, iso profile v1, both modes recalibrated on the deterministic set. Exit: every perf view identical across 2 sessions (TAA off); A5.
- M4 shader base: every coverage-list program, lighting, tonemap; cost rows, timer rows below the CPU floor; offline L3-L4; debug-tier attribution; E2 decided.
- M5 features and temporal: shadows, sky, clouds, water, fog, AO, bloom, full TAA; the history flush (E4, F12), A6, A12; temporal positive controls; live pass.
- M6 1.0: ratio vs Unbound iso reported; live pass; look review; README; release, as 1.0.0, which its first commit writes into VERSION by hand (workflow.md#release). Post-1.0: optimization, the JVM track, the lod tier, the Aperture backend.

## Findings assigned
The Phase -1 spike's handoff findings (2026-10-06) and later ones, each with the milestone and phase that acts on it.

| # | Finding | Lands in | What it changes |
|---|---|---|---|
| F1 | PresentMon stop: CTRL_BREAK_EVENT, not CTRL_C; the CSV grows during the run; the first row arrives ~4 s after the start | landed in 0.01.09 (the start and stop, A9); M2.P02 and M2.P05 the window and its cut | GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT) to a CREATE_NEW_PROCESS_GROUP child; rows cut by the mod's window stamps, never a sleep; a killed PresentMon fails the run (measurement.md#tools) |
| F2 | AMD Software starts PresentMon-x64.exe (RSXTraceSession) with every game | landed in 0.01.03 (launch gate) | the gate blocks only on Minecraft processes and optilux-* ETW sessions; AMD's process and session are recorded in the run record, never stopped or waited on |
| F3 | options.txt needs version:5023 and graphicsPreset custom; Sodium forces exclusiveFullscreen on a fresh file; the dev tier needs use_no_error_g_l_context=false | landed in 0.01.03 (pre-launch files) | the harness writes suite.json display.optionsTxt verbatim and the Sodium file with both keys; every written key and the Sodium file's hash are identity (run-record.md#identity); simulationDistance stays 12 (user, 2026-10-06) |
| F4 | Dev-tier reload memory: 20.6 MiB heap and 320 MiB private bytes per reload over 50 reloads | landed in 0.01.09 (reload table); M2.P06 sets the cap | 50 `shaders.reload` on the bench tier through the mod, heap after GC and private bytes every 10 reloads, written as an acceptance record; M2 sets capture.reloadCap and the session budget from it, replacing ALC's 288 |
| F5 | Iris error path: in a world a failed load goes to chat; read `isFallback()`, hook `handleException` | landed in 0.01.07 (Iris adapter); A4 in 0.01.09 | `shaders.reload` answers `iris-compile-error` from the hooked message; A4 proves it (platform.md#mod-adapter-surface) |
| F6 | Viewfinder has no server-command tool; terrain shows only as "Terrain solid"; 30 fps under the debug context | landed in 0.01.10 (dev session 1); E5's check not in M2: M4 if E3 reopens, else E5 stays diagnostic (plans/m2.md D53) | /tick, /summon and /setblock go through the mod's `command` (V2's freeze findings: platform.md#mc-263-verified); dev session 1 runs the deferred batch: the look review of the L1, V1 and V6 captures (user), the /mcp reconnect and one Viewfinder call from Claude Code, V2 with /summon and /setblock; E5's overhead check separates the debug context from the mod |
| F7 | Dev-tier quit: WM_CLOSE saves the world, then the watchdog writes a crash report and the process exits -8 | closed (user, 2026-10-06) | accepted as known in platform.md#mod-tiers; the dev-session protocol treats exit -8 after "Saving worlds" as a clean quit; no shutdown step |
| F8 | 26.3 stores the singleplayer player under players/data/<uuid>.dat | landed in 0.01.03 (launch); M2.P04 world verbs | `launch` takes `--uuid` from that file name when the snapshot has one; `world snapshot` records it (platform.md#install-and-launch) |
| F9 | Iris has no release tags since 1.7.3; the 26.3 branch head says MOD_VERSION 1.11.6 | landed in 0.01.04 | the pinned jar's bytecode is the authority (`javap -c -p`); the source at commit adc75283b is context; the mixin-target test reads every target from the hash-checked jars with ASM (mod.md#11-build-and-test) |
| F10 | Offline mode still calls api.minecraftservices.com at startup; GPULatency read 1.04 frames idle at 141 fps | M2.P05 (the call recorded) and M2.P08 (GPULatency beside the floor) | the call is recorded, not blocked; the CPU-floor measurement reads GPULatency next to the 90 % rule (measurement.md#validity) |
| F11 | A launch takes about 20 s; 167 s only with the modal dialog | landed in 0.01.03 (launch) | the world timeout is 120 s (6x the spike's 18.4 s join); the Sodium file is written before every launch so no dialog appears; a timeout ends the process and fails the run |
| Q1 | The game directory under runtime/ still holds the spike world and files | landed in 0.01.08 | the provisional world is a copy of runtime/mc-26.3/game/saves/spike under snapshots/provisional/, made by hand and hashed (design.md#6-milestones); nothing else under runtime/ is reused: `install` rebuilds from the launch spec |
| F12 | The flush frame is the one where the hideGUI uniform reads 0 (shader.md#determinism-and-taa), but the entities view shows the GUI (measurement.md#session), where it reads 0 on every frame (the 2026-10-07 doc audit) | M5 (E4) | the history flush gets a signal that holds with the GUI shown, or the entities view keeps its hand another way; no design change before M5 |
| F13 | M1's full acceptance records run to 238 KB (m1-acceptance-9 and -10) against run-record.md#record's ~200 KB budget | M2.P07 (`verify records`) | the budget is scoped to measurement records, or acceptance records shed their per-frame lists to results/raw/; committed records are never edited |
| F14 | F4's heap per reload: about 20 MiB in m1-acceptance-5 to -7 (A4, A7, A9, A10 in one dimension), about 33 MiB in -9 and -10 (the full set, A2 and A3 visiting the Nether and End first; each reload 0.48 s against 0.34 s). Between them the identities differ in the helper jar (0.01.12.4: Protocol's mutation set, emptied on every path), inactivityFpsLimit, the platform and suite files and the world's 5 new files | M2.P06 (capture.reloadCap) | the cap is set from a session that visits all three dimensions, as M2's do; one controlled pair, the same session with and without the dimension visits, names the cause before calibration |
| F15 | The live world differs from its snapshot after every launch (0.01.12) | M2.P04 (`world restore`) | `run` restores the snapshot before every session; until then every run retakes it first |
| F16 | World prep (0.01.11 to 0.01.13): the kill would take end_dragon's end crystals; untagged mobs stand in several views; end_city (D29) needs a second End area; on 26.3 a function reports success only through `/return` | M2.P04 (`world prep`) | the kill spares minecraft:end_crystal (suite.json world.setup); view functions end in `return 1`; the reference frames are retaken after prep |
| F17 | A9's capture: 44.5 s for 120 4K frames, bound by the four PNG writers (about 1.4 s a frame each), not the readback (0.01.13) | M3 (plans/m2.md D48: kept in M2, the jar change waits for M3's captures) | more writers, or A9's stamps without PNGs; either changes the jar, so it is decided before calibration |
| F18 | The session's time split (m1-acceptance-9, 215 s): the GPU warm-up's 30 s, `ticks.step 120`'s 6 s per weather change, A2's 9 s per view, A9's 44.5 s, a join's 13-14 s | M2.P05 (plans/m2.md D48); A2's and A9's share with F17 in M3 | each gain moves identity or the jar, so it is taken or left before calibration |
| F19 | A run needs the machine to itself: m1-acceptance-8 met the user at the computer (focus.lost three times); in exclusive fullscreen a click on the second display minimizes the game; the gate refuses only a game under runtime/, an optilux- ETW session and a Gradle build, and records other JVMs (0.01.12's r2) | M2.P05 (validity, plans/m2.md D42) | what blocks a measured run before its launch and what a focus change does to a session; when runs happen is the user's |
| F20 | A run killed from outside writes no record and leaves A4's copy (m1-acceptance-8) | M2.P05 (plans/m2.md D41) | the next `run` refuses A4's copy (built in M1); a session journals as it goes, and the next `run` or `calibrate` ends an orphan and writes its record as aborted |
| F21 | Identity (0.01.12's review; D31's reading 2): options.txt's unwritten keys recorded, never matched (id1); PresentMon and the harness in no key (id3, id4, c2); the render target never compared with the display (id5); HwSchMode is the requested HAGS state (id6); the launch spec, views and Java hashed after the session, no identity after a failed launch (id7, id9, c3); the suite hash covers copies no code reads (id8); the reference pack in identity twice, through referencePacks and shaderPack (c4) | M2.P01, before calibration; the render target in M2.P02 (plans/m2.md D38) | each key fixed or decided before the first calibration session |
| F22 | The session (0.01.12's review; D31's reading 2): a failed selftest does not end a session (c5); the GUI hidden at entities, whose torch measurement.md#session keeps (c1); perform keeps the session skeleton inline and the end-the-game policies apart (simp2, simp20); the spec's notes, pack and resource_packs unread (simp11); wait_rows re-reads the CSV at every poll (cr10) | M2.P05 | the measured session's runner |
| F23 | The jar (0.01.12's review): a hello after its own disconnect cancels the 10 s release (conc2); a stopped capture's frames outlive its resource (conc5); the game adapter's delegates are dead code | M2.P02, before calibration | one jar change with `window.measure` |
| F24 | Gradle's other downloads are trusted by coordinate (0.01.12) | the mod's next dependency change | verification metadata not taken (D28); M2 plans no dependency change |

## Decisions
Owner: who decides. Recommendation: what an unattended run takes. The user's decisions of 2026-10-05 live in design.md#7-decisions-taken-user-2026-10-05, later closed ones in this table; evidence decisions E1-E5 in design.md#8-open-decisions.

| Id | Decision | Owner | Recommendation | When |
|---|---|---|---|---|
| D1 | Installing uv (not on PATH on 2026-10-06) | user | closed: `pip install uv==0.12.23` into the user's Python 3.12, whose Scripts folder was already on PATH (user, 2026-10-06) | closed |
| D2 | CLI framework | Claude | argparse from the standard library: no dependency; `--json` per verb; click would add a dependency no M0 verb needs | 0.00.01 |
| D3 | Where git hooks live | Claude | .githooks/ committed and `core.hooksPath` set with `git config --local` in 0.00.03, reported by `optilux status`; copying into .git/hooks would need an installer verb outside the verb table | 0.00.03 |
| D4 | Commit-message check | Claude | one line, at most 72 characters, `0.MM.PP.N: ` then text (D32), no attribution token (Co-Authored-By, Claude, Anthropic, Generated; the tool name "Claude Code" passes unless "by", "with" or "via" precede it, as the 0.00.03 subject names it); the trailing period of the user's examples is style, not enforced | 0.00.03 |
| D5 | CI runner | Claude | ubuntu-latest: M0's tests are pure Python, and Windows minutes cost 2x on a private repo (2,000 minutes a month on GitHub Free); switch to windows-latest when a Windows-only path (ctypes, the named pipe) gets a test, in M1; switched in 0.01.03 (plans/m1.md D19) | 0.00.06 |
| D6 | Release tag and asset | Claude | tag v<version> (workflow.md#release), asset optilux-<version>.zip, body = the milestone's CHANGELOG entry; the workflow creates the tag at main's head; title `Optilux <version>: <Name>`, the name from the CHANGELOG heading `## 0.MM <Name>` (user, 2026-10-06; from v0.01) | 0.00.06 |
| D7 | Repository merge settings | user | rebase merge on, squash and merge commits off, set in 0.00.06 by `gh repo edit` so a merge cannot pick another method; the prompt names the command and stops for the go | 0.00.06 |
| D8 | When optilux-plan is built | Claude | in 0.01.10 (M1's last phase when planned), from two hand-made plans (m0.md, m1.md), used from M2's plan on; workflow.md#skills said after the first hand-written plan, and one plan is too little for the creation rule's 3 eval scenarios; built in 0.01.10 | 0.01.10 |
| D9 | Placeholder pack content | Claude | shader/shaders/shaders.properties with one comment line and no programs; never launched in M0; M3's hello pack replaces it and BENCH_DETERMINISTIC starts there (shader.md#determinism-and-taa) | 0.00.05 |
| D10 | Default branch name | Claude | `git init -b main`: the machine's init.defaultBranch is master and no config changes | 0.00.00 |
| D11 | Phase 0 question: the simulationDistance pin | user | closed: 12, the value the game chose (user, 2026-10-06); config/suite.json display | closed |
| D12 | Phase 0 question: the dev-tier exit code -8 | user | closed: accepted as known, no shutdown step (user, 2026-10-06); F7 | closed |
| D27 | The QA pass: shape, review and cleanup | user | closed: two phases, 0.01.12 review and cleanup offline and 0.01.13 debug, timing and the acceptance re-run; the reviewer agent per dimension plus /code-review high, every finding verified at its source; cleanup takes the run.py seam, the bugs and any change that largely justifies itself (user, 2026-10-07) | closed |
| D28 | The QA pass's tools | user | closed: ruff adds BLE, S, SIM, RUF, PERF; pyright basic over optilux/ in CI; javac -Xlint:all -Werror; one coverage.py branch report; pytest-xdist; Gradle verification metadata not taken (user, 2026-10-07). Pins (Claude's recommendation): the newest release the day 0.01.12 runs, locked by uv (resolved 2026-10-07 by `uv pip compile`: coverage 7.16.2, pyright 1.1.414 with nodejs-wheel-binaries 24.19.0, pytest-xdist 3.8.0) | closed |
| D29 | The End city view | user | closed: an 11th perf role, end_city, added in 0.01.12 from 0.01.11's kept pose and frame; every full run gains a view and M2 pre-generates a second End area (user, 2026-10-07) | closed |
| D31 | Critique readings at M1's close | user | closed: two narrow /critique --repo readings with gpt-6-astra at xhigh, each in its own Codex 5 h window started at or under 10 % so neither stops mid-review (Astra fills the Plus plan's window at about 7 M tokens: 6.7 M took 0-98 %): the contracts, run-record.md and mod-protocol.md against the code, on 2026-10-07; the measurement-path code, optilux/record.py and session.py, as 0.01.13's debug's last step; each on a trimmed copy of the tracked files; findings handled under D27 before the acceptance re-run (user, 2026-10-07) | closed |
| D30 | 0.01.11's candidate worlds | user | closed: 0.01.12 deletes bench_7800 and bench_20261005 from runtime/mc-26.3/game/saves/, a one-off exception to the runtime/ rule, after checking nothing names them (user, 2026-10-07) | closed |
| D32 | Patch versions between phases | user | closed: commits carry `0.MM.PP.N: `, N 0 for the phase and 1, 2, ... for a fix after it, before the next phase (0.01.12.1 the first); the commit-msg hook refuses the phase alone from then on; releases take main's newest prefix, four parts (v0.01.13.0) (user, 2026-10-07) | closed |
| D33 | Commits, versions and releases | user | closed: commits in Conventional Commits form, `type(scope)!: summary` (feat, fix, perf, refactor, test, docs, build, ci, chore, revert), one line of at most 72 characters, no body or trailer, the subject naming no milestone, phase, version or date; a commit is one logical, test-green change and a phase may take several. One version source, the root file VERSION (MAJOR.MINOR.PATCH), read by `optilux status`, CI and `pack`; the mod jar keeps its own version, its sha512 being identity. Before 1.0 a milestone is a minor release (M1 0.2.0, M2 0.3.0), set by its first commit, which CI checks against origin/main's; PATCH for a bad release or an urgent fix, through its own PR; M0's v0.00.06 stays. Phases M<N>.P<PP> from M2, the last one done in docs/handoff.md's `Last phase:` line, which Status lines no longer repeat. CHANGELOG `## <version> <Name>`, release `Optilux <version>: <Name>`, PR `<version> <Name>: <what it delivers>`. A merge to main with a released version fails release.yml; CI's check on the PR refuses it first. Supersedes D4's message format, D6's heading and D32 (user, 2026-10-07) | closed |
| D34 | Per-pass timers (A8, A11, `timers.*`, E3): M2 or M4 | user | closed: kept in M2, as design.md#6-milestones has them (user, 2026-10-08), against the recommendation to move them to M4, which first needs timer rows; plans/m2.md builds the helper's own timers before calibration and runs A8 and A11 after it | closed |

## Estimates
- M0: 0.3 + 1 + 1 + 1.5 + 1.5 + 1 + 1.5 = 7.8 h agent, no machine time. Basis: ALC's phases took about 1 h each (workflow.md#git); the spike estimated 4 h and took 2.5 h; ALC's run estimates of 4-6 h took about 1.2 h (workflow.md#running-a-milestone), so these are expected to run short rather than long.
- M1: 28 h agent from plans/m1.md (2, 2, 2, 3, 3, 3, 2.5, 2, 1.5, 2, 3, 2; 25 h before the QA pass became two phases, D27; the mod phases carry 3 h each: ALC's mod ran 3x its line estimate, lessons.md#mod).
- M2: 23.5 h agent from plans/m2.md (2, 2.5, 3, 3, 3, 1.5, 3, 1.5, 1.5, 1, 1.5; its section 8 has the basis); machine time apart: 26-31 launches, M2.P09's calibration sessions 3-5 h. M3, rough until its plan is approved: 10 h.
- Tripwire baseline: M0-M3 summed 69.3 h (7.8 + 28 + 23.5 + 10); the trip is at 138.6 h, recomputed whenever a plan replaces a rough figure. Actuals: M0 about 3.3 h; M1 about 20.3 h against 28 (18.6 h through 0.01.13, its handoff in git history, and 1.7 h for the workflow pass).
