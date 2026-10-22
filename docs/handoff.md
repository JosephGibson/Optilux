# Handoff
Status: the latest stop: M3.P07 done, the coverage views built, rebuilt live and framed across launches (m3-coverage-1 to -3), and what M3.P08 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P07
- The exit holds, shown in this session (2026-10-22, ADT), each launch announced and run with the machine left alone:
  - `world prep bench_263` (prep-bench_263-20261022-180856, 15:08:56-15:12:56) ended ok:
    - Chunky's tasks hit 100 % from the console's finished line, ticks frozen throughout. The overworld's took 7,209 chunks in 9 s, centre (-26, 658), radius 629 x 702 (x -655..603, z -44..1360; it was 486 x 621).
    - The coverage step: after the build, and again after the sweep, one of each of the seven content entities counted, all 17 block tests "Test passed", the sign read back `313, 101, 1072 has the following block data: "Optilux"`.
    - The End's clock read back "Clock minecraft:the_end is at 6000 tick(s)" at end_dragon and end_city; end_dragon held ten end crystals and no dragon; the entities role's seven mobs did not move.
    - The snapshot was retaken: 1b081885... (128 files).
  - m3-coverage-1 (15:13:58-15:15:33): a visual run of mode coverage with the hello pack (optilux.zip sha512 d86371b7..., `check L0` ok) and Unbound r5.9.3 on iso v1.
    - It ended ok: 6 of 6 pairs valid; the 12 frames re-hashed equal to the record; every option read back; recorded on 89d4686, the tree clean.
    - The hello pack's three pairs identical; Unbound's moving (TAA), REVIEW.
- The first prep (prep-bench_263-20261022-180041, 15:00:41) stopped at its first gamerule: the prepared snapshot answered "Game rule advance_time is already set to false", a failure gamerules() refused. It was fixed in 89d4686 and the prep rerun; that launch took no snapshot.
- Follow-ups at the user's request (16:53-17:02, after the user's hold from 15:58):
  - The live rebuild: prep-bench_263-20261022-195457 on the built site.
    - The old content read "Count: 7" at the first read and was killed ("Killed 7 entities", 40 ticks, none left); the kill then took its 2 drops.
    - The fills refilled 9 blocks each; the four setblocks answered "Could not set the block" (unchanged, accepted, each tested present after); the seven summons followed.
    - Every count held after the build and after the sweep. The snapshot was retaken: 33a4074d4198ea0143a5dc2a47b3e21ce900cbe9baa8276b5c918dc4a5a03035, 128 files, 169,126,119 bytes, now the world's.
  - m3-coverage-2 (16:58:59-17:00:33) and m3-coverage-3 (17:00:41-17:02:15) on it: each ok, 6 of 6 valid, 12 of 12 frames re-hashed equal, the hello pairs identical.
  - `compare m3-coverage-3 --against m3-coverage-2`, the hello pack across launches:
    - coverage_mobs identical.
    - coverage_items: 7,442 pixels, exactly the two dropped items (the apple at x 1288-1366, the diamond at 1428-1493): their spin is ItemEntity.bobOffs, random at each load and never saved (javap).
    - coverage_beacon: 44,074 pixels, exactly the beam (x 1893-1947, y 0-1334): its turn and scroll follow the game time, and `/tick freeze` came 6.74 s after the join in -2 and 6.26 s in -3, so the unfrozen ticks before it differed (P22).
- The site: a smooth-stone floor at y 100 over x 306..322, z 1061..1077, near (314, 1069). Its three views lie 531.9-532.9 blocks (Chebyshev) from the nearest overworld perf view; the snapshot's chunks under it (15..23, 62..70) reach y 83 at most.
- What each item shows (Claude's pre-screen of the runs' frames and prep's Unbound-default frames):
  - coverage_items:
    - The enchanted golden apple: plain gold in the hello pack, which draws an item's glint as built (shader.md#facts: no mc_sampleGlint, and BENCH_DETERMINISTIC applies no texture matrix); glint-tinted with a pink rim in Unbound.
    - The dropped diamond edge-on; the item frame's diamond sword on its spruce planks; the sign's "Optilux / coverage", sharp at 4K in both packs.
    - The armor stand in the iron helmet and diamond chestplate; the fox and the polar bear's flank at the right.
  - coverage_mobs: the fox, polar bear and mooshroom (its mushrooms drawn) in noon sun; the armor stand close at the left; the campfire's logs and flame at the right edge.
  - coverage_beacon:
    - The beam rises from the beacon on its iron base to the top of the frame in both packs.
    - The campfire's flame shows in both; its smoke only in Unbound (particles discarded under BENCH_DETERMINISTIC, the exempt item).
    - The mooshroom at the left; the held torch at the bottom right (creative; frames come before the GUI pass, so no hotbar). Unbound also draws the player's own shadow.
  - Every coverage item is in its frames.

## What changed
- e215b49: the views file's `coverage` list:
  - record.load_views, check_view, COVERAGE_KEYS hand and ticks, COVERAGE_APART 512 (Chebyshev over x and z, per dimension), every_view, coverage_views;
  - visual runs of mode `coverage` (VISUAL_MODES, `verify records`);
  - measure.arrive's `hand` (D49's GUI and creative) and own `ticks` after the weather's;
  - bench_263's three coverage views.
- 8924692: world prep's coverage step and the End clock:
  - build_coverage: the old tagged content waited for and killed, the kill, the fills, setblocks and summons through `command`, then coverage_counts and coverage_problems after the build and after the sweep;
  - the selection, functions, views loop and sweep over every view;
  - the End views' functions also run `time of minecraft:the_end set <time>`, read back at each End view (parse_clock);
  - session.shows_hand; measure.stale_functions over every view.
