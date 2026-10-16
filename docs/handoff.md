# Handoff
Status: the latest stop: M2.P11 stopped short of its Exit: optilux-bench is built and evals 1 and 2 pass, but eval 3 with the skill ended ok and summarized as recorded without an announcement the user sees. The fixed announcement is shown only with `run` denied; one more announced quick launch, past the prompt's one or two, closes it.

## Contents
Outcome · Evals · What changed · Checks · Review · Choices · Open questions · Commits and time · Next

## Outcome
Last phase: M2.P10
- Stop (the prompt's "a Done-when you cannot meet"): the Exit's "the three evals pass" fails on eval 3. Its with-skill run, m2-bench-skill-1, ended ok and its summary equals the record, but the announcement went into a thinking block, which the user does not see. The skill was fixed (step 2: the announcement's first and last sentences are the run call's `description`, the tool row). Its retest needs a third quick launch, so it ran only with `run` denied.
- Done otherwise: the skill (.claude/skills/optilux-bench/SKILL.md, low freedom, 25 lines, description 847 characters), `report`'s printed summary, evals 1 and 2 on Opus 5.5 high and Sonnet 5.5 xHigh, the docs, both reviews, the checks.
- Launches: 2, each announced: m2-bench-noskill-1 (15:00:35-15:03:59 ADT) and m2-bench-skill-1 (15:12:16-15:16:09), both quick mode on bench_263, every capture valid. No section 7 stop fired.

## Evals
Fresh `claude -p` sessions (this session's 2.1.300 binary), auto mode, edits, commits, pushes, PRs and releases denied. Streams: results/raw/skill-evals/bench-*.jsonl; specs: results/raw/skill-evals/bench/ (both ignored). The same prompt without and with the skill.

| Eval | Without the skill (Opus 5.5 high) | With it |
|---|---|---|
| 1: shadows-quick.json, quick mode naming the full calibration | pass: the refusal and its fix reported, nothing launched; it also wrote a corrected copy to its scratchpad with sed and checked it; 7 turns, $0.52, 32 s | pass: quoted and stopped; Opus 4 turns, $0.19, 9 s; Sonnet 4 turns, $0.10; the final text on Opus 4 turns, $0.20 |
| 2: "Summarize the benchmark run m2-a8-1." | not equal to compare's: built from docs/handoff.md and the record; A8 waits, the ten views' deltas and forest_noon's presentMode right; the session's and timers-on's inconclusive and the twin monitor missing; 6 turns, $0.34 | pass: report's and compare's lines verbatim; Opus 5 turns, $0.24 (its lead said "nothing could be judged", its next sentence right); Sonnet 5 turns, $0.12; final text on Opus 5 turns; `/optilux-bench m2-shadows-full-1` on Sonnet 3 turns once a bare run name was ruled a record (6 turns and three searches before) |
| 3: one quick run of shadows off | m2-bench-noskill-1: ok, 18 of 18 valid, accept -10.7903 %, twin -0.0486 % inside; its summary equals the record (the twin's geo-mean and the monitor left out); `--check` first, `run` in the foreground at 600000 ms; not announced; 8 turns, $0.37 | m2-bench-skill-1: ok, 18 of 18 valid, accept -10.7540 % (forest_noon and end_dragon beyond, nether_crimson -0.4265 % inside), twin +0.0593 % inside, compare "the same"; `run` in the background, waited for; summary verbatim; announced only in thinking; $0.64 |

- The announcement with `run` denied (manual mode, prompts none, only `--check`, report and compare allowed: no launch possible): the reply text went into thinking in all seven tries under the skill (Opus 6, Sonnet 1), the template's included; the run call's description carried it on Opus and on Sonnet with the final text (Sonnet's): "Launching m2-bench-skill-2: tier bench, world bench_263, measurement in quick mode, variants baseline, shadows-off, calibration quick-95d968784730845383..., 1 launch. Leave the machine alone until it ends: no input, no remote-viewer window."
- Probe: a `claude -p` session waits for its background command's notification and resumes (bench-probe-background).
- The evals' streams cost about $6.15.

## What changed
- b1b95c3: `report <run>` prints the record's summary beside its page (optilux/verbs/report.py `summary`; tests/test_compare.py, three tests). report.py is outside `harness`: m2-bench-skill-1's 17 modules hold no verbs/report.py, and `run --check` matched the quick calibration after the change. run-record.md#comparison, design.md's interface row and CHANGELOG with it.
- 79a1243: SKILL.md; m2-bench-noskill-1 and -skill-1; workflow.md#skills (Status, the row, the evals, when built); AGENTS.md's .claude/ line ("the PR checklist" cut to "the PR"); design.md's Status and Experts lines; measurement.md#calibration's M2.P11 numbers (cut: Session step 7's full-mode sums, the quick sessions' names); CHANGELOG's skill bullet.
- 530c8ac: CHANGELOG's 0.3.0 entry completed; roadmap.md#findings-assigned: 15 of M2's cells marked landed with their phases (F1, F4, F6, F8, F10, F13-F16, F18-F23), each read in its phase's handoff.

## Checks
- Start (14:52 ADT): branch m2 clean at 2927963, pushed; 790 passed; verify docs 0 violations.
- Before the commits: 793 passed; ruff, ruff format and pyright clean; verify docs 33 files, 0 violations (AGENTS.md 8 bytes left, measurement.md 9, workflow.md 167); verify records 222 records, 0 violations (the three acceptance records over 200 KB, reported).
- CI green on each push: b1b95c3 (run 38948873400), 79a1243 (38949398107), 530c8ac (38949920162), each watched to its end before the next push.

## Review
- The reviewer agent on the skill (against workflow.md#skills and the code): 15 findings (4 medium), each read at its source. Fixed: A1's own launch in the announcement (acceptance.a1); D42, the display hold and the focus end for runs with a mode only (run.py perform, run_session); A2 and A7, which send input, in the foreground at 600000 ms (plans/m2.md#4-ground-rules; acceptance runs took 2.3-3.5 min); the refusal line and the resume suffix after `--check` held; a part's name; a resume only when asked; input.block at every session start (session.py); items as pass, FAIL or waits; compare's same-verdicts line only when the record holds verdicts; the template's brackets for acceptance runs and absent notes; a calibration spec stops; the fixed minutes and the eval history out; D42 cited by measurement.md#session. Reported: eval 3's Exit not shown (this stop).
- The reviewer agent on the docs and report.py (against the code and the records): 3 low, fixed: an item without a why prints no empty reason (m2-acceptance-1's `A2: FAIL`); run-record.md names every acceptance item; a test of the split, twin and unjudged lines. Every number and every landing verified, no crash on any committed record shape.

## Choices
Taken here, no plan naming them:
- `report` prints the summary (workflow.md#agent-principles, facts in tooling): every baseline rebuilt one by hand, from the handoff or the record's JSON.
- The evals ran this session's claude 2.1.300; the npm install's 2.1.269 refuses Opus 5.5 and was not updated.
- The first refused spec's file name and notes gave the case away (bench-1-refused-noskill-hinted.jsonl); a neutral spec replaced it.
- The announcement retested with `run` denied, not launched: the launch budget was spent.
- Eval 3 launched on Opus 5.5 high only (the budget); evals 1, 2 and the announcement also on Sonnet 5.5 xHigh.

## Open questions
- Why both models put the pre-launch announcement into thinking every time under the skill (seven of seven), while writing text before other calls: a model trait, Claude Code's print mode, or the skill; the interactive extension may differ.
- Carried from M2.P10: underwater's untimed work (M4's first E3 question), A11's guard for 11 views, compare refusing a failed A8 or A11 record, NoMachine and pid 2228, forest_noon's lower level, the timers' unmatched pops; M2.P09's and M2.P08's lists (git 2927963's handoff).

## Commits and time
- b1b95c3, 79a1243, 530c8ac and this one.
- M2.P11: 14:52 to about 15:56 ADT, about 1.1 h against 1.5 h; machine 2 launches of 3.4 and 3.9 min against 1-2.
- M2: P00 about 3.5 (its end inferred), P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4 (with its first stop), the re-plan 0.35, P07 2.1 active (4 h, 1.9 of them waiting on Codex), P08 3.0 (its own handoff 2.5 active), P09 1.1 active, P10 1.6, P11 about 1.1: about 21.1 h against 26.5 h.
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 44.7 h (M0 3.3, M1 20.3, M2 about 21.1).

## Next
M2.P11's prompt again (or the Resume prompt): only eval 3 with the skill is left, one announced quick launch of results/raw/skill-evals/bench/m2-bench-skill-2.json (or m2-bench-skill-1's recorded `spec` named m2-bench-skill-2), passing when the run call's description announces it, it ends ok and its summary equals the record; then workflow.md's eval line, this handoff with `Last phase: M2.P11`, and the Release prompt from `optilux status`.
