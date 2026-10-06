# Roadmap
Status: M0 closed (release v0.00.06); M1 in progress: 0.01.02 (install and the launch-spec check) is the last phase done, next 0.01.03, pre-launch files and launch. Latest stop: handoff.md.

## Contents
Rules · M0 foundation · M0 phases · M1 game control · M1 phases · M1 to M6 · Findings assigned · Decisions · Estimates

## Rules
- Versions: 0.MM.PP = milestone MM, phase PP; one commit per phase, one PR and one release per milestone (workflow.md#git). A phase is one reviewable, test-green change: `optilux test` (from 0.00.01) and `optilux verify docs` (from 0.00.02) pass before its commit.
- Sizing rule (design.md#6-milestones): a milestone whose plan would pass the 40,960-byte plan cap is split before it starts. Unattended machine time (calibration, the overhead experiment) does not count: agent time is the constraint (design.md#3-core-rule).
- Tripwire (design.md#6-milestones): if M0-M3 together run past twice their summed estimates, stop and re-plan before building more infrastructure. Estimates holds the sums; every handoff adds the actuals.
- This file holds the current milestone in detail and the others one line each (workflow.md#docs-rules). When a milestone closes, its section shrinks to one line and the next one expands from its approved plan; Findings assigned keeps a row until the finding has landed.
- Running a milestone: plan from docs/templates/plan.md, optional /critique, the user's approval, the prompt set, the unattended run, one commit per phase, the handoff (workflow.md#running-a-milestone). An unattended run asks nothing mid-run: it takes the recommendation in Decisions or the plan, or logs the question in the handoff.
- No milestone closes on dummies (design.md#3-core-rule). M0 ships a placeholder pack because its exit is the release path, not a pack; M1-M3 exit on real packs.

## M0 foundation
- Closed with release v0.00.06 (2026-10-06): repository, harness skeleton (`test`, `verify docs`, `status`, `milestone start`, `pack build`, `pack release`), hooks, CI, the release workflow, optilux-next, optilux-release, the agents, the placeholder pack; about 3.3 h against 7.8 estimated. Plan: plans/m0.md; prompts: prompts/m0.md; what happened: the 0.00.06 handoff in git history.

## M0 phases
- 0.00.00 to 0.00.06 ran as planned in plans/m0.md section 5; the per-phase table is in the 0.00.06 handoff (git history).

## M1 game control
- Goal (design.md#6-milestones): `install`, `launch`, the `run` skeleton, `mod build` and `mod test`, and the helper mod's M1 commands (mod-protocol.md#commands), proven by acceptance A1-A4, A7, A9 and A10 on unmodified Complementary in a provisional world with three views.
- Verbs (design.md#5-interfaces, From = M1): `install`, `launch`, `run`, `mod build`, `mod test`. Mod: optilux-helper under mod/ with the 17 M1 commands and commands.json. Skill: optilux-plan (Decisions D8). CI moves to windows-latest (Decisions D5).
- Not in M1: PresentMon's session and window cut beyond A9's minimal start and stop, the world verbs, `calibrate`, `compare`, `report`, `verify records`, the reload cap and the final views (M2); `camera.path`, `window.measure`, timers, `shaders.dump`, capture align and flush (M2-M5); the hello pack and `verify similarity` (M3); A5, A6, A8, A11, A12; the TCP fallback (design.md#8-open-decisions E1) unless the pipe fails acceptance.
- Exit, all of: every verb above runs with its tests green; the 17 commands answer as mod-protocol.md specifies; acceptance records under results/records/ hold A1-A4, A7, A9, A10 passed and F4's bench-tier reload table; snapshots/provisional/ hashed and config/views/provisional.json committed; dev session 1 done; optilux-plan built; CI green on every push and on the PR; the PR `0.01 Game control: <what it delivers>` rebase-merged by the user; the release for the newest phase with its optilux-<version>.zip; docs/handoff.md written.
- Branch m1; 0.01.00 (workflow tooling) and 0.01.01 (this plan) precede the phases 0.01.02 to 0.01.10. Plan: plans/m1.md, premises verified 2026-10-06, decisions D17-D26 there. Prompts: prompts/m1.md.

## M1 phases
Change, exit and agent-time estimate per phase; files, tests, decisions and commit messages are in plans/m1.md section 5.

### 0.01.02 `install` and the launch spec
- Change: `install [--tier] [--refresh]` fills runtime/mc-26.3/ hash-checked: Minecraft through minecraft-launcher-lib, the Fabric profile, the tier's Modrinth files by sha512, Temurin by sha256, PresentMon by sha256; the launch spec built from Mojang's and Fabric's JSON and compared with the committed one, `--refresh` rewriting it. Mojang moved asset index 34 on 2026-10-06 (plans/m1.md P6, D20): the spec is refreshed once and committed.
- Exit: `optilux install` exits 0 with every hash equal and the spec equal to the committed one.
- Estimate: 2 h.

### 0.01.03 Pre-launch files and `launch`
- Change: options.txt, sodium-options.json and iris.properties written before every launch (F3; rawMouseInput false joins suite.json display); the launch gate (F2); `launch <world>`: game/mods/ made to hold exactly the tier's jars, jar and asset-index hashes checked, the offline session with the fresh token (`--no-token` for A1, `--set` for A7's option), `--uuid` from the snapshot's player file (F8), the started command line checked, the join awaited within 120 s (F11), WM_CLOSE until `quit` exists. CI to windows-latest. One announced launch.
- Exit: launch, join and quit pass with exit 0; the options read back equal the written keys; CI green on windows-latest.
- Estimate: 2 h.

### 0.01.04 Mod project, inert gate, `mod build` and `mod test`
- Change: mod/ as a Gradle project (Loom 1.18.2, Gradle 9.7.1 pinned by sha256, Java 25, Iris and Sodium compile-only from the pinned jars); fabric.mod.json generated from the platform file; the mixin config plugin and entrypoint inert without `-Doptilux.token`; the frame hook; `optilux mod build` and `mod test`; the metadata and mixin-target tests (F9).
- Exit: the jar builds, the JUnit tests pass, a launch without a token applies no mixin (A1's evidence).
- Estimate: 2 h.

### 0.01.05 Transport, protocol core and the client
- Change: the named pipe (token-derived name, first instance only, local clients only, a user-only DACL), framing and the envelope, dispatcher, errors, events, `cancel`, `busy`, the state owner, `hello`, `frames.index`, `quit`; commands.json; the Python client with its redacted request log and the protocol fake.
- Exit: `hello` answers from the game with its pid; `quit` ends it with exit 0.
- Estimate: 3 h.

### 0.01.06 Game adapter commands
- Change: `state`, `world.wait`, `command` at OWNER, `ticks.step`, `camera.place` with `/tp` semantics and the dimension argument, `camera.get`, `hud.set`, `input.block` with raw input, the world, focus and screen events.
- Exit: one launch runs the commands end to end, a Nether round trip included.
- Estimate: 3 h.

### 0.01.07 Renderer and Iris adapters, capture, selftest
- Change: `ready` on Sodium 0.9.2's fields, `shaders.reload` with the hooked error path (F5) and sinceReload, `shaders.options`, `frames.capture` with its manifest, `selftest`.
- Exit: one launch: ready holds, the reload answers Unbound, three captured frames match the manifest, selftest passes.
- Estimate: 3 h.

### 0.01.08 `run` skeleton, the provisional world, A1-A3 and A10
- Change: the spike's world copied to snapshots/provisional/ and hashed (Q1); config/views/provisional.json with three poses; `run <spec>` validates, launches, runs the session start and the items, writes the acceptance record with its identity; A1, A2 (F2 parity through SendInput), A3, A10; the snapshot retaken after the Nether and End visits.
- Exit: an acceptance record with A1-A3 and A10 passed; the snapshot hashed; the views file committed.
- Estimate: 2.5 h.

### 0.01.09 A4, A7, A9 and the reload memory table
- Change: PresentMon start and stop (CTRL_BREAK_EVENT, F1's mechanism) and the row match for A9; A4 on a broken copy of Unbound; A7 with and without raw input; F4's 50 reloads on the bench tier with heap after GC and private bytes every 10.
- Exit: the records hold A4, A7, A9 passed and F4's table.
- Estimate: 2 h.

### 0.01.10 Dev session 1 and optilux-plan
- Change: the dev tier installed and launched once; F6's deferred batch (the /mcp reconnect, one Viewfinder call, V2's pairs through `command`, the user's look review); the optilux-plan skill from the two hand-made plans (D8); the pending skill evals; the Status lines and CHANGELOG entry closed; the handoff.
- Exit: the session's captures and notes in the handoff; optilux-plan present; the Release prompt is next.
- Estimate: 1.5 h. Attended: the user's /mcp reconnect and look review.

## M1 to M6
One line each, from design.md#6-milestones; phase lists are provisional until each plan is approved. F and Q numbers refer to Findings assigned.
- M1 game control: the current milestone, detailed above (M1 game control, M1 phases); exit: design.md#6-milestones M1.
- M2 perf loop: PresentMon session and window cut (F1, F10); `world prep`, `world snapshot`, `world restore` (F8); `calibrate`, `compare`, `report`, run records and `verify records`; capture.reloadCap and the session budget from F4; the final views placed; optilux-bench after the first manual sessions. Exit: design.md#6-milestones M2.
- M3 visual loop: the static-texture pack, the hello pack with BENCH_DETERMINISTIC and pipeline spec v0, offline L0-L2 (`check`), `verify similarity`, coverage views, review page, iso profile v1, both modes recalibrated on the deterministic set. Exit: every perf view identical across 2 sessions (TAA off); A5.
- M4 shader base: every coverage-list program, lighting, tonemap; cost rows, timer rows below the CPU floor; offline L3-L4; debug-tier attribution; E2 decided.
- M5 features and temporal: shadows, sky, clouds, water, fog, AO, bloom, full TAA; the history flush (E4), A6, A12; temporal positive controls; live pass.
- M6 1.0: ratio vs Unbound iso reported; live pass; look review; README; release. Post-1.0: optimization, the JVM track, the lod tier, the Aperture backend.

## Findings assigned
The Phase -1 spike's handoff findings (2026-10-06), each with the milestone and phase that acts on it.

| # | Finding | Lands in | What it changes |
|---|---|---|---|
| F1 | PresentMon stop: CTRL_BREAK_EVENT, not CTRL_C; the CSV grows during the run; the first row arrives ~4 s after the start | M2 P1 PresentMon session | GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT) to a CREATE_NEW_PROCESS_GROUP child; rows cut by the mod's window stamps, never a sleep; a killed PresentMon fails the run (measurement.md#tools) |
| F2 | AMD Software starts PresentMon-x64.exe (RSXTraceSession) with every game | 0.01.03 launch gate | the gate blocks only on Minecraft processes and optilux-* ETW sessions; AMD's process and session are recorded in the run record, never stopped or waited on |
| F3 | options.txt needs version:5023 and graphicsPreset custom; Sodium forces exclusiveFullscreen on a fresh file; the dev tier needs use_no_error_g_l_context=false | 0.01.03 pre-launch files | the harness writes suite.json display.optionsTxt verbatim and the Sodium file with both keys; every written key and the Sodium file's hash are identity (run-record.md#identity); simulationDistance stays 12 (user, 2026-10-06) |
| F4 | Dev-tier reload memory: 20.6 MiB heap and 320 MiB private bytes per reload over 50 reloads | 0.01.09 reload table; M2 sets the cap | 50 `shaders.reload` on the bench tier through the mod, heap after GC and private bytes every 10 reloads, written as an acceptance record; M2 sets capture.reloadCap and the session budget from it, replacing ALC's 288 |
| F5 | Iris error path: in a world a failed load goes to chat; read `isFallback()`, hook `handleException` | 0.01.07 Iris adapter | `shaders.reload` answers `iris-compile-error` from the hooked message; A4 proves it (platform.md#mod-adapter-surface) |
| F6 | Viewfinder has no server-command tool; terrain shows only as "Terrain solid"; 30 fps under the debug context | 0.01.10 dev session 1; M2 A8 and E5 | /tick, /summon and /setblock go through the mod's `command`; dev session 1 runs the deferred batch: the look review of the L1, V1 and V6 captures (user), the /mcp reconnect and one Viewfinder call from Claude Code, V2 with /summon and /setblock; E5's overhead check separates the debug context from the mod |
| F7 | Dev-tier quit: WM_CLOSE saves the world, then the watchdog writes a crash report and the process exits -8 | closed (user, 2026-10-06) | accepted as known in platform.md#mod-tiers; the dev-session protocol treats exit -8 after "Saving worlds" as a clean quit; no shutdown step |
| F8 | 26.3 stores the singleplayer player under players/data/<uuid>.dat | 0.01.03 launch; M2 world verbs | `launch` takes `--uuid` from that file name when the snapshot has one; `world snapshot` records it (platform.md#install-and-launch) |
| F9 | Iris has no release tags since 1.7.3; the 26.3 branch head says MOD_VERSION 1.11.6 | 0.01.04 mixin-target test | the pinned jar's bytecode is the authority (`javap -c -p`); the source at commit adc75283b is context; the mixin-target test reads the jars (mod.md#11-build-and-test) |
| F10 | Offline mode still calls api.minecraftservices.com at startup; GPULatency read 1.04 frames idle at 141 fps | M2 P1 and calibration notes | the call is recorded, not blocked; the CPU-floor measurement reads GPULatency next to the 90 % rule (measurement.md#validity) |
| F11 | A launch takes about 20 s; 167 s only with the modal dialog | 0.01.03 launch | the world timeout is 120 s (6x the spike's 18.4 s join); the Sodium file is written before every launch so no dialog appears; a timeout ends the process and fails the run |
| Q1 | The game directory under runtime/ still holds the spike world and files | 0.01.08 | the provisional world is a copy of runtime/mc-26.3/game/saves/spike under snapshots/provisional/, made by hand and hashed (design.md#6-milestones); nothing else under runtime/ is reused: `install` rebuilds from the launch spec |

## Decisions
Owner: who decides. Recommendation: what an unattended run takes. Closed decisions live in design.md#7-decisions-taken-user-2026-10-05; evidence decisions E1-E5 in design.md#8-open-decisions.

| Id | Decision | Owner | Recommendation | When |
|---|---|---|---|---|
| D1 | Installing uv (not on PATH on 2026-10-06) | user | closed: `pip install uv==0.12.23` into the user's Python 3.12, whose Scripts folder was already on PATH (user, 2026-10-06) | closed |
| D2 | CLI framework | Claude | argparse from the standard library: no dependency; `--json` per verb; click would add a dependency no M0 verb needs | 0.00.01 |
| D3 | Where git hooks live | Claude | .githooks/ committed and `core.hooksPath` set with `git config --local` in 0.00.03, reported by `optilux status`; copying into .git/hooks would need an installer verb outside the verb table | 0.00.03 |
| D4 | Commit-message check | Claude | one line, at most 72 characters, `0.MM.PP: ` then text, no attribution token (Co-Authored-By, Claude, Anthropic, Generated; the tool name "Claude Code" passes unless "by", "with" or "via" precede it, as the 0.00.03 subject names it); the trailing period of the user's examples is style, not enforced | 0.00.03 |
| D5 | CI runner | Claude | ubuntu-latest: M0's tests are pure Python, and Windows minutes cost 2x on a private repo (2,000 minutes a month on GitHub Free); switch to windows-latest when a Windows-only path (ctypes, the named pipe) gets a test, in M1 | 0.00.06 |
| D6 | Release tag and asset | Claude | tag v<version> (workflow.md#release), asset optilux-<version>.zip, body = the milestone's CHANGELOG entry; the workflow creates the tag at main's head; title `Optilux <version>: <Name>`, the name from the CHANGELOG heading `## 0.MM <Name>` (user, 2026-10-06; from v0.01) | 0.00.06 |
| D7 | Repository merge settings | user | rebase merge on, squash and merge commits off, set in 0.00.06 by `gh repo edit` so a merge cannot pick another method; the prompt names the command and stops for the go | 0.00.06 |
| D8 | When optilux-plan is built | Claude | in M1's last phase, from two hand-made plans (m0.md, m1.md), used from M2's plan on; workflow.md#skills says after the first hand-written plan, and one plan is too little for the creation rule's 3 eval scenarios | 0.01.10 |
| D9 | Placeholder pack content | Claude | shader/shaders/shaders.properties with one comment line and no programs; never launched in M0; M3's hello pack replaces it and BENCH_DETERMINISTIC starts there (shader.md#determinism-and-taa) | 0.00.05 |
| D10 | Default branch name | Claude | `git init -b main`: the machine's init.defaultBranch is master and no config changes | 0.00.00 |
| D11 | Phase 0 question: the simulationDistance pin | user | closed: 12, the value the game chose (user, 2026-10-06); config/suite.json display | closed |
| D12 | Phase 0 question: the dev-tier exit code -8 | user | closed: accepted as known, no shutdown step (user, 2026-10-06); F7 | closed |

## Estimates
- M0: 0.3 + 1 + 1 + 1.5 + 1.5 + 1 + 1.5 = 7.8 h agent, no machine time. Basis: ALC's phases took about 1 h each (workflow.md#git); the spike estimated 4 h and took 2.5 h; ALC's run estimates of 4-6 h took about 1.2 h (workflow.md#running-a-milestone), so these are expected to run short rather than long.
- M1: 21 h agent from plans/m1.md (2, 2, 2, 3, 3, 3, 2.5, 2, 1.5; the mod phases carry 3 h each: ALC's mod ran 3x its line estimate, lessons.md#mod). M2 and M3, rough until each plan is approved: 10 h each. Machine time apart: M2 calibration about 2 h per identity (measurement.md#calibration).
- Tripwire baseline: M0-M3 summed 48.8 h (7.8 + 21 + 10 + 10); the trip is at 97.6 h, recomputed whenever a plan replaces a rough figure. Actuals: M0 about 3.3 h; M1 0.01.00 about 0.5 h, the rest in handoff.md.
