---
name: optilux-bench
description: Runs one Optilux run spec exactly as written and summarizes its record. First `uv run optilux run <spec> --check`; a refusal is reported with its fix and nothing launches. Then the launch announcement (tier, world, mode, launches, purpose), `uv run optilux run <spec>` with nothing beside it, and the summary from `uv run optilux report <run>` and `uv run optilux compare <run>`, their lines repeated as printed. Also summarizes an existing record by its run name without launching anything. Use when the user types /optilux-bench, asks to run or check a run spec, a benchmark, a measurement or an acceptance session (A8, A11, M1's items), to measure a shader change against the baseline, or to summarize, judge or report a run under results/records/. Never edits or fixes a spec, reruns a refused or failed run unasked, runs calibrate or commits.
---

Low freedom: the commands below, exactly and in order; stop at the first refusal or failure. `<spec>` is the spec file's path (a .json), `<run>` its `name` (docs/run-record.md#run-spec); a bare run name, not a path, is a record to summarize, nothing to run or look for. One spec per invocation. A spec of kind calibration is the `calibrate` verb's (hours of launches): say so and stop.

## Run a spec
1. `uv run optilux run <spec> --check`. Exit 1 is a refusal: quote its line (`optilux run: <problem>; fix: <fix>`), say that nothing launched, and stop. The fix is the user's: never edit the spec, write a corrected copy, check another spec or run one.
2. It holds: announce the launch where the user sees it, filled from the spec and the check's lines, each bracket only where it applies:
   `Launching <run>: tier <tier>, world <world>, <kind>[ in <mode> mode], variants <ids>[, items <items>][, calibration <its first 24 chars>... | , calibration null: no verdicts], <n> launch(es)[ and A1's own]. Purpose: <notes, or none given>. The game blocks input while it runs[; A2 and A7 send it input]. Leave the machine alone until it ends: no input, no remote-viewer window.`
   `<n>` is one, or the `split:` line's count. Write it as reply text before step 3's call, never only in thinking, and make its first and last sentences that call's `description`: the tool row the user sees. A run with a mode waits up to 10 min for an idle machine and a GPU no other process uses, and a focus change ends it invalid (docs/measurement.md#session).
3. `uv run optilux run <spec>`: with A2 or A7 among its items (they send the game input) in the foreground with the timeout at 600000 ms; else with `run_in_background` true, then wait for its exit notification without polling. Run nothing beside it: no test, no other command, no other launch. It restores the world, launches, runs the session and quits by itself (a run with a mode also waits for the idle machine and holds the displays on); never send the game input or stop it. Its last line: `optilux run: <status>; results/records/<name>.json: <outcome>[; <reason>][; rerun to resume <session> at this part]`, or a refusal `optilux run: <problem>; fix: <fix>` with no record.
4. Anything but status ok (a refusal, no such line, a traceback): quote the last lines and stop. Ok: summarize `<run>` as below.

## Summarize a record
1. `uv run optilux report <run>`: the record's lines (the status and reason, a split session's parts, the calibration, the verdicts as recorded, each acceptance item's pass, FAIL or waits, the captures valid and each view with an invalid one and its flags), the last naming the page it wrote under results/raw/. A part's name is refused, naming its session: summarize that session if results/records/<session>.json exists, else quote the refusal and stop.
2. `uv run optilux compare <run>` when report's lines name a calibration (not null) and the status is ok: the verdicts re-judged from the captures, each view's delta and threshold, the twin monitor, A8's and A11's pass, FAIL or waits, and, when the record holds verdicts of its own, whether they are the same. A refusal is quoted, never worked around.
3. The summary: one or two sentences with the outcome first (the status; each candidate's verdict and geo-mean delta; the twin; each item's pass, FAIL or waits; the captures valid), then report's and compare's lines verbatim in one text block. Every number as printed; nothing from memory, docs, the handoff or other records. An interpretation, if any, comes last and says it is one.

## Never
- Launch without step 1 holding and step 2's announcement, or beside another game, a test run or another launch.
- Edit, copy or fix a spec; run `calibrate`; commit a record (the phase's prompt does).
- Rerun a refused, failed or invalid run unless the user asks. A split session's spec run again resumes at its first part not ok, which `run` prints part by part; its announcement says it resumes.
- Change a system setting.
