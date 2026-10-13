# Handoff
Status: the latest stop: M2.P05, the measured session, and what M2.P06 starts from.

## Contents
Outcome · What changed · Checks · Review · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M2.P05
- Exit held: one announced quick-mode measurement run, m2-measurement-1 on bench_263 (calibration null, D40; the baseline Unbound r5.9.3 with the played profile, D35, and its A/A twin optilux-twin1-ComplementaryUnbound_r5.9.3.zip, a byte copy, sha512 a085d1d8...): status ok, 12 of 12 captures valid, 314 to 436 frames each, every row Hardware: Independent Flip, GPUBusy over FrameTime 0.998 to 1.000, halves within 0.31 %.
- The cut's edges (each window's first row less frame start's row, its last less frame end - 1's, rows found by the swap stamps): [0, 0] on ten windows, [1, 1] on capture 5 (314 rows, 314 frames), [1, 0] on capture 11 (318 rows for 319 frames).
- Captures, median GPUBusy (ms) and frames: warm-up pass forest_noon 7.857 (315), nether_crimson 5.669 (434), end_dragon 7.745 (320); measured pass forest_noon A 7.821 (316), twin 7.845 (314), A 7.853 (315); nether_crimson 5.679 (435), 5.673 (436), 5.677 (434); end_dragon 7.756 (319), 7.775 (319), 7.770 (320).
- Informative, no verdict (calibration null): the twin against its two baselines +0.107 %, -0.085 %, +0.158 %; the warm-up pass against the measured pass's baselines +0.259 %, -0.152 %, -0.223 % (D47 is M2.P08's).
- The session's time split: D42's wait 201.8 s (input within 30 s, nxplayer.bin at 2.1 to 3.4 % of the 3D engine), launch to join 19.1 s, the mod 4.1 s, the session start 37.0 s (selftest 3.2 s, the start-of-run reload 2.5 s, the 30 s warm-up), warm-up pass 31.2 s, measured pass 51.1 s, PresentMon's stop 2.1 s, quit 1.1 s (exit code 0). PresentMon 121.3 s, 14,392 rows, 2,530,857 bytes; the record 53,314 bytes.
- F10: no remote connection at the join this run (the game's startup call had ended); recorded per run.
- A run killed in a test leaves an aborted record: tests/test_measure.py kills the runner after two captures, the next run's finisher ends the orphan's game (WM_CLOSE) and PresentMon's ETW session, deletes its twin and settings files and writes the record aborted with both captures summarized.

## What changed
- optilux/measure.py (new): variants and twins, their files (shaderpacks/<pack>.txt from the profile's literal text, iris.properties), the schedule, D48's laps, the settle, arrive (function, camera.place, `ready` after a dimension change, D49's GUI and creative, weather ticks), capture (the files, shaders.reload, the options checked, timers, window.measure, camera.get), the summaries' validity flags, D42's wait (GetLastInputInfo, typeperf on the display adapter's LUID), the heap rows, D41's orphan finisher.
- optilux/presentmon.py: RowsTail (wait_rows reads only what grew, cr10), Timeline, cut_window with its edges, summary.
- optilux/record.py: the measurement and calibration kinds and A8 and A11 on a mode's schedule, variants with profiles and options, calibration null (D40), heap, the budget with selftest's reload (P12); write_record writes whole, then renames.
- optilux/session.py: c5 (a failed selftest ends the session), the focus end (Session.stop_on), the journal, Attached, RunHost's idle, 3D engine, process facts, connections and logman stop.
- optilux/verbs/run.py: one Runner for acceptance and measured runs (simp2), one way to end a game (simp20), notes in the record (simp11), F10's connections; optilux/modfake.py: pack switches at a reload, the game's loading and quit screens.
- Choices no plan or prompt names, taken here:
  - laps, not one order: two passes need three weather steps (into clear, thunder, back), against D48's "at most twice", which counted one pass;
  - GPUBusy over FrameTime is median over median; halves split the rows in order, apart in % of their mean; a window's events are those of frames start to end - 1;
  - the twin last among the candidates; option values text or booleans (a JSON number would turn "0.50" into 0.5, which Iris refuses);
  - `ready` after a dimension change (its loading screen closed) before the reload; `camera.get` after every window must read the view's pose;
  - D42's end ignores the screens the game opens itself (a dimension change's loading screen, the quit's); a calibration run takes no timers (M4's timer twins) and no heap reads; a measured run refuses a snapshot whose view functions left the views file;
  - A8 and A11 recorded unjudged and failed until M2.P07's verdicts; the timers' maxFrames 10,000; heap rows at the start and every 10 reloads;
  - a measured record keeps its steps and events in raw/ (counted in the record), the baseline's whole effective option map and the others' differences.
- Docs: measurement.md (Session, Validity, Tools), run-record.md (Status, Record, Fields, Run spec), AGENTS.md's layout (measure.py; the placeholder's file list cut), CHANGELOG's 0.3.0 entry.

