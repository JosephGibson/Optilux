# Optilux
Shader + runtime benchmark suite for Minecraft, driven by Claude Code. Solo and boutique: one machine (Win11, RX 7800 XT, 5800X3D, 3840x2160), one platform at a time (mc-26.3).
Status: the entry point: rules, layout, docs and terms. Where the milestone stands: `uv run optilux status`, from git and docs/handoff.md.

## Rules
- The loop is the product (docs/design.md#3-core-rule). Build only what makes it faster or its verdicts more trustworthy.
- Python core (`optilux` package); Java only for the helper mod; PowerShell only where Windows forces it.
- Configs are JSON under config/. Platform specifics live in config/platforms/, the mod adapter, the world snapshot and suite.json's display block, plus some 26.3 facts in code (docs/design.md#4-architecture).
- Shader: full rewrite. Complementary source may be studied (reference/, never committed). No 1-1 copies; `optilux verify similarity` (M3) must pass.
- Never compare runs with different identities. Never fabricate, estimate silently or pass a missing measurement.
- Never change system settings. Never touch the user's played Minecraft instance. Graphics drivers are assumed good: no workarounds, never part of identity (records note the version).
- Announce every game launch.
- Git (docs/workflow.md#git): Conventional Commits, one line of at most 72 characters naming no milestone, phase, version or date; one logical, test-green change per commit, pushed after it; PRs rebase-merged by the user; no force push, no `--no-verify`.
- No Claude or Anthropic attribution anywhere.

## Layout
- optilux/: Python harness (uv, one .venv); cli.py the verb registry, verbs/ one module per verb, prompts.py stored prompts, repo.py the git facts, platform.py the platform file and launch spec, launch.py the gate and the launch, record.py the run spec, identity and record, session.py a game session, measure.py the measured session, stats.py the statistics, budget.py the reload budget, acceptance.py M1's items, world.py the world verbs, modclient.py and winpipe.py the pipe client, modfake.py the protocol fake, sendinput.py SendInput, presentmon.py PresentMon, visual.py the tiers, offline.py, l1.py and l2.py the offline levels, similarity.py the similarity check, packzip.py the pack zip, docs_check.py the doc rules. Run `uv run optilux <verb>`.
- tests/: pytest, run in parallel by `uv run optilux test`; fixtures/ saved 26.3 output; `windows`-marked tests skip elsewhere.
- .githooks/: commit-msg and pre-commit sh shims over optilux/hooks.py (`core.hooksPath`, set --local).
- .claude/: settings.json (Claude Code hooks, allow rules); skills/optilux-next (`optilux status`), optilux-release, optilux-plan, optilux-bench (docs/workflow.md#skills); agents/researcher.md and reviewer.md (read-only).
- .github/: workflows/ci.yml and release.yml (docs/workflow.md#release).
- mod/: optilux-helper (Fabric), a Gradle project (Loom, wrapper pinned by sha256); `mod build` puts its jar into runtime/<platform>/files/, `mod test` runs its JUnit tests.
- shader/: the pack (the hello pack), zipped by `pack build`, released by `pack release` (docs/workflow.md#release).
- config/: platforms (+ launch specs), suite, profiles, java, tools, similarity, views, pipeline, calibrations.
- snapshots/<world>/: world copies, tree-hashed; results/: records/<run>.json and raw/<run>/.
- docs/.
- VERSION: the release version (docs/workflow.md#release). Ignored: results/raw/, runtime/, snapshots/, reference/, build/, mod/.gradle/, .venv/, .coverage.

## Docs
- docs/design.md: goals, architecture, interfaces, milestones, decisions.
- docs/measurement.md: baseline suite, session, verdicts, calibration, visual protocol.
- docs/run-record.md: identity, record fields, comparison, run spec.
- docs/platform.md: platforms, renderer transition (Vulkan, Aperture), mod tiers, spike.
- docs/shader.md: rewrite policy, scope, method, pipeline spec.
- docs/playbook.md: design defaults, technique candidates, pitfalls, checklists.
- docs/offline.md: offline testing levels, what each may decide, tools.
- docs/gpu-iris.md: GPU and Iris facts with evidence tags.
- docs/mod.md, docs/mod-protocol.md: helper mod spec and wire contract (full rewrite).
- docs/jvm.md: JVM track (after 1.0).
- docs/workflow.md: skills, agents, milestones, doc ownership and rules, git, release, hooks, tests.
- docs/lessons.md: what AlaCarteShaders (ALC) learned, tagged by platform dependence.
- docs/handoff.md: the latest stop: the last phase done, what passed, failed or was deferred, the next step.
- docs/sources/: external documents kept verbatim (the user's optimization playbook).
- docs/roadmap.md: milestones M0-M6, the current one in detail; findings assigned; decisions, each with an owner.
- docs/plans/: one plan per milestone, from the strict template docs/templates/plan.md.
- docs/prompts/: stored prompt sets, one prompt per phase plus Resume; standing.md, the Plan and Release prompts every milestone uses.

## Terms
- view: fixed camera pose in the bench world; perf views are gated, coverage views are visual only.
- motion path: pose as a function of frames since the path start.
- variant: pack + effective option values.
- capture: one timed window or frame set at one view.
- session: one launch, or a split session's launches. run record: JSON for one launch, and one per split session.
- sinceReload: frames since the last pipeline creation; equals Iris's frameCounter. flush: one-frame TAA history invalidation (BENCH_DETERMINISTIC).
- A/A twin: byte-identical baseline copy measured as a candidate.
- threshold: minimum detectable effect, from null calibration.
- verdict: accept / reject / inconclusive (optimizations). cost row: per-view ms delta (features).
- level (offline): L0-L5, each with a power: close, predict or explain (docs/offline.md).
- tier (visual): identical / near / close / review. mod tier: bench / played / debug / dev / lod / jvm.
- platform: MC version + loader + renderer backend + pinned mods + formats + world snapshot.
- identity: every input that can move a measurement; different identities are never compared.
