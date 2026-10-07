# Handoff
Status: M1 in progress: 0.01.10 (dev session 1 and optilux-plan) is done; the user's look review passed and optilux-plan is built. The next prompt is 0.01.11, the bench world and its views, which /optilux-next prints.

## Contents
0.01.10 dev session 1 · V2 · optilux-plan and the skill evals · Close-out · F4's table · Choices · Earlier · Open questions · Time · Next

## 0.01.10 dev session 1
- `install --tier dev`: 5,242 hashes checked, 0 files downloaded, viewfinder-26.3-2.1.4+26.3.jar sha512-equal.
- Two announced dev-tier launches of world spike against the prompt's one. Launch 1 (01:51, pid 20036) joined in 14.0 s with the mod connected (hello with the launched pid, the DACL one allow ACE, a second instance refused with error 231); the user closed its window at 01:52:14 and asked for a relaunch: "Saving worlds", exit 4294967288 (-8), crash report crash-2026-10-07_01.52.30-client.txt, F7's clean dev quit.
- Launch 2 (01:52:40, pid 16532) joined in 12.9 s; "Viewfinder MCP server started at http://127.0.0.1:7150/mcp" at 01:52:47; the mod's quit at 02:11:10: "Stopping!", "Saving worlds", exit 4294967288 (-8) after 17.3 s, crash report crash-2026-10-07_02.11.27-client.txt ("Watchdog (Client shutdown from post-main)", Viewfinder's "HTTP-Dispatcher" alive): F7's clean dev quit. Request log 450 lines, the token absent; options.txt's 23 keys, iris.properties and the Sodium flags read back as written. Raw: results/raw/dev-session-1/ (launch 1's files under launch-1/).
- `input.block on` while the user switched windows locked the game for them; released at their word, on again only for the V2 scene and captures.
- Viewfinder: `/mcp reconnect viewfinder` answered "Reconnect, enable, and disable aren't available in this session" (the VS Code extension); a raw initialize to the server answered 200 with 23 tools, and `claude mcp get viewfinder` read "Pending approval". The user then reconnected it ("Reconnected") and the 23 mcp__viewfinder__ tools appeared. The one call, get_diagnostics through Claude Code's MCP client: request fd244f6a..., 32 ms, "Viewfinder operation completed"; pack ComplementaryUnbound_r5.9.3.zip, IrisRenderingPipeline, debugEnabled true, errors [], 29 observed passes, 10 programs, fps 30, 3840x2160 fullscreen, GL "3.3.0 Core Profile Context 26.9.2.260915"; saved as viewfinder-get_diagnostics.json. S7's client check is done; the mod drove the scene, Viewfinder only read.
- Look review (user, 2026-10-07) of L1 (runtime/spike/launch-1/screenshot.png), V1 (v1-A1, v1-A2, v1-B, v1-C), V6 (v6-water.png) and the V2 pairs below: "Everything looks good". No retake.

## V2
- Through the mod's `command`, ticks frozen: /time set 6000, /weather clear; a cow summoned at (-550.5, 64.0, -379.5) (the surface found with a server-only marker and /spreadplayers), an area_effect_cloud with custom_particle flame at (-552.5, 66, -381.5); /setblock two glass, two ice and a campfire; camera.place (-555.5, 66.9, -376.5, yaw -116.6, pitch 15.0); `ready` before each capture.
- Captures (4K, manifests verified): v2-setblock/attempt-001 and -002 (before, after); v2-frozen/attempt-001 (two frames 3 s apart, frames 56085 and 56175); v2-stepped/attempt-001 (after `/tick step 20`, two frames 3 s apart); 1280 px copies and diff masks in review/; preview/ holds five framing frames.
- Mean |d| in a box around the cow: frozen pair 0.348, across the step 2.414 (60.6 % of the box changed), the stepped pair 0.318; the frozen pair's campfire box 0.456 and flames box 0.617. Whole frames: 47.6 % of pixels changed within the frozen pair (Unbound's TAA and wall-clock animation; the spike's 44.5 %).
- Findings: under /tick freeze particles neither spawn nor age (each stepped tick adds some, which then hold) and campfire smoke appears only after a step; a mob moved by /spreadplayers or /tp while frozen keeps its client position, because the client's interpolation advances only with ticks (the cow was invisible until summoned in place); a mob summoned in place renders at once. Recorded in platform.md#mc-263-verified V2.
- Cleanup: both cows sent to y -200 (they died below the world when ticks resumed, no item left), the cloud killed, the five blocks set to air, /tick unfreeze; `execute if entity @e[tag=v2]` failed. The time stays 6000 and the weather clear.

## optilux-plan and the skill evals
- .claude/skills/optilux-plan/SKILL.md (D8): 28 lines, description 833 characters (third person, triggers /plan, /optilux-plan, plan the milestone, the standing Plan prompt), medium freedom; read first; steps: section 3 first with every premise verified that day or `open:`, sections 1-2, the phases with their Estimate lines, sections 4 and 6-10, verify docs and the 40,960-byte cap (or a proposed split), the /critique offer, the approval stop, then the prompt set and the status check; never. Files are m<N>.md without zero padding.
- The standing Plan prompt's step 1 now opens "With /optilux-plan"; workflow.md (Skills, Running a milestone) says so, and holds the three eval scenarios of each skill.
- Evals, 16 fresh `claude -p` sessions in auto mode with pushes, PRs, commits, releases and edits denied (streams in results/raw/skill-evals/, about $5.85):
  - optilux-next (Sonnet 5): byte-for-byte against `optilux status`. Two of six runs cut the briefing at its first dashed rule (11 of 24 lines; one also dropped the prompt's first line); the skill now names the briefing's last rows (TREE, CHECKS, PROBLEM); after it 4 of 4 exact (three `/optilux-next`, one natural question). The first two `/optilux-next` runs were void: Git Bash turned the argument into C:/Program Files/Git/optilux-next.
  - optilux-release (Sonnet 5 xHigh): real state with no PR: steps 0-3 run (verify docs, 360 tests), stopped at `pack release --check`'s "the tree is not clean" with its fix; dry from OPEN: steps 6-7, no merge; dry from MERGED: steps 8-10, the switch block printed, never run (its prose called the branch m01). 3 of 3.
  - optilux-plan (Fable 5.1 xHigh), the plan's fresh-session test: the ten headings in order, section 3 first, the cap and split, critique, approval, prompt set; the first run wrote m02.md and `# M02`, the rerun after the m<N> fix docs/plans/m2.md and `# M2 perf loop`. The baseline with skills disabled found the skill file by Glob and read it (11 turns, $1.66, 64 s against 3 turns, $1.29, 31 s), so it is not a clean measure.

## Close-out
A second 0.01.10 commit, after the user's "Close out any remaining items with your judgement":
- ProtocolTest's race: aDisconnectCancelsWorkAndAReconnectIsResumed failed twice while the user's Prism Launcher game used about 11 cores. A request answered before its worker starts never runs its handler (Protocol.execute, as designed), so the test's wait for the handler's end timed out when the disconnect came first; the cancel and timeout tests shared the window (50 ms in the latter). The test now waits for a waitStarted latch before cancelling, and the timeout test uses 1 s; the mod is unchanged. `mod test`: 80 of 80 three times idle and twice with all 16 threads busy (a scratchpad load script, 150 s).
- platform.md: S7, the L1 screenshot, V1, V2 and V6 read pass with 0.01.10's outcomes; two cuts of duplicated text paid for it (the dev row's Viewfinder details, now offline.md#tools; the dev-quit sentence, now the L2 quit row); margin 8 -> 54 bytes. roadmap.md F6 cites platform.md for V2's findings.
- The time line now separates the first commit (0.8 h; the first handoff put its end at 02:50) from the close-out.
- Not closable now: optilux-plan's two real-run scenarios (M2's plan) and optilux-release's first real run (M1's PR).

