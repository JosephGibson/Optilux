# Handoff
Status: the latest stop: M3.P06 done, the static-textures pack, the deterministic set, visual runs and their tiers built and accepted (m3-visual-2), and what M3.P07 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P06
- The exit holds, shown in this session (2026-10-22, ADT): m3-visual-2 (13:26-13:28, announced, the machine left alone), a visual run on quick mode's views with the hello pack (`optilux`, optilux.zip sha512 d86371b78b24b77ff53a2e072f1ab39e419287475ee9a7944a09c29d1683fb154197740afc8eef2e30476084b11e02a22f2e666e547f9e478ed5199c085636d4, `check L0` ok) and Unbound r5.9.3 on iso v1:
  - status ok; 6 of 6 pairs valid, each two frames 2.000-2.007 s apart, every frame's PNG hashed and its sha256 recorded;
  - every option read back: options.txt's 24 keys (resourcePacks among them) and iris.properties' 5 after the quit; each variant's written options equal to their effective values after each reload (hello none written, its 1 option at its default; Unbound 48 of 398);
  - every hello-pack pair identical (forest_noon 80080902..., nether_crimson e027f4cf..., end_dragon 3ef4672d...), water in sight at forest_noon, a lava lake at nether_crimson; Unbound's three pairs moving (TAA);
  - `compare m3-visual-2`: per view the hello pair identical, the Unbound pair REVIEW (FLIP mean 0.086, 0.017, 0.061; SSIM 0.81, 0.99, 0.98), Unbound vs hello REVIEW; review.html and report.html under results/raw/m3-visual-2/;
  - the game loaded both packs (latest.log: `..., file/Faithful 64x - Release 15.zip, file/optilux-static-textures.zip`), with 63 "Unused frames in sprite" warnings, one per held texture.