## Checks
- At the start: 528 passed, verify docs 0 violations, tree clean on m2.
- At the end: `optilux test` 600 passed; ruff, ruff format and pyright clean; verify docs 0 violations. The first commit alone: 534 passed.
- Tests added (72): the schedule and its reloads, the laps, the settle; the cut on synthetic rows and on A9's real CSVs and stamps; the summaries and each flag; the variant files' bytes, the twins, the options read back; D42 on typeperf's real output; the measured spec's 23 refusals; the runner on the protocol fake: a quick run, D49, the focus end (and in the warm-up), the game's own screens, a moved camera, a failed selftest, A8 admitted with its timers, the heap rows, an orphan finished (its pids checked, a reused pid left alone, a short CSV left unsummarized), a dead PresentMon's session stopped, files not the run's kept.

## Review
The reviewer agent three times, each finding read at its source: correctness (6: 2 high, 2 medium, 2 low), failure paths (15: 2 high, 5 medium, 8 low; 6 the same), identity (9: 1 medium, 8 low).
- Fixed: the game's own LevelLoadingScreen ended every session at its first dimension change and the quit's screens made every record invalid (both high; verified in M2.P04's request log and m1-acceptance-10, the fake now sends them); D42's GPU check passed on no reading; a reused pid of a protected process crashed every run; a focus.lost in the warm-up went unseen; twins left when the mod session failed; a dead PresentMon's ETW session left; an error after the session lost the record; the journal written outside the trys that end the game and PresentMon; a pid checked through one handle, ended through another; an orphan's CSV taken as complete; files that were not the run's deleted; latest.log not kept for a broken session; a short record on a killed write; timers on in calibration runs; heap reads in calibration runs; an orphan's record without its variant fields or its suite; the Java mismatch's journal identity; the view functions unchecked.
- Left: below.

## Open questions
- For M2.P06 and M2.P08: D47 from this one run: pass 1 differs from pass 2 by -0.22 to +0.26 %, within D47's 0.5 % on all three views.
- nxplayer.bin (NoMachine) drew 2.1 to 3.4 % of the 3D engine while input arrived; at the launch 0.63 %. Whether a remote viewer moves GPU time is unread.
- A game killed during its join, A9's PresentMon and A1's second game are never journaled, so an orphan of those needs the user's hands (launch owns the process until the join).
- The baseline's profile and options are not enforced (D35 fixes them for M2); one sha512 per run holds only while every variant runs the reference zip (M2.P08's passthrough needs its own).
- Stepped thunder ticks may leave random snow, ice or a bolt near a view, the same within a session; inputs outside identity (power plan, AMD per-app settings, game/config's other files) carried.
- Carried: the views file's end_city `why`; 1 or 2 entities at forest_noon under ticks; world.py in `harness`; unmatched pops; the residual (M2.P10); the display's rate and count; machine state; window 1's start frame.

## Left alone
- WM_CLOSE to an orphan's game goes by its pid's windows after the handle check (a microsecond window).
- notNumbers counts the larger missing column, not their union; any NA still flags.
- The first prep's raw folder prep-bench_263-20261012-214122.

## Weak points
- One live run, quick mode, three views; the focus end, the orphan finisher and the timers path ran only on the fake.
- The fake models the game's screens from the logs; the loading screen's close is awaited with `ready`, not read.

## Commits and time
- bf47ddd feat: cut PresentMon rows by window stamps and summarize each window; 5f1b3d7 feat: run measurement and calibration sessions through one runner; 295e31e chore: record the first quick-mode run of the baseline and its twin; this handoff. Each pushed after the previous one's CI ended green.
- M2.P05: 21:49 to about 23:20 ADT, about 1.5 h against 3.5 h.
- Tripwire: M0-M3 summed 70.8 h, the trip at 141.6 h; actuals about 33.0 h (M0 3.3, M1 20.3, M2.P00 about 3.5, P01 0.6, P02 0.8, P03 1.8, P04 1.2, P05 1.5).

## Next
/optilux-next prints M2.P06's prompt: the reload budget, 1.5 h (M), 2-3 launches.