## F4's table
m1-acceptance-7's reloadTable (bench tier, 50 `shaders.reload`, heap after GC, private bytes): M2 sets capture.reloadCap from it.

| reloads | heap after GC MiB | private MiB | available MiB |
|---|---|---|---|
| 0 | 597.3 | 13,174.6 | 13,336 |
| 10 | 947.5 | 13,990.0 | 13,312 |
| 20 | 1,096.1 | 14,684.0 | 13,184 |
| 30 | 1,216.4 | 15,396.9 | 13,083 |
| 40 | 1,406.8 | 16,077.8 | 12,912 |
| 50 | 1,599.6 | 16,809.7 | 12,724 |

- Per reload: heap 20.05 MiB, private 72.7 MiB (repeated in -5 and -6); the current reloadCap 288 would add about 20 GiB of private bytes.

## Choices
- The session ran from a scratchpad driver over launch.launch and launch.open_mod with a file queue, in the background, because it had to outlive the two stops; the foreground rule exists for SendInput items, and none ran.
- World spike: V2 left no entity or block; the snapshot is retaken before the next `run` as before.
- The step through `command` (`/tick step 20`), as the prompt says; `ticks.step 5` once to settle the moved cow before the summon in place.
- optilux-next's one-sentence fix after its eval (the creation rule's step 4), inside this phase.

