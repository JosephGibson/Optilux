# Offline testing
Status: L0 built in M3.P04 (optilux/offline.py), L1 and L2 but L2's uniform-work scan in M3.P08 (optilux/l1.py, l2.py), L3's function tests in M4.P02 (optilux/l3.py), each run with `optilux check <level>` (design.md#5-interfaces); L3's custom uniforms, L4 and the scan are spec, for M4, and L5 runs in a dev session. Each method is ranked by what ALC recorded about it.

## Contents
Rules · Levels · Decision powers · ALC evidence · Tools · Costs · Verify

## Rules
- Offline methods judge a change without a measured session. They come in three powers:
  - close: a candidate is decided without measurement;
  - predict: an expected size and sign, confirmed later by measurement;
  - explain: why a result happened, never a gate.
- A method may only use the power its record earned (Decision powers).
- Ground truth is what Iris compiles, not the pack's source: Iris rewrites built-ins, and compiled code depends on the settings.
- Every offline closure names its method and evidence in the run record. ALC never checked a closure live; Optilux spot-checks one per milestone.
- ALC named its replay method "E2". Optilux calls it replay A/B, because design.md's evidence decisions also use E-numbers.

## Levels
Cheapest first; a change climbs only as far as it needs.

| Level | Method | Needs | Power |
|---|---|---|---|
| L0 static | glslang preprocess (`-E`) under Iris's macros, then compile + link (`-l`) + reflection (`-q`) + cross-stage check (`--validate-io`) per program over a variant matrix (the defaults, each option switched alone, each dimension); similarity check; profile check (every key in config/profiles/ declared by its pack, its value listed or the default) | source only | close (broken builds) |
| L1 Iris-faithful | Iris dumps (`patched_shaders`, via iris.properties' enableDebugOptions, plans/m3.md D60, or Viewfinder). Then: premise check (is the code compiled and executed at these settings?), dump equality / took-effect, impact matrix and pipeline audit from the pipeline spec | one launch per settings set | close |
| L2 compiler view | RGA OpenGL gfx1101 on dump stages: ISA, VGPR, `--livereg`, `--livereg-sgpr`, `--cfg`; uniform-work scan (PB) | dumps | explain |
| L3 function tests | each include under shaders/lib/ with a test file under tests/l3/ compiled by moderngl into a program calling its functions over a float texture of synthetic cases, read back against numpy goldens within the test's tolerance (tonemap, packing, noise, TAA maths). Custom uniforms evaluated in Iris's own expression engine (gpu-iris.md#custom-uniforms) against the GLSL they replace | source and a GL 3.3 context | close (function correctness) |
| L4 replay | RenderDoc 1.46 on a stored capture: attribution shares; replay A/B (candidate vs no-op replacement); per-pass golden images (`GetTextureData` + FLIP) | one capture launch per baseline | predict (A/B), close (pass golden images: identical) |
| L5 in-game dev | Viewfinder MCP (dev tier): shader hot-swap with compiler diagnostics, pass-output dumps, texture/SSBO inspection, program reflection, per-pass GPU timings | a dev session; not evidence until E5 (design.md#8-open-decisions) | explain; dumps become L3/L4 fixtures |

- Variant matrix: generated from the pack's option list and the pipeline spec, not hand-written. ALC verified only its played settings, and a "profiles x dimensions" check was planned but never built.
- L0 as built (M3.P04, `optilux check L0 [<pack>]`: shader/, a folder holding shaders/, a zip, or - for a zip on stdin):
  - Iris 1.11.7's rules, read in the pinned jar with javap: a dimension takes its world0, world-1 or world1 folder when it holds a program (a file of Iris's program names), else the base set, world0's when that folder exists, else the root's; never a merge (a dimension.properties that maps anything is refused). Includes expanded, absolute from shaders/ or relative to the file, a missing one failing as Iris refuses the pack. Options as OptionAnnotatedSource registers and edits them: an on/off `#define` or const that a bare `#ifdef`/`#ifndef` in its include-graph component tests, a value `#define` with its `//[...]` list and default, Iris's 81 const names; declarations with different defaults dropped.
  - Iris's defines from StandardMacros and IrisDefines: MC_VERSION 260300 and IRIS_VERSION 11107 from the pins, MC_MIPMAP_LEVEL from options.txt, MC_GL_VERSION 330 (the game's "3.3.0 Core Profile Context", m3-hello-1's log), MC_OS_WINDOWS, IS_IRIS, the render stages, the biome categories; no dimension macro exists. A stage fails as unchecked when it names what only the running game knows (the driver's GLSL version, vendor, renderer and extensions, biome ids, feature flags, texture formats, colour spaces) or, in a conditional, a macro of glslang's own (`__VERSION__`, GL_core_profile, GL_<extension>), which Iris's preprocessor (JCPP) never has.
  - Not built yet, so refused: tessellation stages (Iris reads them only under the TESSELLATION_SHADERS flag) and compute programs.
  - The matrix: the defaults, then each option alone at each of its other values; each pass's program in each of its dimensions, a stage file no pass names failing. The hello pack: 8 programs x 3 dimensions x 2 variants = 48 builds, 16 compiled (the dimensions share the root), 48 glslang runs in 0.3 s.
  - A failure names the program, the stage file and the line glslang's error maps back to, the option values and the dimensions, under the defines printed once.
- L1 as built (M3.P08, `optilux check L1 <run>`) on a dump run's record (`run`'s dump kind, plans/m3.md D60), each candidate against the baseline, the first variant:
  - Dump equality: per dimension, its print against the baseline's file by file, a name without Iris's NNN_ counter, an ID map's copy without its date line. Equal in a dimension: skipped there; in every dimension the baseline was dumped in: no effect. No closure when the candidate changes a file no print shows (a texture, its .mcmeta, a lang file, dimension.properties). Prints are compared only within one ok record, so debug prints only with debug prints (P13).
  - The premise check: the candidate's source against the baseline's by bytes (each zip kept under raw/<run>/packs/), each changed function looked up in its dumped stages (a removed one in the baseline's) and walked from main through its calls. None defined: not compiled; defined, never reached: not executed (Iris keeps uncalled functions under its flag, P13). It reads the source with continued lines joined and each directive in place, and stays undecided on a change outside a function's text, a changed comment (Iris reads RENDERTARGETS and option lists there), a name a #define also takes, unbalanced braces, a file that is no GLSL or a print with no stage. A verdict closes only for a candidate of the baseline's options dumped in every dimension: not compiled where the prints are equal too, not executed where every differing stage differs in dead changed functions alone.
  - The impact matrix: changed files -> the program files including them (Iris expands includes as text, before its preprocessor) -> pipeline.json's passes in each dimension's folder -> their views; a changed option -> the passes naming it.
  - The audit, per dump of an Optilux variant (pipeline.json is its pack's): the passes enabled there (their dimensions, no `program.<name>.enabled = false` in its preprocessed.properties); each colortex a pass samples written by an enabled pass before it, each one written read after it, each custom uniform a pass reads defined wherever it runs. Each uniform the pack declares that a printed stage still reads is Iris's (l1.IRIS_UNIFORMS, 195 names read in the pinned jar with javap: what UniformHolder's registering calls receive, MatrixUniforms' composed matrices, ExternallyManagedUniforms' helpers) or a custom one, else it reads 0. The transformers replace the core names (modelViewMatrix, chunkOffset, ...) before the print; Iris's own programs (the shadow_* keys) are not the pack's, so not read for it.
  - `run` runs it on its own record in a child process (out of `harness`) once the session ended ok, so the record's `offline` holds the closures; `verify records` re-derives each candidate's dump-equality closure from the manifests and holds the record's to it; `check L1 <run>` says whether the record's closures agree.
- L2 as built (M3.P08, `optilux check L2 <run>`, optilux/l2.py) on a dump run's record: each print's stage files grouped by program, held to their sha256, one RGA run per distinct program (`-s opengl -c gfx1101`, P7) with its ISA, statistics, live VGPRs and SGPRs and CFG under results/raw/<run>/l2/<program>-<sha>/ and l2.json beside them; per stage its VGPRs and SGPRs used, spills, scratch, ISA bytes and live-register peaks. RGA names its outputs by stage as vert, tesc, tese, geom and frag (seen 2026-10-22) and must print the pin's `printed` version exactly. RGA exits 0 on a failed build, so a stage of a program without its "succeeded" line, its statistics or a live-register peak is listed as a known offline failure with RGA's lines (the game compiled every stage of an ok record); RGA not running fails the verb; L2 never gates.
- L3 as built (M4.P02, `optilux check L3 [<pack>]`, optilux/l3.py):
  - per include under lib/, its test file tests/l3/<path>.py (lib/fog.glsl's is tests/l3/lib/fog.py), Python whose TESTS lists l3.Function entries: the function, its result type, its arguments per case (float, int, bool, vec2-4, mat4), the golden (float32 numpy from the formula the function implements, never read off the GPU), an absolute and a relative tolerance, the option values (the pack's own options, refused where Iris registers none), the include's uniforms and samplers; an include without a test file is listed untested;
  - the program: `#version 330 core`, L0's Iris macros, the include expanded at the option values as L0 expands it, then a main reading each case's arguments by texelFetch from an RGBA32F texture (a column per case) and writing the result into an RGBA32F target (a texel per case), read back. A case fails beyond its tolerance or with NaN or an infinity on one side alone; a failure names the include, the function, the input, both values and the options, a compile error the include's line;
  - the first goldens (2026-10-27): fog.glsl's fogDistances, fogRamp and withFog at far 32, 256 and 1024, on and off BENCH_DETERMINISTIC, and light.glsl's restingBlockLight over 0-240 and surfaceLight on a synthetic lightmap at its texel centres: 14 functions over 29,578 cases, each within its tolerance. Their first run found light.glsl testing the define without including options.glsl, so it saw it only through its includer; it now includes it;
  - its tests skip without a GL 3.3 context (CI).
- Impact matrix: changed files -> includes -> passes (pipeline spec) -> views that exercise them. This replaces ALC's text-walk `deps`, which over-reported (enderBeams reached 37 files; 5 were really kept) and missed Voxy wrappers.

## Decision powers
What may close a candidate:
- L0 build failure: the variant is broken; fix it, do not measure.
- L1 premise failure: the changed code is not compiled or not executed at the measured settings. ALC closed 4 entries this way, all from reading dumps.
- L1 dump equality: a candidate whose dumped stages and properties equal the baseline's in a dimension is skipped there. If they equal it everywhere, the change did not take effect. ALC skipped 16 of 40 candidate-view captures.
- L3 failure: a function returns wrong values.
- L4 pass golden image identical: if the changed pass's outputs match the baseline's bit for bit on every captured view (captures cover every perf view), the visual tier is identical for that pass. Timing still needs measurement.

What may only predict:
- Replay A/B: always against a no-op replacement, never the original (a no-op build alone changed 682 px). Replay time follows the GPU clock, so use shares, never ms.
  - The no-op spread on gbuffers stages (0.07-3.6 % of a frame) is larger than any closure limit, so replay A/B never closes a gbuffers candidate.

What may only explain:
- RGA: ISA comparable to the dumps on only some stages (ALC: 17 of 48 post stages; every vertex stage differed). Occupancy predictions did not pay (60 -> 24 VGPRs measured slower). Static counts hide dynamic skips (-1.2 % instructions; -59 % pass time in replay). Directive and constant changes leave the ISA identical yet are real (-1.57 %, -0.69 %).
- Viewfinder per-pass timings, until checked against GPUBusy (mod.md#12-acceptance, A11).

## ALC evidence
Ranked by value x reliability / cost:
1. Iris dumps + glslang under inferred macros, for premise checks: 7 entries closed with no measurement; ~2 s for 219 wrappers.
2. Dump equality / took-effect: exact and cheap; 16 of 40 captures skipped.
3. Replay A/B as a predictor: sign and size right on 5/5 (B01-B02); EXP-036 predicted 7.1 %, measured 7.3 %. EXP-018 over-predicted on 7/8 views.
4. RenderDoc attribution and resource audits: ranked the frame; an audit premise (1,344 reads, all NoFilter) led to an accepted -2.14 %.
5. RGA on dumps: three closures, all on premises, never on occupancy.
6. Tree-diff impact matrix and coverage: flagged 4 of 5 B02 candidates; missed Voxy wrappers.
7. Region-file camera scouting found a camera inside nylium (~12,000 scored). Optilux checks poses in game instead (measurement.md#baseline-suite; user, 2026-10-06).

ALC never rendered anything offline: glfw and PyOpenGL were only a GL-capability probe.

## Tools
glslang, RGA and RenderDoc are pinned in config/tools.json (file, sha256, source), which `install` unpacks into runtime/tools/.
- glslang 16.6.0, runtime/tools/glslang-16.6.0/bin/glslang.exe (`-E` preprocess, `-l` link, `-q` reflection). It is not AMD's compiler and can accept code the driver rejects; the in-game reload is the final compile check.
  - `-l` alone links a fragment input no vertex output writes, which the driver refuses (gpu-iris.md#programs-and-alpha-tests); `--validate-io` refuses it and mismatched types, and still links unread outputs (M3.P04). `-E` keeps the input's line numbers.
- Iris dumps: `enableDebugOptions=true` (iris.properties) writes `patched_shaders/` per pipeline build. They are fully preprocessed, and debug mode may change performance.
  - 1.11.7 (javap, M3.P08): a reload under the flag writes game/preprocessed.properties and original.properties, then patched_shaders/<id>.properties per ID map (Properties.store: its first line the date), then every program as NNN_<name>.vsh, .fsh and .json, the counter per pipeline; ShaderMap fills every ShaderKey when the pipeline is made, so the print is whole once the reload answers. Its clear spares *.properties, so a dump run empties both places before each reload.
  - TransformPatcher caches each transform (a static LRUCache of 400, keyed by the sources and parameters, never cleared) and reads the flag only on a miss: a program first built without the flag prints its flag-off transform later. A dump run turns the flag on from its start-of-run reload; selftest's reload of the launch's reference pack stays flag-off.
  - Iris's patcher is the Java library glsl-transformer (1.11.7 bundles glsl-transformer-3.0.0-pre3 and jcpp-1.4.14). Running it outside the game could produce dumps with no launch [verify].
- Shadesmith (GPL-3.0; expands includes and options, then glslang -> spirv-opt -> spirv-cross): unused, as glslang on the pack's own source covers L0 (plans/m3.md D58).
- RGA 2.15, runtime/tools/rga-2.15/rga.exe (`-s opengl -c gfx1101`; `--version` prints 2.15.0.30); the GUI no longer does OpenGL. Driver-independent, so it explains and never gates.
- RenderDoc 1.46, runtime/tools/renderdoc-1.46/RenderDoc_1.46_64/ (renderdoccmd.exe, qrenderdoc.exe, renderdoc.dll; `renderdoccmd version` prints v1.46 built from e4bd23b6, 2026-10-26); RenderDoc_1.46_64.zip pinned by the sha256 of the day's download (101,000,153 bytes), as renderdoc.org publishes only a .sig (plans/m4.md P7):
  - headless `renderdoc` Python module (`InitialiseReplay`, `FetchCounters` for EventGPUDuration);
  - 1.46 renamed `ActionDescription.next/previous` and removed `GetDefaultCaptureOptions`;
  - no GL ISA view on current AMD drivers;
  - ALC quirks: qrenderdoc's bundled Python 3.8, the first-run analytics dialog, 77 % of events unmapped until mapped by bound program, replay ~1.7x live.
- Iris's expression engine (gpu-iris.md#custom-uniforms), for L3's custom uniforms: optilux/IrisExpressions.java, run by optilux/expressions.py through the pinned Temurin's java as a single source file (about 1 s a start), the store's Iris jar (sha512) and the launch spec's JOML 1.10.9 and fastutil 8.5.18 (sha1) on its classpath, each hash-checked before every start. kroppeb.stareval's Parser with IrisOptions.options, ExpressionResolver with IrisFunctions.functions; inputs and expressions typed (bool, int, float, vec2-4, mat4), in order, each expression an input of those after it; floats cross as float32 both ways (hex in, Java's shortest decimal out), a mat4 by column. Iris's CustomUniforms itself needs Guava and Iris's logging, so the runner skips it.
- moderngl 5.13.0 with glcontext 3.1.0, pinned in pyproject.toml (plans/m4.md P9): a standalone WGL context for L3, `create_standalone_context()` giving "3.3.0 Core Profile Context" on the RX 7800 XT (2026-10-26). EGL is Linux-only.
- Viewfinder v2.1.4+26.3 (MIT, Fabric, needs Iris), dev tier:
  - MCP over streamable HTTP at http://127.0.0.1:7150/mcp, started with the game, loopback only, no authentication. It is not read-only: an MCP client can edit packs and change scenes. One active request, 32 queued. Spike L2: 23 tools (reload, pack switch with effective options, captures to game/viewfinder_captures/, per-pass GPU timings in ns, set_scene, control_ticks), no server-command tool; its MCP thread keeps the JVM alive at quit (watchdog crash report, exit -8).
  - Claude Code can connect to it directly during shader work.
  - Its per-pass GPU timings may replace building GL timers in optilux-helper (E3).
  - Overhead unknown; under Iris's debug context it reported 30 fps where the bench tier ran 141 (confounded, spike L2).
- Image metrics, pinned in pyproject.toml: flip-evaluator 1.7 (FLIP on frames), scikit-image 0.26.0 (SSIM), with pillow 13.0.0 and numpy 2.5.4 decoding. ColorVideoVDP 0.5.7 is the candidate metric for a temporal gate; it must first flag the positive controls (measurement.md#visual-protocol).

## Costs
ALC timings, for planning:
- glslang preprocess + compile: 59 ms per program, 219 wrappers in ~2 s on 16 threads.
- RGA: 21 s for 86 programs.
- Replay A/B: ~25 s per view on the first run, then cached by capture, sources, helper version and driver.
- Attribution: ~6 min per launch for 8 views; captures 192-462 MB at 4K.
- A replay A/B baseline goes stale when the baseline pack changes. ALC's never did, because it was frozen upstream; Optilux's will, so each new baseline needs one capture launch (debug tier).

## Verify
- glsl-transformer offline: does it reproduce Iris 1.11.7's dumps byte for byte?
- Viewfinder:
  - its overhead: before 1.0 only the in-session A8 timers arm with Viewfinder as the timer source (its presence sits in both arms); the declared-treatment presence check waits for J1 (jvm.md#build-order);
  - do its per-pass sums track GPUBusy;
  - is it quiet when no client is connected?

Sources:
- https://gpuopen.com/rga/
- https://github.com/GPUOpen-Tools/radeon_gpu_analyzer/releases/
- https://github.com/baldurk/renderdoc/releases/v1.46
- https://renderdoc.org/docs/python_api/examples/renderdoc/fetch_counters.html
- https://github.com/KhronosGroup/glslang/releases
- https://shaders.properties/current/reference/miscellaneous/debugging_shaders/
- https://github.com/IrisShaders/glsl-transformer
- https://github.com/Luna5ama/shadesmith
- https://github.com/xirreal/viewfinder
- https://github.com/moderngl/moderngl/releases
- https://github.com/gfxdisp/ColorVideoVDP
