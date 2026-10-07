# Mod protocol (draft v1)
Status: rough draft, 2026-10-05; the harness client and the mod are written against this file (mod spec: mod.md). As built, 0.01.05: transport, envelope, errors, the event mechanism, hello, frames.index, cancel, quit and commands.json; 0.01.06: state, world.wait, command, ticks.step, camera.place, camera.get, hud.set, input.block and the world, dimension, focus and screen events; the rest is still spec.

## Contents
Transport · Envelope · Errors · Events · Commands · Choreography · Client rules

## Transport
- Windows named pipe, `\\.\pipe\optilux-` + the first 32 hex digits of SHA-256("optilux-pipe:" + token).
- One client at a time. A client may reconnect. On disconnect, state survives and work does not: running requests are cancelled, and input blocking is released after 10 s without a reconnect (mod.md#4-architecture).
- UTF-8, one JSON value per line (`\n`; a trailing `\r` is dropped).
- Lines are at most 1 MiB before the `
`. An overlong or malformed line is answered at once with a coded error and `id: null`, never by a timeout: an overlong one the moment it passes 1 MiB, its rest skipped up to its `
`.
- Security: see mod.md#5-safety. `hello` must carry the token before any other command.

## Envelope
- Request: `{"id": int|string(1..64), "cmd": "<namespace.verb>", "args": {...}}`. Unknown top-level fields are refused; `args` may be left out for `{}`; the id of a running request is refused. Lines are judged in order, so a request right behind `hello` is authenticated.
- Response: `{"id", "ok": true, "result": {...}}` or `{"id", "ok": false, "error": {"code", "message"}}`.
  - Every result carries `frameIndex`, `sinceReload` and `qpcNs` at answer time (`sinceReload` null until the Iris adapter, 0.01.07). `qpcNs` is raw QueryPerformanceCounter time in ns; PresentMon's CPUStartQPCTime x 1e6 is on the same clock (mod.md#6-time-and-determinism).
- Concurrency:
  - requests run concurrently, at most 32 at once (more answer `busy`, `cancel` excepted);
  - responses may arrive out of order, matched by `id`;
  - exclusive resources (window, capture, path, timers) answer `busy`; while one is active, `camera.place`, `camera.path`, `command`, `ticks.step`, `shaders.reload`, `hud.set` and `input.block` also answer `busy`, so no mutation lands inside a measurement.
- Long requests can be cancelled with `cancel {"id"}`. The cancelled request answers `cancelled`; `cancel` answers `cancelled: true`, or false when that id was not running. Game-thread work already queued for a request answered `timeout` or `cancelled` skips its mutation when it runs (mod.md#4-architecture).
- Event: `{"event": "<name>", "data": {...}, "frameIndex", "sinceReload", "qpcNs"}`. Events have no `id`; the mod pushes them after `hello`.
- Versioning: `hello` returns `protocol` (integer) and `capabilities` (the commands this build answers). The client adapts to capabilities, never to version strings. A missing capability answers `unsupported`.

## Errors
| Code | Meaning |
|---|---|
| bad-json, bad-encoding, line-too-long, bad-request | the line or its arguments are invalid; answered at once |
| unknown-command, unsupported | no such command; capability absent on this platform |
| unauthenticated | anything before a valid `hello` |
| not-ready | no world, no player, or a screen open when one is required |
| busy | exclusive resource in use, or 32 requests running |
| timeout | the request's own `timeoutSeconds` expired (game work may still finish: see mod.md#4-architecture) |
| cancelled | stopped by `cancel` |
| iris-compile-error | reload failed; message holds Iris's error (cut at 16 KiB) |
| failed | anything else, message required |

## Events
- `world.joined` (dimension), `world.left`, `dimension.changed` (from, to); a join before `hello` is not pushed: `world.wait` reports it
- `focus.lost`, `focus.gained`, `screen.opened` (screen: the class name of any screen or overlay that opens)
- `reload.done` (pack, pipeline, seconds), `reload.failed` (message)
- `window.start`, `window.end` (see window.measure)
- `path.started`, `path.done`
- `capture.frame` (name, sha256, frameIndex), `capture.done`
- `timers.dropped` (count), `hook.error` (message: an exception inside a frame hook, once per run of failures; the session marks the run invalid)

## Commands
Phase: the milestone that first needs the command (design.md#6-milestones): M1 game control, M2 perf loop, M3 visual loop, M5 temporal; post = after 1.0. mod/src/main/resources/commands.json is this table in machine form: argument types, ranges and defaults, result fields, `mutating` and `exclusive` for `busy`; the mod's checks, the client and the fake read it, and a test keeps it equal to this table.

| Command | Args | Result | Phase |
|---|---|---|---|
| hello | token | protocol, mod (id, version), platform, versions (minecraft, loader, iris, sodium, java), capabilities, pid; `resumed` and the ids cancelled by the last disconnect (false and empty at the first hello) | M1 |
| selftest | - | per-capability pass/fail (frame clock, renderer probe, reload, capture to temp, input); needs a world and answers `not-ready` before `world.wait` | M1 |
| state | - | inWorld, dimension, gamemode, screen, paused, focused, frameIndex, tick | M1 |
| world.wait | timeoutSeconds | pose (dimension, x, y, z, yaw, pitch), time (the overworld clock), joinedQpcNs; answered once a frame rendered in the world; replaces latest.log polling | M1 |
| command | text, timeoutSeconds | succeeded, messages, failures (OWNER level) | M1 |
| ticks.step | n, timeoutSeconds | ticks; answers after n server ticks ran while frozen (`failed` unfrozen) | M1 |
| ready | stableFrames, minSeconds, timeoutSeconds | seconds, predicateSeconds, limitedBy, renderer's own check | M1 |
| camera.place | dimension, x, y, z, yaw, pitch, tpSemantics, timeoutSeconds | the pose the client holds, arrivedSeconds | M1 |
| camera.get | - | pose, eye | M1 |
| camera.path | kind (yawSweep, keyframes), params, clock (frame, wall), flush, align (cycle, phase), capture (directory, every), frames or seconds | path id; events started and done with frameIndex, sinceReload and qpcNs; capture manifest. One request: no ordering gap between path and capture | M5 |
| camera.stop | - | stops a path | M5 |
| shaders.reload | framesAfter (2), timeoutSeconds | pack, pipeline, seconds, framesAfter, reloadFrame (frameIndex at the reload; sinceReload restarts there, as at every pipeline creation) | M1 |
| shaders.options | - | effective option values of the active pack (run records need them from M1) | M1 |
| shaders.dump | on | dump folder and file list after the next reload | M3 |
| frames.index | - | frameIndex, sinceReload (= Iris frameCounter), qpcNs | M1 |
| frames.capture | directory, count, every (frames) or intervalMs, align (cycle, phase on sinceReload), flush + after (frames after the flush), timeoutSeconds | manifest: frames (name, sha256, frameIndex, sinceReload, qpcNs), dropped. The mod aligns, flushes and captures itself | M1 (align M3, flush M5) |
| window.measure | after (reload, path, now), skipSeconds, seconds (or skipFrames, frames) | start and end frameIndex, sinceReload and qpcNs; seconds are timed on the QPC clock | M2 |
| input.block | on | state | M1 |
| hud.set | hideGui, debugOverlay | state (session start needs it from M1) | M1 |
| timers.start / .read / .stop | perPass, maxPending, maxFrames | frames with passes (name, depth, gpuNanos) | M2 (cost rows below the CPU floor need them) |
| metrics.read | - | tick ms (mean, p99), GC count and time, heap, loaded chunks | post |
| player.path | waypoints, speed | server-side flight for the JVM track | post |
| cancel | id | the cancelled request answers `cancelled` | M1 |
| quit | - | closes the game cleanly | M1 |

- Pack switch: the harness writes `shaderPack=<folder or zip in shaderpacks/>` in iris.properties and the pack's settings .txt, then calls `shaders.reload`; the result's `pack` must equal the requested one, else the variant is failed. Spike R4 checks that `Iris.reload()` re-reads both files (V1 exercises it); if it does not, the switch needs another mechanism.

## Choreography
- Session start:
  1. launch (token on the command line);
  2. connect (retry until the pipe exists; check the server PID);
  3. `hello`;
  4. `world.wait`, then `state`;
  5. `selftest` (A10);
  6. `input.block on`, `hud.set {hideGui: true}`, `command /tick freeze`;
  7. `ready`;
  8. `shaders.reload` (start-of-run), then the 30 s GPU warm-up (measurement.md#session).
- Perf capture of one variant at one view (M2):
  1. `command /function optilux:view/<id>` (time, weather), `camera.place` (exact), `ticks.step` if the overworld weather changed;
  2. `shaders.reload`;
  3. `window.measure {after: reload, skipSeconds: settle, seconds: window}`;
  4. the harness keeps PresentMon running and cuts its rows by the window's qpcNs. This replaces ALC's sleeps around a 150 ms PresentMon start.
- Static visual capture, TAA off (M3):
  1. `camera.place`, `shaders.reload`, `ready`;
  2. `frames.capture {align: {cycle, phase}}`: the mod waits for the phase and captures that frame, with no round trip in between.
- Static visual capture, TAA on (M5): `frames.capture {align, flush: true, after: N_conv}`. Run it twice; the two captures must be identical (measurement.md#visual-protocol).
- Motion sequence (M5):
  1. `camera.place`, `shaders.reload`, `ready`;
  2. `camera.path {clock: frame, flush: true, align: cycle, capture: {directory, every: k}}`, one request.
- Compile-error probe: reload a broken pack -> `iris-compile-error`; reload the good pack -> ok; `ready`; one frame.
- Session end: `input.block off`, `quit`.

## Client rules
- Timeouts nest: the mod's `timeoutSeconds` < the client wait < any outer wait. A client timeout ends the request, not the session; send `cancel`.
- Log every request, response and event as JSONL in the run folder (`launch`: results/raw/launch-<UTC time>/requests.jsonl), with the token in `hello` redacted: the token is never written to a file (mod.md#5-safety). ALC had no per-request log.
- Treat `hook.error`, `focus.lost`, `screen.opened`, `reload.done` and `dimension.changed` during a window or capture as invalidating it.
- The harness keeps verifying frame hashes against the manifest. The mod's answer is used to proceed, the files to judge.
- Tests: a protocol fake generated from the command table, covering every command, including capture, path and timers.
