# Standing prompts
Status: the Plan and Release prompts every milestone uses, printed by `optilux status` with the milestone filled in.

## Rules
- Two sections, `## Plan` and `## Release`; each holds one `- Estimate: <h> h.` line, which sizes it S/M/L/XL, and one fenced block holding the prompt.
- `optilux status` prints Plan when the milestone has no prompt set (prompts/m<N>.md), or when the set starts at the phase after the next one (the plan phase in progress), and Release when every phase of the set is done and origin/main carries another VERSION; after the merge it prints the switch block and the next milestone's Plan (workflow.md#running-a-milestone).
- Placeholders, filled in by `optilux status`: {M} the milestone's number (2), {PREV} the previous milestone's number, {PHASE} the phase the Plan prompt completes (M2.P00), {VERSION} the version the milestone ships as, the minor after origin/main's (workflow.md#release).
- Like every stored prompt, these are handed out verbatim and changed only in a commit, never per session.

## Plan
- Estimate: 1 h.

```text
Plan milestone M{M} as phase {PHASE} on branch m{M} in C:\Projects\Optilux. Take `date` first, for the report. Why: the unattended phases run from this plan and its prompts, so a premise read wrongly here costs a phase, not a line. Done when: I have approved the plan, the prompt set is written, VERSION reads {VERSION}, the checks are green and the commits are pushed with CI green. Read docs/handoff.md, docs/workflow.md (Running a milestone, Docs rules, Git, Release), docs/roadmap.md (Rules, the M{M} line under M1 to M6, Findings assigned, Decisions, Estimates), docs/templates/plan.md, and docs/plans/m{PREV}.md as the worked example (where an M0 or M1 plan or prompt differs from docs/workflow.md, as in commit lines, per-phase Status lines or 0.MM.PP IDs, workflow.md wins). No game launch; nothing under runtime/; no system settings. Branch m{M}, tests and verify docs green at the start, and the tree clean unless this run resumes an earlier one (its plan or prompt set already written: carry on from the first step not done), or stop.
1. With /optilux-plan, write docs/plans/m{M}.md from docs/templates/plan.md, section 3 first: every premise verified at its source today (a command and its output, a file, a doc heading, a URL); one that cannot be verified is marked "open:" with what would decide it. Number the phases M{M}.P01 on; each has its change, tests, exit and a `- Estimate: <h> h; machine: <launches, downloads, or none>.` line (add `Attended: <what needs me>.` where I must act), which /optilux-next turns into its size. Decisions carry an owner and a recommendation. At most 40,960 bytes, or split the milestone.
2. Close M{PREV} in the records: its roadmap section shrinks to one line. Set VERSION to {VERSION} and add `## {VERSION} <Name>` to CHANGELOG.md with the milestone's user-facing goal: CI's release check refuses a VERSION not newer than origin/main's, or one without its entry.
3. Offer me /critique of the plan; fold in each finding verified at its source, or list it with the reason.
4. STOP for my approval of the plan. Apply what I ask, then record the approval in its section 10; M{M}'s roadmap section expands from the approved plan, and the findings assigned to M{M} cite their phases.
5. Write docs/prompts/m{M}.md: one self-contained prompt per phase plus Resume, headed `## M{M}.P<PP> <title>` (workflow.md#running-a-milestone), in the form of docs/prompts/m1.md Rules: the why and a Done-when (the phase's exit) first; what to read, not AGENTS.md, which loads with the session; the change as the plan states it; the tests; a reviewer-agent pass before the commit where a launch or a mod carries the risk; the commits, each pushed with CI green, the last one with docs/handoff.md's `Last phase:` line naming the phase; the stops and the unattended defaults in one sentence; a Report that backs each claim with output.
6. docs/handoff.md overwritten: `Last phase: {PHASE}`, what passed, the open questions, the time, the next command. Tests green, ruff clean, `verify docs` passes.
7. Commit in the form of docs/workflow.md#git, one logical change per commit, the first one carrying VERSION and its CHANGELOG entry (step 2); push each; `optilux pack release --check` passes after the last push; CI green.
8. Report: the phases with their estimates and sizes, the decisions waiting for me, the time since the first `date`, and that /optilux-next now prints the first phase prompt.
```

## Release
- Estimate: 0.3 h.

```text
/optilux-release
```
