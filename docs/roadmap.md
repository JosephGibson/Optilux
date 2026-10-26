# Roadmap
Status: milestones M0-M6, the current one in detail, the findings assigned and the decisions.

## Contents
Rules · M0 foundation · M0 phases · M1 game control · M2 perf loop · M3 visual loop · M3 phases · M1 to M6 · Findings assigned · Decisions · Estimates

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
- Closed with release v0.3.0 (2026-10-16): `world prep`, `world snapshot`, `world restore`, `calibrate`, `compare`, `report`, `verify records` and `run`'s measurement and calibration kinds with `run --check`; the mod's `window.measure` and per-pass timers (A8 passed, A11 failed at underwater: dropped from use, design.md#8-open-decisions E3); bench_263 prepared and surveyed, every view GPU-bound, the CPU floors; capture.reloadCap 20 and the split session; both modes calibrated on unmodified Unbound, shadows off detected beyond the 0.5 % floor; optilux-bench; about 21.3 h against 26.5 estimated. Plan: plans/m2.md; prompts: prompts/m2.md; what happened: the M2.P11 handoff in git history; its open rows: Findings assigned.

## M3 visual loop
- Goal (plans/m3.md section 1): a shader change is judged by its frames as well as its GPU time: the hello pack renders the same bits across launches with TAA off, frames are taken at every view and compared by tier, offline checks gate a build before its launch and the similarity check before its commit, and both perf modes are calibrated on the static-texture set every session now uses.
- Verbs (design.md#5-interfaces, From = M3): `check L0`, `check L1`, `check L2`, `verify similarity`; `run`'s visual and dump kinds and A5; `compare`'s tiers and the review page. Mod: frames.capture's align, ready and image-less captures; `shaders.dump` dropped (plans/m3.md D60).
- Not in M3 (plans/m3.md section 2): L3-L4, RenderDoc, the filled coverage list and spider eyes, cost and timer rows, E2, E3 with Viewfinder (M4); TAA, the flush, `camera.path`, A6, A12, temporal gates, the live pass (M5); BENCH_DETERMINISTIC's cost row and the uniform-work scan (M4); F12 (M5); F24.
- Exit, all of (plans/m3.md section 1): the verbs above run, tests green, the similarity hook on staged shader changes; the hello pack with BENCH_DETERMINISTIC and pipeline.json v0 passing `check L0` and `verify similarity`; the iso profile v1 passing L0's profile check; the static-textures pack holding every animated texture on its first frame in the deterministic set; coverage views built, the snapshot retaken and hashed; two visual sessions of the hello pack on the 11 perf views, every view identical; A5 judged over 33 waits; a quick and a full calibration on the deterministic set, each mode's twin inside its threshold and shadows off faster beyond it; CI green on every push and on the PR; the user's rebase merge and release v0.4.0; docs/handoff.md written.
- Branch m3; M3.P00 (the plan) precedes the phases M3.P01 to M3.P11. Plan: plans/m3.md, premises verified 2026-10-17, its decisions D54-D70, approved by the user on 2026-10-18 (its section 10). Prompts: prompts/m3.md.

## M3 phases
Change, exit and estimate per phase; files and tests are in plans/m3.md section 5, its decisions D54-D70 in section 6.

### M3.P01 Tools and reference copies
- Change: glslang 16.6.0 and RGA 2.15 pinned and installed; pillow, numpy, flip-evaluator and scikit-image locked; reference/ filled by `install` with Unbound r5.9.3 and the control pack (plans/m3.md D54, D58, D59).
- Exit: `install` reports both tools and both copies hash-checked; each tool prints its pinned version; the packages import; `git status` clean.
- Estimate: 1.5 h; machine: downloads.

### M3.P02 verify similarity
- Change: winnowing over normalized GLSL tokens against reference/, each shared fingerprint extended to its whole match; the threshold from Unbound against itself and the control pack (D55); the pre-commit hook on the staged shader tree.
- Exit: the controls hold, a planted copy is refused by the hook, shader/ passes.
- Estimate: 2 h; machine: none.

### M3.P03 The hello pack and pipeline spec v0
- Change: the hello pack in `#version 330 core` (basic, textured, textured_lit, final), BENCH_DETERMINISTIC on by default (D56); config/pipeline.json v0 (D57); `run`'s variants `optilux` and `optilux@<ref>` (D63).
- Exit: an acceptance run of A2 and A10 on the eleven views with the hello pack ends ok, A2 passed at every view.
- Estimate: 2.5 h; machine: 1 launch. Attended: the machine left alone (A2 sends input).

### M3.P04 check L0 and the iso profile v1
- Change: `check L0`: glslang over the variant matrix, the similarity check, the profile check; the iso profile v1 with its `options`; `run` refusing an Optilux zip that fails L0.
- Exit: L0 passes on the hello pack and the profile check on both Unbound profiles; a broken stage fails it.
- Estimate: 2 h; machine: none.

### M3.P05 Aligned, ready-triggered and image-less captures
- Change (mod): frames.capture's align, ready and images false, selftest using align and ready, A9 on stamps alone (F17; D61); `shaders.dump` dropped (D60).
- Exit: `mod test` green; A2, A9 and A10 pass on the eleven views with the reference pack, A9's capture under 5 s.
- Estimate: 3 h; machine: 1 launch. Attended: the machine left alone (A2 sends input).

### M3.P06 The deterministic set and visual runs
- Change: the .mcmeta-only static-textures pack and the deterministic set in every session (D62); the visual kind (D63); the tiers in optilux/visual.py; `compare --against`; review.html.
- Exit: a visual run on quick mode's views ends ok, every frame hashed, every option read back, every hello-pack pair identical; a tier per view; review.html written.
- Estimate: 3.5 h; machine: 1 launch. Attended: the machine left alone while it runs.

### M3.P07 Coverage views
- Change: `world prep`'s coverage step at a site at least 512 blocks (Chebyshev) from every perf view of its dimension (D64), the views file's `coverage` list with `hand` and `ticks`, the End views setting the End's clock (D56); the snapshot retaken.
- Exit: every coverage item counted, the snapshot hashed; a visual run of the coverage views ends ok.
- Estimate: 2.5 h; machine: 2 launches and the new area's generation. Attended: the machine left alone while they run.

### M3.P08 check L1 and L2
- Change: the dump kind through iris.properties (D60); `check L1`: dump equality, the premise check, the impact matrix and pipeline.json's audit, closures in the record (D69); `check L2`: RGA's metrics (D70).
- Exit: the define's changed stages named; a dump-equal closure spot-checked live, identical; each stage's VGPRs or a known offline failure.
- Estimate: 3 h; machine: 2 launches. Attended: the machine left alone while they run.

### M3.P09 A5 and the determinism exit
- Change: A5 over 33 waits in two linked launches (D68); the twin first among the Ci (D65, F26).
- Exit: A5 judged; two visual runs of the hello pack on the 11 perf views identical on every view; the schedule's test puts the twin first.
- Estimate: 2.5 h; machine: 4 launches. Attended: the machine left alone while they run.

### M3.P10 Recalibration on the deterministic set
- Change: a budget run first when the driver differs from 32.0.31041.3013 (D66, F27); the quick and full calibrations; shadows off per mode; an M2 record refused live.
- Exit: both calibrations committed; per mode the twin inside the threshold and shadows off faster beyond it; the refusal names resourcePacks.
- Estimate: 1.5 h; machine: about 5 h, about 135 launches. Attended: the user's go after the driver call, the machine left alone.

### M3.P11 The close
- Change: the docs as built; CHANGELOG's 0.4.0 entry completed; the findings marked landed.
- Exit: `optilux status` prints the Release prompt.
- Estimate: 1 h; machine: none.

## M1 to M6
One line each, from design.md#6-milestones; phase lists are provisional until each plan is approved. F and Q numbers refer to Findings assigned.
- M1 game control: closed (above); exit: design.md#6-milestones M1.
- M2 perf loop: closed (above); exit: design.md#6-milestones M2.
- M3 visual loop: detailed above (M3 visual loop, M3 phases); exit: design.md#6-milestones M3.
- M4 shader base: D72 decided first; every coverage-list program, lighting, tonemap; cost rows, timer rows below the CPU floor; offline L3-L4; debug-tier attribution; E2 decided.
- M5 features and temporal: shadows, sky, clouds, water, fog, AO, bloom, full TAA; the history flush (E4, F12), A6, A12; temporal positive controls; live pass.
- M6 1.0: ratio vs Unbound iso reported; live pass; look review; README; release, as 1.0.0, which its first commit writes into VERSION by hand (workflow.md#release). Post-1.0: optimization, the JVM track, the lod tier, the Aperture backend.

## Findings assigned
The Phase -1 spike's handoff findings (2026-10-06) and later ones, each with the milestone and phase that acts on it.

| # | Finding | Lands in | What it changes |
|---|---|---|---|
| F1 | PresentMon stop: CTRL_BREAK_EVENT, not CTRL_C; the CSV grows during the run; the first row arrives ~4 s after the start | landed in 0.01.09 (the start and stop, A9), M2.P02 (the window) and M2.P05 (its cut) | GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT) to a CREATE_NEW_PROCESS_GROUP child; rows cut by the mod's window stamps, never a sleep; a killed PresentMon fails the run (measurement.md#tools) |
| F2 | AMD Software starts PresentMon-x64.exe (RSXTraceSession) with every game | landed in 0.01.03 (launch gate) | the gate blocks only on Minecraft processes and optilux-* ETW sessions; AMD's process and session are recorded in the run record, never stopped or waited on |
| F3 | options.txt needs version:5023 and graphicsPreset custom; Sodium forces exclusiveFullscreen on a fresh file; the dev tier needs use_no_error_g_l_context=false | landed in 0.01.03 (pre-launch files) | the harness writes suite.json display.optionsTxt verbatim and the Sodium file with both keys; every written key and the Sodium file's hash are identity (run-record.md#identity); simulationDistance stays 12 (user, 2026-10-06) |
| F4 | Dev-tier reload memory: 20.6 MiB heap and 320 MiB private bytes per reload over 50 reloads | landed in 0.01.09 (reload table) and M2.P06 (the cap) | 50 `shaders.reload` on the bench tier through the mod, heap after GC and private bytes every 10 reloads, written as an acceptance record; M2 sets capture.reloadCap and the session budget from it, replacing ALC's 288 |
| F5 | Iris error path: in a world a failed load goes to chat; read `isFallback()`, hook `handleException` | landed in 0.01.07 (Iris adapter); A4 in 0.01.09 | `shaders.reload` answers `iris-compile-error` from the hooked message; A4 proves it (platform.md#mod-adapter-surface) |
| F6 | Viewfinder has no server-command tool; terrain shows only as "Terrain solid"; 30 fps under the debug context | landed in 0.01.10 (dev session 1); E5's check in M4, E3 having reopened (M2.P10, plans/m2.md D53) | /tick, /summon and /setblock go through the mod's `command` (V2's freeze findings: platform.md#mc-263-verified); dev session 1 runs the deferred batch: the look review of the L1, V1 and V6 captures (user), the /mcp reconnect and one Viewfinder call from Claude Code, V2 with /summon and /setblock; E5's overhead check separates the debug context from the mod |
| F7 | Dev-tier quit: WM_CLOSE saves the world, then the watchdog writes a crash report and the process exits -8 | closed (user, 2026-10-06) | accepted as known in platform.md#mod-tiers; the dev-session protocol treats exit -8 after "Saving worlds" as a clean quit; no shutdown step |
| F8 | 26.3 stores the singleplayer player under players/data/<uuid>.dat | landed in 0.01.03 (launch) and M2.P04 (world verbs) | `launch` takes `--uuid` from that file name when the snapshot has one; `world snapshot` records it (platform.md#install-and-launch) |
| F9 | Iris has no release tags since 1.7.3; the 26.3 branch head says MOD_VERSION 1.11.6 | landed in 0.01.04 | the pinned jar's bytecode is the authority (`javap -c -p`); the source at commit adc75283b is context; the mixin-target test reads every target from the hash-checked jars with ASM (mod.md#11-build-and-test) |
| F10 | Offline mode still calls api.minecraftservices.com at startup; GPULatency read 1.04 frames idle at 141 fps | landed in M2.P05 (the call recorded) and M2.P08 (GPULatency beside the floor) | the call is recorded, not blocked; the CPU-floor measurement reads GPULatency next to the 90 % rule (measurement.md#validity) |
| F11 | A launch takes about 20 s; 167 s only with the modal dialog | landed in 0.01.03 (launch) | the world timeout is 120 s (6x the spike's 18.4 s join); the Sodium file is written before every launch so no dialog appears; a timeout ends the process and fails the run |
| Q1 | The game directory under runtime/ still holds the spike world and files | landed in 0.01.08 | the provisional world is a copy of runtime/mc-26.3/game/saves/spike under snapshots/provisional/, made by hand and hashed (design.md#6-milestones); nothing else under runtime/ is reused: `install` rebuilds from the launch spec |
| F12 | The flush frame is the one where the hideGUI uniform reads 0 (shader.md#determinism-and-taa), but the entities view shows the GUI (measurement.md#session), where it reads 0 on every frame (the 2026-10-07 doc audit) | M5 (E4) | the history flush gets a signal that holds with the GUI shown, or the entities view keeps its hand another way; no design change before M5 |
| F13 | M1's full acceptance records run to 238 KB (m1-acceptance-9 and -10) against run-record.md#record's ~200 KB budget | landed in M2.P07 (`verify records`) | the budget is scoped to measurement records, or acceptance records shed their per-frame lists to results/raw/; committed records are never edited |
| F14 | F4's heap per reload: about 20 MiB in m1-acceptance-5 to -7 (A4, A7, A9, A10 in one dimension), about 33 MiB in -9 and -10 (the full set, A2 and A3 visiting the Nether and End first; each reload 0.48 s against 0.34 s). Between them the identities differ in the helper jar (0.01.12.4: Protocol's mutation set, emptied on every path), inactivityFpsLimit, the platform and suite files and the world's 5 new files | landed in M2.P06 (capture.reloadCap) | the cap is set from a session that visits all three dimensions, as M2's do; one controlled pair, the same session with and without the dimension visits, names the cause before calibration |
| F15 | The live world differs from its snapshot after every launch (0.01.12) | landed in M2.P04 (`world restore`) | `run` restores the snapshot before every session; until then every run retakes it first |
| F16 | World prep (0.01.11 to 0.01.13): the kill would take end_dragon's end crystals; untagged mobs stand in several views; end_city (D29) needs a second End area; on 26.3 a function reports success only through `/return` | landed in M2.P04 (`world prep`) | the kill spares minecraft:end_crystal (suite.json world.setup); view functions end in `return 1`; the reference frames are retaken after prep |
| F17 | A9's capture: 44.5 s for 120 4K frames, bound by the four PNG writers (about 1.4 s a frame each), not the readback (0.01.13) | landed in M3.P05 (plans/m3.md D61: A9 on stamps alone, 1.5 s for 120 frames in m3-capture-2) | more writers, or A9's stamps without PNGs; either changes the jar, so it is decided before calibration |
| F18 | The session's time split (m1-acceptance-9, 215 s): the GPU warm-up's 30 s, `ticks.step 120`'s 6 s per weather change, A2's 9 s per view, A9's 44.5 s, a join's 13-14 s | landed in M2.P05 (plans/m2.md D48) and M3.P05 (A9's share; A2's kept, plans/m3.md D61) | each gain moves identity or the jar, so it is taken or left before calibration |
| F19 | A run needs the machine to itself: m1-acceptance-8 met the user at the computer (focus.lost three times); in exclusive fullscreen a click on the second display minimizes the game; the gate refuses only a game under runtime/, an optilux- ETW session and a Gradle build, and records other JVMs (0.01.12's r2) | landed in M2.P05 (validity, plans/m2.md D42) | what blocks a measured run before its launch and what a focus change does to a session; when runs happen is the user's |
| F20 | A run killed from outside writes no record and leaves A4's copy (m1-acceptance-8) | landed in M2.P05 (plans/m2.md D41) | the next `run` refuses A4's copy (built in M1); a session journals as it goes, and the next `run` or `calibrate` ends an orphan and writes its record as aborted |
| F21 | Identity (0.01.12's review; D31's reading 2): options.txt's unwritten keys recorded, never matched (id1); PresentMon and the harness in no key (id3, id4, c2); the render target never compared with the display (id5); HwSchMode is the requested HAGS state (id6); the launch spec, views and Java hashed after the session, no identity after a failed launch (id7, id9, c3); the suite hash covers copies no code reads (id8); the reference pack in identity twice, through referencePacks and shaderPack (c4) | landed in M2.P01; the render target in M2.P02 (plans/m2.md D38) | each key fixed or decided before the first calibration session |
| F22 | The session (0.01.12's review; D31's reading 2): a failed selftest does not end a session (c5); the GUI hidden at entities, whose torch measurement.md#session keeps (c1); perform keeps the session skeleton inline and the end-the-game policies apart (simp2, simp20); the spec's notes, pack and resource_packs unread (simp11); wait_rows re-reads the CSV at every poll (cr10) | landed in M2.P05 | the measured session's runner |
| F23 | The jar (0.01.12's review): a hello after its own disconnect cancels the 10 s release (conc2); a stopped capture's frames outlive its resource (conc5); the game adapter's delegates are dead code | landed in M2.P02 | one jar change with `window.measure` |
| F24 | Gradle's other downloads are trusted by coordinate (0.01.12) | the mod's next dependency change | verification metadata not taken (D28); M2 plans no dependency change |
| F25 | A pack near 1 ms a frame meets PresentMon's row loss before the 90 % rule: the passthrough's captures were cut invalid on cave, night, entities, nether_crimson and nether_soul at 1,850-2,060 fps (m2-survey-1, -2; M2.P08's handoff) | landed in M3.P11 (plans/m3.md D67: no row in 0.4.0, measurement.md#session step 9); the row in M4 | no GPUBusy row for a pack that light: BENCH_DETERMINISTIC's cost row and the hello pack's timings wait for a heavier base or timer rows (E3) |
| F26 | Quick mode's first Ci slot reads slow: each view's first measured baseline follows a dimension change and reads 0.13-0.16 % below the second, so slot 1, a candidate's and never the twin's, reads +0.085 % on the geo-mean (M2.P09's review 1) | landed in M3.P09 (plans/m3.md D65: the twin first) | the schedule changes before M3's calibration, so no candidate sits unwatched in that slot |
| F27 | Each reload leaks about 0.5 GiB of GPU memory under driver 32.0.31041.3013, which an AMD installer put in place of 32.0.32015.2008 on 2026-10-10 (M1's 46 MiB of private bytes a reload), hence capture.reloadCap 20 (M2.P06; M2.P09's handoff) | landed in M3.P10 (plans/m3.md D66: the driver as found, 32.0.31041.1004; m3-diag-alone-1 leaked 580 MiB of GPU memory a reload, so the cap stays 20) | a newer driver and one budget run of m2-diag-alone-1's spec may let plans/m2.md D43 raise the cap: fewer launches a full session |

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
| D71 | The shader's direction | user | closed: an original, next-generation pack, heavily inspired by Complementary Unbound but with a look of its own, every feature on a measured cost budget; Unbound stays the reference pack and the side-by-side look reference, not the target; the drop list becomes a not-yet list; M3 runs as planned, its iso profile included (user, 2026-10-20) | closed |
| D72 | What next-generation means for Optilux: the look target (reference images, art direction); the features taken back from the not-yet list (ray or path tracing and colored light among the candidates); a frame-time budget at 3840x2160; M6's ratio vs Unbound iso kept, narrowed to the shared features or dropped | user | asked at M4's Plan prompt, each candidate with Claude's research of its cost and of its fit with TAA-on determinism (A12) and the Aperture port (platform.md#renderer-transition); until then nothing on the not-yet list is built | M4's plan |
| D73 | Shader research before M4's plan | user | closed: M4 and M5 keep their cut (merged, the plan would be about twice the 40,960-byte cap), but M4's choices are made for M5's features (the per-pixel data, TAA as the denoiser), so one research step on branch m4 before M4.P00, outside the phase numbering, covers both: 13 topics (lighting, tonemap, TAA, shadows, AO, sky, clouds, fog and volumetrics, water, reflections, post, D72's candidates, Iris's capabilities), each by a read-only researcher and an adversarial verifier, then a synthesis, in docs/research/ for D72, E2 and the plan, which reads it; then a targeted pass: the coverage-list programs no topic held and the base cost, the not-yet items none assessed, the topic docs brought in line with the synthesis; the Iris facts stay [verify in jar] for M4.P00's premises (user, 2026-10-26) | closed |
| D74 | Unbound as a springboard | user | closed: Optilux diverges from Unbound wherever a technique is faster, more performant or more modern; matching Unbound's approach is never a reason on its own, so research, plans and phases recommend the faster or more modern option, judged by cost rows and the visual tiers, and may go ahead with it; D71's roles stand (Unbound the reference pack and the look reference beside Optilux's frames), and D72 keeps the look target and M6's ratio (user, 2026-10-26) | closed |

## Estimates
- M0: 0.3 + 1 + 1 + 1.5 + 1.5 + 1 + 1.5 = 7.8 h agent, no machine time. Basis: ALC's phases took about 1 h each (workflow.md#git); the spike estimated 4 h and took 2.5 h; ALC's run estimates of 4-6 h took about 1.2 h (workflow.md#running-a-milestone), so these are expected to run short rather than long.
- M1: 28 h agent from plans/m1.md (2, 2, 2, 3, 3, 3, 2.5, 2, 1.5, 2, 3, 2; 25 h before the QA pass became two phases, D27; the mod phases carry 3 h each: ALC's mod ran 3x its line estimate, lessons.md#mod).
- M2: 26.5 h agent from plans/m2.md (2, 2.5, 3.5, 3, 3.5, 1.5, 5, 1.5, 1.5, 1, 1.5, P03, P05 and P07 raised from 3 h on 2026-10-12 to size XL, Opus 5.5 Max, P07 to 5 h on 2026-10-13 for D43's split; its section 8 has the basis); machine time apart: 104-113 launches, M2.P09's sessions about 4 h.
- M3: 25 h agent from plans/m3.md (1.5, 2, 2.5, 2, 3, 3.5, 2.5, 3, 2.5, 1.5, 1; its section 8 has the basis); machine time apart: about 146 launches, M3.P10's sessions about 5 h.
- Tripwire baseline: M0-M3 summed 87.3 h (7.8 + 28 + 26.5 + 25; 72.3 h with M3's rough 10 h); the trip is at 174.6 h, recomputed whenever a plan replaces a rough figure. Actuals: M0 about 3.3 h; M1 about 20.3 h against 28 (18.6 h through 0.01.13, its handoff in git history, and 1.7 h for the workflow pass); M2 about 21.3 h against 26.5 (the M2.P11 handoff in git history).
