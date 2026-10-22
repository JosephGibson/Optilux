# Handoff
Status: the latest stop: M3.P07 done, the coverage views built (the views file's coverage list, world prep's coverage site, the End views' clock) and framed by m3-coverage-1, and what M3.P08 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P07
- The exit holds, shown in this session (2026-10-22, ADT):
  - `world prep bench_263` (prep-bench_263-20261022-180856, 15:08:56-15:12:56, announced, the machine left alone) ended ok. Its Chunky tasks hit 100 % from the console's finished line, ticks frozen throughout; the overworld's took 7,209 chunks in 9 s, centre (-26, 658), radius 629 x 702 (x -655..603, z -44..1360; it was 486 x 621).
  - The coverage step: after the build, and again after the sweep, one of each of the seven content entities counted, all 17 block tests "Test passed", the sign's first line read back `313, 101, 1072 has the following block data: "Optilux"`.
  - The End's clock read back "Clock minecraft:the_end is at 6000 tick(s)" at end_dragon and end_city; end_dragon held ten end crystals and no dragon. The entities role's seven mobs unmoved; no hook failure; quit exit 0.
  - The snapshot was retaken and hashed: 1b08188525ef673fe44f26653170adf55302a458cd767d0dd1e93e748fd72c82, 128 files, 168,978,587 bytes (it was 65e7ae73..., 116 files).
  - m3-coverage-1 (15:13:58-15:15:33, announced, the machine left alone): a visual run of mode coverage with the hello pack (optilux.zip sha512 d86371b7..., `check L0` ok) and Unbound r5.9.3 on iso v1. It ended ok: 6 of 6 pairs valid, 2.0004-2.0040 s apart; the 12 frames re-hashed equal to the record; every option read back; 8 reloads; recorded on 89d4686, the tree clean.
  - Its pairs: the hello pack's three identical (`compare`); Unbound's three moving (TAA), REVIEW (FLIP mean 0.0099, 0.0143, 0.0137). The weather's 120 ticks were stepped at coverage_items; coverage_beacon's own 100 at its pose, after creative and the GUI.
- The first prep (prep-bench_263-20261022-180041, 15:00:41) failed at its first gamerule, before Chunky: the prepared snapshot answered "Game rule advance_time is already set to false" (a failure), which gamerules() refused. Fixed in 89d4686, then rerun: three launches, not the prompt's two. No snapshot was taken by the failed one.
- The site: a smooth-stone floor at y 100 over x 306..322, z 1061..1077, near (314, 1069). Its three views lie 531.9-532.9 blocks (Chebyshev) from the nearest overworld perf view (ocean_sunset); the snapshot's chunks under it (15..23, 62..70; chunk 20 full, 21-23 initialize_light) reach y 83 at most.
- What each item shows (Claude's pre-screen of m3-coverage-1's frames and prep's Unbound-default frames):
  - coverage_items: the enchanted golden apple, plain gold in the hello pack, glint-tinted with a pink rim in Unbound. The dropped diamond stands edge-on. The item frame holds the diamond sword on its spruce planks. The sign reads "Optilux / coverage", sharp at 4K in both packs. The armor stand wears the iron helmet and diamond chestplate. The fox and the polar bear's flank show at the right.
  - coverage_mobs: the fox, polar bear and mooshroom (its mushrooms drawn) in noon sun, the armor stand close at the left, the campfire's logs and flame at the right edge.
  - coverage_beacon: the beam rises from the beacon on its iron base to the top of the frame in both packs. The campfire's flame shows in both, its smoke only in Unbound (BENCH_DETERMINISTIC discards particles: the exempt item). The mooshroom stands at the left, and the held torch at the bottom right (creative; frames come before the GUI pass, so no hotbar). Unbound also draws the player's own shadow at the bottom centre.
  - Every coverage item is in its frames, so section 7's stop does not apply. The hello pack shows no glint on the apple; see Open questions.

## What changed
- e215b49: the views file's `coverage` list (record.load_views, check_view, COVERAGE_KEYS hand and ticks, COVERAGE_APART 512 by Chebyshev over x and z per dimension, every_view, coverage_views); visual runs of mode `coverage` (VISUAL_MODES, `verify records`); measure.arrive's `hand` (D49's GUI and creative) and own `ticks` after the weather's; bench_263's three coverage views.
- 8924692: world prep's coverage step (build_coverage: the site's old tagged content waited for and killed, the kill, fills, setblocks and summons through `command`, coverage_counts and coverage_problems after the build and after the sweep); its selection, functions, views loop and sweep over every view; the End views' functions also run `time of minecraft:the_end set <time>`, read back at each End view (parse_clock); session.shows_hand; measure.stale_functions over every view.
- 89d4686: gamerules() takes "Game rule <name> is already set to <value>" as set; the read-back decides.
- 2c565f8: m3-coverage-1's record; suite.json coverageViews' status.
- Docs: measurement.md#baseline-suite (coverage views, prep's coverage step and End clock; session step 5; cut: the buried-camera aside, prep's pack.mcmeta and Chunky-line detail, the tag bullet (suite.json world.setup holds it), step 5's held-item rationale, the GPULatency and display-state definitions, the CTRL_C aside, Readiness' fields line); run-record.md#run-spec (mode coverage); CHANGELOG.md 0.4.0 (one bullet).

## Review
The reviewer agent on world.py's changes and the views file (correctness): 6 findings, 1 medium and 5 low, each read at its source.
- 1 (medium) held and is fixed: the old content was read once, before its entities could load; it is now read once a second for up to 10 s, and a kill must leave none.
- 2 (low) is fixed: a view's own ticks outside the overworld left the ramp stale, in prep and measure.arrive.
- 3 and 4 hold as built: `execute if block`'s bare "Test passed" (ExecuteCommand.addConditional) and `time of <clock> query time` (TimeCommand, en_us.json), both by javap of the 26.3 jar, then live in this prep.
- 5 did not hold: chunk 20 under the floor's east strip is full in the old snapshot.
- 6 is partly fixed: the ticks' order is now recorded, and the dragon-fight guard is tested; session()'s order stays untested (Weak points).
- The kill sparing the content, the counts and the selection were found to hold.

## Choices
Neither the prompt nor the plan names these:
- A visual run takes the coverage views by `mode: "coverage"`, a visual-only mode, not a suite.json mode: perf modes and the suite's identity unchanged.
- The poses came from geometry, not flight (no input is sent): a floor at a fixed y 100 over the measured terrain, each item's place in frame computed for fov 0.5 at 16:9; prep's frames confirmed them. The poses went in with the loader (e215b49), so the launches ran on a committed views file; 2c565f8 carries no pose change.
- The content:
  - three passive mobs that Peaceful summons: mooshroom, polar bear, fox;
  - the armor stand in an iron helmet and diamond chestplate;
  - the item frame (Fixed, with Pos and block_pos, so no "invalid position" log line), holding a diamond sword on planks;
  - a dropped diamond and an enchanted golden apple, whose glint needs no enchantment data (NoGravity, Age -32768, PickupDelay 32767);
  - an oak sign facing north, a beacon on 3x3 iron, a lit campfire.
  - Every entity carries PersistenceRequired (only mobs read it); summon coordinates are decimal, so the command never centres them.
- `hand` is a boolean (creative and the GUI, the snapshot's torch); `ticks` is 100 at coverage_beacon, since the beacon sets its level on a game tick divisible by 80 (javap).
- Counts: entities by selector in the site's box (the two items told apart by nbt), 17 blocks by `execute if block` (the floor's corners, the base's nine, the four blocks), the sign read back.
- A scratch display hold (the harness's request, scratchpad hold.py) ran 14:41:50-15:15:45 over both preps and the visual run.

## Checks
- Start (14:04 ADT): branch m3 clean at f057558; 947 passed; verify docs 0 violations.
- Before each commit, on a tree equal to it: 962, 975, 976 and 976 passed; ruff, ruff format and pyright clean; verify docs 0 violations; verify records 229 records, 0 violations.
- The first full run before e215b49 failed one test (962 items) that the passing reruns cleared from pytest's cache before it was named; five reruns and every later run passed. Runs since list failures by name (`-rf`).
- CI green on e215b49, 8924692 and 89d4686, each watched to its end before the next push or launch; 2c565f8's watched before this handoff's push.

## Open questions
- The hello pack shows no glint on the enchanted golden apple: plain gold, its pair identical. Unbound draws the glint, which runs on the wall clock (TextureTransform.setupGlintTexturing: Util.getMillis x glintSpeed). Whether the hello pack's glint fallback (textured, P14) draws nothing or draws without the texture matrix is for M4's coverage list.
- Moving under /tick freeze across launches (D64, named in suite.json): the dropped items' spin (ItemEntity.bobOffs, random at each load, not saved: javap), the campfire's smoke, the glint where drawn. One visual run, so the cross-launch differences are unverified.
- Unbound on iso draws no shadow under the coverage mobs; the frame's block and the sign keep theirs. A profile look note.
- Carried: the hello pack's olive End stone; whether 26.3 animates textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; the water fog colour (M3.P09); D66, the driver; D72; the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- session()'s order (the build after Chunky, the counts after the sweep, then positions) is tested only by this prep's own run, not by a test.
- A rebuilt site (a later prep on this snapshot) is untested live: the old content is waited for, killed and must leave none, on the fake alone.
- Margins: measurement.md 20 bytes; platform.md 7; AGENTS.md 16; mod.md 62; workflow.md 199.

## Commits and time
- e215b49, 8924692, 89d4686, 2c565f8; then this handoff.
- 2026-10-22 14:04-15:25 ADT: about 1.4 h against 2.5 h. Tripwire: actuals about 57.2 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1, P07 1.4); the trip at 174.6 h.

## Next
/optilux-next prints M3.P08's prompt: check L1 and L2, 3 h, 2 launches (dump runs); the world is the new snapshot 1b081885..., so every later run and M3.P10's calibration take it.
