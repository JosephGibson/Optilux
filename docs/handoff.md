# Handoff
Status: the latest stop: M4.P04 RenderDoc captures done on branch m4, committed and pushed: the debug tier launched with RenderDoc's JVM properties, `run`'s capture kind and view lists built and reviewed, the exit's capture run ok with one hashed .rdc per view and variant. M4.P05 is next.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P04
- The Exit of M4.P04 (docs/plans/m4.md) held in this session (2026-10-28 and -30, ADT), shown:
  - m4-capture-3, a capture run on the debug tier of the hello pack (`optilux@HEAD`, b786d2e's zip) and Unbound played on quick mode's views: "optilux run: ok; results/records/m4-capture-3.json: 6 of 6 captures valid, 6 .rdc hashed, 2200.6 MiB", 15:20:06 to 15:22:28 ADT (2026-10-30), one launch;
  - one .rdc per view and variant, each re-hashed on disk equal to the record, header RDOC: forest_noon 308.3 and 606.8 MiB, nether_crimson 276.6 and 561.3, end_dragon 106.0 and 341.7 (hello, then Unbound), written in 0.5-1.9 s; `verify records` 398 records, 0 violations; `report` prints ".rdc: 6, 2200.6 MiB".
- The trigger: F12 held 0.25 s through SendInput with input.block on (D81's first path), sent and taken at all six presses: P23's third question answered, no jar change, no mod test needed. Each capture's RenderDoc frame lay between the frames.index reads around its press (9196 < 9197 < 9198 at the first): RenderDoc's frame number is the mod's frame index.
- RenderDoc loaded from the pinned renderdoc.dll (sha256 809da38e3867...) at 15:20:12 by gfx-debuggers' log; every capture named that minute.
- Before it, m4-capture-1 and -2 (2026-10-28) ended failed before any F12: RenderDoc's listening socket raised a Windows Defender Firewall prompt for runtime's java.exe over the game; the user answered it; runtime's java.exe now holds two inbound Block rules (Public profile).

## What was built
- Re-pin (the user's, 2026-10-28, section 7's first stop): `install --tier debug`, needed for gfx-debuggers' jar, fetched Mojang's republished 26.3 version JSON (its asset index alone: 142 language files and pack.mcmeta); `install --refresh` rewrote the launch spec (4 facts); tests/test_platform.py builds it from that JSON (LATEST). launchSpec moved in the identity; M4.P09 recalibrates.
- The debug tier (D81, P8): the platform file's `jvmProperties` (`debugger=renderdoc`; `renderdoc.path`, the pinned renderdoc.dll itself, which gfx-debuggers 3.2.0 System.loads at preLaunch in the game's own process on Windows, javap); platform.jvm_properties, launch.tier_properties (a path resolved under the repo, refused when absent, also at `run --check`; hashed), build_command (after the token; the token's and the spec's names refused) and command_facts (each once before the main class); suite.json's irisTiers.debug sets enableDebugOptions true.
- `run`'s capture kind (record.CAPTURE: the debug tier alone, every other kind bench alone; measure.capture_body): RenderDoc's load read in latest.log; the visual run's steps to the settle; A2's focus step (session.ensure_focus); RenderDoc's folder (GetTempPathW's RenderDoc) checked for strays; F12 held through SendInput (sendinput.key_hold, its up retried) via acceptance.inject; the game still in front and frames presented; take_rdc: the one new `java_<minute>_frame<n>.rdc`, its minute the load's, moved under raw/<run>/rdc/<view>/<variant>/ once no other handle holds it (RunHost.unheld), header RDOC, hashed; no file in 30 s fails the run; D42's check, the displays refused off. `verify records`, `report` and `compare` (refused) know the record; an orphan keeps its captures.
- View lists: a visual or capture spec's `mode` may list view ids, perf or coverage (record.listed_views).
- Docs: platform.md#mod-tiers, run-record.md#run-spec, offline.md#tools (captures, their record, m4-capture-3's facts), design.md#5-interfaces' run row, CHANGELOG.md's 0.5.0 bullet.

