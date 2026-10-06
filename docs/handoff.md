# Handoff
Status: M0 closed pending merge: the six phases 0.00.01-0.00.06 are on m0, and the milestone PR awaits the user's rebase merge, which creates release v0.00.06 (URL pending).

## Contents
Outcome · Commits and time · Deviations from the plan · Deferred · Open questions · Release · First command of M1

## Outcome
- M0 exit (plans/m0.md#1-goal-and-exit), as of the 0.00.06 commit: every M0 verb runs with its tests green (`test`, `verify docs`, `status`, `milestone start`, `pack build`, `pack release`); the hooks refuse a bad commit message and a forbidden git command (0.00.03); `optilux status` printed each next prompt (0.00.04 on); the skills optilux-next and optilux-release and the agents researcher and reviewer exist.
- Pending at the commit, reported in the session's closing report: CI on the m0 push and on the PR, the merge settings (D7, after the user's go), the PR, the release.
- Checks at the commit: `optilux test` green, ruff check and format clean, `optilux verify docs` 0 violations; `pack release --check` passes on the pushed commit (run after the push, since it requires a clean, pushed tree).
- No game launch; nothing under runtime/ read or written; no system setting changed.

## Commits and time
Phase time is the interval from the previous commit, so it includes the stops for the user's answers; "n/a" where the interval spans more than the phase.

| Version | Subject | Committed (2026-10-06) | Time | Estimate |
|---|---|---|---|---|
| 0.00.00 | Repo bootstrap. | 05:20 | n/a (session start not recorded) | 0.3 h |
| 0.00.01 | Python project and optilux test. | 05:32 | 12 min | 1 h |
| 0.00.02 | verify docs and the doc-limit test. | 05:47 | 15 min | 1 h |
| 0.00.03 | Git and Claude Code hooks. | 11:12 | n/a (the 5.4 h interval spans a pause between sessions) | 1.5 h |
| 0.00.04 | optilux status, milestone start, optilux-next, agents. | 11:33 | 21 min | 1.5 h |
| 0.00.05 | Placeholder pack, pack build, license. | 11:47 | 14 min | 1 h |
| 0.00.06 | CI, release workflow, optilux-release. | 12:31 | 27 min to the commit, from 12:04 (the push, CI and the PR follow) | 1.5 h |

- Measured: about 89 min over five phases against their 6 h. Even with the two unmeasured phases at their estimates (1.8 h), M0 sums to about 3.3 h of its 7.8 h.
- Tripwire (roadmap.md#estimates): M0-M3 summed 43.8 h, trip at 87.6 h; M0 at about 3.3 h at most leaves it far from tripping. As at ALC, the estimates ran wide.

## Deviations from the plan
Each was needed for a release rule to hold; none touches a closed decision.
- `pack build --ref R` (exclusive with `--version`): on pull_request the checkout is GitHub's merge commit, whose subject has no version (P27), so `pack build` in CI failed there exactly like the check; the plan applied HEAD^2 to the check only. ci.yml passes the same ref to both.
- The pushed rule of `pack release --check` judges R, not literal HEAD: the merge commit is no branch tip, while HEAD^2 is origin/m0's. R defaults to HEAD, so the local check is the plan's.
- Added refusals: the check refuses a tag v<version> on origin without a release; `pack release` refuses a HEAD that is not origin/main's tip (run by hand on m0 it would tag a commit the rebase merge replaces, and every later release would stop at that tag), a dirty tree (the zip is built from the tree) and a release whose tag is absent (a draft). Each would otherwise fail, or ship the wrong bytes, after the merge.
- repo.git decodes git's output as UTF-8: the Windows code page misread or refused a non-ASCII subject that the Linux CI reads fine.
- optilux-release lists the release run with `gh run list` before `gh run watch <id>`: without an id, `gh run watch` needs an interactive terminal.
- README: "License: MIT (planned)" became "MIT (see LICENSE)": wrong since 0.00.05, and the README ships in the zip.

## Deferred
- optilux-release: the creation rule's three eval scenarios and the fresh-session test (workflow.md#skills); its first full use is M1's PR. It appeared in the session's skill list as soon as it was written.
- plans/m0.md keeps its Phase 0 Status line ("awaiting the user's approval; nothing built yet") and section 10 "Draft": the plan was approved before 0.00.00 and is now the record; left as written for the user to settle (no phase prompt names it).

## Open questions
- From M1 on, ci.yml's `pack release --check` on every push refuses until the milestone's `## 0.MM` CHANGELOG entry exists, while workflow.md#release asks for it only before the PR. Recommendation: each milestone's first phase writes its entry, extended as phases land; the alternative, running the check only on pull_request and main, loses the subject and pushed rules on branch pushes. M1's plan settles it before 0.01.01.
- A CI run that a newer push overtakes before its check step goes red on the pushed rule (its commit is no branch tip any more); the newer run is the one that counts.
- P11: the account's GitHub plan (Free or Pro) is still unnamed; D5 (ubuntu-latest) holds on either.
- D13: actions are pinned to release tags (checkout v7.0.1, setup-uv v10.2.0, upload-artifact v7.0.1, the newest on 2026-10-06); commit-SHA pins are stricter and are adopted if the user asks.
- After the merge, `optilux status` reports no stored prompt for 0.00.07 and names `optilux milestone start 1` as the fix; that is the expected state between milestones.

## Release
- v0.00.06: URL pending the user's Rebase and merge of the PR `0.00: Foundation.`; release.yml then runs `optilux pack release`, and `gh release view v0.00.06` must list optilux-0.00.06.zip.
- If the release run fails, `gh run view <id> --log-failed` shows why; rerunning it is safe: an existing release at HEAD is left alone, and a tag elsewhere stops it.

## First command of M1
After the release exists: `uv run optilux milestone start 1` (cuts m1 from the new origin/main with --no-track), then write docs/plans/m1.md from docs/templates/plan.md, every premise verified at its source, and the m1 prompt set. The m0 branch is deleted after the merge (workflow.md#git), on the user's go.
