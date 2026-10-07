# Workflow
Status: how Optilux is developed: skills, agents, the milestone cycle, docs, git, release, hooks, tests and code. Built: optilux-next, optilux-release, optilux-plan, both agents, the hooks, `milestone start`, the standing prompts, CI and the release workflow; each later skill follows the creation rule.

## Contents
Skills · Agents · Agent principles · Running a milestone · Doc ownership · Docs rules · Git · Release · Hooks and guards · Testing · Code conventions

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
| optilux-next | /next, status, next prompt | Built: injects `uv run optilux status` (a briefing: the next prompt's kind, complexity, model and effort, critique, stops and machine needs; progress, last commit, the phases after, the handoff's open questions; branch, versions, tree, hooks, problems with fixes) and prints it in a block, the switch block after a merge, and the next prompt verbatim last, unless a PROBLEM row names the fault (Running a milestone); `allowed-tools: Bash(uv run optilux status*)`; read-only, in the main context (a fork would hand the prompt back as a result instead of printing it) | low |
| optilux-milestone | /milestone, /phase | Milestone kickoff: injects the roadmap section and run rules, loads the stored prompt set | low |
| optilux-plan | /plan, plan the milestone | Built (0.01.10, from plans/m0.md and plans/m1.md): writes docs/plans/m<N>.md from docs/templates/plan.md section by section, section 3 first with every premise verified at its source that day or marked `open:`, at most 40,960 bytes or a proposed split, the /critique offer and the approval stop, then docs/prompts/m<N>.md; the standing Plan prompt's step 1 calls it; no allowed-tools, no model pin | medium |
| optilux-bench | (Benchmark) | Validates a run spec, announces the launch, runs `optilux run`, summarizes the run record | low |
| optilux-release | /release | Built: picks its half from `gh pr view m<N>`; before the PR `verify docs`, `test`, `pack release --check`, push, `gh pr create` with the title of Git and an empty body, `gh pr checks --watch`; after the user's merge `gh run watch` on the release run, `gh release view v<version>`, and the switch block from `optilux status` for the user to paste, never run (user, 2026-10-06); no allowed-tools, so `gh pr create` keeps its permission prompt | low |
| optilux-research | (Shader Expert research) | docs/research/<topic>.md with sources; built after 2-3 manual research tasks | high |