## Review
The reviewer agent on the launch and capture changes: the command-line check held; 1 medium and 11 low findings, each read at its source. Fixed (64a5cf1): a late second capture taken by the next press, an .rdc not tied to this game's RenderDoc, F12 lost during the hold, a refused key-up, every missing file blamed on P23, seconds not from the press, properties read twice, an orphan's candidates without their option values, a move while RenderDoc writes, the renderdoc.path notes. Kept: the dll's bytes recorded per launch, never pinned (tools.json pins the zip); renderdoc_loaded reading the whole latest.log (rolled at each start; two "Found" lines refused). Found running it: `run --check` printed a measured line for a capture spec, and an orphan's capture record was summarized as a measured one (both fixed, 64a5cf1); the firewall prompt (A2's focus step, d4a8645, which the prompt still defeated: the user's answer cleared it).

## Checks
- Start (2026-10-28 14:42 ADT): branch m4 clean at e8b825d; 1083 passed; verify docs 0 violations. Resume (2026-10-30 15:18): clean at b786d2e; 1105 passed; verify docs 0 violations.
- Before each commit: `optilux test` green (1105 passed), ruff and pyright clean, verify docs 0 violations, verify records 0 violations (398 records with m4-capture-3); the mod unchanged, so no mod test.
- 7d93cd2 (the re-pin) went out with one test failing (a `| tail` hid the exit code); its CI failed on that test alone and c13bdff fixed it. CI green on every later commit, each watched to its end before the next push.
- tests/test_launch.py::test_logman_lists_sessions_on_this_machine failed twice in parallel runs ("The GUID passed was not recognized as valid by a WMI data provider") and passed alone 3 of 3: perhaps M3's unnamed flaky test.

## Deferred and logged
- `install` ran (the plan's ground rules allow it; the prompt's list of runtime/ writers omits it): no other path puts gfx-debuggers into the store.
- Three debug-tier launches, one beyond the prompt's two, the user asking to rerun once the prompt was answered; m4-capture-1 and -2 committed as failed records.
- The displays woken once (2026-10-28) by a 1-pixel SendInput nudge at the user's request; no setting changed.
- displays_on's refusal still says "PresentMon records no frame" for a capture run, which uses none.

## Open questions
- P22 and P23's RGBA16UI readback and renderStage (M4.P06's probe).
- RenderDoc's target-control server listens while the debug tier runs; runtime's java.exe is blocked inbound on Public networks (the user's answer). A new Temurin pin will prompt again.
- From the last handoffs: pinning gamma, Smooth Lighting and See-Through Leaves (the user's); M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- One capture per view and variant so far: two captures of one view (M4.P05's identical pass outputs) are untested; a capture is of the frame after the press, not aligned on the pack's cycle (the hello pack's cycle is 1).
- Captures run 106-607 MiB at 3840x2160 under results/raw/ (ignored): about 2.2 GB a quick run of two packs.
- From the last handoffs: the hello pack's 800-1,250 fps; the displays held only from `run`'s start.

## Commits and time
- 7d93cd2 (the re-pin), c13bdff (its fixture), 60e8b4f (the debug tier's launch), 8cf1509 (the capture kind), 56f8d91 (key_hold's test), 4a5658b (view lists), 64a5cf1 (the review's fixes), d4a8645 (A2's focus step), b786d2e (the stop's handoff, m4-capture-1 and -2), 1b6a212 (m4-capture-3), then this handoff.
- M4.P04: about 2.1 h of work against 3 h (2026-10-28 14:42 to 16:30, then 2026-10-30 15:18 to about 15:35 ADT); about 47 h between waited on the user. Machine: 3 launches, about 5 min.
- Tripwire: actuals about 72.3 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 8.1: P00 3.8, P01 0.6, P02 0.7, P03 0.9, P04 2.1) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P05 check L4 and E3's evidence (docs/prompts/m4.md), in a fresh session; its one launch (underwater's captures) sends input, so the user at hand to wake the displays, then hands off; `check L4` reads m4-capture-3's .rdc.