- 89d4686: gamerules() takes "already set" as set. 472e5b4: a test of prep's order around the coverage step.
- 2c565f8 and accaa2d: the three records; suite.json coverageViews' status (built; what moves across launches).
- Docs:
  - measurement.md#baseline-suite: coverage views, prep's coverage step and the End clock, session step 5.
  - measurement.md's cuts, each held elsewhere: the buried-camera aside, prep's pack.mcmeta and Chunky-line detail, the tag bullet, step 5's held-item rationale, the GPULatency and display-state definitions, the CTRL_C aside, Readiness' fields line.
  - run-record.md#run-spec: mode coverage. CHANGELOG.md 0.4.0: one bullet.

## Review
The reviewer agent on world.py's changes and the views file (correctness): 6 findings, 1 medium and 5 low, each read at its source.
- 1 (medium) held and is fixed: the old content was read once, before its entities could load. It is now read once a second for up to 10 s, and the kill must leave none; shown live (Count: 7, then none).
- 2 (low) is fixed: a view's own ticks outside the overworld left the ramp stale, in prep and in measure.arrive.
- 3 and 4 hold as built: `execute if block` answers a bare "Test passed", and `time of <clock> query time` exists (javap of the 26.3 jar, en_us.json); both were then seen live.
- 5 did not hold: chunk 20, under the floor's east strip, was full in the old snapshot.
- 6 is fixed: the ticks' order is recorded, the dragon-fight guard tested, and session()'s order tested (472e5b4).
- The kill sparing the content, the counts and the selection were found to hold.

## Choices
Neither the prompt nor the plan names these:
- A visual run takes the coverage views by `mode: "coverage"`, a visual-only mode rather than a suite.json mode: the perf modes and the suite's identity are unchanged.
- The poses came from geometry, not flight, as nothing sends input: a floor at a fixed y 100 over the measured terrain, each item's place in frame computed for fov 0.5 at 16:9, then confirmed by prep's frames. The poses went in with the loader (e215b49) and no pose changed after.
- The content:
  - three passive mobs Peaceful summons: mooshroom, polar bear, fox;
  - the armor stand in an iron helmet and diamond chestplate;
  - the item frame (Fixed, Pos and block_pos given, so no "invalid position" log line), its diamond sword on planks;
  - a dropped diamond and an enchanted golden apple (NoGravity, Age -32768, PickupDelay 32767);
  - an oak sign facing north, a beacon on 3x3 iron, a lit campfire.
- Every entity carries PersistenceRequired (only mobs read it); summon coordinates are decimal, so the command never centres them.
- `hand` is a boolean (creative and the GUI, with the snapshot's torch). `ticks` is 100 at coverage_beacon, since the beacon sets its level on a game tick divisible by 80 (javap).
- Counts:
  - the entities by selector in the site's box, the two items told apart by nbt;
  - 17 blocks by `execute if block`: the floor's corners, the base's nine, the four blocks;
  - the sign's first line, read back.
- Follow-ups, at the user's request (16:00 "Can we fix what didn't go as planned"):
  - the live re-prep, which made 33a4074d... the world before M3.P10's freeze;
  - two runs to compare across launches.
- The poses and records were committed after each run, so m3-coverage-3 records dirty true: -2's record was untracked at its launch.
- A scratch display hold (the harness's request, scratchpad hold.py) ran 14:41:50-15:15:45 and from 16:53 to 17:02.

## Checks
- Start (14:04 ADT): branch m3 clean at f057558; 947 passed; verify docs 0 violations.
- Before each commit, on a tree equal to it: 962, 975, 976, 976, 977 and 977 passed; ruff, ruff format and pyright clean; verify docs 0 violations; verify records 0 violations (231 records at the end).
- One test failed in the first full run (962 items). Its name was lost to a `tail -1` on the output, and pytest's cache was cleared by the passing reruns. About 30 full runs since, 12 of them a dedicated hunt with `-rf`, all passed; it stays unnamed.
- CI green on e215b49, 8924692, 89d4686, 2c565f8, 7c37e2a, 472e5b4 and accaa2d, each watched to its end before the next push or launch.

## Open questions
- The beacon beam moves across launches with the game time, which the unfrozen ticks between the join and /tick freeze advance (P22, now seen: 6.74 against 6.26 s). Clouds share the cause; the hello pack discards them. For M3.P09's diagnosis of perf views across sessions: freezing at a set tick, or a pack-side pin.
- Moving across launches, named in suite.json and kept out of identical and near (D64): the dropped items' spin, the beam, the campfire's smoke, the glint where a pack draws it.
- Unbound on iso draws no shadow under the coverage mobs, while the frame's block and the sign keep theirs: a profile look note.
- Carried: the hello pack's olive End stone; whether 26.3 animates textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; the water fog colour (M3.P09); D66, the driver; D72; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- The flaky test above is unnamed.
- Margins: measurement.md 20 bytes; platform.md 7; AGENTS.md 16; mod.md 62; workflow.md 199.

## Commits and time
- e215b49, 8924692, 89d4686, 2c565f8, 7c37e2a, 472e5b4, accaa2d; then this handoff.
- 2026-10-22, 14:04-15:28 and 15:35-15:58, then 16:53-17:12 ADT (the user's hold apart): about 2.1 h against 2.5 h. Tripwire: actuals about 57.9 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1, P07 2.1); the trip at 174.6 h.

## Next
/optilux-next prints M3.P08's prompt: check L1 and L2, 3 h, 2 launches (dump runs), on the world 33a4074d....
