# Handoff
Status: the latest stop: M4.P09 Recalibration at its go, on branch m4 at 31ab777: the identity the calibrations will carry built and checked (70979fe8360f...), nothing launched; the user's go is awaited before about 132 launches over about 4.5 h.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P08
- The stop: M4.P09 step 2, the user's go for the calibration hours (plans/m4.md section 4).
- The identity (`run --check --json` on calibrate's own session spec, Unbound r5.9.3 played, quick and full, 2026-11-20 17:12-17:14 AST): sha256 70979fe8360fd1db80b28b893be01d1e87728cddbe0b2b3028f4b2918091d659, the same in both modes; sessions will be cal-quick-70979fe8360f-<n> and cal-full-70979fe8360f-<n>. Against M3's quick- and full-4edbb05a... it differs in launchSpec.sha256 (0b815ffe..., the sixth JSON's re-pin), world.treeSha256 (31830e43..., 129 files, M4.P08's snapshot), views.sha256 (5a987858...), suite.sha256 (dcc6d36e...) and harness.modules["optilux/launch.py"]; the 18 modules, PresentMon 2.6.0, Temurin 25.0.4.1+1 at 6144 MiB, the 4 jars, the deterministic set, 3840x2160 exclusive fullscreen with HAGS on, Windows build 26200 otherwise as checked.
- From the first calibration session on, identity is frozen (plans/m4.md section 4).

## What was built
- Nothing yet: the spec checks only (scratchpad), no file under the repository or runtime/ written.

## Review
- None yet: the reviewer pass follows the runs (M4.P09 step 6).

## Checks
- Start (2026-11-20 17:10 AST): branch m4 clean at 31ab777, equal to origin/m4; `optilux test` 1137 passed; verify docs 0 violations.
- `run --check --json`: quick ok, 20 reloads in one launch; full ok, 132 reloads in 11 groups of one view.

## Deferred and logged
- The plan after the go, one command at a time: `calibrate --mode quick` (10 sessions of 2 twins, one launch each: M3's took 27 min of sessions, 35 min wall); `calibrate --mode full` (10 sessions of 11 launches, 110 in all: M3's 20.3 min a session, about 3.4 h); then SHADOW_QUALITY -1 over the baseline beside the twin, quick (1 launch, about 3 min) and full (11 launches, about 21 min). In all 132 launches, about 4.4 h of sessions plus D42's waits.
- Attended: the machine left alone, no remote viewer connected (NoMachine composes the frames: presentMode invalid), the displays held on by calibrate over its sessions; the game window takes no input while a session runs.

## Open questions
- The go (this stop).
- The look (D86), the user's, no stop: Claude's pre-screen in git 31ab777's handoff (ocean_sunset's sky, the sun square, night with no moon or stars, underwater near black, rain lit as clear noon, dark cloud smudges, the End's flat sky, the Nether's saturation, faint coverage shadows; the tonemap alternatives).
- A leashed mob for basic's leash key (no D83 item); the shadow program's stale comment.
- From the last handoffs: E3; RenderDoc's target control on Public networks; pinning gamma, Smooth Lighting and See-Through Leaves; M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- Mojang republishes 26.3's index every week or two: after the freeze a seventh JSON is a stop (plans/m4.md section 7), and the calibrations would need redoing after a re-pin.
- From the last handoffs: test_logman's parallel flake; P22's list; renderStage per pass; sky.glsl without an L3 test; LIGHT_PATH 0 against 1 unmeasured until M4.P10; the coverage fixture holds draws, not visible pixels.

## Commits and time
- This handoff alone.
- M4.P09 so far: about 0.1 h from 2026-11-20 17:10 AST; machine none.
- Tripwire: actuals about 79.7 h (M4 so far 15.5) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
The user's go in this session: then `calibrate --mode quick`, `calibrate --mode full`, the two shadows-off runs, the review, the docs and the commits (docs/prompts/m4.md M4.P09). In a fresh session, the Resume prompt resumes at the go.
