# Optilux
Shader + runtime benchmark suite for Minecraft, driven by Claude Code. Solo and boutique: one machine (Win11, RX 7800 XT, 5800X3D, 3840x2160), one platform at a time (mc-26.3).
Status: M0 in progress; 0.00.04 (status, milestone start, optilux-next, agents) is the last phase done, next 0.00.05 (docs/prompts/m0.md). Latest stop: docs/handoff.md.

## Rules
- The loop is the product (docs/design.md#3-core-rule). Build only what makes it faster or its verdicts more trustworthy.
- Python core (`optilux` package); Java only for the helper mod; PowerShell only where Windows forces it.
- Configs are JSON under config/. Platform specifics live only in config/platforms/, the mod adapter and the world snapshot.
- Shader: full rewrite. Complementary source may be studied (reference/, gitignored, never committed). No 1-1 copies; `optilux verify similarity` must pass.
- Never compare runs with different identities. Never fabricate, estimate silently or pass a missing measurement.
- Never change system settings. Never touch the user's played Minecraft instance. Graphics drivers are assumed good: no workarounds, never part of identity (records note the version).
- Announce every game launch.
- Git: one milestone branch; one commit per phase, `0.MM.PP: <summary>`, one line, at most 72 characters; push after each commit; one PR per milestone, rebase-merged by the user; no force push, no `--no-verify`.
- No Claude or Anthropic attribution anywhere.

## Layout
- optilux/: Python harness, a uv project (pyproject.toml, uv.lock, .python-version, one .venv); cli.py holds the verb registry, verbs/ one module per verb, prompts.py the stored-prompt parser, repo.py the git facts. Run `uv run optilux <verb>`.
- tests/: pytest, run by `uv run optilux test`.
- .githooks/: commit-msg and pre-commit sh shims over optilux/hooks.py (`core.hooksPath`, set --local).
- .claude/: settings.json (Claude Code hooks, allow rules); skills/optilux-next (`optilux status` and the next prompt); agents/researcher.md and reviewer.md (read-only).
- mod/ (planned): optilux-helper (Fabric).
- shader/ (planned): the pack.
- config/: platforms (+ launch specs), suite, profiles, java, tools; views and pipeline planned.
- docs/.
- Ignored: results/raw/, runtime/, snapshots/, reference/, .venv/. Committed: results/records/, config/calibrations/.

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
- docs/workflow.md: skills, agents, milestones, docs rules, git, release, hooks, tests.
- docs/lessons.md: what AlaCarteShaders (ALC) learned, tagged by platform dependence.
- docs/handoff.md: the latest stop: what passed, what failed, what is deferred, what the next phase plans around.
- docs/sources/: external documents kept verbatim (the user's optimization playbook).
- docs/roadmap.md: milestones M0-M6; the current one in detail (phases, exits, estimates); findings and decisions assigned, each decision with an owner.
- docs/plans/: one plan per milestone (m0.md first), written from docs/templates/plan.md, premises verified at their source.
- docs/prompts/: stored prompt sets, one prompt per phase plus Resume (m0.md first).
- docs/templates/: plan.md, the strict plan template.

## Terms
- view: fixed camera pose in the bench world; perf views are gated, coverage views are visual only.
- motion path: pose as a function of frames since the path start.
- variant: pack + effective option values.
- capture: one timed window or frame set at one view.
- session: one game launch. run record: JSON for one session.
- sinceReload: frames since the last pipeline creation; equals Iris's frameCounter. flush: one-frame TAA history invalidation (BENCH_DETERMINISTIC).
- A/A twin: byte-identical baseline copy measured as a candidate.
- threshold: minimum detectable effect, from null calibration.
- verdict: accept / reject / inconclusive (optimizations). cost row: per-view ms delta (features).
- level (offline): L0-L5, each with a power: close, predict or explain (docs/offline.md).
- tier (visual): identical / near / close / review. mod tier: bench / played / debug / dev / lod / jvm.
- platform: MC version + loader + renderer backend + pinned mods + formats + world snapshot.
- identity: every input that can move a measurement; different identities are never compared.
