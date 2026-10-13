# Handoff
Status: the latest stop: M2.P08 stopped at the survey's first launch, twice: PresentMon wrote no row because the displays had powered off on the machine's 10-minute idle timeout; a decision for the user (Open questions). The passthrough pack and the survey's readings are built and committed.

## Contents
Outcome · What changed · Checks · Review · The stop · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P07
- M2.P08's Exit does not hold: no survey record, no floors, no D47 outcome, no acceptance run. Done: P17 read in the pinned jar and agreeing (below); the passthrough pack (D46) and the readings as functions of a record, with their tests, reviewed, committed (12079c5), CI green.
- Two announced launches on bench_263 ended failed before their first window: m2-survey-1-p1 and its retry m2-survey-1-p1b (records committed), each "presentmon.csv held 0 rows and no a row after 30 s", the game ended by WM_CLOSE, exit code 0. Nothing else launched; no system setting touched (powercfg and logman only queried).

## What changed
- P17 against the pinned Iris jar (sha512 d8d3312f..., `javap -c -p` of IrisRenderingPipeline, FinalPassRenderer, ShaderMap, ShaderCreator, Iris): createShader sends an absent program to createFallbackShader, whose gbuffer framebuffer draws buffer {0} (colortex0); shadow targets are made eagerly only when isShadowEnabled() is TRUE, else by a program sampling shadow textures, and ShaderMap skips shadow keys while the targets are null (before the program is built), so shadowRenderer stays null; finalPass null reads the baseline framebuffer (colortex0) and copyTexSubImage2D's it to the main target. Iris.isValidShaderpack takes a zip whose walk finds a directory ending in `shaders`: the passthrough zip passed that walk under the pinned JDK's zipfs.
- optilux/measure.py: passthrough_zip (shaders/ and an empty shaders/shaders.properties, stored, the zip epoch, Unix attributes: 242 bytes, sha256 834e06b8...), make_passthrough (written beside the twins, journaled first, checked by sha512, deleted after the quit), variant_sha512; the record's passthrough variant keeps its own sha512 and its whole (empty) option map. record.py: PASSTHROUGH, a measurement run's candidate only, no profile, options or timers. run.py writes it before the launch; modfake answers no options for it.
- optilux/stats.py: gpu_bound(captures, views, minimum), cpu_floors(captures, views, variant) (the passthrough's median FrameTime, all captures valid and left GPU-bound, else no floor and why; GPULatency in ms and frames, F10), warmup_agreement(captures, views) (D47: each view's warm-up capture against the measured pass's first baseline, both settles kept; drop only when every view is within 0.5 %, undecided never dropped).
- docs/run-record.md (the variant's sha512 and effective map, the run spec's pack) as built.
- Choices no plan or prompt names, taken here: the passthrough file name optilux-passthrough.zip; D47 compared at the measured pass's first baseline (the same place in a visit), its spread beside it; a passthrough capture still GPU-bound gives an upper bound, never a floor; the readings take the mode's views, so an unmeasured view is named.

## Checks
- At the start: branch m2 clean at 281a6be, 764 passed, verify docs 0 violations.
- 12079c5: 779 passed (15 added: the zip's bytes and its placement, the spec's admissions and refusals, a fake run writing, measuring and deleting the passthrough, the three readings on fixture captures and on a split session's records); ruff, ruff format, pyright clean; verify docs and verify records 0 violations; CI green (run 38479697108).

## Review
- The reviewer agent on the readings and the pack builder (correctness against measurement.md#validity, D46, D47, P17): 10 findings, each read at its source before 12079c5.
- Fixed: D47's pair at a launch's first view can differ in settle (1.5 s against 4.0 s: m2-measurement-1's forest_noon shows it; rain and end_dragon in the survey's lap), now kept as warmupSettleS, measuredSettleS and sameSettle and judged all the same; a view never captured dropped out of all three readings (they take the mode's views now); the tests did not pin the first baseline against a mean or median, pass 1 or the 0.9 edge; a GPU-bound passthrough capture was named a floor; timers on the passthrough; view_ids' order over a split session (removed).
- Reported, not fixed: a floor's validity reads GPUBusy's halves, not FrameTime's (the capture's validity as built); GPULatency's NA rows are outside notNumbers (0 NA in 39,955 rows of m2-measurement-1 and m2-diag-alone-1; the survey's CSV unread); measurement.md#session step 4 ("kept only if M2 shows pass 1 differs") and D47 ("dropped when every view agrees within 0.5 %, else kept") set opposite defaults, and one capture against one per view at 0.5 % sits under ALC's per-view noise (0.5-1.3 %), so D47 may keep the pass on noise alone (m2-measurement-1 read 0.46, -0.17, -0.13 %).

## The stop
- Both launches: D42 held (1,921 s and 2,082 s without input, no 3D-engine user above 2 %); the join, selftest, the start-of-run reload, `ready` and the 30 s warm-up ran (frames advancing); PresentMon 2.6.0 ran 65.6 s ("Started recording", stopped by CTRL_BREAK_EVENT, exit 0) and never created its CSV.
- Without the game, the pinned PresentMon alone for 5 s on every process (`--timed 5 --terminate_after_timed`, a CSV and then stdout) read 0 rows: no process presented.
- powercfg /query (read only): "Turn off display after" 600 s on AC, sleep never. Every earlier measured run began 32-54 s after the last input (m2-measurement-1 36.7 s, the five budget and diagnosis runs 32.1-53.4 s); both survey launches began after the displays had been off for over 20 minutes. Same driver (32.0.31041.3013), Windows revision 9457, HAGS and AMD's own PresentMon as in those runs.
- Not the cause, by what was read: `GraphicsPerfMonitorSession`, a second ETW session enabling D3D9, DXGI, DxgKrnl and Dwm-Core beside AMD's RSXTraceSession (2,648 buffers at a 1 s flush: started about 19:07); two sessions enable DxgKrnl, under ETW's eight. Its owner is unknown.
- Why it stops: every unattended measured run longer than the idle timeout meets it: the survey's four launches (about 15 min), M2.P09's calibration (about 4 h). Keeping the displays on is a system setting or a new harness behaviour, neither named by a plan or prompt.

## Open questions
- The user's, now: how a measured run keeps the displays on. Recommended: `run` and `calibrate` hold SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED) for a measured session and release it after (a per-process request shown by `powercfg /requests`; no setting changes; recorded in the record), and refuse a measured run whose displays are off or would turn off inside it, naming the fix; unverified until tried: that the request wakes displays already off. Else the user sets "Turn off display after" to never on AC while benchmarking, and `run` reads it (powercfg /query) and refuses a timeout shorter than the session. Attended runs (the user waking the displays before each launch) do not reach M2.P09's 4 h.
- The user's, from the review: D47's 0.5 % on one capture per view against ALC's 0.5-1.3 % noise, and measurement.md step 4's opposite default; a stop if D47 keeps the pass (prompts/m2.md M2.P08 step 6).
- Carried: plans/m2.md section 7 lacks the stop on D47 keeping the warm-up pass; nxplayer.bin's GPU share; orphans of a join or of A9; the baseline's profile unenforced; stepped thunder's debris; the views file's end_city `why`; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- results/raw/m2-survey-1-p1/ and -p1b/ (ignored): no presentmon.csv in either; the scratchpad's javap output, zip check, specs (m2-survey-1, m2-acceptance-1) and readings script.
- m2-survey-1's session record is not written: `run` resumes it at part 1 (its next name m2-survey-1-p1c).
- measurement.md (317 bytes left) and CHANGELOG.md wait for the floors and D47's outcome.

## Weak points
- The diagnosis rests on the timeout, the idle seconds of eight runs and a 5 s system-wide read; the displays' power state at the launches was not read directly.
- The readings have met fixture captures only; the passthrough has met the protocol fake only, never Iris.

## Commits and time
- 12079c5 feat: measure each view's CPU floor with a built passthrough pack; this handoff with the two failed records.
- M2.P08 this session: 19:14 to about 19:58 ADT, about 0.7 h against 1.5 h, stopped.
- Tripwire: M0-M3 summed 72.3 h, the trip at 144.6 h; actuals about 38.6 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5, P06 2.4, the re-plan 0.35, P07 2.1 active, P08 0.7 so far).

## Next
The user's answer on the displays; then M2.P08's prompt again from step 5 (its steps 1-4 are done in 12079c5): `run` resumes m2-survey-1 at part 1.
