# Handoff
Status: the latest stop: M4.P01 Tools done on branch m4, committed and pushed: RenderDoc 1.46 pinned and unpacked by install, moderngl and glcontext locked, Iris's expression engine run outside the game. M4.P02 is next.

## Contents
Outcome · The pins · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P01
- The Exit of M4.P01 (docs/plans/m4.md) held in one session (2026-10-26, ADT), each item shown:
  - `uv run optilux install`: "tools: RenderDoc_1.46_64.zip sha256-equal (equal), unpacked at runtime/tools/renderdoc-1.46/RenderDoc_1.46_64/renderdoccmd.exe", "optilux install: ok; 5,247 hashes checked", the launch spec equal;
  - `renderdoccmd version`: "renderdoccmd x64 v1.46 built from e4bd23b671d3d5a747ff5221dbe08a63eb6ca200";
  - `moderngl.create_standalone_context()`: "3.3.0 Core Profile Context 26.8.1.260810 | AMD Radeon RX 7800 XT", version_code 330;
  - the runner on the fixtures: a * b 3.63, gbufferModelView.y the matrix's second column, frameCounter % 16 15 at 720719, each equal to float32 numpy; tests/test_expressions.py's 16 seeded frames bit-equal;
  - `git status` clean after the commits.

## The pins
- RenderDoc 1.46 (config/tools.json `renderdoc`): RenderDoc_1.46_64.zip from https://renderdoc.org/stable/1.46/, sha256 9ca4d09ecaba2cc791168660d6fc2a7e3d70fe67146e87ec05c5f8dea70772f7, 101,000,153 bytes (P7's size; the URL served the same Content-Length today). Pinned from M4.P00's scratchpad download (15:59 ADT), then install's own download into runtime/tools/ (20:02) checked equal to it: two fetches, one hash. The zip's one top folder RenderDoc_1.46_64/ holds renderdoccmd.exe, qrenderdoc.exe, renderdoc.dll and python38.dll; unpacked into runtime/tools/renderdoc-1.46/. The `later` note is gone.
- moderngl 5.13.0 and glcontext 3.1.0, pinned exactly in pyproject.toml, locked by uv 0.12.23 (33 packages), synced.
- The expression runner: optilux/IrisExpressions.java on the store's iris-fabric-1.11.7+mc26.3.jar (sha512 the platform file's), libraries/org/joml/joml/1.10.9 and it/unimi/dsi/fastutil/8.5.18 (sha1 the launch spec's), all three hashed before each start; the pinned Temurin jdk-25.0.4.1+1's java.exe, found as launch finds it (unhashed, its archive install's sha256). kroppeb.stareval.parser.Parser.parse with IrisOptions.options, ExpressionResolver(IrisFunctions.functions, the inputs' types), Expression.evaluateTo; m.y resolves through IrisFunctions' access functions. Iris's CustomUniforms is not used: it needs Guava and IrisLogging. `-Djoml.nounsafe=true` keeps JDK 25's Unsafe warnings off stderr. About 1 s a start.

## Checks
- Start (19:52 ADT): branch m4 clean at 15211a1; 1024 passed; verify docs 0 violations.
- Before each commit: `optilux test` 1030 passed (1024 + 6: the RenderDoc pin refused off its hash, the Iris jar refused missing and off its sha512, the lines refused before a start, the float and mat4 crossing, the engine against float32 numpy, a refused expression named); verify docs 0 violations (platform.md 24,565 of 24,576 after cutting "from their GitHub releases" and "unpacked into"); ruff and pyright clean; every new file LF without BOM.
- run's module closure still 18 modules without optilux.expressions, and none of them changed: the calibrations' identity holds (P4).
- CI green on bb7ec7b and f7a4f4e, each watched to its end before the next push; 8b2f50b's and this commit's watched the same way.

## Deferred and logged
- install.py's module docstring still lists the tools as "(PresentMon, glslang, RGA)": install.py is in run's closure (P4), so a docstring edit would refuse both calibrations; fixed when M4.P03 changes the closure anyway.
- AGENTS.md's Layout does not name expressions.py or IrisExpressions.java: 16 bytes free; M4.P12's AGENTS.md as built.
- The first install's unpack failed at the rename of renderdoc-1.46.part (WinError 5, access denied), most likely a scanner holding the fresh exe and dll files; the zip was already sha256-equal. The rerun removed the .part folder, unpacked and renamed; nothing was left behind. install.unpack has no retry; if it recurs, a bounded retry on the rename (an install.py change, so with M4.P03).
- The runner evaluates in the given order; ordering a pack's custom uniforms by their references (Iris resolves forward references) is M4.P02's.

## Open questions
- The plan's open premises, each decided in its phase: P22's extension list and P23's RGBA16UI readback and renderStage (M4.P06), F12 through SendInput (M4.P04).
- Pinning gamma, Smooth Lighting and See-Through Leaves (research/lighting.md#open-questions): identity already as read, left unpinned; the user's.
- M5's split (research/synthesis.md#milestones): M5's plan.
- Carried from M3's handoff (git 78ea8b3): the one test that failed once in parallel, unnamed; the quick twin's +0.1782 % under the twin monitor; the available memory at the budget run; the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; M2's carried list (git 7dfc2fa's handoff). The help strings and the docstring go in M4.P03.

## Weak points
- The standalone context is GL 3.3 core, as the game's; L3's float targets and reads need nothing newer, untried until M4.P02.
- smooth() evaluates offline on the runner's clock, not the game's frame times: L3 compares only clock-free expressions (D79 refuses the smoothed ones under BENCH_DETERMINISTIC).
- javap -c prints no invokedynamic targets: the access functions' names rest on the passing m.y fixture, not a read.

## Commits and time
- bb7ec7b (the RenderDoc pin, its test and docs), f7a4f4e (moderngl and glcontext with the lock), 8b2f50b (the runner with its tests and docs), then this handoff.
- M4.P01: about 0.6 h against 1.5 h (19:52 to about 20:25 ADT); machine: RenderDoc's 101 MB into runtime/tools/ by install, no launch.
- Tripwire: actuals about 68.6 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 4.4: P00 3.8, P01 0.6) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P02 check L3 and L0's determinism rule (docs/prompts/m4.md), in a fresh session.
