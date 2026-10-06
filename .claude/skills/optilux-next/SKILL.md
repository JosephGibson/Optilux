---
name: optilux-next
description: Prints where the Optilux milestone stands and the next prompt verbatim, from `uv run optilux status`. It opens with a heads-up on the prompt's kind (planning, implementation or release) and size (S/M/L/XL from its estimate), then the branch and whether it is pushed, the versions locally and on origin/main, the Status lines, the tree, the hooks path and any problems with their fixes. There is always a next prompt in the cycle: a phase prompt, the standing Plan prompt when a milestone has no prompt set yet, or the Release prompt once every phase is committed. After a merge, the block that switches to the next milestone's branch comes first. Use when the user types /next or asks for the status, the next prompt, the next phase, or where the milestone stands. Read-only; runs nothing else and changes nothing.
allowed-tools: Bash(uv run optilux status*)
---

Output of `uv run optilux status`, run just now (it always exits 0; a problem is a printed line with its fix):

!`uv run optilux status`

Reply with exactly these, nothing else:
1. The lines above from `heads-up:` up to the first blank line, as printed.
2. Only if a line `switch to m<N> first, paste:` follows: that line, then the commands under it in one fenced block, unchanged.
3. The next prompt, verbatim: every line after the line `next prompt, <phase> <title>, verbatim:`, in one fenced block, with nothing added, dropped, reworded or explained. If that line is absent, say so with the `problem:` line that explains it.

No summary, no plan, no question, no other command, no file read.
