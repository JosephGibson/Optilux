# Handoff
Status: the latest stop: the workflow and docs pass that closes M1, its checks, and what the first release under the new model must show.

## Contents
Outcome · What changed · Checks · Kept as history · Left alone · Weak points · Open questions · Commits and time · Next

## Outcome
Last phase: 0.01.13
- M1's 12 phases are done (0.01.02 to 0.01.13), and this pass ran after them on m1. The exit's open items: CI green on every push, which two pushes of this pass miss (Weak points; their green reruns are an open question for the user), and the release's (the PR and its CI, the merge, release v0.2.0). `optilux status` prints the Release prompt, version 0.2.0 local against 0.00.06 on origin/main.
- Commits are Conventional Commits, the version is the root file VERSION, and phase progress is this file's `Last phase:` line (roadmap.md#decisions D33; workflow.md#git, workflow.md#release). No game launch, nothing under runtime/, no system setting, no PR, merge, tag or release.

## What changed
- Tooling: hooks.py's commit-msg rule; repo.py reads VERSION at a ref (legacy subjects for refs before it); pack.py's one rule set for `--check` and the release (VERSION newer than origin/main's, no tag v<VERSION> elsewhere, `## <version> <Name>`, a pushed commit behind a later push passing); status.py reads `Last phase:`, decides Release or the switch by VERSION against origin/main's and fills {PHASE} and {VERSION} into the Plan prompt; prompts.py reads M<N>.P<PP> and 0.MM.PP alike; `milestone start` prints the version the first commit sets; release.yml runs `pack release --check` before `pack release`.
- Fixes found on the way: `mod build|test` named nothing when only a Gradle build closed the gate; test_install's JDK zip took the clock's time, so CI's serial run failed when a 2 s boundary fell between two zips.
- Docs: workflow.md (Git and Release rewritten; Agent principles and Doc ownership added), AGENTS.md, roadmap.md (D33, F12, D5 and D8 marked, M1's exit), design.md (Status, E1 closed by evidence, the 26.3 specifics outside the platform layer), the plan template, standing.md, the three skills, the researcher's cite, CHANGELOG's 0.2.0 entry, README; the 75 audit findings' corrections in measurement, run-record, platform, mod, mod-protocol, gpu-iris, shader, playbook and lessons.

## Checks
- `optilux test` 445 passed; `verify docs` 0 violations; `pack release --check` 8 ok; pyright and ruff clean.
- Tests cover the hook's rules end to end, `pack build` naming the zip from VERSION, a version tagged elsewhere refused by CI's command line and by the release, a VERSION not newer than main's, the switch block and `milestone start` taking M7 to M8 with VERSION 0.8.0 to 0.9.0, and mixed old and new history.
- The reviewer agent read the changed docs in five calls per round: 31 findings, then 9, then 4, then 3 in a narrow fourth round on the changed sentences, each fixed or rejected with its reason; the fourth round's three fixes were not read again.

## Kept as history
- Old subjects (`0.MM.PP: `, from 0.01.12.1 `0.MM.PP.N: `) on m1 and main, tag and release v0.00.06, CHANGELOG's `## 0.00 Foundation`, plans/m0.md and m1.md, prompts/m0.md and m1.md, D4, D6 and D32 as written; status and pack read the old subjects and the 0.MM.PP sets.

## Left alone
Wrong at HEAD but closed or out of scope:
- platform.md#mc-263-verified (approved as written): S5's asset index abfaa525... is 1e4e4a68... since 0.01.02; V3's "F4 re-measures on bench" was measured in m1-acceptance-10.
- roadmap.md D28 and 0.01.12 give `javac -Xlint:all -Werror`; the build has `-Xlint:all,-classfile`. The QA row's "12 s against 43 s" against test.py's 12.6 s against 39.8 s.
- measurement.md#calibration records the baseline pack unmatched (user); record.py hashes it (reading 2's c4, M2).
- Config notes: suite.json's capture `why` (M1 re-measures), modes.full's "10 views", mc-26.3.json's renderer `why` (optionKey, which no code reads).
- mod.md#11-build-and-test's first build "on a Gradle cache filled on 2026-10-05" against verbs/mod.py's "the first one downloaded 1-2 GB (0.01.04)": neither the tree nor 0.01.04's handoff settles it.
- A first-round finding that a cached dimension keeps its pipeline was rejected: m1-acceptance-10 shows sinceReload at 0 on every dimension change, a return to the overworld included.

## Weak points
- A phase's last commit must rewrite `Last phase:`; without it status shows the phase again. The Plan prompt's VERSION step is prose, caught by CI's check on the push and by `optilux status` once a phase or the release is next.
- `next_minor` cannot know the 1.0.0 milestone: M6's VERSION is set by hand.
- The subject rule refuses `M` and a number as a word; old phase IDs pass it, shaped like dependency versions.
- Two pushes of this pass stay red in CI: `feat(status)!: progress from the handoff, release from VERSION` (its check ran after the next push moved the tip) and `fix(mod): name a Gradle build that closes the launch gate` (the zip flake); both causes were fixed after them.

## Open questions
- Whether those two commits get green CI runs through two temporary branches before m1 is deleted (the user).
- A run needs the machine to itself; exclusive fullscreen on two displays minimizes on a click on the other one (M2; when runs happen is the user's).
- A run killed from outside writes no record (M2).
- The session's time split and A9's capture (M2); F4's cap (M2, roadmap.md#findings-assigned F4).
- Reading 2's c4 (the reference pack in identity) and c5 (a failed selftest ending a calibration session), with c1-c3 (M2).
- The live world against its snapshot, Gradle's other downloads, 0.01.12's review rows for M2 (M2); the flush against the entities GUI (F12, M5).
- m1-acceptance-9 and -10 run to 238 KB against the ~200 KB record budget (M2's `verify records`).
- F4's heap per reload moved from about 20 MiB (m1-acceptance-5 to -7) to about 33 MiB on the final jar (-9, -10), cause unexamined (M2's cap).

## Commits and time
- This pass: fourteen commits before this one, each pushed alone, CI green on twelve and red on the two in Weak points; this one's CI follows the push.
- 18:26 to 20:10 ADT, about 1.7 h with the decision stop. M1: about 20.3 h against 28 (18.6 h through 0.01.13). Tripwire: M0-M3 55.8 h, trip at 111.6 h; actuals about 23.6 h (M0 3.3, M1 20.3).

## Next
/optilux-next prints the Release prompt (/optilux-release). The first release under the new model must show:
- the PR titled `0.2.0 Game control: <what it delivers>`, CI's `pack release --check --no-remote --ref HEAD^2` passing (VERSION 0.2.0 newer than 0.00.06, no tag v0.2.0);
- after the rebase merge, release.yml's `pack release --check` and `pack release` green: release v0.2.0 titled `Optilux 0.2.0: Game control` with optilux-0.2.0.zip and the `## 0.2.0` entry as its body; CI's run on main passing beside it;
- then `optilux status` printing the switch block (`milestone start 2`, which names VERSION 0.3.0) and M2's Plan prompt for M2.P00.
