# Handoff
Status: the latest stop: M2.P01, the run identity built before the launch and `run --check`, and what M2.P02 starts from.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P01
- The identity is built before the launch from the files the session will use: `harness` (plans/m2.md D36), options.txt's 174 unwritten keys in `settings` (D37), `system.hags` from D3DKMT's WDDM 2.7 caps (D38), referencePacks, worldPrep and shaderPack out (D39), the launch spec, the views file and the JDK's release file hashed before the launch, `world` from the snapshot; suite.json display's ten unread copies removed (id8). F21's rows owned by M2.P01 are done; the render target stays M2.P02's (D38).
- Exit held: `uv run optilux run <scratchpad>/m2-p01-check.json --check --json` (acceptance, views and world bench_263, items A10, A2, A3) exited 0, stderr empty: ok true, launched false, the 11 keys, `system.hags` true, `harness` with 14 modules and PresentMon's sha256 and arguments. The JVMs before and after were the editor's four (same pids), none under runtime/; 1,216 files under runtime/mc-26.3/game/ and results/ unchanged in size and mtime.
- The identity printed: platform 3bc69860... (bench); launchSpec 9bd33805...; mods 4 (the helper c971da15...); world snapshots/bench_263 fc515d35..., 104 files (P11's); views 9b05721e...; resourcePacks standard, Faithful bc534dfb...; settings 24 written options, 174 unwritten, iris without shaderPack, token true, Sodium bf6988db...; suite 04f35104...; java jdk-25.0.4.1+1, 25.0.4.1+1-LTS, release file 86e5e516..., 6144 MiB; system RX 7800 XT, HAGS on, 3840x2160 exclusive fullscreen, build 26200; harness 14 modules, PresentMon-2.6.0-x64.exe b2a706bc....
- The live D3DKMT read: caps 0b1011 (supported, enabled, not by default: P15's), HwSchMode 2, adapter LUID 0x11d82 (P15 read 0x11d94; a LUID changes per boot, so it is recorded, not matched).

## What changed
- optilux/record.py: IDENTITY_KEYS gains `harness` (module_closure reads optilux/verbs/run.py's imports with ast, deferred and relative ones included); platform_identity drops PLATFORM_OUT; java_identity reads and hashes the release file before the launch; settings_identity; launch_differences; the D3DKMT reader (wddm27_caps, Machine.hags); system_facts records the caps, the LUID and HwSchMode (None when unset, `unread: ...` when its read fails).
- optilux/launch.py: wanted_mods, planned_options (read only) and settings_facts, shared by the launch and the identity; optilux/presentmon.py: arguments().
- optilux/verbs/run.py: prepare() (every check before the live world, and the identity; nothing written); perform holds the launch's jars, packs and settings and the config files read again against the identity before the mod opens, then hello's Java; a difference ends the game and records identity null, status failed; `--check [--json]`.
- config/suite.json: display's vsync, fpsLimit, fov, viewBobbing, renderDistance, simulationDistance, guiScale, mipmapLevels, biomeBlend and graphicsPreset removed (optionsTxt holds them), windowKeys renamed windowWhy (a note); the suite hash moved, no calibration existing. recorded.optionsTxt keeps the hash only.
- Docs: run-record.md (Record, Identity, Run spec), measurement.md#calibration's identity list, CHANGELOG's 0.3.0 entry.

## Checks
- At the start: branch m2 clean at e10ea0f, 449 passed, verify docs 0 violations.
- At the end: `optilux test` 467 passed (466 at the first commit); ruff and pyright clean; verify docs 0 violations. CI: 41df571 green; on 8d6d7e9 ruff, pyright, the tests and verify docs passed and `pack release --check` failed ("HEAD (8d6d7e9) is no branch tip on origin"): 41df571 was pushed before that step ran, so no rerun can pass it.
- Tests added (tests/test_record.py): a changed unwritten key moves the identity, the pack does not; a measured module (presentmon.py), PresentMon's flags and bytes move `harness`, an edit to verbs/status.py does not; the runner's closure (14 modules) and a fixture tree's; the D3DKMT reader on a fake gdi32 (type 70, size 4, the close after a failed query, none after a failed open); HAGS from the caps, HwSchMode unset and unread; the platform cut; the release file; prepare writing nothing, each refusal naming its fix; perform with the launch faked: a contradicting launch and a config file changed under it record identity null and end the game, a failed mod session keeps the identity; `run --check` printing and launching nothing; IDENTITY_KEYS equal to run-record.md#identity.

## Review
The reviewer agent twice: correctness (7 findings, all low) and identity against run-record.md (10, one medium); each read at its source.
- Fixed: the launch's facts were held against the identity only after `open_mod`, so a failed mod session kept a contradicted identity (both readings): now right after the launch; files launch reads again were never held against prepare's reading: `reread`; the Java refusal named the wrong fix: `optilux install`; any registry error read as unset: only a missing value; a stale docstring; perform's null path untested: three tests; the doc's "another verb's edit never forces recalibration" was false for verbs/install.py, which run imports: the doc says so; `settings.overrides` undocumented: listed; `--check`'s boundary written (launch's gate, pinned hashes and a saved pack settings file stay `run`'s).
- Left, below: cli.py outside `harness`; prose keys in the platform hash; statistics.schedule; irisTiers for every tier; the display's rate and count, game/config/'s other files, machine state.

## Open questions
- game/config/ holds sodium-mixins.properties (Sodium's default text, no override) and iris-excluded.json beside the two files launch writes; neither is in a key, and a mixin override would move frames under an equal identity. Hashing or writing them is a decision before M2.P09's freeze; M2.P05 is the natural phase.
- The display's refresh rate (240 Hz) and attached-display count are recorded, not matched, with no reason written; D42 (M2.P05) covers the second display's GPU load; whether the rate moves GPUBusy is unmeasured.
- Machine state beyond the five system facts (power plan, driver settings such as Chill or Anti-Lag) is in no key; drivers are assumed good (design.md#7-decisions-taken-user-2026-10-05), their settings unstated.
- Carried: P9 (Chunky under /tick freeze, M2.P04); F10's startup call (M2.P05).

## Left alone
- cli.py is outside `harness`: the plan keeps verbs/status.py out, and cli's own code parses and dispatches; an edit to it after M2.P09 would not move the identity.
- verbs/install.py is inside `harness` (run, launch and session import its paths); moving them to a non-verb module would take it out; no phase after the freeze edits install.
- The platform file's prose keys outside the note set (tiers' purpose, pinSource, pinnedOn, loader.source) are hashed: a re-pin that edits pinnedOn moves `platform` despite D39.
- statistics.schedule is prose no code reads yet (M2.P05's schedule reads or replaces it); display.irisTiers is hashed for every tier, so a dev-tier override moves the bench `suite`.
- `--check` skips launch's own refusals, and `run` creates raw/<name>/ before them, so a launch refusal still uses the name (M1's behaviour; M2.P05's runner).
- The tree holds an uncommitted plan amendment that is not this phase's (user, 2026-10-12: M2.P03, P05 and P07 at 3.5 h, 25 h in all; plans/m2.md, prompts/m2.md, roadmap.md); it is in no commit here, and this handoff replaces the old one's lines that carried it.

## Weak points
- The ctypes structs follow d3dkmthk.h from memory, checked by the live read's 0b1011 equal to P15's; a positive informational NTSTATUS from the open would raise before the close.
- `harness` hashes module bytes: after the freeze a comment in a measured module forces recalibration.
- An unwritten key the game rewrites between sessions would split identities; P14 saw the 174 steady across two sessions.

## Commits and time
- 8d6d7e9 feat: build the run identity before the launch, with the harness; 41df571 feat: add run --check to print the identity without a launch; this handoff. Each pushed alone, the second before the first's CI ended (Checks); from here each push waits for the previous run.
- M2.P01: 14:27 to about 15:05 ADT, about 0.6 h against 2 h.
- Tripwire: M0-M3 summed 69.3 h, the trip at 138.6 h (with the tree's amendment 70.8 h and 141.6 h); actuals about 27.7 h (M0 3.3, M1 20.3, M2.P00 about 3.5, M2.P01 about 0.6).

## Next
/optilux-next prints M2.P02's prompt: window.measure and the jar's M2 rows, 2.5 h, 1 launch.
