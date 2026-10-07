# Handoff
Status: M1 in progress: 0.01.09 (A4, A7, A9 and the reload table, with the M1 amendment: 0.01.11 views, 0.01.12 QA) is done; m1-acceptance-7 holds A4, A7, A9 and A10 passed and F4's table; the next prompt is 0.01.10, dev session 1 and optilux-plan, which /optilux-next prints.

## Contents
0.01.09 acceptance and the reload table · F4's table · Built · Choices · Earlier · Open questions · Time · Next

## 0.01.09 acceptance and the reload table
- Four announced launches against the prompt's two, each bench tier, world spike, unmodified Unbound, quit exit 0, each record committed (results/records/): m1-acceptance-4 (01:06 ADT) failed on A7, -5 (01:13) on A9, -6 (01:29) on A7; -7 (01:35) ok: A4, A7, A9, A10 passed and F4's table, 160,060 bytes, world bddb4929df9d... (68 files, retaken before each run).
- -4's A7: T opened chat and Escape closed it, but the mouse motion right after moved nothing; the same motion after the blocked arm turned the camera. In the 26.3 jar MouseHandler.grabMouse ends by setting ignoreFirstMove (offsets 110-112) and onMove then records the position and returns: the first motion after a grab is dropped. Read as a harness bug, not section 7's A7 stop (SendInput drove the game in the same session, as in 0.01.06); the control now primes the grab with one motion, whose effect is recorded (none, in -5 and -7).
- -5's A9: the HEAD-anchored span paired every frame one present off (swap offset median 19.73 ms, max 1,444.76 ms): PresentMon's CPUStartQPCTime lags the swap stamp by 0.10-0.40 ms, and a frame without readback work stamps its HEAD only 0.10-0.12 ms after the swap, so the first row fell either side of the first HEAD stamp (-0.001 ms in -4, +0.037 ms in -5). Section 7's A9 stop; the session stopped and reported; the user took the recommendation (2026-10-07): the span is anchored on the swap stamps, half the shortest frame wide at each edge (plans/m1.md section 10). Both runs' raw data pass under it, now test fixtures.
- -6's A7: T was sent with `state.focused` true and SendInput inserting 2 of 2, yet opened nothing; this session ran the launch in the background while it ran doc scripts, and a keystroke went elsewhere without the game seeing a focus change. Every injection now also needs the foreground window to be the game's (GetForegroundWindow's pid, recorded); the focus fallback acts on either; -7 ran in the foreground with nothing beside it.
- m1-acceptance-7's evidence. A4: the copy (shaders/world0/final.fsh replaced by 164 bytes using the undeclared optiluxA4Undeclared) selected through iris.properties: iris-compile-error in 0.23 s, "ShaderCompileException: final.fsh: final.fsh: ERROR: 0:20: 'optiluxA4Undeclared' : undeclared identifier ..."; reload.failed sent; iris.properties back to launch's keys; recovery reload IrisRenderingPipeline in 0.340 s; ready 1.39 s; one frame (4284); the copy deleted after the quit. A7, every injection with focused true and the foreground pid the game's (12972): control: T 2 of 2, ChatScreen; Escape 2 of 2, closed; the prime 1 of 1 moved nothing; the motion (200, 100) turned yaw 135 -> 165, pitch 31.2 -> 46.2; blocked: motion and T sent, 156 frames and 1.55 s: pose and state unchanged, no screen; after: the motion turned yaw to 195, pitch to 61.2. A9: PresentMon's first rows 1.1 s after its start; 120 frames in 46.2 s; 120 rows in the span for 120 stamps; swap offset median -0.1732 ms, max size 0.396 ms (limit 1 ms, shortest frame 10.28 ms); HEAD offset median 12.62 ms, max 36.21 ms (the readback's conversion lies between swap and head on captured frames); CTRL_BREAK_EVENT exit 0 in 0.06 s; no ETW session left; 120 PNGs deleted. A10: selftest passed (3.23 s).
- The swap offsets of all four runs under the final rule: -4 median -0.164 / max 0.335 ms, -5 -0.159 / 0.379, -6 -0.165 / 0.409 (passed in its record), -7 -0.173 / 0.396.

## F4's table
m1-acceptance-7's reloadTable (bench tier, 50 `shaders.reload` back to back at overworld_spawn after A4, A7 and A9; heap after `jcmd GC.run` then GC.heap_info; private bytes by psutil):

| reloads | heap after GC MiB | private MiB | available MiB |
|---|---|---|---|
| 0 | 597.3 | 13,174.6 | 13,336 |
| 10 | 947.5 | 13,990.0 | 13,312 |
| 20 | 1,096.1 | 14,684.0 | 13,184 |
| 30 | 1,216.4 | 15,396.9 | 13,083 |
| 40 | 1,406.8 | 16,077.8 | 12,912 |
| 50 | 1,599.6 | 16,809.7 | 12,724 |

- Per reload: heap 20.05 MiB, private 72.7 MiB; each reload 0.320-0.358 s (median 0.331); heap committed 6,144 MiB throughout. Repeated in -5 (19.94 and 71.3 MiB) and -6 (19.9 and 72.8 MiB from 604.2 -> 1,598.2 and 12,909.5 -> 16,549.9). The spike's dev tier: 20.6 and 320 MiB. At 72 MiB per reload the current capture.reloadCap 288 would add about 20 GiB of private bytes on this 32 GiB machine: M2 sets the cap from this table.

## Built
- optilux/presentmon.py: measurement.md#tools' command line; the start in a CREATE_NEW_PROCESS_GROUP child; the stop by CTRL_BREAK_EVENT through GenerateConsoleCtrlEvent (a failed send kills at once and names the Windows error; gone before the stop or deaf for 30 s fails, naming `logman stop <session> -ets`; the harness ignores CTRL_BREAK itself); the CSV read while it grows (PresentMon 2.6 writes a byte-order mark and CRLF and holds the file unshared while it runs: the wait then goes by its size and the complete file is checked after the stop); a9_match (the swap-anchored span, consecutive frames, a row past the span, one process and one swap chain, both offsets, the pass under min(1 ms, half the shortest frame)).
- optilux/verbs/run.py: A4 (write_broken_pack, a leftover copy refused before launching, the copy deleted in the session's finally), A7 (control with the grab primed, blocked, after; a screen left open closed; injections only with the game in front), A9 (the stop guaranteed from PresentMon's start, the PNGs deleted on every path), F4 (reload_table, GC.heap_info's parser, stops and fails under 2 GiB available); items recorded once they start; the A2/A3 view loop only when listed; the announcement asks for hands off. record.py: A4, A7, A9 runnable; the spec's `reloads` and the reload budget. sendinput.py: T and Escape.
- Tests: 360 (25 new): PresentMon's start and stop on a fake process and on a real child stopped by CTRL_BREAK (Windows, skipped without a console); the CSV cut (byte-order mark, CRLF, a partial line); the A9 match on synthetic rows and on -4's and -5's real spans and stamps (tests/fixtures/run/); the jcmd parser on Temurin 25's real GC.heap_info; the broken-pack writer on a fixture zip; the spec's new refusals.
- Docs: mod.md#12-acceptance A9 names both stamps (D26); run-record.md (the items, `reloads`, `reloadTable`, the raw folders); roadmap.md F2-F5, F8, F11 landed; the M1 amendment (user, 2026-10-06): plans/m1.md 0.01.11 and 0.01.12, sections 1, 2, 4, 8 and 10 (0.01.02-0.01.05's built changes condensed to make room, the full text in git history), prompts/m1.md's two prompts, 0.01.10's and Resume's ends, roadmap.md's phases, exit and estimates (M1 25 h; tripwire 52.8 h, trip at 105.6 h).
- Review (reviewer agent, correctness, before the first launch; each read at its source): fixed: A7's blocked arm compared whole `state` answers, whose stamps move every frame (it could never pass); A4's pass needs the message to name the program or identifier; A9's stop error kept and the stop guaranteed; a failed CTRL_BREAK send no longer waits 30 s; a screen A7 leaves open closed; the PNGs deleted on every path; items not run read notRun; one swap chain required. Kept: PresentMon is not tied to the harness's life (the next launch's gate refuses its session).

## Choices
- F4 inside the acceptance session after A4, A7 and A9 (the spec's `reloads`), so one ok record holds every item and the table; the rows are relative to the table's first row.
- A4's copy selected through iris.properties (0.01.07's pack-switch mechanism), the file written back as launch wrote it; read back equal after every quit.
- A9's PNGs deleted after the match (120 4K frames, about 2 GB); capture.json and the CSV kept under results/raw/<run>/a9/.
- PresentMon dry runs before the game (scratchpad only): dwm.exe (another account) wrote no CSV; CTRL_BREAK_EVENT from the starting process stopped it in 0.06 s with no session left; from another console the send failed with error 87.

## Earlier
- 0.01.08 run and acceptance: `run`, the provisional world, A1, A2, A3 and A10 passed in m1-acceptance-3; the full section is in the 0.01.08 handoff (git history).
- 0.01.07 renderer and Iris adapters: mod jar eb840262... (unchanged since); 0.01.06 game adapter; 0.01.05 transport; 0.01.04 mod project; 0.01.03 launch; 0.01.02 install; 0.01.01 Plan M1 (approved 2026-10-06, D17-D26).

## Open questions
- PresentMode: every row of the four runs reads "Composed: Copy with GPU GDI" (SwapChainAddress 0x0, FrameTime about 10 ms); the spike's L1 read "Hardware: Independent Flip" (Sodium had set exclusive fullscreen then; the harness writes borderless, F3). M2's validity rules read PresentMode: decide whether composed copy is the measured mode.
- A2's F2 press still needs only `focused`; A7's foreground check belongs there too (0.01.12's QA).
- 0.01.11 needs a way to hold the mod connected while the user flies (camera.get on demand) and to make worlds of candidate seeds; its prompt leaves both to the phase.
- The live world differs from its snapshot after every launch; every run needed a retake first. Recommended, unchanged: by hand per run in M1; M2's `world restore` removes the step.
- Byte caps: AGENTS.md at its cap (0 bytes of margin), platform.md 8, mod.md 36, plans/m1.md 169: the next sentence in any needs a cut first.
- The A9 capture takes 46 s for 120 frames at 4K (the vanilla readback converts pixel by pixel on the render thread; frames stall up to 1.44 s at maxPendingFrames).
- Carried from 0.01.08: release.yml runs on ubuntu-latest while CI is windows-latest; the skill evals for optilux-next and optilux-release run in 0.01.10; VS Code's Java and Gradle extensions import mod/; Gradle's other downloads trusted by coordinate; `launch` does not look for a running Gradle; a JVM fatal-error log would list the token; whether `/function` reports success without `/return` on 26.3 is unread.

## Time
- 0.01.09: 00:26 to about 01:45 ADT, about 1.3 h against 2 h (the stop and the user's answer included, the amendment written with it); the reviewer's pass 16 min beside the tests and docs; each run about 2.5 min of machine time. M1 so far about 10.0 h of 25 estimated; tripwire: M0-M3 52.8 h, trip at 105.6 h, actuals about 13.3 h (M0 3.3, M1 10.0).
- 0.01.08: about 1.0 h against 2.5 h. 0.01.07: 0.7 h. 0.01.06: 0.8 h. 0.01.05: 1.1 h. 0.01.04: 0.7 h. 0.01.03: 1.6 h. 0.01.02: 0.8 h. 0.01.01: 1.6 h. 0.01.00: 0.5 h. M0: 3.3 h against 7.8.

## Next
/optilux-next prints 0.01.10 Dev session 1 and optilux-plan (implementation, 1.5 h): the dev tier with Viewfinder, the user's /mcp reconnect and look review (attended), optilux-plan, the pending skill evals; commit `0.01.10: Dev session 1 and optilux-plan.`. Then 0.01.11 (the views, with the user) and 0.01.12 (QA). Plan around: retake the snapshot before any `run`, and run launches in the foreground with nothing beside them.
