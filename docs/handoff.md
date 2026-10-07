# Handoff
Status: M1 in progress: 0.01.12 (review and cleanup: static checks, the review's fixes, parallel tests) is done; the next prompt is 0.01.13, debug, timing and the acceptance re-run, which /optilux-next prints.

## Contents
0.01.12 review and cleanup · Tools · Findings · The held-torch launch · Open questions closed · Choices · Not done · Open questions · Time · Next

## 0.01.12 review and cleanup
- Start gate (13:05 ADT): branch m1 clean and pushed; 361 tests passed in 39.8 s wall (pytest 39.2 s); `mod test` 80 passed; verify docs 0 violations; ruff clean. Last CI run before: 1m27s (its test step 63 s).
- The seam (D27): optilux/verbs/run.py (1,725 lines) split into optilux/session.py (the session skeleton M2 reuses: RunHost, Session, session_start, settle_view, the focus checks, record_status), optilux/acceptance.py (A1-A4, A7, A9, F4 and their verdicts as pure functions) and verbs/run.py (perform and the verb, 396 lines).
- After: 404 tests, parallel 12.2 s wall (`optilux test`), serial 42.7 s (`--serial`); ruff (wider rules) and pyright basic clean; javac -Xlint:all,-classfile -Werror clean on main and test sources; `mod test` 80 passed; the jar unchanged, sha512 eb840262... (`mod build`: the store's copy equal); verify docs 0 violations. Branch coverage 79 % to 81 % (run.py's former code 18 % to 31 %).

## Tools
At D28's pins, locked by uv: coverage 7.16.2, pyright 1.1.414 (nodejs-wheel-binaries 24.19.0), pytest-xdist 3.8.0.
- ruff BLE, S, SIM, RUF, PERF: 1,000 hits. 905 S101 (assert in tests): off for tests/ in pyproject.toml (pytest's assert is the test). 47 RUF043 (pytest.raises patterns, regexes): raw strings. Fixed: 7 PERF401, 3 SIM102, SIM105, SIM212, 2 RUF007, RUF021, RUF005, 2 RUF059, 2 RUF100, 4 S324 (sha1 with usedforsecurity=False). Suppressed on the line with the reason: 16 S603 (argv lists, no shell), 2 S105 (a property name, a placeholder), 4 S310 (URLs from committed pins), S314 (Gradle's own XML), BLE001 (run.py: the record is written whatever broke).
- pyright basic: 19 errors, all narrowing pyright could not see; made explicit (Launched.mod_token refuses a --no-token launch; session_text, modclient's ids, modfake's writer, parse_phase's match, pm_exe). Now a CI step.
- javac: 2 [serial] on Errors.Refused and Json.Malformed (suppressed on the declaration line, so the class files and the jar keep their bytes); 31 [classfile] from Minecraft's Guava jar (errorprone annotations absent): `-Xlint:all,-classfile`.
- pytest-xdist: `optilux test` runs `-n auto`; `--serial` for one process.

## Findings
Dimensions: py and mod correctness, fail failure paths, id identity, conc concurrency and protocol, sec security, doc docs against code, cov coverage, simp simplification; cr /code-review high on main...m1; crw its first pass, which read the uncommitted tree only (it compared m1 with origin/m1), kept. Each was read at its source; "holds" = confirmed there. Tests failing before each fix: 7 + 4 + 18 + 1 + 2 + the install names (the session's output).
- py1 fail1 cov-H2 cr1, medium, holds: A1's control passed on an unread session thread dump ("unread: ..." is truthy); fixed (acceptance.a1_seen), test.
- py2 id2, medium, holds: the read-back excepted exclusiveFullscreen and simulationDistance, identity keys both; fixed: every written key and Sodium's text must read back, test; platform.md.
- py3, low, holds: settle_view ignored visualSettleS.underwater; fixed (the role's settle, else default), test.
- py4, low, holds: A4's irisRestored reads back the file just written; no change: recovery.pack carries the restore, no verdict moves.
- py5 cr3, low, holds: the git guard missed `cmd /c` and long-option prefixes (`--no-verif`, `--forc`) and read `-uno` as -n; fixed, tests.
- py6, low, unverified: an iris.properties value with = # ! would read back escaped; rejected: no pinned value holds one.
- mod1, low, holds: an exclusive request is accepted while a mutation runs; owner M2 (window.measure; before calibration).
- mod2, low, holds (JLS 15.25, not run): capture.json writes `every` as 2.0; owner M2.
- mod3 doc3, low, holds: suite.json capture.maxPendingFrames was read by nothing; fixed: removed, mod.md#8-capture names CaptureAdapter.MAX_PENDING.
- mod4, low, unverified: readiness has no term for chunks in flight; owner M2 (A5, readiness).
- fail2, medium, holds: a hook failure before `hello` sends no event; fixed: the session's latest.log is read, a hook failure makes the run invalid, test.
- fail3, medium, plausible (Iris side unread): an Iris load failing outside shaders.reload is only logged; fixed as fail2, test.
- fail4 doc1, low, holds: A9 ignored invalidating events; fixed (acceptance.a9_pass), test.
- fail5 conc6 cr2, low, holds: the client's reader died on a list id (TypeError) and on any non-OSError; fixed (stray, reason kept), test. Stray `id: null` answers: owner 0.01.13 (the request logs).
- fail6, low, holds: the wait after a kill (launch.end, presentmon.stop) could replace the error; fixed both, tests.
- fail7 cr7, low, holds: a missing driver version was recorded as null; fixed: refused with the fix, test.
- fail8, low, holds: a mode read without DPI awareness passed; fixed: refused, test.
- fail9, low, holds: a failed git status read as a clean tree; fixed (repo.GitError; status, pack, milestone and run handle it), test.
- fail10, low, holds: Gradle runs without a timeout; owner M2.
- fail11, low, holds: minecraft-launcher-lib and `milestone start`'s fetch have no timeout; owner M2 (the lib's own, D17: noted).
- fail12, low, unverified: a partial JDK unpack reads as present; owner M2.
- fail13, low, holds: `run` errors before its session are tracebacks and burn the name; owner 0.01.13.
- fail14, low, holds: the git guard passed an unreadable event; fixed: fails closed (exit 2), test.
- id1, high, holds: options.txt keys the harness does not write were neither recorded nor matched, the hash taken after the quit; fixed: the file as the game reads it is recorded (hash and 174 unwritten keys with values, this launch); matching them: owner M2.
- id3, medium, holds: PresentMon's build and flags are in no identity key; owner M2 (its session).
- id4, medium, holds: the harness is recorded, never matched, though the roadmap says it becomes identity; owner M2 (calibrate).
- id5, low, holds: resolution and GPU come from the primary display, the render target is never compared; owner M2 (validity).
- id6, low, unverified: HwSchMode is the requested HAGS state; owner M2.
- id7 id9, low, holds: the spec and views hashes are read after the session; identity null after a launch failure; owner M2.
- id8, low, holds: the suite hash covers descriptive copies no code reads; owner M2.
- conc1, medium, holds: the mod answers `timeout` before freeing the resource, the fake did the reverse, so A2's cleanup could end the session on `busy`; fixed: the fake keeps the mod's order, A2 waits (input_block_when_free), test.
- conc2, low, plausible (no M1 path): a hello after its own disconnect cancels the 10 s release; owner M2.
- conc3, low, holds: a timeout could be raised for an answer the reader already took; fixed, test.
- conc4, low, holds: an event may precede hello's answer; doc fixed (mod-protocol.md).
- conc5, low, holds: a stopped capture's frames outlive its resource; owner M2.
- conc7, low, holds: the pipe thread catches RuntimeException only; owner M2.
- sec1, low, holds: the token check skips a failed session's request log (m1-acceptance-1, -2); owner 0.01.13.
- sec2, low, holds: pinned file names were not checked as one part; fixed (platform.plain_name; pins, tools.json), tests.
- sec3, low, holds: Fabric's profile id became a folder before any check; fixed, test.
- doc2 crw1, medium, holds: pyright was no CI step; fixed (ci.yml).
- doc4 doc5 cov-M11 crw3, medium, holds: workflow.md#testing missed the tools and its list missed most of M1's tests; reconciled.
- doc6, low, holds: `-classfile` against D28's flags (closed): reported; the evidence is the 31 warnings above.
- doc7, doc8, doc11-doc15, low, hold: stamps on results only (design.md, mod.md); error causes, events, the 10 s release, the table test (mod-protocol.md); capture tests, F3 (mod.md); session-threads.txt (run-record.md); WM_CLOSE without a mod session (platform.md); docs fixed.
- doc9, low, holds: the table test ignores the Result column; doc says what it checks.
- doc10, low, holds: the fake accepted align, flush, after; fixed, test.
- doc16, low, holds: AGENTS.md Layout; fixed. doc17, low: test.py's timing cite; fixed.
- cov-H1 to H8, M1-M9, high to medium, hold: perform and the items had no tests; the verdicts are now pure functions with tests (A1, A2, A4, A7, A9, F4, record_status), and launch's quits, presentmon.stop, the manifest, record's and session's refusals tested; the glue that drives the game: owner 0.01.13 (its live run). cov-M10: subprocess code shows as missed; noted in workflow.md. cov-L1 to L6: low, fail closed: left.
- simp1, medium, holds: A2 repeated inject without its foreground check; fixed with the A2 row, test.
- simp2, medium, holds: perform keeps the session skeleton inline; record_status out, the rest: owner M2 (calibrate extracts its runner).
- simp3-7 simp22, low, hold: dead or duplicated Java (Session.protocol, PipeServer.problem, aceCount, two imports, the BigDecimal branch, delegates); owner M2 (the jar stays unchanged here).
- simp8-10 simp18 simp24 cr9, low, hold: winpipe.client_pid, Recording.facts, RequestLog.lines removed; record.file_sha256 streams through platform.sha256; the "never reached" comment fixed. interval_ms and load_commands' root kept (M2, the tests).
- simp11, low, holds: Spec.notes, pack, resource_packs unread; owner M2. simp12: commands.json's schema unread; rejected (a format version). simp13: test-only code listed; no change.
- simp14 simp21 simp23, low: duplicates whose messages or isolation differ; rejected.
- simp15 simp16, low, hold: the snapshot was read twice and A1's controls ran without A1; fixed (record.tree; only for A1).
- simp17 simp19, low, hold: REQUESTS, hooks.MAIN and pack.shown now one definition; SESSION_PREFIX tied to OWN_SESSION by a test; the other equal constants left. simp20: the end-the-game policies; owner M2.
- crw2, medium, holds: a real CTRL_BREAK could reach the parallel run's workers; fixed: every pytest process ignores SIGBREAK (conftest).
- crw4, low: the raw-string patterns stay loose regexes as before; rejected (style only). crw5 crw6, low, hold: parse_phase's second match, pm_exe's double test; fixed. crw7, low: Launched.mod_token; rejected (it names the fault). crw8: S603 suppressions per line; rejected (the prompt's rule). crw9: @SuppressWarnings over serialVersionUID; rejected (the jar's bytes kept).
- cr4, low, holds: platform identity hashed the `why` notes; fixed (stripped as the suite's), test. cr5, low, holds: A4's "final" substring; fixed ("final.fsh"), test. cr6, low: `launch` prints no announcement; rejected (the rule binds the agent; `run` announces because one call launches twice). cr8, low, holds: a9_match's process check is redundant with `--process_id`; kept as a guard. cr10, low, holds: wait_rows re-reads the CSV each poll; owner M2.

## The held-torch launch
Announced, bench tier, world spike (13:47:40, pid 8988, joined in 15.8 s, the mod's quit, exit 0 in 0.9 s); no input injected, input.block never on. Gate: three idle Gradle daemons and one other JVM recorded, none blocking. Creative, a torch in the main hand, camera at the joined pose: hideGui false frame 0ef1d676... shows the torch; hideGui true frame e88fdd77... shows no hand (results/raw/held-torch/). Gamemode spectator and an empty hand restored. options.txt with inactivityFpsLimit "minimized" (sha256 7cdae2e9..., 174 unwritten keys) read back: 24 of 24 keys, the Iris keys, Sodium's flags and text; the request log holds no token.

## Open questions closed
- A JVM fatal-error log would list the token: closed (sec): a fresh token per launch, never stored (records hold `token: true`); one pipe per JVM, never recreated; a stale token finds no pipe or answers unauthenticated; the gate keeps launches apart; hs_err would land in runtime/<platform>/game/, which the harness never copies.
- release.yml: on windows-latest. CI's zip for 0.01.11 (run 37648615599), a local `pack build --ref HEAD` and the v0.00.06 release asset built on ubuntu all hash 689c6994...: no difference seen.
- inactivityFpsLimit, the end crystals, the hand, end_city, A2's check, the Gradle gate, the byte caps: roadmap.md#qa-pass-open-questions.

## Choices
- S101 off for tests/ in pyproject.toml rather than 905 line suppressions.
- `-Xlint:all,-classfile`: the 31 warnings name a third-party jar, no line of ours.
- The mod's findings go to M2: the jar stays eb840262..., so 0.01.13's re-run proves the harness changes alone.
- The entities view keeps the GUI shown (measurement.md#session), the only way the held torch is drawn; its HUD cost is constant across variants. Taken by the user with the other recommendations (2026-10-07).

## Not done
- D30: deleting runtime/mc-26.3/game/saves/bench_7800 and bench_20261005 was refused twice by the permission classifier ("Irreversible Local Destruction"), the second time after the user took the recommendations; nothing names them. The user deletes them (in game, or Remove-Item).

## Open questions
Each in roadmap.md#qa-pass-open-questions with its phase or milestone:
- PresentMode "Composed: Copy with GPU GDI" against the spike's flip (0.01.13; M2).
- Whether `/function` reports success without `/return` (0.01.13).
- The review's rows for 0.01.13 (sec1, fail13, the stray `id: null` answers, the items' glue live) and for M2 (Findings above).
- The live world against its snapshot, A9's 46 s capture, Gradle's other downloads (M2).
- D30's two candidate worlds (the user).

## Time
- 0.01.12: 13:05 ADT to the commit at 14:03, CI green at 14:05: 1.0 h against 3 h, the launch included; the close-out after. M1 so far about 14.5 h of 28; tripwire 55.8 h, trip at 111.6 h; actuals about 17.8 h (M0 3.3, M1 14.5).
- CI: 1m27s before (run 37648615599, test step 63 s); 2m17s on the phase commit (run 37656044338: pyright 7 s, uv sync 4 s, test step 82 s), 95 s on the close-out; ci.yml then runs the tests serially (user, 2026-10-07: recommendations taken).
- Earlier: 0.01.11 2.2 h against 2; 0.01.10 1.1 h against 1.5; the rest in git history.

## Next
/optilux-next prints 0.01.13 Debug, timing and the acceptance re-run (L, 2 h; 2-6 launches). Plan around: the provisional snapshot retaken before any `run` (this launch changed spike); the jar unchanged (eb840262...); 0.01.13's rows above; its session runs uncapped without input now.
