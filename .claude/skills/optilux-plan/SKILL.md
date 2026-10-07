---
name: optilux-plan
description: Writes the plan for an Optilux milestone, docs/plans/m<N>.md, from the strict template docs/templates/plan.md section by section, then its stored prompt set docs/prompts/m<N>.md once the user has approved the plan. Section 3 (Premises) comes first, and every premise is verified at its source on the day (a command and its output, a file, a doc heading, a URL) or marked "open:" with what would decide it; no phase rests on an open premise. Keeps the plan within 40,960 bytes or proposes splitting the milestone, offers a /critique of the draft, and stops for the user's approval before any prompt is written. Use when the user types /plan or /optilux-plan, asks to plan the milestone, plan M<N> or write the milestone plan, or when the standing Plan prompt runs. Never launches the game, touches runtime/ or changes system settings.
---

Medium freedom: the template's sections, their order and its rules are fixed; what goes in them is judgement. One milestone per run: M<N> on branch m<N>, titled `# M<N> <name>`, written to docs/plans/m<N>.md and docs/prompts/m<N>.md without zero padding (m2.md for M2); phases are M<N>.P<PP> (M2.P01), the plan itself M<N>.P00.

## Read first
- templates/plan.md#rules, templates/plan.md#template and templates/plan.md#filling-it: the ten sections, their headings, the cap.
- roadmap.md#rules; the milestone's line under roadmap.md#m1-to-m6; roadmap.md#findings-assigned (the rows landing in this milestone); roadmap.md#decisions (owners, the ones due in it); roadmap.md#estimates (the tripwire).
- design.md#5-interfaces (the verbs whose From is this milestone), design.md#6-milestones (its exit), design.md#7-decisions-taken-user-2026-10-05 (closed: cite, never reopen).
- handoff.md (the open questions handed to this milestone) and the previous milestone's plan as the worked example.
- workflow.md#running-a-milestone, workflow.md#docs-rules, workflow.md#git, workflow.md#release.

## Steps
1. Section 3 first. List every fact the phases will rest on: pins, versions and hashes, URLs and API shapes, config keys, file contents, the repo's state (branch, tree, test count, `verify docs` margins). Verify each today at its source and write its row `| P<n> | <fact> | <source> | <how>, <date> |`: "command, <date>" for a command run now, "read <date>" for a heading or URL read now. A fact copied from an older plan, handoff or memory without rereading its source is described, not verified (ALC's recurring failure). One that cannot be verified reads `open: <what decides it>`. Hand breadth to the researcher agent when the sources are many, and spot-check what it cites.
2. Sections 1 and 2 from the roadmap line and design.md: the exit as checkable conditions; Out names what a reader might expect here and the milestone that owns it.
3. Section 5, numbered from M<N>.P01, the phase after the plan's own (the phase the Plan prompt names). Each `### M<N>.P<PP> <title>` has Change, Tests, Exit (checkable by a command, a test or a record) and `- Estimate: <h> h; machine: <launches, downloads, or none>.`; no commit subjects, which are written when the commits are made (workflow.md#git), plus ` Attended: <what needs the user>.` where the user acts; `optilux status` sizes the phase from that line. A phase that rests on an open premise is not planned yet.
4. Sections 4 and 6 to 10: the ground rules (never touched, announced, the named stops); decisions with an owner and the recommendation an unattended run takes, with the cost of the alternative (decisions about the sequence of milestones stay in roadmap.md#decisions); stop conditions; estimates with their basis and the tripwire recomputed; what the handoff must hold; section 10 `draft, <date>`. A section with nothing to say holds "none".
5. Check: `uv run optilux verify docs` (the 40,960-byte plan cap, Contents, cites, the Status line's ASCII, LF without BOM) and the ten headings exactly as the template has them. Over the cap: cut duplicated text first (cite instead of repeating); if it is still over, propose the split and let the user decide.
6. Offer the user /critique of the plan file (artifact mode; a `--repo` run only on a copy without reference/, runtime/, snapshots/ or results/raw/). Verify each finding at its source, then fold it in or list it with the reason for the handoff.
7. STOP for the user's approval. Apply what they ask, then write `approved by the user, <date>` with the changes in section 10 and the Status line.
8. Only after approval, docs/prompts/m<N>.md: one `## M<N>.P<PP> <title>` heading and one fenced block per phase, `## Resume` last, in the form of prompts/m1.md#rules (the why and a Done-when first; what to read; the stops and unattended defaults in one sentence; the change; the tests; a reviewer pass where a launch or the mod carries the risk; the commits pushed with CI green, the last one writing the handoff's `Last phase:` line; a Report backed by output). Once docs/handoff.md reads `Last phase: M<N>.P00` (the Plan prompt's step 6), check that `uv run optilux status` prints the M<N>.P01 prompt and that `verify docs` passes.

## Never
- Write a prompt before the approval, or change an approved plan without an amendment in its section 10.
- Reopen a closed decision, cite by line number, or write time-sensitive instructions.
- Launch the game, write under runtime/, or change a system setting.
