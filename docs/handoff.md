# Handoff
Status: the latest stop: M4.P04 RenderDoc captures stopped before its exit on branch m4 (the user away for some hours): the debug tier's launch, `run`'s capture kind and view lists built, reviewed, committed and pushed; both debug-tier launches ended before any F12, a Windows Defender Firewall prompt over the game. M4.P04's exit is next.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P03
- M4.P04's Exit did not hold in this session (2026-10-28, ADT): no capture run ended ok, no .rdc taken. Its changes are committed and pushed; only the exit run, its record commit and this handoff's successor remain.
- m4-capture-1 (15:56-15:57 ADT, after the displays were woken at the user's request by a 1-pixel SendInput nudge): the debug tier launched as built (the command line held, its two properties checked, gfx-debuggers' log: RenderDoc loaded from the pinned dll at 15:56:12, renderdoc.dll sha256 809da38e3867...), then "001 forest_noon hello: the game is not focused, its window not in front or a screen open (foreground pid 3204, the game's 11996): no F12 sent"; status failed, the game quit by WM_CLOSE (exit 0).
- The cause, read at the source: pid 3204 is PickerHost.exe, started 15:56:12, owning a "Windows Security" Shell_SystemDialogProxy window; the firewall log (event 2097, 15:56:12) added "Query User" TCP and UDP rules for runtime/java/jdk-25.0.4.1+1/bin/java.exe: RenderDoc opens its target-control listening socket when it loads, and Windows raised its firewall prompt over the game. Answering it changes firewall rules, a system setting: the user's (the user, 2026-10-28: "If you can't approve the firewall, wait").
- m4-capture-2 (16:04-16:05 ADT) with A2's focus step before each press (the user's choice, 2026-10-28; d4a8645): "SetForegroundWindow -> 0", "the window at (1280, 720) is pid 3204's: no click", no F12 sent; failed, the game quit (exit 0). The prompt is still open on the bench PC.
- P23 (F12 through SendInput) is therefore still open: no press has reached a RenderDoc. %TEMP%\RenderDoc\ exists (RenderDoc made it at load: the folder the run watches); its log is gone with each game.

## What was built
- Re-pin (the user's, 2026-10-28, plans/m4.md section 7's first stop): `install --tier debug`, needed for gfx-debuggers' jar, fetched Mojang's republished 26.3 version JSON (only its asset index moved: 142 language files and pack.mcmeta); `install --refresh` rewrote config/platforms/mc-26.3.launch.json (4 facts); tests/test_platform.py builds the spec from that JSON (26.3-5df1795e.json, LATEST). launchSpec moved in the identity; M4.P09 recalibrates.
- The debug tier (D81, P8): the platform file's `jvmProperties` (`debugger=renderdoc`, `renderdoc.path` the pinned renderdoc.dll itself: gfx-debuggers 3.2.0, javap, System.loads it at preLaunch in the game's process on Windows and falls back to RENDERDOC_PATH and Program Files when the path holds none); platform.jvm_properties checks them; launch.tier_properties resolves a path under the repo, refuses a missing file (also at `run --check`), hashes it; build_command passes them after the token, refusing the token's or the spec's names; command_facts holds each to the started line once before the main class. suite.json's irisTiers.debug sets enableDebugOptions true.
- `run`'s capture kind (record.CAPTURE, debug tier only, every other kind bench only; measure.capture_body): RenderDoc's load read in latest.log (one "Found" line naming the tier's dll, the load's time); the visual run's steps to the settle; A2's focus step; RenderDoc's folder (GetTempPathW's RenderDoc, RunHost.rdc_folder) checked for strays; F12 held 0.25 s through SendInput (sendinput.key_hold, the up retried) via acceptance.inject with input.block on; the game still in front and frames presented; take_rdc: the one new `java_<minute>_frame<n>.rdc`, its minute the load's or the one before, moved under raw/<run>/rdc/<view>/<variant>/ once no other handle holds it (RunHost.unheld), header RDOC, hashed; no file in 30 s fails the run (P23); D42's check and the displays refused off. The record: a visual record's fields with each capture's `focus`, `press` and `rdc`; `verify records` (rdc_problem, capture_problems), `report` (its capture table) and `compare` (refused) know it; an orphan keeps its captures.
- View lists: a visual or capture spec's `mode` may list view ids, perf or coverage (record.listed_views), so two packs fit the reload cap over two runs at every view; verify holds an ok record to its list.
- Docs: platform.md#mod-tiers (the Aperture facts research/iris.md holds cut to a pointer), run-record.md#run-spec (the capture paragraph, the list; the AGENTS.md Terms bullet and the report-summary list cut), offline.md#tools (captures and their record), design.md#5-interfaces' run row, CHANGELOG.md's 0.5.0 bullet.

