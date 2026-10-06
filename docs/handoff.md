# Handoff
Status: M0 closed with release v0.00.06; M1 in progress: 0.01.00 (workflow tooling) is done, and the next prompt is 0.01.01, the M1 plan, which /optilux-next prints.

## Contents
M0 closed · 0.01.00 Workflow tooling · Open questions · Next

## M0 closed
- PR #1 `0.00: Foundation.` rebase-merged by the user on 2026-10-06; the release run passed and created v0.00.06 at main's head: https://github.com/JosephGibson/Optilux/releases/tag/v0.00.06, asset optilux-0.00.06.zip, sha256 689c6994b57867c5fdf8cd77e95cc990f5c42f8cc813d31f40c6f9ef705407e4, identical in CI, in the release run and on this machine (D14).
- Merge settings (roadmap.md#decisions D7): rebase merge only. `gh repo edit` needs the owner (`JosephGibson/Optilux`); the bare `Optilux` that `gh repo view` accepts is refused.
- The user switched with the block: m1 cut from origin/main, m0 deleted locally and on origin.
- M0 time: about 3.3 h at most against 7.8 h; the per-phase table is in the 0.00.06 handoff, in git history. The tripwire (roadmap.md#estimates) is far from tripping. M0's release keeps the title `v0.00.06` (user, 2026-10-06).

## 0.01.00 Workflow tooling
Asked by the user on 2026-10-06 after /optilux-next found no M1 prompt set; each choice took the recommended option.
- `optilux status` always yields the next prompt in the cycle (workflow.md#running-a-milestone): the standing Plan prompt when a milestone has no prompt set, the phase prompt, the standing Release prompt once every phase is committed, and after the merge the switch block plus the next milestone's Plan. docs/prompts/standing.md holds Plan (1 h) and Release (0.3 h).
- A heads-up line opens the output: the kind (planning, implementation, release) and the size S/M/L/XL from the estimate (S up to 0.5 h, M up to 1.5, L up to 3, XL above); a phase's estimate is read from its plan.
- Titles: releases `Optilux <version>: <Name>`, PRs `0.MM <Name>: <what it delivers>`; the name is the CHANGELOG heading's (`## 0.00 Foundation`, `## 0.01 Game control`). `pack release --check` refuses a heading without a name.
- optilux-release picks its half from `gh pr view m<MM>` and ends after the merge with the switch block for the user to paste.
- CHANGELOG: M1's first phase wrote `## 0.01 Game control`, which settles the M0 handoff's question on CI's release check: each milestone's first phase writes its entry (workflow.md#release).
- Numbering: this phase took 0.01.00, so the plan is 0.01.01 and M1's phases start at 0.01.02.
- Checks at the commit: 168 tests green, ruff clean, verify docs 0 violations; CI on the m1 push follows the commit.
- Time: about 30 min, unplanned; no estimate existed.

## Open questions
- The creation rule's evals (workflow.md#skills) are still pending for optilux-release and for the reworked optilux-next.
- `optilux status` reads origin/main's version only once it is fetched; after a merge it says so with `git fetch origin` as the fix, and optilux-release fetches first.
- plans/m0.md keeps its Phase 0 Status line; the Plan prompt's step 2 closes M0's records.

## Next
/optilux-next prints 0.01.01 Plan M1 (planning, size M). It writes docs/plans/m1.md, offers /critique, stops for your approval, then writes docs/prompts/m1.md and commits `0.01.01: M1 plan and prompts.`
