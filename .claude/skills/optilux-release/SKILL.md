---
name: optilux-release
description: Runs the Optilux milestone release checklist exactly as written, in two halves. Before the PR it runs `optilux verify docs`, `optilux test` and `optilux pack release --check`, pushes the milestone branch, then runs `gh pr create` with the one-line title `0.MM: <summary>` and an empty body and watches the PR's checks. After the user's rebase merge it watches the release workflow and shows the release v<version> with its optilux-<version>.zip. Use when the user types /release or asks to open the milestone PR, release the milestone, or check the release after the merge. It stops at the first failing step and never merges, tags or creates a release itself.
---

Low freedom: run exactly these commands, in order, from the repo root on the milestone branch m<MM>. Stop at the first step that fails and report its output and the fix it names. Never work around a failure.

Before the PR:
1. `uv run optilux verify docs`
2. `uv run optilux test`
3. `uv run optilux pack release --check`: every line must be `ok:`. If its only problem is "no branch tip on origin", run step 4, then repeat step 3.
4. `git push origin m<MM>` (prints "Everything up-to-date" when each phase was pushed after its commit).
5. `gh pr create --title "0.MM: <summary>" --body ""`, with the title that the milestone's last prompt names (M0: `0.00: Foundation.`). Add no body and no other text. Print the PR URL.
6. `gh pr checks --watch` until the PR's CI run is green.
7. Stop. The user merges with Rebase and merge. Never merge yourself.

After the user's merge:
8. `gh run list --workflow release.yml --branch main --limit 1`, then `gh run watch <id> --exit-status` with the run id it lists.
9. `gh release view v<version>`, where the version is the prefix of the newest commit on main. It must list optilux-<version>.zip. Print the release URL.
