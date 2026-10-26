# Handoff
Status: the latest stop: M4's plan approved and its prompt set written on branch m4, with M3 closed in the roadmap, committed and pushed. M4.P01 is next.

## Contents
Outcome · The plan · What the jars showed · Decisions · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M4.P00
- The Plan prompt, run in one session (2026-10-26, ADT): docs/plans/m4.md, approved by the user (its section 10); docs/prompts/m4.md, 12 phase prompts and Resume; roadmap.md's M3 section closed to one line, M4's sections expanded from the plan, D72 closed, F28 and F29 added and M4's rows pointed at their phases; CHANGELOG's 0.5.0 goal paragraph rewritten from the plan (VERSION 0.5.0 and the entry came in 16b9033).
- `uv run optilux status` prints M4.P01's prompt, checked after this file's commit.

## The plan
- 12 phases, 31 h agent (1.5, 3, 2.5, 3, 3, 4, 4, 3, 1.5, 2, 2.5, 1), about 233 launches and 8 h of machine, 5 of them M4.P09's recalibration; premises P1-P23 verified 2026-10-26; decisions D75-D86.
- Its order follows identity: what the calibrations' identity sees (measured Optilux variants, the debug tier and its capture kind, view lists, coverage content) lands in M4.P03-P08, before M4.P09 freezes it; E2 (M4.P10) precedes the cost rows (M4.P11), so they measure the path that ships.

## What the jars showed
P10-P22, read with javap in the pinned Iris 1.11.7, Sodium 0.9.2 and 26.3 client jars, hash-checked into the scratchpad (four researcher agents, spot-checked). M4.P06 corrects docs/research/ and shader.md#facts where they disagree:
- Iris clears every colortex with a float glClear, integer targets too, which GL leaves undefined: the G-buffer is RGBA16UI with Clear=false, sky found by depth (D75).
- Nearly every blended draw runs after deferred; only opaque-glyph text, banner patterns, armour cracks, the shield and trim glint pass and crumbling on opaque models come before it (D76's targets).
- particles.ordering, separateEntityDraws, prepareBeforeShadow, beacon.beam.depth, rain.depth and stars are read by nothing; sky= drops only Iris's horizon; blend.<program>.<buffer> fails the load without ARB_draw_buffers_blend.
- Sodium's cutout test is > 0.5; vaUV2 is a smooth-lighting average, not 16 x a level; separateAo needs no shadow pass; oldLighting false gives every face UP's shade, 0.9 in the Nether.
- Under /tick freeze 26.3 returns the partial tick as 1.0, so tick-delta uniforms hold still; custom uniforms run every frame; most glint draws in its item's own pass through mc_sampleGlint(), which Iris never calls.
- No GLDebug group covers cutout terrain in either pass, and Viewfinder times the same groups as the helper: the cause of A11's underwater miss (E3, D82).
- Measured runs admit only Unbound and the passthrough (record.check_variants): M4's cost rows need a harness change, so one recalibration (D80).
- Found today: RenderDoc 1.46, RenderDoc_1.46_64.zip, sha256 9ca4d09e... of 101,000,153 bytes (no published checksum); moderngl 5.13.0 and glcontext 3.1.0.

## Decisions
- D72 answered (user, 2026-10-26): Unbound as the reference; nothing from the not-yet list in M4; the budget per view against Unbound played (D84: the default faster on every perf view, a stop otherwise; chosen over the recommended 120 fps default); M6's ratio kept on shared features.
- D82 (no timer rows in M4; E3 open with its evidence; F6 moved) and D83 (a named mob, an off-hand translucent item and an outline pose, plus from the critique a gradient banner and trimmed armour; lightning, the damaged block, snow and spider eyes waived; Peaceful kept) taken as recommended. D86, the look review, is the user's when they choose.
- /critique (gpt-6.1-sol, xhigh, artifact mode): 1 high and 2 medium findings, each read at its source and folded in, none rejected (the plan's section 10); Claude's own reading added view lists, as two packs on 11 views pass the reload cap.

## Checks
- Start (15:44 ADT): branch m4 clean at 78ea8b3, equal to origin/m4; 1024 passed; verify docs 0 violations; ruff clean.
- Before each commit: 1024 passed; verify docs 0 violations (52 files): the plan 33,738 bytes, the prompt set 37,722, roadmap.md 34,166, each LF without BOM; optilux.prompts reads the plan's 12 phases with their estimates and the set's 12 prompts with Resume.
- CI green on 60d574c, 4e05349, 3d2dd07 and 62a610d, each watched to its end before the next push.

## Open questions
- The plan's open premises, each decided in its phase: P22's extension list and P23's RGBA16UI readback and renderStage (M4.P06), F12 through SendInput (M4.P04).
- Pinning gamma, Smooth Lighting and See-Through Leaves (research/lighting.md#open-questions): identity already as read, left unpinned; the user's.
- M5's split (research/synthesis.md#milestones): M5's plan.
- Carried from M3's handoff (git 78ea8b3): the one test that failed once in parallel, unnamed; the quick twin's +0.1782 % under the twin monitor; the available memory at the budget run; the readiness predicate after a reload; `screen = BENCH_DETERMINISTIC`; the moving coverage items (D64); Unbound's coverage-mob shadows; the olive End stone; textures on frozen ticks; the display guard for A9; Nether fog and the features on neither list; M2's carried list (git 7dfc2fa's handoff). The help strings and the docstring go in M4.P03.

## Weak points
- javap -c prints no invokedynamic targets or concat recipes: a few readings (the glint coordinate, FeatureFlags' bindings, the End-flash shadow gate) rest on names and types.
- The plan's cost figures are the research's, about 2x; D84's margin under Unbound is first measured in M4.P11.
- docs/research/ keeps the claims the jars contradict until M4.P06.

## Commits and time
- 60d574c (M3 closed in the roadmap), 4e05349 (the plan and M4's roadmap sections), 3d2dd07 (the 0.5.0 goal), 62a610d (the prompt set), then this handoff; each pushed after the last one's CI ended green.
- M4.P00: about 3.8 h against 1 h (15:44 to about 19:30 ADT); machine: downloads into the scratchpad (the pinned jars, Temurin, RenderDoc's zip), no launch.
- Tripwire: actuals about 64.2 h (M0 3.3, M1 20.3, M2 21.3, M3 19.3) against M0-M3's 87.3 h, the trip at 174.6 h; M4 estimated at 31 h.

## Next
/optilux-next prints M4.P01 Tools (docs/prompts/m4.md), size M, Opus 5.5 high suggested, in a fresh session.
