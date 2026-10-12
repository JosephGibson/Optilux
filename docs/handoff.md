# Handoff
Status: the latest stop: M2.P04, the world verbs and bench_263's preparation, and what M2.P05 starts from.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P04
- The snapshot: snapshots/bench_263/ retaken by `world prep bench_263` (prep-bench_263-20261012-214744): tree hash 65e7ae7326dda8a6e8d95c8812ca5ddaabd9dc7ca261d22bb8d93e91df5e22f9, 116 files, 154,256,843 bytes, player 51ff11bb-8719-3a7c-b3f6-cb4a2d1c5a79 (was fc515d35..., 104 files). `world restore bench_263` after it: live hash equal, copied 0, deleted 0, kept 116, checked against snapshots/bench_263.json.
- Exit held, two announced launches of the worldPrep set (bench + Chunky 1.5.3, fetched by `install`: 5,242 hashes, 1 download):
  - the first (pid 4796, joined in 17.2 s) stopped at ocean_sunset's kill: 238, 221, 28, 6, 5, 9 killed, 14 left after the six-kill cap; WM_CLOSE, no snapshot; its stepped ticks made debris (Review);
  - the second (pid 5648, joined in 13.2 s) restored the first's world (copied 59, deleted 12, kept 45, equal fc515d35...) and passed, quit exit 0 in 1.4 s.
- P9 answered: each task's end reached latest.log as the console's `[Server thread/INFO]: System chat: [Chunky] Task finished for <world>. Processed: N chunks (100.00%), Total time: h:mm:ss`, and Chunky progressed with ticks frozen; no `chunky progress` was asked, no fallback ran. Second launch: overworld rectangle (-169, 577) r 486x621, 4,977 chunks in 3 s; Nether (111, -153) r 408x457, 3,127 in 2 s; End squares (57, -19) and (318, 1055) r 289, 1,521 each in 0 s. Most chunks existed: the region tables grew 120, 293 and 243 chunks, all outside the selections, the neighbours generation writes around chunks brought to full.
- Every view function answered `Function optilux:view/<id> returned 1`, once before Chunky and once at its view (P10 live).
- Counts: entities seven tagged mobs, the same names and positions before Chunky and after the sweep (Chicken -368.04 76.0 249.51, Cow, Horse, Llama, Pig, Sheep, Villager); end_dragon ten end crystals, no dragon; end_city none of either.
- Kills (killed per round): forest_noon 156, 201, 2, 2, 3; ocean_sunset 43, 346; cave 12, 21; rain 11; nether_crimson 80, 10; end_dragon none; night 32, 119; underwater 2, 73; nether_soul 44, 3; entities 173, 274; end_city 23, 10 (its two shulkers among them); the sweep found nothing at all eleven.
- Eleven reference frames, 3840x2160, results/raw/prep-bench_263-20261012-214744/frames/<view>/attempt-001/: forest_noon 2583fef6, ocean_sunset f551d78e, cave b756e5af, rain 610e6fb6, nether_crimson 036a3a01, end_dragon 3d5679a5, night 39df6442, underwater 223813c7, nether_soul 3c4cf320, entities 034297bb (torch in hand, the seven mobs), end_city 02260de0. Looked at on a contact sheet only.

## What changed
- optilux/world.py: `snapshot` (a hidden copy hashed equal to the live world, swapped in, rolled back on a failed rename; snapshots/<id>.manifest and <id>.json beside it), `restore` (D44 in place), `prep`; verbs/world.py `world snapshot|restore|prep`; `run` restores before the session and before A1's launch; Platform.sets and entry give install and launch `--tier worldPrep`; launch.games split from the gate.
- Choices no plan or prompt names, taken here:
  - restore checks the snapshot against its facts when they exist and refuses one taken from another world than the one named; bench_263's old snapshot predated the facts and restored unchecked once;
  - pack.mcmeta min_format and max_format both [121, 0]; the functions run time and weather `execute in minecraft:overworld`;
  - selections in whole blocks rounded outward, an odd width made even; an End square's radius the larger of the two;
  - Chunky's world name read from its `World changed to` echo; an end read from `chunky progress` confirmed by `chunky continue` answering `No tasks to continue.`; a finished line below 100 % refused;
  - D45's re-run read as ticks unfrozen and the same task awaited (never ran);
  - every function called before Chunky (fail fast); the tagged mobs' positions read first, refused unless seven;
  - the kill: ticks only after a kill that took more than debris (item, experience_orb, falling_block), none and no such kill within 256 blocks of the dragon fight, at most ten kills, done at two zero counts 1 s apart, then a sweep of all views with ticks frozen;
  - weather ticks after `camera.place`; prep fails before the snapshot on a hook error, a stray answer, the helper log's failures, the token or a non-zero quit.