- The static pack: 63 animated textures held on frame 0, 6 at their set frame size (conduit wind and wind_vertical 256x128, four gui sprites), sha512 ff44b3cc091747390108ff3acdfc6ba2a81adaebff181f250306ab7a2053279574d7792e762c7d93c4fb224f19ea27f9c7e5dd6522a711c0f48c118015529ee8, in the identity's resourcePacks after Faithful 64x (bc534dfb...).
- m3-visual-1 (11:30) failed before it: 26.3's resource reload threw "Dest texture (72x504) is not large enough to write a rectangle of 72x504" at particle/vibration.png and dropped every selected pack, so the session ran on vanilla textures; read_back caught it (resourcePacks read `[]`). Its hello pairs were identical too.
- The stop at 04:56 (Mojang republished 26.3's version JSON: 142 language files) ended with the user's re-pin (`install --refresh`, 4 facts). runtime/ written only by install, the runs' world restores, launches and the game; no system setting.

## What changed
- The static pack (dcb4d9b, fixed in 46f730f): install's static_textures and static_pack; per texture whose top metadata down to its provider (P11) animates, that metadata with frames [0, 0] at its width and height, its other sections kept; read as Gson reads it; pack.mcmeta min and max_format [97, 1]; packzip's rules.
- The set (79cc518): record.PACK_SET deterministic; launch.set_packs, packs_line, resourcePacks written from the set, check_packs in its order; run's identity from it.
- The visual kind (d70f0d0) and the tiers (fc2269b): plans/m3.md D63 as built (record, run, measure, session, modclient's interval check, the fake, verify records, report; optilux/visual.py, `compare --against`, review.html, suite.json fidelity's numbers).
- The re-pin (7c08e57, its fixture in 3e7e423), the records (ca01ba5 m3-visual-1, ee16c16 m3-visual-2).
- Docs: measurement.md, run-record.md, platform.md, AGENTS.md, CHANGELOG.md (two bullets).

## Review
Two reviewer agents, each finding read at its source. Session and identity: 11 (2 medium, 9 low), 10 fixed, 1 reported (Weak points); the set's packs reach launch_differences in one order, the line in Gson's form (shown in game by m3-visual-2's read-back), visual.py outside run's closure: hold. Tiers and compare: 9 (1 medium, 8 low), all fixed. The 04:56 handoff (git 3e075bf) lists each.

## Choices
Neither the prompt nor the plan names these:
- frames [0, 0], not D62's [0]: 26.3's createAnimatedTexture makes no animation of a one-entry list, and TextureAtlas.uploadInitialContents then writes the sprite's whole strip into a one-frame texture (javap of SpriteContents and TextureAtlas). Two entries keep the animated path, every frame frame 0; still .mcmeta alone.
- A held .mcmeta keeps the provider's other sections (kelp's alpha_cutoff_bias).
- A visual pair is one frames.capture (count 2, intervalMs 2000, align phase 0 on config/pipeline.json's cycle, ready with the view's visual settle, +3 s for the first variant after a dimension change); the 30 s GPU warm-up kept.
- A visual run holds the displays on, never refuses them off, waits no D42 and ends invalid on focus.lost or a foreign screen.
- `moving` by the pair's PNG sha256; compare's tiers on decoded pixels; suite.json fidelity's numbers (not identity).
- The code commits went on after the 04:56 stop; the re-pin and m3-visual-2 at the user's go (11:14 "continue to closeout"; the rerun chosen at 13:25).

## Checks
- Start (03:41 ADT): branch m3 clean at 7e4536b; 908 passed; verify docs 0 violations. Resumed (11:14): clean at 3e075bf; 946 passed.
- Before each commit, on a tree equal to it: 916, 918, 939, 946, 947 passed; ruff, ruff format, pyright clean; verify docs 0 violations; verify records 228 records, 0 violations. Except 7c08e57: pushed with test_platform red (the spec ahead of its fixture), fixed in 3e7e423; CI red on 7c08e57, green on 3e7e423.
- CI green on dcb4d9b, 79cc518, d70f0d0, fc2269b, 3e075bf, 3e7e423, each watched to its end before the next push; 46f730f's and ee16c16's watched before this handoff's push. ca01ba5, pushed with 46f730f, had no CI run of its own: its tree in a worktree passed 938, failing the 4 hook end-to-end tests HEAD's tree fails there too (HEAD 947 in the checkout).
- Double check (13:40): m3-visual-2's 12 frames re-hashed equal to the record, each hello pair equal in decoded pixels, each first frame the ready frame, every written option its effective value, the static pack's sha512 the store's and the game copy's.

## Open questions
- The hello pack's End stone reads olive-green at end_dragon (texture x vertex colour x the End's lightmap?), Unbound's pale; a look note for M4's pack, Claude's pre-screen.
- With ticks frozen, m3-visual-1's hello pairs were identical on vanilla's animated textures too: whether 26.3 animates textures on frozen client ticks (the static pack then guards unfrozen sessions and the TAA history) is unverified.
- Carried: the display guard for A9; Nether fog and the features on neither list; the water fog colour (M3.P09); D66, the driver; D72; the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- Session review 3: every variant aligns on the working tree's pipeline.json cycle; an `optilux@<ref>` commit's may differ. Every M3 cycle is 1.
- `moving` by sha256 assumes the game's PNG writer writes equal pixels as equal bytes (one writer); compare's pair tier judges the pixels.
- Margins: measurement.md 2 bytes; platform.md 7; AGENTS.md 16; mod.md 62; workflow.md 199.

## Commits and time
- dcb4d9b, 79cc518, d70f0d0, fc2269b, 3e075bf, 7c08e57, 3e7e423, ca01ba5, 46f730f, ee16c16; then this handoff.
- 2026-10-22 03:41-05:01, 11:14-11:38 and 13:25-13:50 ADT: about 2.1 h against 3.5 h, the user's re-pin and rerun waits apart. Tripwire: actuals about 55.8 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 2.1); the trip at 174.6 h.

## Next
/optilux-next prints M3.P07's prompt: coverage views, 2.5 h, 2 launches and the new area's generation; its visual run uses the visual kind as built here (the views file's coverage list joins the spec then).
