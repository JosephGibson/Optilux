---
name: optilux-next
description: Prints where the Optilux milestone stands and the next stored prompt verbatim, from `uv run optilux status` (branch and whether it is pushed, the newest version locally and on origin/main, the next phase, the Status lines of AGENTS.md and docs/roadmap.md, tree clean or not, hooks path set or not, problems with their fixes). Use when the user types /next, asks for the status, the next prompt, the next phase, or where the milestone stands. Read-only; runs nothing else and changes nothing.
allowed-tools: Bash(uv run optilux status*)
---

Output of `uv run optilux status`, run just now (it always exits 0; a problem is a printed line with its fix):

!`uv run optilux status`

Reply with exactly two things, nothing else:
1. The lines above from `branch:` to the last `problem:` line (or `hooks path:` when there is none), as printed.
2. The next prompt, verbatim: every line after the line `next prompt, <phase> <title>, verbatim:`, in one fenced block, with nothing added, dropped, reworded or explained. If that line is absent, say so with the `problem:` line that explains it.

No summary, no plan, no question, no other command, no file read.
