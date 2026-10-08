# Handoff
Status: the latest stop: M2's plan phase, the plan approved and amended, its prompt set written, and what the first phase starts from.

## Contents
Outcome · What changed · Checks · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P00
- docs/plans/m2.md approved by the user on 2026-10-08 as written, then amended the same day (its section 10): three facts corrected from the reviewer agent's readings, and the user's choice to build A8's and A11's code before the identity freeze. Eleven phases, M2.P01 to M2.P11, 23.5 h agent, 26-31 launches and 3-5 h of calibration sessions apart (its sections 5 and 8).
- docs/prompts/m2.md holds one prompt per phase and Resume; `optilux status` prints M2.P01's. VERSION 0.3.0 with CHANGELOG.md's `## 0.3.0 Perf loop`; M1 closed in the roadmap (one line), its open rows F15-F24 in Findings assigned. No game launch, nothing under runtime/, no system setting.

## What changed
- docs/plans/m2.md: premises P1-P21 verified at their sources on 2026-10-08, P9 open until M2.P04's first Chunky task; the reviewer agent's 23 findings on the first draft and /critique's four (gpt-6-astra, effort max: three folded in, one rejected as the user's closed decision); the user's answers D34, D35 and D52; after the approval, P20's id9, M2.P06's 68 and 44 reloads (measurement.md#session's budget; 90 and 58 counted three variants), M2.P11's 1-2 launches, and A8's and A11's code moved into M2.P05 (the runner admits them) and M2.P07 (their verdicts, 3 h), M2.P10 only running them (1 h; user, 2026-10-08).
- docs/roadmap.md: D34; the M2 perf loop and M2 phases sections from the plan, each phase's estimate line as the plan's; each finding that lands in M2 names its phase, F17's jar change M3's (D48), E5 outside M2 (D53); Estimates with M2's 23.5 h and the tripwire recomputed.
- docs/prompts/m2.md: in the form of prompts/standing.md#phase-prompts.
- Before this run resumed, on the branch: VERSION, the CHANGELOG entry and the phase-prompt form in one commit; M1's open rows moved into Findings assigned in the next.

## Checks
- `optilux test` 449 passed; ruff clean; `verify docs` 0 violations: the plan 40,155 of 40,960 bytes, the prompt set 40,671, the roadmap 28,926.
- The prompt set parses into M2.P01 to M2.P11 and Resume, each first line in the standing form, each Report's estimate the plan's; every `path#heading` cite in it, fenced ones included, resolves.
- The reviewer agent read the roadmap's expansion (14 findings) and the prompt set (18) against the plan, then the fixes (8): each fixed, or left below with its reason. The A8 and A11 amendment and the fixes of that last round were not read again.

## Open questions
- P9: whether Chunky's end line reaches latest.log in singleplayer and whether a task runs under /tick freeze; M2.P04's first task decides, D45 plans both ways.
- F10's startup call to api.minecraftservices.com may close before the join, where M2.P05 records the game's connections (unverified).
- M1's handoff questions are now phases of the plan: the machine to itself (D42), a killed run's record (D41), the time split and A9's capture (D48), c1-c5 (D36-D39, D49, M2.P05), the live world (M2.P04), the record budget (D51), the heap per reload (D43). The red CI runs of two M1 commits got no rerun: m1 is gone from origin, and main's CI is green.

## Left alone
- roadmap.md keeps M0's second section, M0 phases, against the rule that a closed milestone shrinks to one line: it predates this phase.
- M2.P11's prompt puts its docs before its review, against standing.md's order, so that the review reads them.
- The Resume lets a record under results/records/ made after a phase's last fix stand for a launch's exit: standing.md asks for a rerun because runtime/ leaves nothing in the tree, which a committed record does not share.

## Weak points
- Margins: the prompt set 289 bytes, the plan 805; AGENTS.md 12, platform.md 21, mod.md 110 and workflow.md about 1,100, which M2's phases must cut before they add (their prompts say so).
- M2.P10 rests on M2.P05 and M2.P07 keeping A8's and A11's code within the frozen identity; its first step checks `run --check`'s identity against the full calibration's and stops on a difference.

## Commits and time
- This phase: two commits before the resume, then the amended plan with the roadmap's expansion, the prompt set and this handoff, each pushed alone with CI green.
- The first run from about 00:09 ADT (the switch to m2) to about 01:40 (the draft's last save), its end inferred; this run 02:09 to 03:48 and 10:57 to about 11:20, the A8 and A11 decision stop between them not counted. M2.P00 about 3.5 h against the Plan prompt's 1 h.
- Tripwire: M0-M3 summed 69.3 h, the trip at 138.6 h; actuals about 27 h (M0 3.3, M1 20.3, M2.P00 about 3.5).

## Next
/optilux-next prints M2.P01's prompt: Identity before calibration, 2 h (L), no launch.