- Docs: measurement.md (World, World preparation, Session step 1), run-record.md (Identity's `world`, the record's `session`, Run spec), platform.md (world prep set, `--uuid`; margin 42), design.md#5-interfaces, AGENTS.md (11 bytes left), CHANGELOG's 0.3.0 entry.

## Checks
- At the start: 488 passed, verify docs 0 violations, tree clean on m2.
- At the end: `optilux test` 528 passed; ruff, ruff format and pyright clean; verify docs 0 violations. The first commit alone: 503 passed, all clean.
- Tests added (40): the tree hash and manifest, the snapshot's copy, uuid, swap recovery and rollback; restore on temp trees (changed, added, removed, file and folder swaps, a part file, a changed snapshot, another world, a missing live world); the function and pack.mcmeta bytes; Chunky's selections from bench_263 and its lines; the selectors and answers; the kill on a fake game; Chunky's end both ways, a stopped task, a stall, a short finish; `run` restoring before its launch.

## Review
The reviewer agent twice before the launch, each finding read at its source: correctness (5: 1 high, 1 medium, 3 low), failure paths (15: 6 medium, 9 low).
- Fixed: the overworld weather ticks stepped before `camera.place`, at end_dragon's pose for night (the dragon spawns); "No tasks running." ignored before an update and never checked for completion; the snapshot swap losing the old copy; restore into another world; the cleanup masking the session's error; hook errors and stray answers unjudged; positions read from messages alone; a kill sent beside the dragon fight; the restore before A1; unread lines after an echo dropped (found by a test).
- Found live: stepped ticks fire the block ticks generation left pending, so each 40-tick step after a kill made new debris (2 to 14 entities a round); the second launch's kill split them out.
- Left: below.

## Open questions
- For M2.P05: session.settle_view steps the weather ticks before `camera.place`, at the previous view's pose; in the views file's order night follows end_dragon, so a run on bench_263 would spawn the dragon. Place first (measurement.md#session's own order).
- For M2.P05: the snapshot keeps the pending block ticks; a session's weather steps fire them near the camera (falling sand, popped plants), the same after each restore but random in detail.
- The views file's end_city `why` names two shulkers the kill took (suite.json world.setup): the user's to reword.
- 1 or 2 entities other than debris appeared per round at forest_noon under ticks; their type is unread.
- world.py, prep included, is in `harness` (run imports restore): a prep edit after M2.P09 recalibrates.
- Carried: PresentMon's Composed: Flip (M2.P05 refuses such captures); unmatched pops; the residual (M2.P10); game/config/'s two files in no key; the display's rate and count; machine state; F10's startup call; window 1's start frame.

## Left alone
- Chunky's own config and task files under game/config/chunky/ (the game's).
- The first launch's raw folder prep-bench_263-20261012-214122 (no snapshot came of it).
- Path names Windows treats specially (a trailing dot, ':') in `--world`.

## Weak points
- One passing prep; P9's frozen half rests on 656 neighbour chunks, as nearly all selected chunks existed.
- The debris list comes from two views' entity files; positions compared at the 2 decimals `data get` prints.
- The frames were not reviewed by the user.

## Commits and time
- ed25642 feat: add world snapshot and restore, run restoring before a session; 70da6e9 feat: add world prep: Chunky, the kill, view functions, frames; this handoff. Each pushed after the previous one's CI ended green.
- M2.P04: 17:54 to about 19:05 ADT, about 1.2 h against 3 h.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 31.5 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2).

## Next
/optilux-next prints M2.P05's prompt: the measured session, 3.5 h (XL), 1-2 launches.
