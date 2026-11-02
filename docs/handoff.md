# Handoff
Status: the latest stop: M4.P05 check L4 and E3's evidence done on branch m4, committed and pushed: `check L4` replays a capture run's .rdc in qrenderdoc, the underwater capture run gave E3's shares and two identical captures of one view. M4.P06 is next.

## Contents
Outcome · What was built · Review · Checks · Deferred and logged · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P05
- The Exit of M4.P05 (docs/plans/m4.md) held in this session (2026-11-02, AST), shown:
  - `check L4 m4-capture-3` (12:35:44-12:36:08, 6 captures in 24.2 s) and `check L4 m4-capture-4` (12:34:08-12:34:41, 4 captures in 32.9 s) print per capture the shares per program and per group, the ungrouped share and the cutout draws' groups and part of it, each .rdc held to its record's sha256;
  - m4-capture-4, a capture run on the debug tier at underwater: "optilux run: ok; results/records/m4-capture-4.json: 4 of 4 captures valid, 4 .rdc hashed, 1638.7 MiB", 12:26:15 to 12:28:35, one launch; the hello pack (`optilux@HEAD`, a2408be's zip, sha512 da6e0453..., the bytes m4-capture-3 took), Unbound played, Unbound played with SHADOW_QUALITY -1, the hello pack again;
  - two captures of one view: hello-again against hello at underwater, 8 of 9 passes identical on their used pixels, every pass the pack runs (sky_basic, sky_textured, sodium_terrain_solid, sodium_terrain_cutout, particles, sodium_terrain_translucent, clouds, final); the ninth, vanilla's unlabelled program (Program 441) writing a 16x16 RGBA8 texture, the lightmap's size, differs in 163 of 256 texels, compared on every texel as L4 compares a non-integer target (its block-light flicker runs on the client tick, inferred; D79 keeps the pack off it). No closure: one view, not the 11 perf views (offline.md#decision-powers).
- E3's shares (D82), underwater, Unbound played, of each replayed frame: outside every group 1.16 % with shadows on, 1.91 % off, the same four kinds (copies 0.62 and 1.05 %, blits 0.46 and 0.61 %, clears 0.07 and 0.22 %, vanilla's unlabelled program 0.01 and 0.02 %); the cutout terrain draws 28.98 % on (Terrain solid 21.39 %, Shadow Terrain solid 7.59 %) and 27.09 % off (Terrain solid), 0.00 % of the ungrouped share in both; in all ten captures the cutout draws lie inside groups only, against P10's reading. Recorded in design.md#8-open-decisions E3; E3 stays open (D82).
- The first attempt (11:27:36-11:37:57) ended at D42 after 10 min: input every few seconds and AzerothSurvivors.exe at 39-59 % of the 3D engine; nothing launched, no record; the world restore ran (no change); the user closed it and the second attempt ran.

## What was built
- optilux/l4replay.py, run by `qrenderdoc.exe --python` in RenderDoc 1.46's bundled Python 3.8 (P7), its job named by OPTILUX_L4_JOB, the window minimized (SW_SHOWMINNOACTIVE), replay.json written whole (a .part renamed), then os._exit: the walk reads each draw's program and draw framebuffer from the glUseProgram and glBindFramebuffer chunks (seeded from the first draw's pipeline state) and holds both to RenderDoc's state at each change (probes: 3,896 of 3,896 draws by program, 0.06 s against 146 s by SetFrameEvent; 17 of 17 framebuffer changes); FetchCounters' EventGPUDuration per action; per pass (program and framebuffer, "<label> #2" for a second) its last draw's draw-buffer and depth targets by GetTextureData; replay A/B: no-op (the capture's own source rebuilt, written beside the replay), control (a second no-op) and candidate by BuildTargetShader and ReplaceResource, 5 fetches beside the original, each replacement removed; a failed build or a label naming two programs is its entry's error.
- optilux/l4.py: qrenderdoc beside the pinned renderdoccmd.exe; each .rdc held to its sha256; the replay's events checked; shares per program (else per kind), per outermost group, per path, the ungrouped share and the cutout draws' (CUTOUT: terrain_cutout and sodium_terrain_cutout, main and shadow); pass outputs decoded (RenderDoc's D32 as float, D16) and compared per pixel, an integer target's only where its pass's depth shows geometry, the far value read off the depth; closures only at every perf view of an ok record (closures), a replay A/B or an attribution refused (closure).
- `check L4 <run> [--ab PROGRAM.STAGE=FILE] [--capture VIEW/VARIANT] [--keep] [--json]`: every valid capture replayed; pass outputs per view against the first capture of the same pack family (Optilux builds, or one reference pack); --ab with one --capture; raw/<run>/l4/ (replay.json per capture, l4.json); targets deleted unless --keep. Outside run's imports (P4).
- Docs: offline.md (Status, L4's row, L4 as built, Decision powers, Tools: captures and replays, Costs; cut to fit: internal duplicates, Viewfinder's spike facts pointed at platform.md#mc-263-verified, RGA's figures at gpu-iris.md and playbook.md), design.md (the check row; E3's evidence), AGENTS.md (l1.py-l4.py), CHANGELOG.md's 0.5.0 bullet.

## Review
The reviewer agent on l4.py, l4replay.py and check.py's L4 (correctness): 1 high, 3 medium, 5 low, each read at its source. Fixed before the first commit: closures per view (now every perf view of an ok record), a pass with no target identical (now undecided), --ab in every capture with a failed build losing the run (now one --capture, the error per entry, the source's sha256 kept), only a program's last draw read and one label's programs merged (now per program and framebuffer), CUTOUT's comment, the walk's docstring, closures from a failed record. Logged, not fixed: a candidate that compiles but fails to link may leave the original in place (unverified, Weak points).

## Checks
- Start (2026-11-02 11:12 AST): branch m4 clean at a2408be; 1105 passed; verify docs 0 violations.
- Before each commit: `optilux test` green (1122 passed), ruff and pyright clean, verify docs 0 violations, verify records 0 violations (399 records with m4-capture-4); no mod change. CI green on each push before the next.
- tests/test_l4.py: 17 tests: the parsers on a fixture JSON (tests/fixtures/l4/replay.json, hand-computed shares), the pass-output tier on fixture targets (reversed and forward depth, an integer target masked, unorm on every pixel, undecided cases), a replay A/B refused as a closure, check L4 through a stand-in for qrenderdoc (closures held short of the perf views, given at both, refused for a failed record), the script's Python 3.8 grammar; and the pinned qrenderdoc on m4-capture-3's End capture (skipped without it, as in CI).

## Deferred and logged
- The hello pack's pair joined the underwater run (the prompt names Unbound's two): the exit's two captures of one view need a deterministic pack, and the plan allows one launch.
- L4's closures are printed and kept in raw/<run>/l4/l4.json, not written into the record: no run spec yet needs them (offline.md#rules: a closure names its method and evidence in the record).
- FLIP on pass outputs (offline.md's old row) not built: L4 closes only on identical, so differing pixels are counted.

## Open questions
- 26.3's main depth is reversed in every capture (D32 cleared to 0, the sky 0, geometry in (0, 0.0026]), against platform.md#mc-263's "Iris 1.11.7 undoes it while a pack renders" (R11): M4.P06's probe should read depthtex0 in a pack before D75's sky skip by depth is written.
- E3: whether the timers, hooked at the head of GLDebug's calls, bracket the spans the GL stream shows; where M2's 0.048 ms lies.
- From the last handoffs: P22 and P23's RGBA16UI readback and renderStage (M4.P06's probe); RenderDoc's target-control server and runtime's java.exe blocked inbound on Public networks (a new Temurin pin prompts again); pinning gamma, Smooth Lighting and See-Through Leaves (the user's); M5's split; M3's carried list (git 78ea8b3's handoff).

## Weak points
- Replay shares move between replays (forest_noon, hello: cutout 47.3 %, 41.1 % and 42.4 % in three replays): one replay explains, never measures.
- A replay A/B's candidate that compiles but fails to link may leave the original in place (unverified); the A/B ran once, on m4-capture-3's forest_noon hello (final.frag from m3-dump-1: predicted +0.04 points, the control -0.01).
- Pass outputs of Unbound at 4K write about 2 GB a capture under raw/<run>/l4/ before they are compared and deleted.
- From the last handoffs: one capture per press, not aligned on the pack's cycle (the hello pack's is 1); captures 106-607 MiB under results/raw/ (ignored); the displays held only from `run`'s start.

## Commits and time
- 2750f21 (`check L4` with its tests and docs), 1d385a1 (m4-capture-4 with E3's evidence), then this handoff; CI green on each.
- M4.P05: about 1.8 h of work against 3 h (2026-11-02 11:12 to about 12:58 AST), 10 min of it D42's wait. Machine: 1 launch, 2 min 20 s.
- Tripwire: actuals about 74.1 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3, M4 so far 9.9: P00 3.8, P01 0.6, P02 0.7, P03 0.9, P04 2.1, P05 1.8) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P06 The base pack (docs/prompts/m4.md), in a fresh session; its three launches (the probe's dump and capture runs, the pack's visual run) send input, so the machine left alone; the reversed depth (Open questions) bears on D75's sky skip.
