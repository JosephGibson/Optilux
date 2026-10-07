# Run record
Status: draft; the identity contract, the record's fields and the run spec, split from measurement.md on 2026-10-06; measurement rules: measurement.md. As built, 0.01.08 and 0.01.09: optilux/record.py (the spec's checks, the identity, the writer, the tree hash) and `run` for acceptance runs; measurement and calibration records come with M2.

## Record
One JSON per session, failures included, committed under results/records/<name>.json. It is the ledger; there is no hand-written ledger.
- Self-contained: a record carries every number needed to re-judge its verdicts, as per-capture summaries. Frame-level samples and raw artifacts (PNG, npy, PresentMon CSV) go to results/raw/<name>/, ignored and disposable; the budget is ~200 KB per record (frame samples would add ~2.5 MB per session, est.). ALC's tracked cards cited ignored run folders, and those paths went stale.
- kind: measurement | calibration | acceptance. Acceptance runs carry `acceptance: [{item: A1..A12, pass, evidence}]` and no verdicts; calibration runs carry no verdicts.
- status: ok | invalid | failed | aborted, with `reason` beside it. As built: ok only when every item passed; invalid on a `hook.error`, a hook failure in the session's latest.log (one before `hello` sends no event) or an Iris load failing outside `shaders.reload`; failed when an item failed or the session broke; aborted on the user's stop. A session that failed before its identity was read records `identity: null`, never with status ok.
- As built, an acceptance record also holds `spec` (verbatim), `startedAt` and `endedAt` (UTC), `recorded` (below), `variants`, `session` (the launch's facts, the mod's checks, every step's answer, the events with the step that was running, the quit, the request log's token check, the option files read back, A4's copy deleted) and `raw`; with `reloads` in the spec, `reloadTable` (F4: heap after GC and private bytes every 10 reloads, the growth per reload, each reload's seconds). A1's inert launch never measures: its facts live in A1's evidence, so the identity is the session launch's.
- Raw (0.01.08): requests.jsonl, session-latest.log, world-manifest.txt (the snapshot's file list), session-threads.txt (A1's control), a2/<view>/ (the capture attempts and the F2 screenshots kept), a1/ (latest.log, threads.txt); 0.01.09: a4/ (the recovery frame), a9/ (presentmon.csv and its log, the capture's capture.json; its PNGs deleted after the match), f4/ (each GC.heap_info).

## Identity
Every input that can move a measurement; matched key by key (AGENTS.md Terms). Calibrations match on it (measurement.md#calibration). One key each, in the record's order (optilux/record.py IDENTITY_KEYS; a test keeps the two equal):
- `platform`: a hash of the platform file's loaded sections (every top-level key, the tiers cut to the session tier's chain, the suite's note keys stripped), plus the mod tier; the whole-file hash is recorded, not matched;
- `launchSpec`: the hash of config/platforms/<id>.launch.json (platform.md#install-and-launch);
- `mods`: sorted sha512 of every enabled jar (the platform file's algorithm), optilux-helper included;
- `world`: the snapshot's tree hash (the sha256 of its manifest: one `<sha256>  <path>` line per file, sorted by path), its file count and the live world folder, which `run` checks equal to it before launching;
- `views`: the views file's hash (config/views/<world-id>.json);
- `resourcePacks`: the set (standard) and each pack's sha512;
- `settings`: every game option in suite.json display, written by the harness before launch (key = value), the iris.properties keys, `--set` overrides and whether the token was passed, plus the hash of Sodium's options file. Shader options are never identity: they are variant fields (below);
- `suite`: a hash of display, modes (views and rounds per mode), capture, validity and statistics, with note and ALC-context keys (`why`, `*Why`, `status`, `estMinutes*`, `alc*`) stripped, so editing a note or an estimate never forces recalibration while a changed view list or round count does;
- `java`: runtime, version (the JDK's release file, equal to the version `hello` reports), heap, args (the profile's flags only: `-Doptilux.token` is fresh per launch and the spec's JVM options belong to the launch spec), all checked against the started process;
- `system`: GPU (the primary display's adapter), HAGS, resolution (the primary display's mode read DPI-aware, D22; refused unless it is suite.json display.resolution), window mode (from the written options), Windows build number (the update revision is recorded, not matched, like the driver).
- Recorded but never matched (`recorded`): options.txt as the game reads it at launch, its hash and every key the harness does not write with its value (Minecraft and the harness both write the file; M2 decides what to match), the graphics driver (assumed good, user 2026-10-05; a run refuses when it cannot be read), the update revision, the display's rate and count, the platform file's hash, AMD's PresentMon (F2), the other JVMs the gate saw, the harness version (HEAD and whether the tree was dirty).

## Fields
- identity (above) and calibration id.
- offline: closures and predictions, each with its method and evidence (offline.md#decision-powers).
- per variant, the variant fields (they may differ between compared runs): pack tree hash + effective option values read back after reload. As built for a zip pack: its sha512 and `shaders.options`' values after the start-of-run reload.
- per capture: view, variant and its role (baseline | candidate | twin), round, sequence index, the summaries (median GPUBusy, median and p95 FrameTime, frame count, halves, PresentMode, per-pass timer medians, dropped timer frames), frame hashes, validity flags. Raw artifacts are referenced by run name and capture index.
- verdicts and cost rows (measurement.md#verdicts-and-cost-rows), each with the view set and thresholds it used.

## Comparison
- Comparable = identity equal; only variant fields differ. `compare` refuses otherwise and names the field.
- Declared treatment: an experiment may name one identity field as its treatment (mod presence, JVM runtime and args). `compare` then lets exactly that field differ. Such a field cannot change inside a session, so the experiment uses launch-level bracketing and launch-level null calibration (jvm.md#protocol); the in-session thresholds never judge it.

## Run spec
The input of `run`: name (unique, `[a-z0-9-]{1,40}`; `run` refuses an existing name), kind, mode, views, variants (pack + profile), tier, resource-pack set, treatment (declared-treatment experiments only), notes. As built (0.01.08), a JSON file with name, kind, views (the views file's id, also the snapshot's), world (the live world folder under game/saves/), variants, tier, resourcePacks, items, notes and reloads (F4's count, a multiple of 10); unknown fields are refused.
- `run` validates it before launching: views exist, variants build, identity matches, a measurement run has a matching calibration, the reload budget holds (measurement.md#session), nothing else holds the GPU; errors name the fix.
- As built for acceptance runs: kind acceptance only (no calibration needed), mode and treatment absent, the bench tier, the views file valid and its snapshot present, the world present and its tree hash equal to the snapshot's, one variant (the reference pack, profile null: the pack's defaults), the standard set, items among A1, A2, A3, A4, A7, A9 and A10, the session's reloads (two, A4's two, F4's) within capture.reloadCap, the display equal to the suite's; the launch gate is the GPU check.
