# Roadmap
Status: M0 in progress (plan plans/m0.md, prompts prompts/m0.md); 0.00.03 is the last phase done, next 0.00.04. Latest stop: handoff.md.

## Contents
Rules · M0 foundation · M0 phases · M1 to M6 · Findings assigned · Decisions · Estimates

## Rules
- Versions: 0.MM.PP = milestone MM, phase PP; one commit per phase, one PR and one release per milestone (workflow.md#git). A phase is one reviewable, test-green change: `optilux test` (from 0.00.01) and `optilux verify docs` (from 0.00.02) pass before its commit.
- Sizing rule (design.md#6-milestones): a milestone whose plan would pass the 40,960-byte plan cap is split before it starts. Unattended machine time (calibration, the overhead experiment) does not count: agent time is the constraint (design.md#3-core-rule).
- Tripwire (design.md#6-milestones): if M0-M3 together run past twice their summed estimates, stop and re-plan before building more infrastructure. Estimates holds the sums; every handoff adds the actuals.
- This file holds the current milestone in detail and the others one line each (workflow.md#docs-rules). When a milestone closes, its section shrinks to one line and the next one expands from its approved plan; Findings assigned keeps a row until the finding has landed.
- Running a milestone: plan from docs/templates/plan.md, optional /critique, the user's approval, the prompt set, the unattended run, one commit per phase, the handoff (workflow.md#running-a-milestone). An unattended run asks nothing mid-run: it takes the recommendation in Decisions or the plan, or logs the question in the handoff.
- No milestone closes on dummies (design.md#3-core-rule). M0 ships a placeholder pack because its exit is the release path, not a pack; M1-M3 exit on real packs.

## M0 foundation
- Goal (design.md#6-milestones): repo, AGENTS.md, hooks, CI (tests + packaging), release workflow shipping a placeholder pack, `optilux status`, doc-limit test. Exit: a merged PR produces a private release.
- Verbs (design.md#5-interfaces, From = M0): `test`, `verify docs`, `status`, `milestone start`, `pack build`, `pack release`. Skills: optilux-next and optilux-release (workflow.md#skills). Agents: researcher and reviewer (workflow.md#agents). Hooks: both sets (workflow.md#hooks-and-guards). Tooling: uv, ruff, pytest (workflow.md#code-conventions).
- Not in M0: install, launch, run, the mod and any game launch (M1); `verify records` (M2); `verify similarity`, the hello pack and offline levels (M3); optilux-plan (Decisions D8); `jvm` (post-1.0). Nothing under runtime/ is read or written.
- Exit, all of: every verb above runs with its tests green; the hooks refuse a bad commit message and a forbidden git command; `optilux status` prints the next stored prompt verbatim; CI green on the m0 push and on the PR; the PR `0.00: Foundation.` rebase-merged by the user; the release workflow creates the private release for the newest phase (v0.00.06 unless a fix phase follows) with its optilux-<version>.zip; docs/handoff.md written.
- Branch m0; commit 0.00.00 on main (the bootstrap), 0.00.01 to 0.00.06 on m0. Plan: plans/m0.md, premises verified 2026-10-06. Prompts: prompts/m0.md; the first holds the git bootstrap and stops for the user's go before the first push.

## M0 phases
Change, tests, exit and agent-time estimate per phase; file lists and commit messages are in plans/m0.md.

### 0.00.00 Repo bootstrap
- By hand from the first stored prompt, exactly as workflow.md#git: `git init -b main`; .gitattributes (`* text=auto eol=lf` plus binary rules); first commit `0.00.00: Repo bootstrap.` with .gitattributes, AGENTS.md, CLAUDE.md, README.md, CHANGELOG.md, .gitignore, .mcp.json, docs/ and config/; `gh repo create Optilux --private`; stop for the user's go; `git push -u origin main`; `git switch -c m0 --no-track origin/main`.
- Tests: by hand: nothing under runtime/ staged; one commit, no trailer.
- Exit: `git ls-remote origin main` shows the bootstrap commit; the local branch is m0 with no upstream; the tree is clean.
- Estimate: 0.3 h.

### 0.00.01 Python project and `optilux test`
- Change: uv project (.python-version, pyproject.toml, uv.lock with hashes, .venv); package `optilux` with the `optilux` entry point, a verb registry and `test` (pytest); ruff configured; one test. uv is not installed on 2026-10-06: the prompt stops for the user's OK before installing it (Decisions D1).
- Tests: `optilux test` green; `ruff check` and `ruff format --check` clean; `uv sync --frozen` rebuilds the venv.
- Exit: `optilux test` exits 0 with at least one test.
- Estimate: 1 h.

### 0.00.02 `optilux verify docs` and the doc-limit test
- Change: `verify docs` checks every .md outside docs/sources/: byte caps (AGENTS.md 6,144; docs/*.md 24,576; docs/roadmap.md and docs/plans/*.md 40,960); the TOC rule (`## Contents` after the Status line in a file over 100 lines); cites (`path#heading` resolves to a heading in that file, the path tried relative to the citing file's directory, then docs/, then the repo root; slug rule: lowercase, drop every character that is not a letter, digit, space or hyphen, spaces to hyphens; fenced code skipped); UTF-8 without BOM; LF; a Status line of at most two ASCII sentences. Exit 1 names each violation and its fix; `--json`; sizes and margins printed. Both hook sets call it from 0.00.03.
- Tests: one fixture per violation; a run over docs/.
- Exit: `optilux verify docs` passes on the committed tree.
- Estimate: 1 h.

### 0.00.03 Hooks and guards
- Change: git hooks under .githooks/ (committed; `git config --local core.hooksPath .githooks`): commit-msg (one line, at most 72 characters, `0.MM.PP: <summary>`, no attribution token) and pre-commit (ruff on staged .py, `verify docs` on staged .md; similarity joins in M3). Claude Code hooks in .claude/settings.json: PreToolUse on Bash refuses a force push (`--force`, `-f`, `--force-with-lease`, a refspec with a leading `+`), `--no-verify`, a push to main (a refspec naming main, or a bare `git push` while the current branch is main) and attribution in a commit command; PostToolUse runs ruff on an edited .py and `verify docs` on an edited .md; permission allow rules for the unattended run (workflow.md#hooks-and-guards). Hook bodies are Python in the package, run through the venv; sh shims only where git needs them. `git push -u origin m<MM>` and `gh` through a variable pass.
- Tests: the checkers on message and command fixtures; the git hooks end to end in a throwaway repo in a temp dir that first proves it is not this repo (workflow.md#testing); the Claude Code hooks on JSON stdin fixtures (exit 2 blocks).
- Exit: git refuses a bad message and accepts a good one; the Claude Code hook refuses `git push --force`; the allow rules cover every command the later phases run.
- Estimate: 1.5 h.

### 0.00.04 `optilux status`, `milestone start`, optilux-next, the agents
- Change: `status` prints the branch, the newest version prefix (local, and origin/main through `git ls-remote`), the next phase, the Status lines of AGENTS.md and roadmap.md, tree clean or not, hooks path set or not, and the next stored prompt verbatim from docs/prompts/m<MM>.md (prompts/m0.md Rules); always exits 0 (it is injected into a skill); `--json`. `milestone start <MM>`: refuses a dirty tree or an existing branch, fetches, `git switch -c m<MM> --no-track origin/main`. Skill optilux-next (low freedom: runs `optilux status`, prints the prompt verbatim; forked, read-only). Agents researcher and reviewer in .claude/agents/ with read-only tools and the output rules of workflow.md#agents.
- Tests: `status` on a fixture prompt file and on prompts/m0.md; `milestone start` in a throwaway repo with a bare origin.
- Exit: `optilux status` prints the 0.00.05 prompt; the skill and one researcher call work in a fresh session (new agent and skill files are invisible until a restart: the user runs this check once, between the phases).
- Estimate: 1.5 h.

### 0.00.05 Placeholder pack, `pack build`, LICENSE, CHANGELOG
- Change: shader/ holds the placeholder pack (Decisions D9); LICENSE (MIT, the user's name); README keeps the D7 credit; `pack build` zips shader/ + LICENSE + README.md as optilux-<version>.zip with forward slashes and fixed timestamps, so one tree gives one sha256; version = the newest commit's prefix or `--version`. CHANGELOG.md gets the 0.00 entry (workflow.md#release).
- Tests: build, unzip, compare the tree; two builds byte-identical.
- Exit: `optilux pack build` writes the zip and prints its sha256.
- Estimate: 1 h.

### 0.00.06 CI, release workflow, optilux-release, the PR
- Change: .github/workflows/ci.yml on push and pull_request (ubuntu-latest, Decisions D5; checkout with the full history: `uv sync --frozen`, ruff, `optilux test`, `optilux verify docs`, `optilux pack release --check --no-remote`, which reads the version from HEAD^2 on pull_request events because HEAD is then GitHub's synthetic merge commit, `optilux pack build`, the zip as an artifact); .github/workflows/release.yml on push to main (`permissions: contents: write`; GH_TOKEN set from the workflow token so `gh` is authenticated on the runner; `optilux pack release`: builds the zip itself, version from the newest commit's prefix, body = the CHANGELOG entry for 0.MM, `gh release create v<version> <zip> --target <HEAD>` only when `gh release view` finds none, and an existing tag must resolve to HEAD). `pack release --check` runs locally and in CI: prefix valid, CHANGELOG entry present, no release for the version, tree clean and pushed. Skill optilux-release: the checklist (`verify docs`, `test`, `pack release --check`, push, `gh pr create` with the one-line title and no body), then watches the release after the user's merge. Repo settings: rebase merge on, the other two off (Decisions D7).
- Tests: `pack release --check` on fixtures with a fake gh and git; the workflows by their first run on the m0 push.
- Exit: CI green on the m0 push and on the PR; after the user's rebase merge the release exists with its asset (M0 exit).
- Estimate: 1.5 h, plus the user's merge.

## M1 to M6
One line each, from design.md#6-milestones; phase lists are provisional until each plan is approved. F and Q numbers refer to Findings assigned.
- M1 game control (`install`, `launch`, the `run` skeleton, `mod build` and `mod test`, the mod's M1 commands, mod-protocol.md#commands): P1 install and the launch-spec check; P2 pre-launch files, launch gate, offline session and command-line check (F2, F3, F8, F11); P3 mod core (transport, protocol, state owner, inert gate, mixin-target tests; F9); P4 adapters and M1 commands (F5); P5 acceptance A1-A4, A7, A9, A10 on unmodified Complementary in the provisional world (three views; Q1) plus the bench-tier 50-reload memory measurement (F4); P6 dev session 1 (F6) and the optilux-plan skill (Decisions D8). Exit: design.md#6-milestones M1.
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
| F2 | AMD Software starts PresentMon-x64.exe (RSXTraceSession) with every game | M1 P2 launch gate | the gate blocks only on Minecraft processes and optilux-* ETW sessions; AMD's process and session are recorded in the run record, never stopped or waited on |
| F3 | options.txt needs version:5023 and graphicsPreset custom; Sodium forces exclusiveFullscreen on a fresh file; the dev tier needs use_no_error_g_l_context=false | M1 P2 pre-launch files | the harness writes suite.json display.optionsTxt verbatim and the Sodium file with both keys; every written key and the Sodium file's hash are identity (run-record.md#identity); simulationDistance stays 12 (user, 2026-10-06) |
| F4 | Dev-tier reload memory: 20.6 MiB heap and 320 MiB private bytes per reload over 50 reloads | M1 P5 acceptance; M2 sets the cap | 50 `shaders.reload` on the bench tier through the mod, heap after GC and private bytes every 10 reloads, written as an acceptance record; M2 sets capture.reloadCap and the session budget from it, replacing ALC's 288 |
| F5 | Iris error path: in a world a failed load goes to chat; read `isFallback()`, hook `handleException` | M1 P4 Iris adapter | `shaders.reload` answers `iris-compile-error` from the hooked message; A4 proves it (platform.md#mod-adapter-surface) |
| F6 | Viewfinder has no server-command tool; terrain shows only as "Terrain solid"; 30 fps under the debug context | M1 P6 dev session 1; M2 A8 and E5 | /tick, /summon and /setblock go through the mod's `command`; dev session 1 runs the deferred batch: the look review of the L1, V1 and V6 captures (user), the /mcp reconnect and one Viewfinder call from Claude Code, V2 with /summon and /setblock; E5's overhead check separates the debug context from the mod |
| F7 | Dev-tier quit: WM_CLOSE saves the world, then the watchdog writes a crash report and the process exits -8 | closed (user, 2026-10-06) | accepted as known in platform.md#mod-tiers; the dev-session protocol treats exit -8 after "Saving worlds" as a clean quit; no shutdown step |
| F8 | 26.3 stores the singleplayer player under players/data/<uuid>.dat | M1 P2 launch; M2 world verbs | `launch` takes `--uuid` from that file name when the snapshot has one; `world snapshot` records it (platform.md#install-and-launch) |
| F9 | Iris has no release tags since 1.7.3; the 26.3 branch head says MOD_VERSION 1.11.6 | M1 P3 reading rule | the pinned jar's bytecode is the authority (`javap -c -p`); the source at commit adc75283b is context; the mixin-target test reads the jars (mod.md#11-build-and-test) |
| F10 | Offline mode still calls api.minecraftservices.com at startup; GPULatency read 1.04 frames idle at 141 fps | M2 P1 and calibration notes | the call is recorded, not blocked; the CPU-floor measurement reads GPULatency next to the 90 % rule (measurement.md#validity) |
| F11 | A launch takes about 20 s; 167 s only with the modal dialog | M1 P2 launch | the world timeout is 120 s (6x the spike's 18.4 s join); the Sodium file is written before every launch so no dialog appears; a timeout ends the process and fails the run |
| Q1 | The game directory under runtime/ still holds the spike world and files | M1 P5 | the provisional world is a copy of runtime/mc-26.3/game/saves/spike under snapshots/provisional/, made by hand and hashed (design.md#6-milestones); nothing else under runtime/ is reused: `install` rebuilds from the launch spec |

## Decisions
Owner: who decides. Recommendation: what an unattended run takes. Closed decisions live in design.md#7-decisions-taken-user-2026-10-05; evidence decisions E1-E5 in design.md#8-open-decisions.

| Id | Decision | Owner | Recommendation | When |
|---|---|---|---|---|
| D1 | Installing uv (not on PATH on 2026-10-06) | user | closed: `pip install uv==0.12.23` into the user's Python 3.12, whose Scripts folder was already on PATH (user, 2026-10-06) | closed |
| D2 | CLI framework | Claude | argparse from the standard library: no dependency; `--json` per verb; click would add a dependency no M0 verb needs | 0.00.01 |
| D3 | Where git hooks live | Claude | .githooks/ committed and `core.hooksPath` set with `git config --local` in 0.00.03, reported by `optilux status`; copying into .git/hooks would need an installer verb outside the verb table | 0.00.03 |
| D4 | Commit-message check | Claude | one line, at most 72 characters, `0.MM.PP: ` then text, no attribution token (Co-Authored-By, Claude, Anthropic, Generated; the tool name "Claude Code" passes unless "by", "with" or "via" precede it, as the 0.00.03 subject names it); the trailing period of the user's examples is style, not enforced | 0.00.03 |
| D5 | CI runner | Claude | ubuntu-latest: M0's tests are pure Python, and Windows minutes cost 2x on a private repo (2,000 minutes a month on GitHub Free); switch to windows-latest when a Windows-only path (ctypes, the named pipe) gets a test, in M1 | 0.00.06 |
| D6 | Release tag and asset | Claude | tag v<version> (workflow.md#release), asset optilux-<version>.zip, body = the milestone's CHANGELOG entry; the workflow creates the tag at main's head | 0.00.06 |
| D7 | Repository merge settings | user | rebase merge on, squash and merge commits off, set in 0.00.06 by `gh repo edit` so a merge cannot pick another method; the prompt names the command and stops for the go | 0.00.06 |
| D8 | When optilux-plan is built | Claude | in M1's last phase, from two hand-made plans (m0.md, m1.md), used from M2's plan on; workflow.md#skills says after the first hand-written plan, and one plan is too little for the creation rule's 3 eval scenarios | M1 P6 |
| D9 | Placeholder pack content | Claude | shader/shaders/shaders.properties with one comment line and no programs; never launched in M0; M3's hello pack replaces it and BENCH_DETERMINISTIC starts there (shader.md#determinism-and-taa) | 0.00.05 |
| D10 | Default branch name | Claude | `git init -b main`: the machine's init.defaultBranch is master and no config changes | 0.00.00 |
| D11 | Phase 0 question: the simulationDistance pin | user | closed: 12, the value the game chose (user, 2026-10-06); config/suite.json display | closed |
| D12 | Phase 0 question: the dev-tier exit code -8 | user | closed: accepted as known, no shutdown step (user, 2026-10-06); F7 | closed |

## Estimates
- M0: 0.3 + 1 + 1 + 1.5 + 1.5 + 1 + 1.5 = 7.8 h agent, no machine time. Basis: ALC's phases took about 1 h each (workflow.md#git); the spike estimated 4 h and took 2.5 h; ALC's run estimates of 4-6 h took about 1.2 h (workflow.md#running-a-milestone), so these are expected to run short rather than long.
- M1-M3, rough until each plan is approved: M1 16 h (the mod is the bulk: ALC's ran 3x its line estimate, lessons.md#mod), M2 10 h, M3 10 h. Machine time apart: M2 calibration about 2 h per identity (measurement.md#calibration).
- Tripwire baseline: M0-M3 summed 43.8 h; the trip is at 87.6 h, recomputed whenever a plan replaces a rough figure. Actuals: none yet.
