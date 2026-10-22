# Handoff
Status: the latest stop: M3.P06 stopped before its exit run, the static-textures pack, the deterministic set, the visual kind and the tiers built, reviewed and committed; `install` found 26.3's version JSON republished, so the launch spec differs and the exit's launch waits on the user's re-pin.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P05
- Stopped (plans/m3.md section 7: "a launch spec that differs (the user re-pins)"; the prompt: a Done-when not met): `optilux install` (04:28 ADT) built the static-textures pack, then reported "launch spec: differs from config/platforms/mc-26.3.launch.json in 4 facts". Mojang republished 26.3's version JSON: sha1 11f1aefe... -> 61fff131..., asset index 34 sha1 e787e8af... -> 0c8f43b2..., the two URLs with them; install fetched the new JSON, index and 144 files, the client jar and every classpath jar unchanged (5,246 hashes). `launch` now refuses: "asset index runtime/mc-26.3/assets/indexes/34.json: sha1 0c8f43b2... differs from e787e8af...". No launch was made: the exit's run m3-visual-1 (spec in Next) did not run, so its status, frames, read-back options, hello-pack pairs, `compare`'s tiers and review.html on real frames are not shown.
- Shown in this session:
  - the static pack: optilux-static-textures.zip over 26.3.jar and Faithful 64x - Release 15.zip, 63 animated textures held on frame 0, 6 at their set frame size (conduit wind and wind_vertical 256x128, four gui sprites), 15,721 bytes, sha512 afc28c9093bc3b2aba0e719dd300e27b0cd101ee6ee9e865ebe71e1dfca5bec2c0364b596a7021d006ee033b7e5d844b6e8bae6e93d4fecb70abb28da3c63933, in the store and game/resourcepacks/ (a second install: state equal);
  - `run m3-visual-1 --check` holds: 8 reloads on forest_noon, nether_crimson, end_dragon, aligned on cycle 1; optilux.zip from shader/, 25 entries, sha512 d86371b78b24b77ff53a2e072f1ab39e419287475ee9a7944a09c29d1683fb154197740afc8eef2e30476084b11e02a22f2e666e547f9e478ed5199c085636d4, `check L0` ok; the identity's resourcePacks the deterministic set: Faithful 64x bc534dfb..., the static pack afc28c90....
- runtime/ written only by install (the static pack, the republished version JSON, index and assets); no launch, no system setting.

