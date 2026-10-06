# Workflow
Status: draft; M0 built the hooks, optilux-next, optilux-release, `milestone start`, the read-only agents, CI and the release workflow, and 0.01.00 the standing prompts; each later skill follows the creation rule.

## Contents
Skills · Agents · Running a milestone · Docs rules · Git · Release · Hooks and guards · Testing · Code conventions

## Skills
Rules (Anthropic's skill best practices, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):
- Name: `optilux-<verb>`, at most 64 chars, lowercase/digits/hyphens. "claude" and "anthropic" are reserved words.
- Description: third person, what + when + trigger terms, at most 1024 chars.
- Body: under 500 lines (target under 100). References one level deep. TOC in reference files over 100 lines. Forward slashes. One default per choice.
- Creation:
  1. do the task by hand with Claude and note the context you keep re-supplying;
  2. write 3 eval scenarios;
  3. measure without the skill;
  4. write minimal instructions that pass;
  5. test in a fresh session; watch what it reads, skips and rereads.
- Test each skill on every model that runs it.
- Freedom: low ("Run exactly `optilux <verb> ...`") for anything that launches, commits or releases; high for research and review.
- An injected command that fails cancels the skill, so injected status commands always exit 0. A model-invoked skill shows an injection as "run this first", so it needs an allow rule. `allowed-tools` pre-approves; it does not restrict. (ALC)

| Skill | Draft v0 name | Does | Freedom |
|---|---|---|---|
| optilux-next | /next, status, next prompt | Built: injects `uv run optilux status` (a briefing: the next prompt's kind, complexity, model and effort, critique, stops and machine needs; progress, last commit, the phases after, the handoff's open questions; branch, versions, tree, hooks, Status lines checked against the repo, problems with fixes) and prints it in a block, the switch block after a merge, and the next prompt verbatim last; there is always one (Running a milestone); `allowed-tools: Bash(uv run optilux status*)`; read-only, in the main context (a fork would hand the prompt back as a result instead of printing it) | low |
| optilux-milestone | /milestone, /phase | Milestone kickoff: injects the roadmap section and run rules, loads the stored prompt set | low |
| optilux-plan | /plan | Writes docs/plans/m<MM>.md from docs/templates/plan.md (strict template, at most 40,960 bytes); premises verified at the source | medium |
| optilux-bench | (Benchmark) | Validates a run spec, announces the launch, runs `optilux run`, summarizes the run record | low |
| optilux-release | /release | Built: picks its half from `gh pr view m<MM>`; before the PR `verify docs`, `test`, `pack release --check`, push, `gh pr create --title "0.MM <Name>: <what it delivers>" --body ""`, `gh pr checks --watch`; after the user's merge `gh run watch` on the release run, `gh release view v<version>`, and the switch block from `optilux status` for the user to paste, never run (user, 2026-10-06); no allowed-tools, so `gh pr create` keeps its permission prompt | low |
| optilux-research | (Shader Expert research) | docs/research/<topic>.md with sources; built after 2-3 manual research tasks | high |

- When each skill is built:
  - optilux-next and optilux-release in M0. ALC's status and release skills were the ones actually used.
  - optilux-plan after the first hand-written plan; optilux-bench after M2's first manual sessions; optilux-research after 2-3 manual research tasks.
  - optilux-milestone only if stored prompts prove insufficient. ALC's milestone skill was built and never invoked; its M3 ran on verbatim prompts.
- User-level, existing: /critique (second opinion from another model family; optional) and /rewrite (fast and deep modes as two sections of one skill).
- /rewrite is user-invoked only, never chained from another skill. Skills that emit prompts emit stored, already-written prompts instead.
- Not built:
  - /test: `optilux test` in a background shell does it.
  - a doc-writing skill: Claude writes skills natively; the doc style lives in "Docs rules" plus the limit test.
  - Codex mirrors of skills: Claude-only; ALC's generated dual layout needed a generator and a drift check.

## Agents
- researcher (.claude/agents/researcher.md; tools Read, Grep, Glob, WebFetch, WebSearch): read-only over the repo and the web. Leads with the answer, cites path and heading or URL, marks inferred claims, ends with "Not found:". Proposes no fixes.
- reviewer (.claude/agents/reviewer.md; tools Read, Grep, Glob): read-only, one dimension per call (correctness when none is named); each finding carries a severity, quoted evidence and a cite by path and heading, or is marked "unverified"; no rewrite. Both end with "Not found:".
- MCP: Viewfinder (dev tier; dev sessions only, offline.md#tools). In a dev session one controller drives the scene, Viewfinder or the helper mod, never both.
- ALC facts:
  - Delegate breadth, not a known-file lookup: ~238k subagent tokens bought ~8k in the main window.
  - Spot-check cited claims: one agent named a program the preprocessor gates out.
  - Auto mode refuses launching a write-capable agent and editing `.claude/agents/`. Agent files created mid-session are invisible until a restart.
  - Hooks fire inside subagents but cannot tell who called; "only the main session commits" is a convention.
  - No worktrees: fan out readers, keep writes serial.

## Running a milestone
1. Plan with optilux-plan into docs/plans/m<MM>.md (template docs/templates/plan.md, written with the first hand-made plan in Phase 0). Verify every premise at its source: ALC's recurring failure was "a control described rather than read" (3 times).
2. Optional /critique. The user approves. A `--repo` run works on a copy without reference/, runtime/, snapshots/ or results/raw/: Complementary's source never goes to a third-party model.
3. A stored prompt set, docs/prompts/<milestone>.md: one prompt per phase plus a Resume prompt. The user hands prompts out verbatim; prompts are never rewritten per session.
- The cycle's next prompt, as `optilux status` and /optilux-next print it (user, 2026-10-06): a milestone without a prompt set gets the standing Plan prompt (docs/prompts/standing.md), which runs steps 1-3 as the milestone's first free phase until optilux-plan exists, and so does one whose set starts at the phase after the next one (the plan phase in progress, its set written but not committed); then each phase's prompt; once every phase is committed, the standing Release prompt (/optilux-release); after the merge, the switch block to m<MM+1> and its Plan prompt.
- The briefing names the kind (planning, implementation, release), the size from the estimate in agent hours (S up to 0.5, M up to 1.5, L up to 3, XL above) and the model and effort (user, 2026-10-06): planning Fable 5.1 xHigh, Fable being limited to big-picture planning; S Sonnet 5.5 xHigh, M Opus 5.5 high, L Opus 5.5 xHigh, XL Opus 5.5 Max (status.py SIZE_MODELS has the reasons). A phase's estimate is its plan's `- Estimate:` line, whose `machine:` and `Attended:` notes it shows; a standing prompt carries its own. A /critique offer and a STOP are read from the prompt's numbered steps.
4. Unattended run: no questions mid-run. Take the roadmap's recommendation or log the question in the handoff.
5. One commit per phase; update the Status line after each; push after each commit.
6. Stop on a stated condition; write docs/handoff.md (one file, overwritten at each stop; superseded text deleted); report commits and time against estimates. ALC estimates ran wide (4-6 h estimated, ~1.2 h actual).
- Decisions have a named owner in the roadmap. Settled trade-offs stay closed. Irreversible deletions need an explicit go-ahead.
- State lives in the repo (roadmap Status line, plan, handoff). Claude's memory holds preferences and facts only; a stale memory note misled ALC planning once.

## Docs rules
Applies to every AI-facing doc. README and release notes are human-facing.
- Claude already knows graphics, GLSL, Python and Java. Docs hold project facts, measured numbers, decisions and pitfalls only.
- Evidence overrules docs. When the spike or a measurement contradicts a doc, the doc is fixed in the same phase; the work is never bent to fit it.
- Limits:
  - AGENTS.md at most 6,144 bytes; any .md under docs/ at most 24,576 bytes (sources/ exempt); a plan (optilux-plan output, docs/roadmap.md) at most 40,960 bytes (the critic refuses over 50,000 characters). Raised from 4,096 and 16,384 (user, 2026-10-06): those left the three most-edited docs at zero margin; the cap exists to force cuts of duplicated text, not to split a doc by concern;
  - TOC: a `## Contents` section directly after the Status line in any file over 100 lines;
  - `optilux verify docs` enforces size, TOC, links (every `path#heading` cite resolves to a heading in that file), UTF-8 without BOM, LF and Status lines over the root's .md, docs/ and .claude/ (skills and agents: every rule but the byte cap); optilux/docs_check.py holds the slug rule; a test runs it over the repo.
- AGENTS.md links one level deep. The Terms section is canonical; no synonyms.
- docs/sources/ holds external documents verbatim (the user's playbook). They are cited, never edited, and exempt from the limits.
- Status lines: ASCII, at most two sentences, pointing to the handoff.
- Cite by path and heading or quoted content, never by line number: ALC's line citations went stale within one milestone.
- Every record has a heading, so it can be read by section.
- No time-sensitive text in instructions. History = git log + run records. Superseded text is deleted, not archived.
- Roadmap: the current milestone in detail, later milestones one line each. Run records go in their own file, not in the plan.

## Git
- One branch at a time: the milestone branch (`m0`, `m1`, ...; design.md D6), cut by `optilux milestone start` (below). The private repo `Optilux` is created at the start of M0.
- Commits: one per phase; one line, at most 72 characters, in the user's form `0.MM.PP: <summary>` (e.g. `0.01.02: Run records added to harness.`).
  - A phase is one reviewable, test-green change (ALC's phases took ~1 h), so a regression bisects to one phase; rebase merge keeps every phase commit on main.
  - Shader features and candidates are options (shader.md#method), so a regression is also isolated by switching them off, without bisect.
- Push after every commit, as a backup; no git hook runs on push (Hooks and guards).
- PR per milestone: one-line title `0.MM <Name>: <what it delivers>`, the name as in the CHANGELOG heading, at most 72 characters, no trailing period (user, 2026-10-06; M0's was `0.00: Foundation.`); no body.
- No VERSION file. The release version is the prefix of the newest commit on main, and the commit-msg hook enforces the format, so it is checkable before the merge.
- `optilux milestone start` cuts the branch from origin/main with `--no-track` (ALC: VS Code Sync otherwise merges main into it). It refuses a dirty tree and an existing local or remote branch, fetches first and prints the next step; scripted like ALC's release-next, written after a hand-made branch broke.
- Bootstrap, once, by hand at the start of M0 (design.md D6): create the private repo `Optilux`; first commit on main `0.00.00: Repo bootstrap.` with .gitattributes, AGENTS.md, docs and config; `git push -u origin main`; `git switch -c m0 --no-track origin/main`. Every later branch is cut by `optilux milestone start`.
- The user merges with Rebase and merge. Rebased commits get new SHAs on main, so:
  - docs cite versions, never SHAs;
  - the milestone branch is deleted after the merge;
  - the next one is cut from the new main.
- Never: force push, `--no-verify`, other remotes, history rewrites, worktrees.
- Claude makes the commits under the user's name (user, 2026-10-05).
- No Claude or Anthropic attribution anywhere: no Co-Authored-By, no mention in commits, PRs, tags or releases. Enforced by the commit-msg hook.
- Check GitHub state live (`git ls-remote`, `gh release view`), never from local refs.
- Script multi-step git operations and test them. ALC: a hand-made branch skipped its version commit and the hook then refused it.

## Release
- .github/workflows/release.yml, on push to main (the user's rebase merge), runs `optilux pack release` with `permissions: contents: write` and GH_TOKEN from the workflow token:
  - HEAD must be origin/main's tip: a release cut from m<MM> would tag a commit the rebase merge replaces;
  - version = the newest commit's prefix; `pack build` first (shader/ + LICENSE + README with the credit; one tree, one sha256), so the release needs no other workflow's files; the tree must be clean;
  - `gh release view v<version>`; a tag v<version> already on origin must be at HEAD, else exit 1 (a tag is never moved);
  - when absent, `gh release create v<version> build/optilux-<version>.zip --title "Optilux <version>: <Name>" --notes-file <entry> --target <HEAD sha>`; `--target` because gh would otherwise tag the default branch's head at run time. Private repo, private releases.
- Release notes: each milestone's first phase adds its user-facing entry under `## 0.MM <Name>` to CHANGELOG.md, and later phases extend it; CI's release check needs it on every push. The release body is that entry, the name its title's.
- Every release rule must be checkable before the merge: `optilux pack release --check [--no-remote] [--ref R]` checks the subject of R (default HEAD) by the commit-msg rule, the CHANGELOG entry, no release and no tag for the version on GitHub (skipped with `--no-remote`), a clean tree, and R as a branch tip on origin. ALC's gate judged the merge method and message after the fact and refused 3 merges.
- CI, .github/workflows/ci.yml on push and pull_request (ubuntu-latest, roadmap.md#decisions D5; actions pinned to release tags): `uv sync --frozen`, ruff check and format, `optilux test`, `optilux verify docs`, `pack release --check --no-remote`, `pack build`, the zip as an artifact. On pull_request the checkout is GitHub's synthetic merge commit, whose subject carries no version, so the check and the build read it through `--ref HEAD^2`, the PR head; push events use HEAD. The in-game compile check runs locally through the mod.

## Hooks and guards
Bodies in optilux/hooks.py, run by the venv's python as `python -m optilux.hooks <name>`; .githooks/ holds the sh shims (`git config --local core.hooksPath .githooks`), .claude/settings.json the Claude Code hooks and allow rules. Inert outside this repository.
- Claude Code hooks:
  - PreToolUse git guard (Bash and PowerShell; exit 2 blocks): a push with `--force`, `-f`, `--force-with-lease`, `--mirror` or a `+` refspec; `--no-verify`, `commit -n`, `-c core.hooksPath`; a push naming main, `--all`, or a bare push on main; an attribution token in a commit's message, trailer or author. Passes `git push -u origin m<MM>` and `gh` through a variable;
  - PostToolUse post_edit (Edit, Write): ruff on an edited .py, `verify docs` on an edited .md; findings return as context, never a block.
- Git hooks:
  - commit-msg: one line, at most 72 characters, `0.MM.PP: ` then text, no attribution token (Co-Authored-By, Anthropic, Generated, Claude; the tool name "Claude Code" passes unless "by", "with" or "via" precede it);
  - pre-commit: ruff on staged .py, `verify docs` when a .md is staged; similarity on shader changes from M3, when the tool exists.
- ALC lessons:
  - Never hash files another tool rewrites (Prism rewrote instance.cfg and stopped a run at its gate).
  - Pre-write permission allow rules before an unattended run (auto mode blocked settings edits and a hash re-record).
  - A guard that refuses `gh` through a variable or `git push -u` is pure friction; drop it.

## Testing
- Unit tests only for:
  - statistics (bracketing, thresholds, geo-mean verdicts);
  - run-record schema and identity comparison;
  - platform pin verification (sha512);
  - similarity fingerprints;
  - doc limits;
  - the mod protocol: the round trip (JUnit on the mod side), and commands.json checked against mod-protocol.md's table.
- Runtime validity checks in every session (measurement.md#validity) are the main safety net.
- A test that needs git builds a throwaway repo in a temp dir and checks it is not this repo before writing (ALC rule).

## Code conventions
- uv, installed by pip into the user's Python 3.12 (roadmap.md#decisions D1): .python-version pins Python 3.12, pyproject.toml pins the dev tools exactly, uv.lock locks every dependency with hashes; one `.venv`; ruff format and lint; type hints on public functions.
- No absolute paths in code: paths derive from the repo root or config/.
- Windows APIs via ctypes. PowerShell only where Windows forces it.
- JSON for configs, inputs and records; the one exception is pyproject.toml, where uv, ruff and pytest read their settings. UTF-8 without BOM; LF. Git for Windows here sets core.autocrlf=true system-wide, so M0's first commit adds .gitattributes (`* text=auto eol=lf`); without it, hashed files change on checkout.
- Every constant carries its reason or evidence at its definition (no voodoo constants).
- Errors name the fix; scripts handle failures rather than leaving them to the agent.