## Review
The reviewer agent on the launch and capture changes: the command-line check held; 1 medium and 11 low findings, each read at its source:
- Fixed (64a5cf1): a late second capture taken by the next press (rdc_strays, between presses and 2 s after the last); an .rdc not tied to this game's RenderDoc (the load minute from latest.log); F12 lost to another window during the hold (the front re-checked); a refused key-up (retried, UP_TRIES 3); every missing file blamed on P23 (frames presented checked, the message names RenderDoc's log); seconds not from the press; properties read twice (Sequence); an orphan's candidates without their option values; the move of a file RenderDoc still writes (RunHost.unheld: CreateFileW sharing nothing); the notes on renderdoc.path (both forms work).
- Kept: the dll's bytes are recorded per launch, never pinned (tools.json pins the zip; identity holds the path); renderdoc_loaded reads the whole latest.log, which log4j rolls at each start, and refuses two "Found" lines.
- Found running it: `run --check` printed a measured line for a capture spec and an orphan's capture record was summarized as a measured one (both fixed, 64a5cf1).

## Checks
- Start (14:42 ADT): branch m4 clean at e8b825d; 1083 passed; verify docs 0 violations.
- Before each commit after the first: `optilux test` green (last 1105 passed), ruff and pyright clean, verify docs 0 violations, verify records 0 violations (397 with the two failed records).
- 7d93cd2 (the re-pin) was committed and pushed with test_the_spec_from_the_newest_json_is_the_committed_spec failing (a `| tail` hid the exit code); its CI failed on that test alone; c13bdff fixed it. CI green on c13bdff, 60e8b4f, 8cf1509, 56f8d91, 4a5658b, 64a5cf1 and d4a8645, each watched to its end before the next push.
- tests/test_launch.py::test_logman_lists_sessions_on_this_machine failed twice in parallel runs ("The GUID passed was not recognized as valid by a WMI data provider", logman exit 2147946600) and passed alone 3 of 3: perhaps M3's unnamed flaky test.

## Deferred and logged
- `install` ran (the plan's ground rules allow it; the prompt's list of runtime/ writers omits it): no other path puts gfx-debuggers into the store.
- The displays were woken by a 1-pixel mouse nudge and back (sendinput.mouse_move), at the user's request; no setting changed.
- m4-capture-1 and -2 committed as failed records; three debug-tier launches would exceed the prompt's two (the user asked to rerun after the prompt is answered).
- displays_on's refusal still says "PresentMon records no frame" for a capture run, which uses none.

## Open questions
- The firewall prompt on the bench PC: the user's to answer (Cancel keeps java.exe blocked; RenderDoc works locally either way; Allow opens its port to the network). A new Temurin pin will prompt again.
- P23: F12 through SendInput reaching RenderDoc (D81's fallback: the mod's TriggerCapture, a jar change); P22 and P23's RGBA16UI and renderStage (M4.P06).
- From the last handoff: pinning gamma, Smooth Lighting and See-Through Leaves (the user's); M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- No capture has been taken: the capture size (Unbound at 3840x2160), RenderDoc's write time against RDC_TIMEOUT 30 s and RDC_WRITE_TIMEOUT 300 s, and the load-minute tie are unexercised in game.
- RenderDoc's target-control server listens on the network while the debug tier runs.
- From the last handoff: the hello pack's 800-1,250 fps; the displays held only from `run`'s start.

## Commits and time
- 7d93cd2 (the re-pin), c13bdff (its fixture), 60e8b4f (the debug tier's launch), 8cf1509 (the capture kind), 56f8d91 (key_hold's test), 4a5658b (view lists), 64a5cf1 (the review's fixes), d4a8645 (A2's focus step), then this stop's commit (m4-capture-1, -2 and this handoff).
- M4.P04: about 1.8 h of work against 3 h (14:42 to 16:30 ADT); not done. Machine: 2 launches, about 3 min.
- Tripwire: actuals about 72.0 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 7.8: P00 3.8, P01 0.6, P02 0.7, P03 0.9, P04 1.8 unfinished) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
Once the user has answered the firewall prompt on the bench PC and is at hand to wake the displays: the exit alone, in a fresh session or this one: check `tasklist` holds no PickerHost.exe "Windows Security" window, announce, then `uv run optilux run` a capture spec named m4-capture-3 (the hello pack at `optilux@HEAD` and Unbound at profile played, quick mode, tier debug), in the foreground with nothing beside it; if F12 captures nothing, P23 takes D81's TriggerCapture path; then the record's commit and the handoff with `Last phase: M4.P04`. /optilux-next still prints M4.P04.