## What changed
- The static pack (dcb4d9b): install's static_textures and static_pack. Per texture whose metadata, the top one from the top pack down to the texture's provider (P11), holds an animation: that metadata with frames [0] at its width and height, its other sections kept; read as Gson reads it, the first JSON value (Faithful's friends/background_dark.png.mcmeta ends in a stray byte). pack.mcmeta min_format and max_format [97, 1]; packzip's zip rules; built when one suite.json set names it, last.
- The set (79cc518): record.PACK_SET deterministic; launch.set_packs (pinned packs by slug, the static pack by the store's sha512), packs_line (vanilla, then file/<name>, as Gson writes it), resourcePacks written from the set (display.optionsTxt drops its line; no `--set` of it), check_packs in the set's order; run's identity from the set; an unknown set and another set refused apart.
- The visual kind (d70f0d0): record (check_visual_spec, check_visual_variants, optilux_build), run (each Optilux zip built and L0-checked once, pipeline_cycle, visual_before, visual_session, visual_fields; no D42; displays held, never refused off), measure (visual_body, visual_capture, visual_problems, the orphan path, displays_on's refuse_off), session.visual_settle, modclient.check_schedule's interval, the fake (intervalMs; frames painted by pack and pose; `moving` packs), verify records' and report's visual records. Tests 918 to 939.
- The tiers (fc2269b): optilux/visual.py (fidelity, decode, tier, plan, unmatched, lines, page), compare's visual path and `--against`, suite.json fidelity's numbers. Tests to 946.
- Docs: measurement.md (set, visual capture, tiers, review page; Placement, the budget run's reads, the calibration refusals and the deps list cut as duplicates of suite.json and run-record.md), run-record.md (Status, identity, record, comparison, run spec), platform.md (install, options.txt), AGENTS.md (visual.py), CHANGELOG.md (two bullets).

## Review
Two reviewer agents, each finding read at its source.
- Session and identity: 11 (2 medium, 9 low). Fixed: 1 the pair's 2 s unchecked (check_schedule refuses a frame under intervalMs after the one before); 2 `--against` silent on pairs one run lacks (fixed with the tiers); 4 the orphan record (problems stripped, builds and L0 journaled, each visual variant's options in full); 5 a second ref of one commit took the first's build; 6 visual_sha512's default; 7 the cap's fix text; 8 report's options column; 9 verify passing an ok visual record lacking a pair; 10 the fake's 256-frame period; 11 timers false refused. Reported: 3 (Weak points). Identity: the set's packs reach launch_differences in one order (holds); the line in Gson's form (holds harness-side, the game's side unverified until a launch, read_back judges it); visual.py outside run's closure (holds, test_visual pins it).
- Tiers and compare: 9 (1 medium, 8 low), all fixed: 1 as 2 above, and `--against` refused when no pair matches; 2 close decided unrounded, printed to 7 digits; 3 ppd 0 (FLIP exits the process) and a float near refused; 4 frame paths held to the run's shape (Windows forms) and a record's name to its file; 5 `--against` itself refused; 6 a moving pair's second frame on the page; 7 one reading of valid; 8 fixtures failing close on p99.9 alone and SSIM alone; 9 the CLI through the fixture root, `--json` and the untested refusals. Outside its dimension: run-record.md#comparison, updated.

## Choices
Neither the prompt nor the plan names these:
- The code commits went on after install's stop: they need no launch and change no pin; the stop holds the launch.
- A held .mcmeta keeps the provider's other sections (kelp's texture.alpha_cutoff_bias 0.1): replacing the file would move the alpha cutoff.
- pack.mcmeta's formats [97, 1], world.py's data-pack form at the platform's resource format.
- A visual pair is one frames.capture (count 2, intervalMs 2000, align phase 0 on config/pipeline.json's cycle, ready with the view's visual settle, +3 s for the first variant after a dimension change); the 30 s GPU warm-up kept (measurement.md#session's start).
- A visual run holds the displays on, never refuses them off (frames are read back: m3-capture-1's selftest read 3840x2160 with them off), waits no D42, ends invalid on focus.lost or a foreign screen.
- `moving` by the pair's PNG sha256; compare's pair tier by decoded pixels; variants' roles baseline then candidate.
- suite.json fidelity's tiers as numbers (not identity).

## Checks
- Start (03:41 ADT): branch m3 clean at 7e4536b; 908 passed; verify docs 0 violations.
- Before each commit, on a tree equal to it: 916, 918, 939, 946 passed; ruff, ruff format, pyright clean; verify docs 0 violations; verify records 226 records, 0 violations.
- CI green on dcb4d9b, 79cc518, d70f0d0, each watched to its end before the next push; fc2269b's watched before this handoff's push.

## Open questions
- The re-pin (user's, section 7; D20 the precedent): `uv run optilux install --refresh`, then commit config/platforms/mc-26.3.launch.json. Recommended: yes, as in D20: nothing is calibrated on the deterministic set yet (M3.P10 recalibrates both modes), only the asset index moved, and a spec off Mojang's JSON fails every later install; the identity's launchSpec moves with it.
- Carried: the display guard for A9; Nether fog and the features on neither list; the water fog colour (M3.P06, M3.P09); D66, the driver; D72; the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- Session review 3: every variant aligns on the working tree's pipeline.json cycle; an `optilux@<ref>` commit's may differ. Every M3 cycle is 1.
- Unverified in game until a launch: the options line in Gson's form and the pack's [97, 1] formats (an incompatible pack leaves the line: read_back fails the run), and `moving` by sha256 (the game's one PNG writer assumed to write equal pixels as equal bytes).
- Margins: measurement.md 2 bytes; platform.md 7; AGENTS.md 16; mod.md 62; workflow.md 199.

## Commits and time
- dcb4d9b the static pack; 79cc518 the set; d70f0d0 the visual kind; fc2269b the tiers, compare and the review page; then this handoff.
- 2026-10-22 03:41 to about 04:55 ADT, 1.2 h against 3.5 h, the exit still to run. Tripwire: actuals about 54.9 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, P01 0.8, P02 0.8, P03 1.9, P04 1.9, P05 1.4, P06 so far 1.2); the trip at 174.6 h.

## Next
After the user's re-pin and its commit, M3.P06's exit, announced, the machine left alone: `uv run optilux run <spec> --check`, then `uv run optilux run <spec>`, `uv run optilux compare m3-visual-1` and `uv run optilux report m3-visual-1`; the record committed (`chore: add the visual run`), then this file with `Last phase: M3.P06`. The spec, m3-visual-1.json:
`{"name": "m3-visual-1", "kind": "visual", "mode": "quick", "views": "bench_263", "world": "bench_263", "variants": [{"id": "hello", "pack": "optilux", "profile": null}, {"id": "unbound-iso", "pack": "ComplementaryUnbound_r5.9.3.zip", "profile": "iso"}], "tier": "bench", "resourcePacks": "deterministic", "notes": "M3.P06's exit: the hello pack (its pairs identical, lava in sight at nether_crimson) and Unbound r5.9.3 on iso v1 (TAA: its pairs move), on the deterministic set"}`
