# Handoff
Status: the latest stop: M2.P11 done, M2's last phase: optilux-bench is built and its three evals pass, eval 3 on its third launch (m2-bench-skill-2, the user's go) with the announcement in the run call's description. Next: the Release prompt.

## Contents
Outcome · M2 as built · Evals · What changed · Checks · Review · Choices · Open questions · Commits and time · Next

## Outcome
Last phase: M2.P11
- Exit holds: the three evals pass (Evals); `optilux status` prints the Release prompt after the last push (Checks).
- The first run stopped short (git 1e0f25f's handoff): eval 3 with the skill ended ok and summarized as recorded, but announced only in thinking. The skill's fix, the announcement as the run call's `description`, passed with `run` denied, then live in m2-bench-skill-2 on the user's "Continue to close out this milestone" (2026-10-16), a third quick launch against the prompt's one or two.
- Launches: 3, each announced: m2-bench-noskill-1 (15:00:35-15:03:59 ADT), m2-bench-skill-1 (15:12:16-15:16:09), m2-bench-skill-2 (18:17:11-18:20:47); quick mode on bench_263, 18 of 18 captures valid each. No section 7 stop fired.

## M2 as built
- bench_263's snapshot snapshots/bench_263, tree sha256 65e7ae73..., 116 files (m2-bench-skill-2's identity).
- Heap 6144 MiB (config/java/bench.json), capture.reloadCap 20, 2 twins a session, 10 sessions a mode (config/suite.json; M2.P06, the driver's reload leak).
- CPU floors per view: measurement.md#validity (m2-survey-1 and -2).
- Calibrations: quick-95d96878... (cal-quick-95d968784730-1 to -10) and full-95d96878... (cal-full-95d968784730-1 to -11 but -5), 20 nulls each, every threshold the 0.5 % floor (measurement.md#calibration). Shadows off: quick -10.69 % (m2-shadows-quick-1), -10.79, -10.75, -10.67 % (M2.P11's three); full -12.33 % (m2-shadows-full-1). The quick twin monitor: 0 of the last 4 twins beyond.
- The timers: A8 passed (m2-a8-2), A11 failed (m2-a11-1), dropped from use (design.md#8-open-decisions E3).

## Evals
Fresh `claude -p` sessions (the extension's 2.1.300 binary; 2.1.301 for m2-bench-skill-2), auto mode, edits, commits, pushes, PRs and releases denied. Streams: results/raw/skill-evals/bench-*.jsonl; specs: results/raw/skill-evals/bench/ (both ignored). The same prompt without and with the skill.

| Eval | Without the skill (Opus 5.5 high) | With it |
|---|---|---|
| 1: shadows-quick.json, quick mode naming the full calibration | pass: the refusal and its fix reported, nothing launched; it also wrote a corrected copy to its scratchpad with sed and checked it; 7 turns, $0.52, 32 s | pass: quoted and stopped; Opus 4 turns, $0.19, 9 s; Sonnet 5.5 xHigh 4 turns, $0.10; the final text on Opus 4 turns, $0.20 |
| 2: "Summarize the benchmark run m2-a8-1." | not equal to compare's: built from docs/handoff.md and the record; A8 waits, the ten views' deltas and forest_noon's presentMode right; the session's and timers-on's inconclusive and the twin monitor missing; 6 turns, $0.34 | pass: report's and compare's lines verbatim; Opus 5 turns, $0.24; Sonnet 5 turns, $0.12; the final text on Opus 5 turns; `/optilux-bench m2-shadows-full-1` on Sonnet 3 turns once a bare run name was ruled a record (6 turns and three searches before) |
| 3: one quick run of shadows off | m2-bench-noskill-1: ok, accept -10.7903 %, twin -0.0486 % inside; its summary equals the record (the twin's geo-mean and the monitor left out); `run` in the foreground at 600000 ms; not announced; 8 turns, $0.37 | m2-bench-skill-1 (the first text): ok, accept -10.7540 %, twin +0.0593 %, summary verbatim, announced only in thinking: fail. m2-bench-skill-2 (the committed skill): pass: the run call's description "Launching m2-bench-skill-2: tier bench, world bench_263, measurement in quick mode, variants baseline, shadows-off, calibration quick-95d968784730845383..., 1 launch. Leave the machine alone until it ends: no input, no remote-viewer window.", reply text after it; ok, accept -10.6749 % (forest_noon and end_dragon beyond), twin +0.0663 % inside; summary report's and compare's lines verbatim, compare "the same"; $1.02 |

- Before the live retest, with `run` denied (manual mode, prompts none, only `--check`, report and compare allowed: no launch possible): the description carried the announcement on Opus and on Sonnet with the final text.
- The reply text before the launch call went into thinking in all eight tries under the skill (Opus 7, Sonnet 1), the template's included, so the description is the announcement the user sees.
- Probe: a `claude -p` session waits for its background command's notification and resumes (bench-probe-background).
- The evals' streams cost about $7.2.

## What changed
- b1b95c3: `report <run>` prints the record's summary beside its page (optilux/verbs/report.py `summary`; tests/test_compare.py, three tests). report.py is outside `harness`: m2-bench-skill-1's 17 modules hold no verbs/report.py, and `run --check` matched the quick calibration after the change. run-record.md#comparison, design.md's interface row and CHANGELOG with it.
- 79a1243: SKILL.md (low freedom, 25 lines, description 847 characters); m2-bench-noskill-1 and -skill-1; workflow.md#skills (Status, the row, the evals, when built); AGENTS.md's .claude/ line ("the PR checklist" cut to "the PR"); design.md's Status and Experts lines; measurement.md#calibration's M2.P11 numbers (cut: Session step 7's full-mode sums, the quick sessions' names); CHANGELOG's skill bullet.
- 530c8ac: CHANGELOG's 0.3.0 entry completed; roadmap.md#findings-assigned: 15 of M2's cells marked landed with their phases (F1, F4, F6, F8, F10, F13-F16, F18-F23), each read in its phase's handoff.
- 1e0f25f: the first run's stop handoff.
- cb3b029: m2-bench-skill-2; workflow.md's eval line; measurement.md's third run (cut: Session step 1's "run names are single-use", its "One launch per run name" saying it).

## Checks
- First start (14:52 ADT): branch m2 clean at 2927963, pushed; 790 passed; verify docs 0 violations. Second (18:16): clean at 1e0f25f, pushed; 793 passed; verify docs 0 violations; m2-bench-skill-2's `--check` matched the quick calibration.
- Before the commits: 793 passed; ruff, ruff format and pyright clean; verify docs 33 files, 0 violations (AGENTS.md 8 bytes left, measurement.md 20, workflow.md 161); verify records 223 records, 0 violations (the three acceptance records over 200 KB, reported).
- CI green on each push, each watched to its end before the next: b1b95c3 (run 38948873400), 79a1243 (38949398107), 530c8ac (38949920162), 1e0f25f (38950617070), cb3b029 (38968882083).

## Review
- The reviewer agent on the skill (against workflow.md#skills and the code): 15 findings (4 medium), each read at its source. Fixed: A1's own launch in the announcement (acceptance.a1); D42, the display hold and the focus end for runs with a mode only (run.py perform, run_session); A2 and A7, which send input, in the foreground at 600000 ms (plans/m2.md#4-ground-rules; acceptance runs took 2.3-3.5 min); the refusal line and the resume suffix after `--check` held; a part's name; a resume only when asked; input.block at every session start (session.py); items as pass, FAIL or waits; compare's same-verdicts line only when the record holds verdicts; the template's brackets for acceptance runs and absent notes; a calibration spec stops; the fixed minutes and the eval history out; D42 cited by measurement.md#session. Its fourth, eval 3 not shown with the final text, closed by m2-bench-skill-2.
- The reviewer agent on the docs and report.py (against the code and the records): 3 low, fixed: an item without a why prints no empty reason (m2-acceptance-1's `A2: FAIL`); run-record.md names every acceptance item; a test of the split, twin and unjudged lines. Every number and every landing verified, no crash on any committed record shape.

## Choices
Taken here, no plan naming them:
- `report` prints the summary (workflow.md#agent-principles, facts in tooling): every baseline rebuilt one by hand, from the handoff or the record's JSON.
- The evals ran the extension's claude (2.1.300, then 2.1.301 after the session restarted; the first try at m2-bench-skill-2 found the old path gone and exited 127 before launching); the npm install's 2.1.269 refuses Opus 5.5 and was not updated.
- The first refused spec's file name and notes gave the case away (bench-1-refused-noskill-hinted.jsonl); a neutral spec replaced it.
- m2-bench-skill-2's notes read "its run denied", written for the denied sessions; it ran. Records are never edited; this line is the correction.
- Eval 3 launched on Opus 5.5 high only; evals 1, 2 and the announcement also on Sonnet 5.5 xHigh.

## Open questions
- Why both models put the pre-launch announcement into thinking every time under the skill (eight of eight), while writing text before other calls: a model trait, Claude Code's print mode, or the skill; the interactive extension may differ.
- Carried from M2.P10: underwater's untimed work (M4's first E3 question), A11's guard for 11 views, compare refusing a failed A8 or A11 record, NoMachine and pid 2228, forest_noon's lower level, the timers' unmatched pops; M2.P09's and M2.P08's lists (git 2927963's handoff).

## Commits and time
- b1b95c3, 79a1243, 530c8ac, 1e0f25f, cb3b029 and this one.
- M2.P11: 14:52-15:56 and 18:16 to about 18:30 ADT, about 1.3 h against 1.5 h; machine 3 launches (their eval sessions 3.4, 3.9 and 3.6 min) against 1-2.
- M2: P00 about 3.5 (its end inferred), P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4 (with its first stop), the re-plan 0.35, P07 2.1 active (4 h, 1.9 of them waiting on Codex), P08 3.0 (its own handoff 2.5 active), P09 1.1 active, P10 1.6, P11 about 1.3: about 21.3 h against 26.5 h.
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 44.9 h (M0 3.3, M1 20.3, M2 about 21.3).

## Next
The Release prompt (docs/prompts/standing.md, /optilux-release), as `optilux status` prints it: verify docs, test, pack release --check, the push, `gh pr create` for 0.3.0 Perf loop and its checks; the rebase merge is the user's, then the release watch and the switch block to m3.
