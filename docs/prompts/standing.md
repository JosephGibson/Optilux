# Standing prompts
Status: the Plan and Release prompts every milestone uses, printed by `optilux status` with the milestone filled in (handoff.md).

## Rules
- Two sections, `## Plan` and `## Release`; each holds one `- Estimate: <h> h.` line, which sizes it S/M/L/XL, and one fenced block holding the prompt.
- `optilux status` prints Plan when the milestone has no prompt set (prompts/m<MM>.md) and Release when every phase of the set is committed and origin/main lacks the newest; after the merge it prints the switch block and the next milestone's Plan.
- Placeholders, filled in by `optilux status`: {M} the milestone's number (1), {MM} its two digits (01), {PREV} the previous milestone's number, {VERSION} the phase the Plan prompt commits.
- Like every stored prompt, these are handed out verbatim and changed only in a phase commit (prompts/m0.md#rules).

## Plan
- Estimate: 1 h.

```text
Plan milestone M{M} as phase {VERSION} on branch m{M} in C:\Projects\Optilux. Take `date` first, for the report. Why: the unattended phases run from this plan and its prompts, so a premise read wrongly here costs a phase, not a line. Done when: I have approved the plan, the prompt set is written, the checks are green and the commit is pushed with CI green. Read docs/handoff.md, docs/workflow.md (Running a milestone, Docs rules, Git, Release), docs/roadmap.md (Rules, the M{M} line under M1 to M6, Findings assigned, Decisions, Estimates), docs/templates/plan.md, and docs/plans/m{PREV}.md as the worked example. No game launch; nothing under runtime/; no system settings. Branch m{M}, tree clean, tests and verify docs green at the start, or stop.
1. With /optilux-plan, write docs/plans/m{M}.md from docs/templates/plan.md, section 3 first: every premise verified at its source today (a command and its output, a file, a doc heading, a URL); one that cannot be verified is marked "open:" with what would decide it. Number the phases from the one after {VERSION}; each has its commit, change, tests, exit and a `- Estimate: <h> h; machine: <launches, downloads, or none>.` line (add `Attended: <what needs me>.` where I must act), which /optilux-next turns into its size. Decisions carry an owner and a recommendation. At most 40,960 bytes, or split the milestone.
2. Close M{PREV} in the records: its roadmap section shrinks to one line, M{M}'s expands from the plan, and the findings assigned to M{M} cite their phases. CHANGELOG.md holds `## 0.{MM} <Name>` with the milestone's user-facing goal (CI's release check needs it on every push).
3. Offer me /critique of the plan; fold in each finding verified at its source, or list it with the reason.
4. STOP for my approval of the plan. Apply what I ask, then record the approval in its section 10.
5. Write docs/prompts/m{M}.md: one self-contained prompt per phase plus Resume, in the format and form of docs/prompts/m1.md Rules: the why and a Done-when (the phase's exit) first; what to read, not AGENTS.md, which loads with the session; the change as the plan states it; the tests; a reviewer-agent pass before the commit where a launch or a mod carries the risk; the commit, pushed with CI green; the stops and the unattended defaults in one sentence; a Report that backs each claim with output.
6. Status lines of AGENTS.md, docs/roadmap.md and the plan; docs/handoff.md overwritten (what passed, the open questions, the time, the next command). Tests green, ruff clean, verify docs passes.
7. Commit `{VERSION}: M{M} plan and prompts.`; push; CI green.
8. Report: the phases with their estimates and sizes, the decisions waiting for me, the time since the first `date`, and that /optilux-next now prints the first phase prompt.
```

## Release
- Estimate: 0.3 h.

```text
/optilux-release
```
