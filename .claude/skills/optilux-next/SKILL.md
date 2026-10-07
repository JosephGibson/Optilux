---
name: optilux-next
description: Prints a briefing on where the Optilux milestone stands, then the next prompt verbatim, from `uv run optilux status`. The briefing gives the next prompt's kind (planning step, implementation, release), complexity (S/M/L/XL), suggested model and effort, whether it offers a /critique or stops for the user, its machine needs, the milestone's progress, the last commit, the phases after, the handoff's open questions, and the branch, versions, tree, hooks and Status lines with any problems and their fixes. There is always a next prompt: a phase prompt, the standing Plan prompt or the Release prompt; after a merge, the block that switches to the next milestone's branch comes first. Use when the user types /next or asks for the status, the next prompt or phase, the model to use, or where the milestone stands. Read-only; runs nothing else and changes nothing.
allowed-tools: Bash(uv run optilux status*)
model: sonnet
effort: medium
---

Output of `uv run optilux status`, run just now (it always exits 0; a problem is a printed `PROBLEM` row with its fix):

!`uv run optilux status`

Reply with exactly these, nothing else:
1. The briefing: every line above from the first down to the line before the first blank line, in one fenced block, as printed. The dashed rules do not end it; its last rows are `TREE`, `CHECKS` and any `PROBLEM` rows.
2. Only if a line `switch to m<N> first, paste:` follows: that line, then the commands under it in one fenced block, unchanged.
3. The next prompt, verbatim, last in the reply: every line after the line `next prompt, <phase> <title>, verbatim:`, in one fenced block, with nothing added, dropped, reworded or explained. If that line is absent, say so with the `PROBLEM` row that explains it.

No summary, no plan, no question, no other command, no file read.
