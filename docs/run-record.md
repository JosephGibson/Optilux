# Run record
Status: draft; the identity contract, the record's fields and the run spec, split from measurement.md on 2026-10-06. Measurement rules: measurement.md.

## Record
One JSON per session, failures included, committed under results/records/<name>.json. It is the ledger; there is no hand-written ledger.
- Self-contained: a record carries every number needed to re-judge its verdicts, as per-capture summaries. Frame-level samples and raw artifacts (PNG, npy, PresentMon CSV) go to results/raw/<name>/, ignored and disposable; the budget is ~200 KB per record (frame samples would add ~2.5 MB per session, est.). ALC's tracked cards cited ignored run folders, and those paths went stale.
- kind: measurement | calibration | acceptance. Acceptance runs carry `acceptance: [{item: A1..A12, pass, evidence}]` and no verdicts; calibration runs carry no verdicts.
- status: ok | invalid(reason) | failed(reason) | aborted.

## Identity
Every input that can move a measurement; matched key by key (AGENTS.md Terms). Calibrations match on it (measurement.md#calibration).
- platform: a hash of the platform file's loaded sections (everything but the tiers the session does not load), plus the mod tier; the whole-file hash is recorded, not matched;
- launch spec: the hash of config/platforms/<id>.launch.json (platform.md#install-and-launch);
- mods: sorted sha512 of every enabled jar (the platform file's algorithm), optilux-helper included;
- world: snapshot tree hash; views: the views file's hash (config/views/<world-id>.json); resource packs + hashes;
- settings: every game option in suite.json display, written by the harness before launch (key = value), plus the hash of Sodium's options file. Shader options are never identity: they are variant fields (below);
- suite: a hash of display, modes (views and rounds per mode), capture, validity and statistics, with note and ALC-context keys (`why`, `*Why`, `status`, `estMinutes*`, `alc*`) stripped, so editing a note or an estimate never forces recalibration while a changed view list or round count does;
- java: runtime, version, heap, args (the profile's flags only: `-Doptilux.token` is fresh per launch and the spec's JVM options belong to the launch spec), all checked against the started process;
- system: GPU, HAGS, resolution, window mode, Windows build number (the update revision is recorded, not matched, like the driver).
- Recorded but never matched: the whole options.txt (Minecraft and the harness both write it), the graphics driver (assumed good, user 2026-10-05), the harness version.

## Fields
- identity (above) and calibration id.
- offline: closures and predictions, each with its method and evidence (offline.md#decision-powers).
- per variant, the variant fields (they may differ between compared runs): pack tree hash + effective option values read back after reload.
- per capture: view, variant and its role (baseline | candidate | twin), round, sequence index, the summaries (median GPUBusy, median and p95 FrameTime, frame count, halves, PresentMode, per-pass timer medians, dropped timer frames), frame hashes, validity flags. Raw artifacts are referenced by run name and capture index.
- verdicts and cost rows (measurement.md#verdicts-and-cost-rows), each with the view set and thresholds it used.

## Comparison
- Comparable = identity equal; only variant fields differ. `compare` refuses otherwise and names the field.
- Declared treatment: an experiment may name one identity field as its treatment (mod presence, JVM runtime and args). `compare` then lets exactly that field differ. Such a field cannot change inside a session, so the experiment uses launch-level bracketing and launch-level null calibration (jvm.md#protocol); the in-session thresholds never judge it.

## Run spec
The input of `run`: name (unique, `[a-z0-9-]{1,40}`; `run` refuses an existing name), kind, mode, views, variants (pack + profile), tier, resource-pack set, treatment (declared-treatment experiments only), notes.
- `run` validates it before launching: views exist, variants build, identity matches, a measurement run has a matching calibration, the reload budget holds (measurement.md#session), nothing else holds the GPU; errors name the fix.
