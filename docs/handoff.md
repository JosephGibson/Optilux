# Handoff
Status: M1 in progress: 0.01.01 (the M1 plan and prompts) is done; the next prompt is 0.01.02, install and the launch spec, which /optilux-next prints.

## Contents
0.01.01 Plan M1 · Open questions · Time · Next

## 0.01.01 Plan M1
- docs/plans/m1.md approved by the user (2026-10-06): nine phases 0.01.02 to 0.01.10, 21 h agent against the roadmap's rough 16 h; 39 premises verified at their sources the same day; decisions D17-D26, two of them the user's and both closed on the recommendation: D20 (Mojang moved asset index 34 on 2026-10-06; `install --refresh` once in 0.01.02, the new spec committed) and D26 (A9 judged on a swap-return stamp next to the render-HEAD one; mod.md#12-acceptance changes in 0.01.09). D23 names the stop if the spike's world is gone.
- Found at the sources: only the asset index changed in Mojang's republished 26.3 JSON (P6); jna-platform 5.17.0 lacks FILE_FLAG_FIRST_PIPE_INSTANCE, QueryPerformanceCounter and the SDDL converter (P12, D21); gradlew.bat needs JAVA_HOME (P37); a DPI-unaware process reads 2560x1440 on the 4K panel (P32, D22); a CPython named-pipe round trip with the server-pid check passed (P14); Loom's newest release is 1.18.2 and Gradle 9.1+ runs on Java 25 (P17, P18).
- /critique (gpt-6.1-sol, artifact mode, 212 s): five findings (tier contamination of game/mods/, missing launch modes for A1 and A7, A9's unestablished stamp relation and matching rule, A7 without a positive control, the wrapper's JAVA_HOME), every one verified at its source and folded in (plan section 10); none rejected.
- Records: roadmap.md M0 shrunk to one line per section, M1 expanded with its phases, findings F2-F6, F8, F9, F11 and Q1 cite their phases, D8 moved to 0.01.10, the tripwire recomputed (M0-M3 48.8 h, trip 97.6 h); CHANGELOG's 0.01 entry rewritten; docs/prompts/m1.md written, nine prompts plus Resume.
- `optilux status` gained the plan-phase case: with the prompt set written but not committed, the next phase (0.01.01) precedes the set's first (0.01.02), and the cycle now yields the Plan prompt instead of a gap problem; a set starting any later is still a gap (workflow.md#running-a-milestone, one test added).
- Checks at the commit: 169 tests green, ruff clean, verify docs 0 violations; CI on the m1 push follows the commit.

## Open questions
- P34: whether runtime/mc-26.3/game/saves/spike still exists; the user was unsure, and this phase read nothing under runtime/. 0.01.03's first launch checks and stops if it is absent (plans/m1.md D23).
- The creation rule's evals for optilux-next and optilux-release (workflow.md#skills) are still pending; 0.01.10 runs them.
- `optilux status` reads origin/main's version only once it is fetched (unchanged from 0.01.00).
- Window.updateDisplay as the swap-return target (D26) is read in the pinned jar in 0.01.07; if the swap sits elsewhere, that phase names the real target.

## Time
- 0.01.01: about 1.6 h against the standing Plan prompt's 1 h; premise verification across about twenty sources and the critique's 3.5 min dominated. M0: about 3.3 h against 7.8. M1 so far: 0.01.00 about 0.5 h (unplanned) plus this phase. Tripwire standing (roadmap.md#estimates): M0-M3 48.8 h estimated, trip at 97.6 h; actuals about 5.4 h.

## Next
/optilux-next prints 0.01.02 install (implementation, size L, 2 h): minecraft-launcher-lib and psutil locked, `optilux install` with the file store and the launch-spec check, `install --refresh` once for the moved asset index, commit `0.01.02: optilux install and the launch-spec check.`
