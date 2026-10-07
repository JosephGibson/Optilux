# Handoff
Status: M1 in progress: 0.01.11 (the bench world's seed and its ten views, found with the user) is done; the next prompt is 0.01.12, review and cleanup, which /optilux-next prints.

## Contents
0.01.11 the bench world · Seeds · Snapshot · The ten views · End city candidate · Checks · Choices · F4's table · Earlier · Open questions · Time · Next

## 0.01.11 the bench world
- Start gate: branch m1, pushed; tests 360 passed, `mod test` 80 passed, verify docs 0 violations, ruff clean; the tree held the uncommitted QA split (D27, D28: plans/m1.md, prompts/m1.md, roadmap.md, handoff.md, test_status.py), folded into this phase's commit at the user's word (2026-10-07), as 0.01.09's amendment was.
- Two announced bench-tier launches through a scratchpad driver (launch.launch and launch.open_mod, requests from a file queue, run in the background; no SendInput, input.block never on):
  - Launch 1 (10:47:06, pid 5032), world spike: joined in 14.2 s; the user created the three candidate worlds from the title screen; the mod's quit at 11:08:03, exit 0 in 1.7 s; request log 1,903 lines, the token absent; options.txt (23 keys), iris.properties and the Sodium flags read back unmoved. Raw: results/raw/views-seeds/.
  - Launch 2 (11:09:16, pid 16236), world bench_263: joined in 13.6 s, `Seed: [263]`; `/tick freeze`, spectator; the flights; the player put back at spawn (-5.5, 75, 8.5), spectator, time 6000, clear; the mod's quit at 11:58:44, exit 0 in 2.7 s; request log 13,881 lines, the token absent; the read-back unmoved. Raw: results/raw/views-flights/ (frames, previews, views.jsonl, PresentMon probes).
- config/views/bench_263.json (sha256 e074f336f4499d8319c45511da33eed8ed9ef6bf88e3ecabb081c7877810c143) loads through record.load_views; suite.json world.seed 263 and its source; test_record.py checks the file holds suite.json's roles in order with each role's dimension, time and weather, and the seed.

## Seeds
Candidates proposed unscreened: no seed map covers 26.3, which adds dappled_forest, sulfur_caves and the abandoned camps (the client jar's worldgen lists), so `/locate` in game was the screen. Worlds created by the user: Default, Peaceful, structures on, no bonus chest, commands on. `/locate` through the mod's `command` from the join point (the Nether from the spawn / 8): results/raw/views-seeds/locate-<seed>.json.

| Role | 263 | 7800 | 20261005 |
|---|---|---|---|
| forest_noon, rain | forest 258 | forest 250 | forest 417 |
| ocean_sunset, night | beach 250, cold ocean 226 | beach 0, cold ocean 45 | beach 615, frozen ocean 550 |
| underwater | cold ocean 226; lukewarm 2,815 | cold ocean 45; lukewarm 921 | frozen ocean 550; lukewarm 1,601 |
| cave | deep_dark 0, mineshaft 123 | sulfur_caves 91, mineshaft 189 | mineshaft 21, deep_dark 45 |
| entities | plains 0 | plains 45 | plains 724 |
| nether_crimson | 163 | 264 | 258 |
| nether_soul | 115 | 250 | 0 |

The user picked 263 (the recommendation): the most compact nearest sites. Warm ocean lies 3.7-4.2 km out in all three. bench_7800 and bench_20261005 stay under runtime/mc-26.3/game/saves/ (deletable in game).

## Snapshot
- First copy (11:08, after launch 1): snapshots/bench_263/ da7ee4207564a4334616d40080af2c1dec78458d36b13218b4e652df0a8355f8, 42 files, equal to the live world.
- Retaken after the flights (11:58:50): **fc515d355c076ad023cc3619745da0f43e7011e19b2b06bff820339fa3c52f67**, 104 files, 148,253,469 bytes, equal to the live world. It holds the entities role's seven mobs.

## The ten views
Each pose flown by the user in spectator (creative for entities), read with camera.get, rounded to 0.1 (yaw wrapped to -180..180), the role's weather (120 ticks stepped when it changed) and time set, camera.place at the rounded pose, `ready` (10 frames, settle 1 s, underwater 2 s), one 4K frame. Every frame kept by the user (cave, nether_crimson and underwater confirmed after the flights). GPUBusy: one 5 s PresentMon window each, median, informal (not M2's check); "capped": the inactivity cap below held, so it reads high.

| View | Pose (x, y, z, yaw, pitch) | Frame | GPUBusy ms |
|---|---|---|---|
| forest_noon | 22.6, 102.8, 533.0, -136.0, 37.2 (attempt 2) | 2db48ebc | 11.54 (10.42 at pitch 15) |
| ocean_sunset | -218.4, 81.0, 779.9, 77.4, 34.1 (attempt 3) | e381ed75 | 10.73 |
| cave | 28.3, -52.5, 426.9, 14.4, -13.8 | 5209aba3 | 9.18 |
| rain | -20.5, 76.8, 491.2, -89.5, 30.3 (attempt 2) | 4b26c24c | 9.93 (11.76 at forest_noon's pose) |
| nether_crimson | 230.2, 86.6, 15.7, 175.7, 27.0 | 25b4faf2 | 6.77 |
| end_dragon | 56.9, 101.6, -19.9, 66.0, 38.7 | fdc8306a | 16.76 capped |
| night | -301.9, 72.5, 637.6, -11.1, -9.4 | ea1aa10b | 7.81 |
| underwater | -333.1, 54.5, 908.5, -145.6, 34.9 | 7df29a9d | 11.11 |
| nether_soul | -9.0, 91.4, -321.3, -54.0, 27.3 | dcff6592 | 7.15 |
| entities | -366.8, 80.0, 244.4, -5.8, 19.0 | 80b13c92 | 12.52 capped |

- ocean_sunset: attempt 1 faced a small enclosed sea (land on the horizon); a biome map (`execute if biome ... #minecraft:is_ocean`, 96-block cells within 2.4 km) found one open ocean, x -680..-200, z 490..1060, and its east shore.
- cave: a lava lake found by testing air at y -46 and -52 over lava at -56 on a 16-block grid near the views.
- entities: seven mobs summoned in place under the freeze (chicken, sheep, cow, pig, villager, horse, llama) 7-13 m ahead, facing the camera: NoAI, PersistenceRequired, Silent, tag optilux_bench; creative, a torch in the main hand.
- end_dragon: ten end crystals on the pillars, no dragon (ticks frozen before the End first loaded; M2's frozen sessions see the same). The role's beams are Complementary's End beams (playbook.md), not crystal beams.
- Pre-generation extents for M2: overworld x -367..28, z 244..909; Nether x -9..230, z -321..16; the End around the main island; each plus 256 blocks.

## End city candidate
The user asked for an End city view; scouted here, then the user made it an 11th perf role, end_city, added in 0.01.12 (D29, 2026-10-07). Nearest city (368, ~, 992), 1,058 blocks from the main island. Kept pose: the End, (317.1, 75.1, 1054.8), yaw -120.3, pitch -9.0, time 6000; frame a2727557 (results/raw/views-flights/end_city/attempt-001/); GPUBusy 9.42 ms. Shulkers survive Peaceful: two closed ones at 56 and 62 m are in view; the ship's elytra item frame at 65 m is past its render limit.

## Checks
- The entity counts the capture script printed for the first six views were void: the game answers "Test passed. Count: N" and the pattern sought "count: " (lowercase). Fixed for the last four, and every kept view rechecked: each non-player entity within 128 blocks of the eye listed (`execute as @e[...] run data get entity @s Pos`, the camera at the view so its chunks load) and projected into the camera (vertical FOV 90 at 16:9). In-frustum hits beyond their render limit (64 blocks times the bounding box's mean size: chicken about 32, cow and sheep about 67, item 16, strider 75): forest_noon chickens 74-79 m and cows 110-117 m (crops of the frame at their pixels show canopy only), rain chickens 125-127 m, night sheep 111-117 m, cave items 117 m, nether_crimson striders 95-127 m, nether_soul striders 111 m; ocean_sunset and underwater none. entities: the seven tagged at 7-13 m, and untagged horses at 57-62 m (rendered: small shapes mid-frame), a villager at 65.5 m and cows near 70 m. All untagged; M2's world prep kills them.
- Eye block: air for every view, water for underwater; no frame near-black (darkest: cave 7.5 % of pixels under 8, its unlit roof).
- The game's frame rate read 29.9 fps by frames.index at three poses (156 frames in 5.21 s each) while the user was away: options.txt keeps inactivityFpsLimit "afk", the game's default, which "Limits framerate to 30 when the game is not getting any player input for more than a minute. Further limits it to 10 after 9 more minutes" (en_us.json). Uncapped windows ran 85-148 fps; the capped ones read GPUBusy high (rain at forest_noon's pose 21.58 ms capped, 11.76 uncapped). Open question below.
- PresentMode: every row of the session's 14 probes reads "Composed: Copy with GPU GDI".

## Choices
- Candidate seeds 20261005, 263 and 7800, unscreened (above); worlds Peaceful (no hostile mobs in any view; the entities role uses passive mobs), commands on, creative at creation, spectator for the flights.
- World id bench_263: the views file, the snapshot and the save folder share it ([a-z0-9_], record.VIEW_ID).
- One launch for all candidate worlds (created from the title screen), a second for the flights; `/locate` from the join point, the Nether from spawn / 8; the views file's `why`s written once (its bytes are identity).
- Each role's time and weather set before its flight, so the user framed it lit as captured; the pose re-placed rounded before the frame, so the frame is the recorded pose.
- The driver, the informal GPUBusy probe, the entity projection, `/locate` and the ocean map: scratch tools, nothing committed (roadmap.md's QA row on the driver: nothing to review in 0.01.12); copies kept in results/raw/views-flights/tools/ (ignored) for M2's world prep and view checks.

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

## Earlier
- 0.01.10: dev session 1, the look review passed, optilux-plan built and its evals; the full section is in the 0.01.10 handoff (git history).
- 0.01.09: A4, A7, A9, A10 and F4's table in m1-acceptance-7; 0.01.08 run and acceptance (A1-A3, A10 in m1-acceptance-3); 0.01.07 renderer and Iris adapters (mod jar eb840262..., unchanged since); 0.01.06 game adapter; 0.01.05 transport; 0.01.04 mod project; 0.01.03 launch; 0.01.02 install; 0.01.01 Plan M1 (approved 2026-10-06, D17-D26).

## Open questions
Each has its phase or milestone in roadmap.md#qa-pass-open-questions; 0.01.11's five close in 0.01.12 (user, 2026-10-07; D29, D30).
- inactivityFpsLimit "afk" caps every session without player input at 30 fps after a minute, 10 after 10 (0.01.12: display.optionsTxt writes "minimized", an identity change before M2 calibrates).
- World prep's kill spares only the dragon and optilux_bench: it would take end_dragon's ten end crystals and change the entities frame (0.01.12 spares end crystals in the spec; M2 implements it).
- The entities frame shows no hand: the capture point follows renderLevel, which skips the hand when the GUI is hidden (F1 or hud.set hideGui); whether F1 was on is unread (0.01.12: one launch on world spike, hideGui false, a frame).
- end_city, the 11th role (0.01.12, D29); the candidate worlds bench_7800 and bench_20261005 deleted (0.01.12, D30, the user's exception to the runtime/ rule).
- PresentMode: "Composed: Copy with GPU GDI" in every row of 0.01.09's runs and this session's probes, against the spike's "Hardware: Independent Flip" (0.01.13; M2).
- A2's F2 press still needs only `focused`; A7's foreground check belongs there too (0.01.12).
- The live world differs from its snapshot after every launch; every run needs a retake first (M2's `world restore`). bench_263 equals its snapshot now.
- Byte caps: AGENTS.md 9 bytes of margin, platform.md 54, mod.md 36, plans/m1.md 58, prompts/m1.md 5: the next sentence in any needs a cut first (0.01.12).
- The A9 capture takes 46 s for 120 frames at 4K (M2).
- Carried: release.yml runs on ubuntu-latest while CI is windows-latest; VS Code's Java and Gradle extensions import mod/; Gradle's other downloads trusted by coordinate; `launch` does not look for a running Gradle; a JVM fatal-error log would list the token; whether `/function` reports success without `/return` on 26.3 is unread.

## Time
- 0.01.11: 04:36 ADT to the commit at 12:36:51, CI green at 12:38: 8.0 h on the clock, of which about 5.8 h waited on the user's answer to the start gate's question (asked within the first 20 minutes; the next step at 10:46); about 2.2 h of work against 2 h, the flights included, about 2.4 h with the close-out (the first commit's handoff said 12:20 and 1.8 h). M1 so far about 13.5 h of 28; tripwire: M0-M3 55.8 h, trip at 111.6 h, actuals about 16.8 h (M0 3.3, M1 13.5).
- 0.01.10: 1.1 h against 1.5. 0.01.09: 1.3 h against 2. 0.01.08: 1.0 h against 2.5. 0.01.07: 0.7 h. 0.01.06: 0.8 h. 0.01.05: 1.1 h. 0.01.04: 0.7 h. 0.01.03: 1.6 h. 0.01.02: 0.8 h. 0.01.01: 1.6 h. 0.01.00: 0.5 h. M0: 3.3 h against 7.8.

## Next
/optilux-next prints 0.01.12 Review and cleanup (offline, L, 3 h), then 0.01.13 debug, timing and the acceptance re-run on the final jar (L, 2 h). Plan around: 0.01.11's five rows close in 0.01.12 (the inactivity cap, the crystals in the kill, the held-torch launch on world spike, end_city, the two worlds), the cap before 0.01.13's timed session; the provisional snapshot retaken before any `run`; bench_263 is not used by M1's acceptance runs.