## Earlier
- 0.01.09: A4, A7, A9, A10 passed and F4's table in m1-acceptance-7 (four launches, A9's span anchored on the swap stamps by the user's decision); the full section is in the 0.01.09 handoff (git history).
- 0.01.08 run and acceptance (A1-A3, A10 in m1-acceptance-3); 0.01.07 renderer and Iris adapters (mod jar eb840262..., unchanged since); 0.01.06 game adapter; 0.01.05 transport; 0.01.04 mod project; 0.01.03 launch; 0.01.02 install; 0.01.01 Plan M1 (approved 2026-10-06, D17-D26).

## Open questions
- 0.01.11 needs the mod held connected while the user flies (camera.get on demand) and worlds of candidate seeds; this session's driver (a background process taking requests from a file queue) is one shape, untested for SendInput.
- PresentMode: every row of 0.01.09's runs reads "Composed: Copy with GPU GDI" against the spike's "Hardware: Independent Flip"; M2's validity rules decide whether composed copy is the measured mode.
- A2's F2 press still needs only `focused`; A7's foreground check belongs there too (0.01.12).
- The live world differs from its snapshot after every launch; every run needs a retake first (M2's `world restore` removes the step).
- Byte caps: AGENTS.md at its cap (0 bytes), platform.md 54, mod.md 36, plans/m1.md 169: the next sentence in any needs a cut first.
- The A9 capture takes 46 s for 120 frames at 4K (the vanilla readback on the render thread).
- Carried: release.yml runs on ubuntu-latest while CI is windows-latest; VS Code's Java and Gradle extensions import mod/; Gradle's other downloads trusted by coordinate; `launch` does not look for a running Gradle; a JVM fatal-error log would list the token; whether `/function` reports success without `/return` on 26.3 is unread.

## Time
- 0.01.10: 01:47 to 02:36 ADT to the first commit, 0.8 h (both stops and 16 eval sessions included); with the close-out to about 02:53, about 1.1 h against 1.5 h. M1 so far about 11.1 h of 25 estimated; tripwire: M0-M3 52.8 h, trip at 105.6 h, actuals about 14.4 h (M0 3.3, M1 11.1).
- 0.01.09: 1.3 h against 2. 0.01.08: 1.0 h against 2.5. 0.01.07: 0.7 h. 0.01.06: 0.8 h. 0.01.05: 1.1 h. 0.01.04: 0.7 h. 0.01.03: 1.6 h. 0.01.02: 0.8 h. 0.01.01: 1.6 h. 0.01.00: 0.5 h. M0: 3.3 h against 7.8.

## Next
/optilux-next prints 0.01.11 The bench world and its views (implementation, L, 2 h; attended: the seed veto and the flights). Then 0.01.12 (QA). Plan around: summon entities in place under /tick freeze (the entities role); a driver that outlives the user's turns; retake the snapshot before any `run`.
