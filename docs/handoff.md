# Handoff
Status: the latest stop: M3.P04 done, `check L0` and the iso profile v1 built, `run` refusing an Optilux zip that fails L0, and what M3.P05 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P04
- The exit holds, shown in this session (2026-10-20, ADT):
  - `uv run optilux check L0` (15:47): pass on shader/, 23 files, its zip sha512 d86371b7... (M3.P03's). The matrix: 8 programs x 3 dimensions x 2 variants (defaults, BENCH_DETERMINISTIC false) = 48 builds, 16 compiled as the dimensions share the root's programs, 48 glslang runs in 0.3 s; verify similarity 0 matches of 72 tokens (21 GLSL files, 629 tokens); the profile check ok for complementary-unbound-iso.json (119 names) and -played.json (26) against reference/complementary-unbound-r5.9.3/. The whole check under 1 s.
  - A broken copy of one stage in a scratch copy (final.fsh reading colortex9): exit 1, at both variants "FAIL final, its fragment stage shaders/final.fsh (compile and link), at BENCH_DETERMINISTIC true, in minecraft:overworld, minecraft:the_nether, minecraft:the_end, under the 78 macros above: shaders/final.fsh:9: 'colortex9' : undeclared identifier", the 78 defines printed once (-DMC_VERSION=260300 ... -DPPT_SNOW=2). A broken shared include (lib/surface_fragment.glsl:52) failed the 4 programs that compile that line, at both variants.
  - `run --check` of an acceptance spec with the `optilux` variant (in the scratchpad, never launched): the child's verdict on the zip's bytes passed, bound to its sha512, with pipeline.json's sha256 939b4bf0....
- No launch. runtime/tools/ only read (glslang; the Iris jar read with javap into the scratchpad). No system setting. reference/ read by `check L0` and by the reviewer agent on the iso profile.

## What changed
- `optilux check L0 [<pack>]` (optilux/offline.py, optilux/verbs/check.py): shader/ by default, a folder holding shaders/, a zip, or - for a zip on stdin. Iris 1.11.7's rules read in the pinned jar with javap: the dimension folders (world0 the base set once it exists), includes, options as OptionAnnotatedSource registers and edits them (on/off options per include-graph component, 81 const names), the 78 environment defines. Per program glslang -E, then -l -q --validate-io, its errors mapped back to the pack's file and line. A stage naming what only the game sets (the driver's macros, biome ids, feature flags, glslang's own macros in a conditional) fails as unchecked; tessellation, compute and dimension.properties are refused. Then verify similarity and the profile check of every config/profiles/*.json.
- The iso profile v1 (config/profiles/complementary-unbound-iso.json): `options` (48: played's 13, RAIN_STYLE 1 over played's 2, each dropped switch), `dropped` (41 names, three added by the review), `droppedNotes`, `kept` with BLOOM_ENABLED for bloom (as played's ablation row) and refraction and End switches added; `unresolved` gone. record.profile_options reads 48 options.
- `run` (optilux/verbs/run.py check_l0): prepare runs `python -m optilux.cli check L0 - --json` on an Optilux variant's zip in a child process, so the check stays out of the harness hash (record.module_closure holds 18 modules, none of them offline or check); a verdict on other bytes is refused; the summary (sha512, glslang, pipeline.json's hash, builds, variants, profiles) goes to the record's session.optilux.l0.
- Docs: offline.md (Status, Levels: L0 as built, Tools: --validate-io), design.md's verb row, shader.md#dropped-features, run-record.md#run-spec, played.json's `verify` note, CHANGELOG.md's 0.4.0 entry (three bullets).

## Review
- L0 (reviewer agent, correctness: the macros, the matrix, a false pass): 16 findings (1 high, 3 medium, 12 low), all latent for the hello pack; each verified in the jar (javap) or with glslang.
  - Fixed: H1 glslang's own macros (__VERSION__, GL_core_profile, GL_<extension>), which JCPP never has, refused in a conditional; M1 world0 the base set, a folder holding a program only under Iris's names; M2 tessellation (read under a feature flag) and compute refused; M3 a const bool needs an #ifdef too; L1 the 56 numbered const names; L2 references per include-graph component; L3 a missing include fails, as Iris refuses the pack; L4 any unset MC_ name; L6 the lone .fsh message; L7 an unknown dimension crashed; L8 Java's split; L10 a real failing verdict through the child (a test, skipped without glslang); L11 pipeline.json's hash recorded; L12 the copy must be the platform's reference pack.
  - Reported: L5 MC_GL_VERSION 330 rests on the game's log, "3.3.0 Core Profile Context 26.8.1.260810" in m3-hello-1's latest.log today, and nothing re-reads it; L9 a name declared on/off in one file and valued in another fails L0, while Iris keeps both (a false fail only).
- iso v1 (reviewer agent, against the unpacked pinned zip): 8 findings (4 medium, 4 low); every key and value valid, each value off by its en_US.lang label.
  - Fixed: 2 RP_MODE 0 also gates screen-space block reflections (noted); 3 WEATHER_TEX_OPACITY has no off, 100 draws rain at a quarter of the texture's alpha (note fixed, shader.md says so); 5 the End keeps its light-shaft pass for its End beams (noted); 6 WB_ANAMORPHIC, SELECT_OUTLINE_AUTO_HIDE and IPBR_EMISSIVE_MODE added to `dropped`; 7 DETAIL_QUALITY (refraction), END_FLASHES and END_BEAM_INTENSITY added to `kept`; 8 the kept notes say which are off at played's values.
  - Reported: 1 and 4 (Open questions).

## Choices
Neither the prompt nor the plan names these:
- "The dimension's" macros: Iris 1.11.7 defines none (StandardMacros, IrisDefines, ShaderPack); a dimension changes only its folder, so the dimensions sharing a folder share one build.
- --validate-io beside -l -q: plain -l links a fragment input no vertex output writes, which the driver refuses (gpu-iris.md#programs-and-alpha-tests).
- A value option is switched alone to each of its other values.
- What L0 cannot set fails a stage that names it, rather than passing on a guess; MC_GL_VERSION 330 from the game's log, MC_MIPMAP_LEVEL from suite.json's options.txt, MC_VERSION and IRIS_VERSION from the pins, all guarded by the bench tier's Iris sha512.
- The profile check reads options, defaultsKept, dropped, droppedNotes, kept.keys and the ablation rows; a missing reference copy is a problem in its verdict, not an abort.
- iso's `dropped` holds names, their values once in `options`.
- An `optilux@<ref>` zip is judged against the working tree's pipeline.json and profiles; the verdict records which pipeline.json.

## Checks
- Start (14:17 ADT): branch m3 clean at 643f270; 851 passed; verify docs 0 violations.
- Before each commit, on a tree equal to it: 899, 900, then 903 passed; ruff, ruff format and pyright clean; verify docs 0 violations; check L0 pass.
- CI green on b0d570d, 165c36e and 610736a, each watched to its end before the next push.

## Open questions
- Nether fog in iso (review finding 1): BORDER_FOG false (played's, and border fog is on the not-yet list) is Unbound's only distance fog in the Nether, as it undefines its atmospheric and cave fog there (lib/common.glsl), while Nether fog is in scope (shader.md#look-and-scope). nether_crimson and nether_soul compare unequal fog until the user decides which list wins there.
- Features on neither list (review finding 4): Unbound's waving foliage, leaves, lava, water and rain and its special portal effects stay on in iso; shader.md#look-and-scope sends everything not in scope to the not-yet list. The user's call, with D72.
- Carried: the water fog colour (M3.P06, M3.P09); D66, the driver 32.0.31041.1004 since 2026-10-20; D72; the ticks before /tick freeze; spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- MC_GL_VERSION 330 is a fixed fact: a driver giving another context version would move Iris's value unseen (L5).
- L0 models the bench tier only, and refuses rather than builds tessellation, compute and dimension.properties; a name both on/off and valued fails (L9).
- glslang is not AMD's compiler; the in-game reload stays the final check (offline.md#tools).
- Margins: AGENTS.md 26 bytes; measurement.md 23; platform.md 56; workflow.md 199.

## Commits and time
- b0d570d: check L0 with its tests. 165c36e: the iso profile v1. 610736a: run's gate with its tests. Then this handoff.
- 2026-10-20 14:17 to about 16:10 ADT: M3.P04 took about 1.9 h against 2 h. Tripwire: actuals about 52.3 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.8, M3.P02 about 0.8, M3.P03 about 1.9, M3.P04 about 1.9); the trip is at 174.6 h.

## Next
/optilux-next prints M3.P05's prompt: the mod's aligned, ready-triggered and image-less captures, 3 h (L), one launch with A2. `check L0` now gates every Optilux variant before its launch.