- Evals (creation rule step 2), run in fresh `claude -p` sessions in this repo in auto mode with pushes, PRs, commits, releases and edits denied; streams under results/raw/skill-evals/ (0.01.10):
  - optilux-next, on its pinned Sonnet: `/optilux-next`; "Which phase is next and what model should run it?"; "Where does the milestone stand?". It passes when the briefing and the prompt equal `optilux status`'s lines byte for byte. Two of six runs cut the briefing at its first dashed rule; once the skill named the briefing's last rows, 4 of 4 were exact.
  - optilux-release, on Sonnet xHigh (the Release prompt's model): on m1 with no PR and barred from pushing or opening one, it runs steps 0-3 and stops at the first problem with its fix; dry from OPEN, steps 6-7 and no merge; dry from MERGED, steps 8-10 with the switch block printed, never run. 3 of 3, with the PR title of then.
  - optilux-plan, on Fable xHigh (the planning model): dry for M2, it names the file and title, the ten headings in order, section 3 first with how each premise is verified, the cap and the split, the critique offer, the approval stop and the prompt set (passed once the skill pinned m<N>.md; the first run wrote m02.md); M2's real plan passes `verify docs` with every premise dated at its source and no prompt before the approval; a premise that cannot be read is marked `open:` and no phase rests on it. The last two run with M2's plan.
- When each skill is built:
  - optilux-next and optilux-release in M0. ALC's status and release skills were the ones actually used.
  - optilux-plan in 0.01.10, from the two hand-written plans (roadmap.md#decisions D8); optilux-bench after M2's first manual sessions; optilux-research after 2-3 manual research tasks.
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

## Agent principles
- Small permanent instructions: AGENTS.md and the skills hold rules and pointers; facts live in docs and code.
- Context loaded progressively: AGENTS.md links one level deep, a prompt names what to read, a skill injects what it needs.
- Facts in tooling: what a command can compute or check (versions, the last phase, the release rules, doc limits), it does, and docs and skills cite the command instead of restating it.
- Read-only agents for research and review (Agents); they propose no fixes.
- One writer at a time: one session edits, commits and pushes; agents fan out as readers.
- A new skill only after repeated real work shows the need (Skills, creation rule).

## Running a milestone
1. Plan with optilux-plan into docs/plans/m<N>.md (template docs/templates/plan.md, written with the first hand-made plan in Phase 0). Verify every premise at its source: ALC's recurring failure was "a control described rather than read" (3 times).
2. Optional /critique. The user approves. A `--repo` run works on a copy without reference/, runtime/, snapshots/ or results/raw/: Complementary's source never goes to a third-party model.
3. A stored prompt set, docs/prompts/m<N>.md: one `## M<N>.P<PP> <title>` heading per phase (M0's and M1's sets: `0.MM.PP`), each followed by exactly one fenced block holding its prompt, and `## Resume` last with one; in the form of docs/prompts/m1.md Rules (the why and a Done-when first, a reviewer pass where risk is, a Report that backs each claim with output). The user hands prompts out verbatim; prompts are never rewritten per session.
- The cycle's next prompt, as `optilux status` and /optilux-next print it (user, 2026-10-06): a milestone without a prompt set gets the standing Plan prompt (docs/prompts/standing.md), which runs steps 1-3 through optilux-plan as the milestone's first free phase, and so does one whose set starts at the phase after the next one (the plan phase in progress, its set written but not committed); then each phase's prompt; once every phase is done, the standing Release prompt (/optilux-release); after the merge (origin/main carries the branch's VERSION), the switch block to m<N+1> and its Plan prompt.
- The briefing names the kind (planning, implementation, release), the size from the estimate in agent hours (S up to 0.5, M up to 1.5, L up to 3, XL above) and the model and effort (user, 2026-10-06): planning Fable 5.1 xHigh, Fable being limited to big-picture planning; S Sonnet 5.5 xHigh, M Opus 5.5 high, L Opus 5.5 xHigh, XL Opus 5.5 Max (status.py SIZE_MODELS has the reasons). A phase's estimate is its plan's `- Estimate:` line, whose `machine:` and `Attended:` notes it shows; a standing prompt carries its own. A /critique offer and a STOP are read from the prompt's numbered steps.
4. Unattended run: no questions mid-run. Take the roadmap's recommendation or log the question in the handoff.
5. A phase takes one or more commits (Git). The commit that completes it overwrites docs/handoff.md, whose `Last phase: M<N>.P<PP>` line is how far the milestone stands; M<N>.P00 is the plan phase. M0 and M1 named their phases in subjects, which `optilux status` reads when the handoff has no such line.
6. Stop on a stated condition; write docs/handoff.md (one file, overwritten at each stop; superseded text deleted); report commits and time against estimates. ALC estimates ran wide (4-6 h estimated, ~1.2 h actual).
- Decisions have a named owner in the roadmap. Settled trade-offs stay closed. Irreversible deletions need an explicit go-ahead.
- State lives in the repo (Doc ownership). Claude's memory holds preferences and facts only; a stale memory note misled ALC planning once.

## Doc ownership
- design.md: what the system is now, built or spec. roadmap.md: the next major outcome, the current milestone in detail and later ones one line each. plans/m<N>.md: how one milestone runs, then the record of what was planned. handoff.md: where execution stopped. workflow.md: how development is done.
- Roadmap decisions hold durable, non-obvious rationale only; a closed row is never edited, a later row supersedes it.
- Milestone position lives in one place, the handoff's `Last phase:` line, which `optilux status` reads with git. Status lines say what a doc covers and how far it is built, never where the milestone stands.

## Docs rules
Applies to every AI-facing doc. README and release notes are human-facing.
- Claude already knows graphics, GLSL, Python and Java. Docs hold project facts, measured numbers, decisions and pitfalls only.
- Evidence overrules docs. When the spike or a measurement contradicts a doc, the doc is fixed in the same phase; the work is never bent to fit it.
- Limits:
  - AGENTS.md at most 6,144 bytes; any .md under docs/ at most 24,576 bytes (sources/ exempt); a plan (optilux-plan output, docs/roadmap.md) or a prompt set (docs/prompts/) at most 40,960 bytes (the critic refuses over 50,000 characters). Raised from 4,096 and 16,384, and for prompt sets from 24,576 (user, 2026-10-06): those left the three most-edited docs at zero margin; the cap exists to force cuts of duplicated text, not to split a doc by concern;
  - TOC: a `## Contents` section directly after the Status line in any file over 100 lines;
  - `optilux verify docs` enforces size, TOC, links (every `path#heading` cite resolves to a heading in that file), UTF-8 without BOM, LF and Status lines over the root's .md, docs/ and .claude/ (skills and agents: every rule but the byte cap); optilux/docs_check.py holds the slug rule; a test runs it over the repo.
- AGENTS.md links one level deep. The Terms section is canonical; no synonyms.
- docs/sources/ holds external documents verbatim (the user's playbook). They are cited, never edited, and exempt from the limits.
- Status lines: ASCII, at most two sentences (Doc ownership).
- Cite by path and heading or quoted content, never by line number: ALC's line citations went stale within one milestone.
- Every record has a heading, so it can be read by section.
- No time-sensitive text in instructions. History = git log + run records. Superseded text is deleted, not archived.
- Run records go in their own file, not in the plan.

## Git
- One milestone branch at a time (`m0`, `m1`, ...; design.md D6), cut from origin/main by `optilux milestone start` with `--no-track` (ALC: VS Code Sync otherwise merges main into it); it refuses a dirty tree and an existing local or remote branch, fetches first and prints the next step. A patch release takes its own short branch from main. Bootstrap, once, by hand at the start of M0 (design.md D6).
- Commits (roadmap.md D33): Conventional Commits, `type(scope)!: summary`, the type one of feat, fix, perf, refactor, test, docs, build, ci, chore, revert, the scope optional and lowercase, `!` for a breaking change. One line, at most 72 characters, no body and no trailer; the subject never names a milestone, phase, version or date. The commit-msg hook enforces it (Hooks and guards).
- A commit is one logical, test-green change: `optilux test` and `optilux verify docs` pass before it. A phase may take several (ALC's phases took about 1 h). Push after every commit, as a backup; no git hook runs on push.
- Shader features and candidates are options (shader.md#method), so a regression is isolated by switching one off as well as by bisect.
- M0's and M1's subjects carry their phase (`0.MM.PP: `, from 0.01.12.1 `0.MM.PP.N: `, roadmap.md D32); they stay as written, and `optilux status` reads them.
- A PR is the integration and review boundary: one per milestone, plus one per patch release. Title `<version> <Name>: <what it delivers>`, the version and name as `optilux pack release --check` prints them, at most 72 characters, no trailing period; no body.
- The user merges with Rebase and merge only (roadmap.md D7). Rebased commits get new SHAs on main, so docs cite versions and phases, never SHAs; the merged branch is deleted and the next one is cut from the new main.
- Never: force push, `--no-verify`, other remotes, history rewrites, worktrees.
- Claude makes the commits under the user's name (user, 2026-10-05). No Claude or Anthropic attribution anywhere: commits, PRs, tags or releases; the commit-msg hook and the git guard refuse it.
- Check GitHub state live (`git ls-remote`, `gh release view`), never from local refs. Script multi-step git operations and test them (ALC: a hand-made branch skipped its version commit).

## Release
- The version is the root file VERSION, MAJOR.MINOR.PATCH, and nothing else: `optilux status`, CI, `pack build`, `pack release`, the asset optilux-<version>.zip, the tag v<version> and the title `Optilux <version>: <Name>` all read it (roadmap.md D33). It is no part of run identity, and the mod jar keeps its own version (mod.md#11-build-and-test).
- Policy: before 1.0 a completed milestone is a minor release, so Mn ships as 0.(n+1).0 (M1 as 0.2.0, M2 as 0.3.0); the final production milestone ships as 1.0.0, set by hand. PATCH (0.2.1, ...) is the escape hatch for a bungled release, a packaging error or an urgent fix, through its own PR. M0 shipped as v0.00.06, before VERSION existed; no v0.1.0 is issued.
- A milestone's first commit (the Plan prompt's) sets VERSION to the minor after origin/main's, which `optilux status` fills into the prompt and `milestone start` prints, and adds `## <version> <Name>` to CHANGELOG.md with the user-facing entry; later commits extend it. The release body is that entry, its name the title's. No release-prep commit.
- `optilux pack release --check [--no-remote] [--ref R]` applies every release rule to R (its help lists them), here and in CI on every push and PR; `pack release` applies the same rules again after the merge, so the merge is never their first run.
- .github/workflows/release.yml, on push to main (the rebase merge), windows-latest, `permissions: contents: write`, GH_TOKEN: `pack release --check`, then `pack release`, which needs HEAD at origin/main's tip, builds the zip (shader/ + LICENSE + README; one tree, one sha256) and creates release v<version> at HEAD with `--target` when absent; a rerun on the tagged commit does nothing. A version released at another commit fails the run: the merge brought no new VERSION, which CI's check on the PR refuses first. A tag never moves. Private repo, private releases.
- CI, .github/workflows/ci.yml on push and pull_request (windows-latest from 0.01.03, plans/m1.md D19; steps in bash; actions pinned to release tags): `uv sync --frozen`, ruff check and format, pyright, `optilux test --serial`, `optilux verify docs`, `pack release --check --no-remote --ref R`, `pack build --ref R`, the zip as an artifact. R is HEAD on a push and HEAD^2, the PR head, on a pull request, whose checkout is GitHub's synthetic merge commit. `--no-remote` skips only the GitHub release lookup (gh has no login there); origin's tags and main are read with git. The in-game compile check runs locally through the mod.


## Hooks and guards
Bodies in optilux/hooks.py, run by the venv's python as `python -m optilux.hooks <name>`; .githooks/ holds the sh shims (`git config --local core.hooksPath .githooks`), .claude/settings.json the Claude Code hooks and allow rules. Inert outside this repository.
- Claude Code hooks:
  - PreToolUse git guard (Bash and PowerShell; exit 2 blocks): a push with `--force`, `-f`, `--force-with-lease`, `--mirror` or a `+` refspec; `--no-verify`, `commit -n`, `-c core.hooksPath`; a push naming main, `--all`, or a bare push on main; an attribution token in a commit's message, trailer or author. Passes `git push -u origin m<N>` and `gh` through a variable;
  - PostToolUse post_edit (Edit, Write): ruff on an edited .py, `verify docs` on an edited .md; findings return as context, never a block.
- Git hooks:
  - commit-msg: the commit rule of Git (no milestone such as M2, phase M2.P01, tag v0.2.0, date or the version in VERSION in the subject), no attribution token (Co-Authored-By, Anthropic, Generated, Claude; the tool name "Claude Code" passes unless "by", "with" or "via" precede it). The shim runs the working tree's optilux/hooks.py, so a commit that changes the rule is judged by it;
  - pre-commit: ruff on staged .py, `verify docs` when a .md is staged; similarity on shader changes from M3, when the tool exists.
- ALC lessons:
  - Never hash files another tool rewrites (Prism rewrote instance.cfg and stopped a run at its gate).
  - Pre-write permission allow rules before an unattended run (auto mode blocked settings edits and a hash re-record).
  - A guard that refuses `gh` through a variable or `git push -u` is pure friction; drop it.

## Testing
- `optilux test` runs pytest in parallel (pytest-xdist's auto: a worker per physical core, psutil being installed; optilux/verbs/test.py has the timing); `--serial` runs one process, as CI does (ci.yml has its runner's timing). The suite passes both ways.
- Unit tests for (reconciled with M1's tests in 0.01.12):
  - the run record: identity, the run spec, the views file, the run's status and the acceptance items' verdicts on fakes;
  - platform pins (sha512, sha1, sha256), install and the launch spec;
  - the launch: the gate, the pre-launch files and their read-back, the command and its check, the join, quit and end;
  - the mod protocol: commands.json against mod-protocol.md's table, the client against the protocol fake (a socket pair and a real named pipe), the mod's JUnit tests (mod.md#11-build-and-test);
  - PresentMon's start, stop and CSV, and A9's match;
  - the workflow verbs and hooks; doc limits;
  - from M2 and M3: statistics (bracketing, thresholds, geo-mean verdicts) and similarity fingerprints.
- Not unit-tested: the glue that drives the game or Windows (RunHost's calls, the items' request sequences); the acceptance runs cover it.
- Runtime validity checks in every session (measurement.md#validity) are the main safety net.
- A test that needs git builds a throwaway repo in a temp dir and checks it is not this repo before writing (ALC rule).
- Static checks: ruff with pyproject.toml's rules and pyright basic over optilux/, both in CI; javac -Xlint:all,-classfile -Werror on the mod (classfile: Minecraft's Guava jar names annotations absent from the classpath). A hit is fixed, or suppressed on its line with the reason; tests/ may assert (S101 off there).
- Coverage, when a QA pass asks: `uv run coverage run -m pytest tests`, then `uv run coverage report` (branch, optilux/); code run in a subprocess (the hooks' entry points) shows as missed.

## Code conventions
- uv, installed by pip into the user's Python 3.12 (roadmap.md#decisions D1): .python-version pins Python 3.12, pyproject.toml pins the dev tools exactly, uv.lock locks every dependency with hashes; one `.venv`; ruff format and lint; type hints on public functions.
- No absolute paths in code: paths derive from the repo root or config/.
- Windows APIs via ctypes. PowerShell only where Windows forces it.
- JSON for configs, inputs and records; the one exception is pyproject.toml, where uv, ruff and pytest read their settings. UTF-8 without BOM; LF. Git for Windows here sets core.autocrlf=true system-wide, so M0's first commit adds .gitattributes (`* text=auto eol=lf`); without it, hashed files change on checkout.
- Every constant carries its reason or evidence at its definition (no voodoo constants).
- Errors name the fix; scripts handle failures rather than leaving them to the agent.
