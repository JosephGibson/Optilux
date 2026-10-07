---
name: optilux-release
description: Runs the Optilux milestone release checklist exactly as written, picking its half from the PR's state. Before the PR it runs `optilux verify docs`, `optilux test` and `optilux pack release --check`, pushes the milestone branch, then runs `gh pr create` with the one-line title `<version> <Name>: <what it delivers>` (the version from VERSION, the name from its CHANGELOG heading) and an empty body and watches the PR's checks. After the user's rebase merge it watches the release workflow, shows the release `Optilux <version>: <Name>` with its optilux-<version>.zip, and prints the block that switches to the next milestone's branch for the user to paste. Use when the user types /release or asks to open the milestone PR, release the milestone, check the release after the merge, or move to the next milestone. It stops at the first failing step and never merges, tags, creates a release or runs the switch block itself.
---

Low freedom: run exactly these commands, in order, from the repo root on the milestone branch m<N>. Stop at the first step that fails and report its output and the fix it names. Never work around a failure.

0. `gh pr view m<N> --json state,url`: "no pull requests found" (exit 1, not a failure here), start at step 1; OPEN, print its URL and start at step 6; MERGED, start at step 8.

Before the PR:
1. `uv run optilux verify docs`
2. `uv run optilux test`
3. `uv run optilux pack release --check`: its last line must end `0 problems`. If its only problem is "no branch tip on origin", run step 4, then repeat step 3. Its CHANGELOG line names the heading `## <version> <Name>` and the release title.
4. `git push origin m<N>` (prints "Everything up-to-date" when each commit was pushed after it was made).
5. `gh pr create --title "<version> <Name>: <what it delivers>" --body ""`. <version> and <Name> are those of the heading step 3 printed; <what it delivers> condenses that entry's first line. One line, at most 72 characters, no trailing period (M1's would begin `0.2.0 Game control: `). Add no body and no other text. Print the PR URL.
6. `gh pr checks --watch` until the PR's CI run is green.
7. Stop. The user merges with Rebase and merge. Never merge yourself.

After the user's merge:
8. `gh run list --workflow release.yml --branch main --limit 1`, then `gh run watch <id> --exit-status` with the run id it lists.
9. `git fetch origin`, then `gh release view v<version>`, where <version> is the output of `git show origin/main:VERSION`. Its title must be `Optilux <version>: <Name>` and it must list optilux-<version>.zip. Print the release URL.
10. `uv run optilux status`. Print the line `switch to m<N+1> first, paste:` and the commands under it in one fenced block, unchanged, for the user to paste. Never run them: they delete the merged branch.
