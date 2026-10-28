# Handoff
Status: the latest stop: M4.P03 measured runs of the Optilux pack done on branch m4, committed and pushed: `optilux` and `optilux@<ref>` measured as a measurement run's baseline or candidate, each zip built and L0-gated, its twin a byte copy. M4.P04 is next.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P03
- The Exit of M4.P03 (docs/plans/m4.md) held in this session (2026-10-27 and -28, ADT), shown:
  - m4-optilux-budget-1, a budget run (heap true, calibration null) on quick mode's views: `optilux` (the working tree's zip, id tree) the baseline, `optilux@HEAD` (2caf3a1's, id head) the candidate, the twin a byte copy of the baseline's zip; "optilux run: ok; results/records/m4-optilux-budget-1.json: 17 of 18 captures valid", exit 0, 14:18:23 to 14:21:35 ADT, one launch, 20 reloads;
  - every capture with its numbers (GPUBusy, FrameTime, its p95; none unsummarized); capture 16 (end_dragon, the baseline) flagged `cut`: "2814 rows from frame start's row to frame end's, 3035 frames", PresentMon short of rows at about 1,210 fps (measurement.md#validity's row loss); no decision reads a budget run's captures;
  - each variant's zip hashed: tree optilux.zip, head optilux-2caf3a16c0a5.zip and twin optilux-twin1-optilux.zip, all sha512 da6e04533b8df16f... (a clean tree: one set of bytes), each with its `build` (the twin's its baseline's) and its `l0` summary (48 builds, glslang 16.6.0), the twins' copy checked against the built sha512; every journaled file gone after the quit ("kept": []), shaderpacks/ holding only the reference pack.
- Medians as measured (budget run, no verdict): forest_noon 1.24 ms GPUBusy, nether_crimson 1.00-1.02, end_dragon 0.82-0.83; heap after GC 546.0, 705.3, 750.9 MiB at 2, 10, 20 reloads; the game's private bytes +348.4 MiB and its GPU memory +306.6 MiB per reload (the driver's leak: the cap of 20 stands).

## What was built
- record.check_variants (D80): `optilux` and `optilux@<ref>` (record.optilux_build, the ref resolved at the check) as a measurement run's baseline or candidate, profile null, options as text; a calibration run's or A8's and A11's refused naming the reference pack; the passthrough's rules unchanged; each checked variant carries `build`. check_spec's docstring as built (the deterministic set, visual and dump runs, the Optilux pack).
- The measured session: run.py's prepare builds and gates a measured run's zips (variant_zips, `check L0` in a child, as a visual run's); measured_before writes them (write_zip), then copies the twins from the baseline's zip on disk and holds them to its built sha512; the variants' sha512 by their source (zip_pins, measure.variant_sha512), `build` and `l0` beside (zip_build); measure.zip_name and pack_file name the files (zip naming moved from run.py); `run --check` prints a measured run's zips with their sha512 ("measured: <reloads> on <views>; zips: [...]", `zips` and `planned` in --json).
- Help strings (2caf3a1): `check` names L0-L3, `run` every kind.
- Docs: run-record.md#run-spec (the visual paragraph's Optilux rules cut to the measured one's, 24 bytes left after #split-sessions' line below), measurement.md#session step 6 (step 7's duplicated split rules cut first, 18 bytes left), CHANGELOG.md's 0.5.0 bullet.

## Review
The reviewer agent on the record and session diff found no verdict between different builds, no twin unlike its baseline and no gate skipped; five low findings, each read at its source:
- F1, fixed: a split session's next part was checked for identity alone, so a working tree or ref moved between parts launched every remaining part before the session record refused them; run_split now holds each part's zips to the first ok part's (zips_moved) and ends the session invalid before launching; tested; run-record.md#split-sessions as built.
- F3 and F4, fixed (older than this phase, in measure.py, which moves identity now and is frozen after M4.P09): make_twins and make_passthrough journal their part files before writing them, and refuse a settings file already beside them.
- F2, logged: two commits sharing their first 12 hex digits would share one zip name and so one zip (variant_zips dedups by name), as visual runs already did; about 2^-48 a pair.
- F5, kept: `run --check` prints the `measured:` line for every measured kind, `zips: []` for the reference pack's.

## Checks
- Start (2026-10-27 17:06 ADT): branch m4 clean at 8e3212b; 1068 passed; verify docs 0 violations.
- Before each commit: `optilux test` 1083 passed; ruff and pyright clean; verify docs 0 violations; verify records 395 records, 0 violations (with the new record); every changed file LF.
- CI green on c630dd5 (1065 passed, 18 skipped) and 2caf3a1 (1065 passed, 18 skipped), each watched to its end before the next push; 17d4469's and this commit's watched the same way.
- Identity: run's closure still 18 modules; the run's identity differs from quick- and full-4edbb05a's only in `harness` (measure.py first), as P4 foresaw: M4.P09 recalibrates.

## Deferred and logged
- Logged (no prompt names it): the exit's "the hello pack against itself" ran as the tree's zip against HEAD's (both build paths, one set of bytes) beside the automatic twin, rather than the baseline and twin alone.
- Logged: a measured Optilux variant's empty settings file is gone by the quit and never in `filesCleanup.removed`, as in M3's visual records (m3-closure-1); the journal names it and nothing was kept.
- Logged: the launch announcement's plan names variant ids (tree, head, twin), not their files; write_zip's lines name each file and sha512.
- install.py's docstring (P4) and AGENTS.md's and workflow.md#testing's gaps: as the last handoff left them, for M4.P12.

## Open questions
- The plan's open premises, each decided in its phase: P22's extension list and P23's RGBA16UI readback and renderStage (M4.P06), F12 through SendInput (M4.P04).
- Pinning gamma, Smooth Lighting and See-Through Leaves (research/lighting.md#open-questions): the user's.
- M5's split (research/synthesis.md#milestones): M5's plan.
- Carried from M3's handoff (git 78ea8b3): the one test that failed once in parallel, unnamed; the quick twin's +0.1782 % under the twin monitor; the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; M2's carried list (git 7dfc2fa's handoff). The available memory at the budget run: 16,084-16,233 MiB of 32,691 here, above F4's 2 GiB.

## Weak points
- The hello pack runs at 800-1,250 fps, where PresentMon loses rows (one capture cut here); M4.P06's pack should sit far lower (D82's 2.5-7.3 ms).
- The runs' displays: the session began after the user woke them (off 30 min idle on 10-27); `run` holds them only from its start.
- From the last handoff: the properties model javap-read only; the custom-uniform check run on fixtures only; L3's tolerances from GLSL's stated precision.

## Commits and time
- c630dd5 (the spec and session change, the review's fixes, their tests and docs), 2caf3a1 (the help strings), 17d4469 (m4-optilux-budget-1), then this handoff.
- M4.P03: about 0.9 h of work against 2.5 h (2026-10-27 17:06 to 17:40, then 2026-10-28 14:17 to about 14:40 ADT); about 20.6 h between waited on the user to wake the displays. Machine: 1 launch, 3.2 min.
- Tripwire: actuals about 70.2 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 6.0: P00 3.8, P01 0.6, P02 0.7, P03 0.9) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P04 RenderDoc captures (docs/prompts/m4.md), in a fresh session; its two launches send input (F12), so the user at hand to wake the displays and then hands off.
