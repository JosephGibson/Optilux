# Handoff
Status: Phase 0 closed 2026-10-06, run unattended on the user's approval of the same day; next M0, whose first prompt (prompts/m0.md) is handed out once the user has approved plans/m0.md.

## Contents
Outcome · Produced · Approvals recorded · Critique · Open questions · First command of M0 · Time

## Outcome
- Phase -1 closed: the spike's results stand as written in platform.md#mc-263-verified; spike-plan.md and v0-coverage.md deleted; every cite to them rewritten (the AGENTS.md Docs index, measurement.md#baseline-suite, config/tools.json); a grep over docs/, AGENTS.md and config/ finds none.
- Phase 0 exit (design.md#6-milestones): docs/roadmap.md and the M0 prompt set exist, with the plan template and the first hand-made plan.
- Checks at the close: every .md under its cap (platform.md the tightest, 190 bytes of margin after four bullet lists were compacted to make room for the approval tags); LF without BOM everywhere; `## Contents` after the Status line in every file over 100 lines; 215 path#heading cites resolved by a scratch check whose rule 0.00.02 adopts (path relative to the citing file's directory, then docs/, then the repo root; slug lowercase, every character other than letters, digits, spaces and hyphens dropped, spaces to hyphens; fenced blocks skipped).
- No git, no code, no launch; nothing under runtime/ touched; no question asked mid-run.

## Produced
- docs/roadmap.md (new): rules with the sizing rule and tripwire; M0 in detail, seven phases each with change, tests, exit and estimate (7.8 h agent in all); M1-M6 one line each with provisional phase lists; the eleven spike findings and the runtime/ question assigned to a milestone and phase; twelve decisions with owners; estimates and the tripwire baseline.
- docs/templates/plan.md (new): the strict ten-section plan template and its rules.
- docs/plans/m0.md (new): the first hand-made plan; 29 premises, each verified at its source on 2026-10-06 (commands on this machine, the docs, GitHub's, gh's, git's and uv's documentation); one open (P11, below).
- docs/prompts/m0.md (new): seven phase prompts and a Resume prompt, in the format `optilux status` will parse; the first holds the git bootstrap exactly as workflow.md#git says and stops for the user's go before the first push.
- AGENTS.md: Status line; the Docs index gains roadmap.md, plans/, prompts/ and templates/ and loses the spike-plan, v0-coverage and Planned lines.
- docs/design.md: Status line; section 6 no longer says that Phase 0 writes the roadmap, nor "(now)" on Phase -1.
- docs/platform.md: the Status line and the "mc-26.3 verified" intro carry the approval; the dev-tier quit bullet carries the accepted exit code; four bullet lists compacted into sentences, nothing dropped but one IP address and one timing aside.
- docs/measurement.md: the display line cites suite.json's optionsTxt block and platform.md#install-and-launch instead of the deleted spike plan.
- config/suite.json: optionsTxtWhy records simulationDistance 12 as the identity value. config/tools.json: the PresentMon pin cites platform.md#mc-263-verified.
- Deleted: docs/spike-plan.md, docs/v0-coverage.md.
- docs/handoff.md: this file, the previous one replaced in full.

## Approvals recorded
Each tagged (user, 2026-10-06) where it lands:
- the spike's results approved as written: platform.md Status line and "mc-26.3 verified" intro;
- simulationDistance stays 12: config/suite.json display.optionsTxtWhy; roadmap.md#decisions D11;
- the dev-tier exit code -8 accepted as known, no shutdown step: platform.md#mod-tiers dev bullet; roadmap.md#findings-assigned F7 and D12;
- the deferred batch is M1's first dev session: roadmap.md#m1-to-m6 (M1 P6) and F6.

## Critique
One /critique run on roadmap.md and plans/m0.md together (artifact mode, gpt-6.1-sol, effort xhigh, 257 s); the raw critique stayed in the session's scratchpad, outside the repo. Five findings, every one verified at its source and folded in; none rejected.
1. [HIGH] Nothing in the release workflow built the zip, while workflow.md#release says the release path builds it. Folded: `pack release` runs `pack build` first (roadmap and plan 0.00.06, prompt 0.00.06).
2. [HIGH] On a pull_request event the checkout is GitHub's synthetic merge commit, whose subject carries no version, so the version check would fail on the PR (GitHub's events reference, plan P27). Folded: `pack release --check --ref HEAD^2` on pull_request events with a full-history checkout; CI must be green on the PR as well as the push (plan D16).
3. [HIGH] `permissions: contents: write` does not authenticate `gh` on a runner (gh's environment manual, plan P28). Folded: release.yml sets GH_TOKEN from the workflow token.
4. [MEDIUM] `gh release create` tags the default branch's head at execution time, not the checked-out commit (plan P13). Folded: `--target <HEAD sha>`, and an existing tag must resolve to HEAD.
5. [MEDIUM] The git guard missed a `+refspec` push and a bare `git push` while on main (git-push manual, plan P29). Folded: both refused, with fixtures (roadmap and plan 0.00.03, prompt 0.00.03).

## Open questions
Logged, not asked:
- The account's GitHub plan (Free or Pro) is not readable through the token; roadmap.md#decisions D5 (ubuntu-latest) holds on either; the user may name it in plans/m0.md P11.
- plans/m0.md section 10 is a draft until the user has read this report; the prompts are handed out after that approval (workflow.md#running-a-milestone).
- optilux-plan is scheduled for M1's last phase (D8), after two hand-made plans, rather than inside M0; the user may move it.
- The M1-M3 figures in roadmap.md#estimates (16, 10, 10 h) are rough tripwire placeholders until each plan is written.
- docs/research/ left the AGENTS.md index with the Planned line, as asked; shader.md#research still defines it; it returns to the index when the first research doc lands.

## First command of M0
After approving plans/m0.md: open a Claude Code session in C:\Projects\Optilux and paste the fenced block under "## 0.00.00 Repo bootstrap" in docs/prompts/m0.md. It makes the first commit, creates the private repository and stops before `git push -u origin main` for your go.

## Time
- Agent: about 35 min from the first read to this handoff (reading the set and verifying premises, the edits and four new docs, the critique and its fold-in).
- Machine: the critique's 257 s; nothing else ran.
