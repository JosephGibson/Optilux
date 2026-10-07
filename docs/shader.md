# Shader
Status: design only; no pack code yet.

## Contents
Policy · Look and scope · Dropped features · Method · Pipeline spec · Determinism and TAA · Facts · Coverage list · LOD · Research

## Policy
- Full rewrite. Complementary's dev team agreed (user, 2026-10-05), as long as nothing is a 1-1 copy.
- Study:
  - Complementary Unbound r5.9.3 is unpacked from the pinned Modrinth zip to reference/complementary-unbound-r5.9.3/.
  - That folder is gitignored: never committed, never redistributed.
  - Agents may read it.
- Write:
  - Every Optilux line is written fresh: own structure, names and decomposition.
  - Describe a technique in your own words in docs/research/ before implementing it.
- `optilux verify similarity` (built in M3; not yet a verb):
  - method: normalized-token fingerprints (winnowing) of Optilux shader files against reference/; spans over the threshold are flagged.
  - Runs locally before each commit; CI has no reference copy.
  - The threshold is set in M3 from controls: Complementary against itself, and against an unrelated pack.
- License: MIT. README credits Complementary Shaders as the inspiration (wording: design.md D7). No "Complementary" in any Optilux name.

## Look and scope
- Look: Complementary Unbound style, starting from a similar tonemap. Judged side by side against Unbound reference frames (`played` profile) at perf and coverage views.
- In scope (user, 2026-10-05):
  - lighting: sun, sky and block light (uncolored), held-item light, block-light flicker;
  - shadows, entity shadows, AO;
  - sky: atmosphere, clouds, night nebula, star and sun/moon styles, End beams and End flash, Nether and End skies;
  - fog: atmospheric, underwater, Nether, End;
  - water: refraction, screen-space reflection + sky color, underwater distortion;
  - block reflections and rain puddles on a minimal material map (below);
  - vanilla weather (rain, snow) without styles;
  - post: bloom, tonemap, TAA, image sharpening;
  - selection outline as vanilla draws it. This is Complementary's "Default" mode, which leaves the line color untouched and is what the played settings use.
- Minimal material map: block reflections and puddles need to know which blocks are smooth. A small block-ID map (block.properties groups such as glass, ice, metal, polished stone) sets smoothness. No generated normals, coated textures or per-texture analysis.
- Everything else is dropped (next section).
- Settings: most features Off / Low / Medium / High; fewer look knobs than Unbound. Option profiles are JSON (config/profiles/), written to the Iris settings file by the harness from M2; until then a run takes the pack's defaults (run-record.md#run-spec).
- Textures: built and tested on Faithful 64x; no texture assets ship.

## Dropped features
The user's list of 2026-10-05. Unbound's switch for each, where known, is in config/profiles/complementary-unbound-iso.json; its `unresolved` block lists the switches still to confirm, dropped and kept (bloom), against r5.9.3 before the first M2 capture.
- Anti-aliasing: FXAA. TAA is the only anti-aliasing.
- Colored light: Advanced Color Tracing (voxel floodfill colored block light) and all its extras:
  - colored light fog, saturation, torch warmth, colored candles;
  - connected glass, glowing portal edges, the puddle fix under glass.
- Reflections: world-space reflections (every mode, player reflections); sky-effect reflections.
- Camera and post:
  - vignette, chromatic aberration, motion blur, lens flare, distant light bokeh;
  - world blur: depth of field, distance blur per condition, FOV-scaled, chromatic, anamorphic.
- Atmosphere:
  - aurora, rainbows, Nether storm;
  - weather styles: light/warm and heavy/cold rain, special biome weather, texture opacity, improved weather textures;
  - volumetric light shafts, border fog, cave fog.
- Materials: every resource pack is treated as a basic pack.
  - IPBR+:
    - generated normals and coated textures, on blocks and entities;
    - glowing ores, amethyst, lichen, redstone and lapis blocks, armor trims;
    - emissive modes, particle features, compatibility mode;
    - improved, distant-reflective and mirror-tinted glass; green-screen lime; hide armor.
  - Custom PBR: normal maps, emission, POM, directional block light.
- Other: selection-outline styles (rainbow, custom color, versatile, brightness, auto-hide), world outline, dark outline, hand sway, light-level overlay.
- Also out (draft v0): ray and path tracing.
- Cost context (ALC): Unbound's Nether storm cost 1.837 ms in nether_crimson. The iso profile switches it off, so the comparison stays fair.

## Method
- Cost budget, not feature list:
  - start from a minimal pack;
  - every feature lands as an option with its cost row and reference frames (measurement.md#verdicts-and-cost-rows).
- Where Unbound spends its time here. ALC, MC 1.21.11, replay shares weighted by the played settings; Unbound frames are 4.6-7.7 ms at 4K:

  | Pass | Share |
  |---|---|
  | terrain | 40 % |
  | deferred1 (clouds, SSAO, sky fog) | 12 % |
  | composite1 (volumetrics; 73 % in the End) | 11 % |
  | TAA | 6 % |
  | sky | 6 % |
  | water | 4 % |
  | shadow | 4 % |

- Unbound feature costs: config/profiles/complementary-unbound-played.json ablations (mean and worst view per feature); the storm's 1.837 ms is its nether_crimson worst view, mean 0.228.
- Implication: draft v0's cuts are mostly cheap or already off. Savings come from terrain shading, clouds and AO, and volumetrics.
- Iso-feature baseline: Unbound with only the features Optilux has (`iso` profile). 1.0 reports the ratio; there is no gate.
- Design defaults built into every pass from its first version: playbook.md#4-design-defaults.
- Testing ladder (draft v0 "software, shallow, deep"); an idea that fails a rung stops there:
  - software: offline levels L0-L4 (offline.md) and the compile through the mod's reload;
  - shallow: quick mode;
  - deep: full mode, visual tiers, live pass when temporal code changed.

## Pipeline spec
- A backend-neutral description of the pack. Per pass:
  - name, stage, inputs, outputs, formats, scale;
  - feature and option;
  - budget;
  - views that exercise it.
- Uses:
  - cost rows join to passes;
  - coverage check: a changed pass that no view draws needs a written waiver (ALC);
  - pipeline audit: every producer -> buffer -> reader and uniform -> reader pair is enabled under the same conditions, per option and dimension (playbook.md#3-workflow);
  - the Aperture port maps pass by pass.
- Format: config/pipeline.json; v0 with the hello pack in M3, complete in M4. The iris-gl backend maps passes to Iris programs (gbuffers_*, shadow, deferred*, composite*, final).
- Portability rules:
  - use explicit ping-pong textures instead of reading and writing one texture (Aperture has no buffer flipping);
  - keep algorithms in includes free of Iris built-in names, with thin per-backend glue.

## Determinism and TAA
- BENCH_DETERMINISTIC from M3's hello pack, the first with programs (measurement.md#visual-protocol; roadmap.md#decisions D9).
- Every frame-varying term (jitter, dither, noise offsets) derives from frameCounter modulo one short cycle. frameCounter resets at every reload (gpu-iris.md#frame-counters-and-reload).
  - Complementary's dithers use frameCounter mod 3600, so its bitwise cycle would be 3600 frames, not its 8-step jitter.
- History: zero marks it invalid, as in Complementary's TAA. A reload clears it. BENCH_DETERMINISTIC also invalidates it in the flush frame, the one frame where the hideGUI uniform reads 0 (mod.md#6-time-and-determinism).
- TAA is research topic 1. Questions:
  - jitter sequence and cycle length;
  - history rejection (clamp or clip, disocclusion);
  - history weight w, which sets N_conv;
  - sharpening;
  - interaction with clouds, fog and water;
  - which previous-frame matrices Iris provides.
- Automated temporal gates only after positive controls (measurement.md).

## Facts
- GPU and Iris facts, evidence-tagged, conflicts marked: gpu-iris.md.
- Techniques, design defaults and checklists: playbook.md.
- 26.3: with a pack active Iris disables the OIT option, translucent terrain and water run through `gbuffers_water`, and depthtex0/1/2 and shadowtex0 hold forward depth (platform.md#mc-263).
- GLSL version: Iris 1.11.7 writes `#version 330 core` for Unbound's `#version 130` (spike V4) on a 3.3.0 Core Profile context; M3 picks the pack's version from that.
- Loops are bounded. Fetch-heavy loops take their count from an int custom uniform (gpu-iris.md#occupancy).

## Coverage list
Filled in M4: every program Iris draws, its fallback and its coverage view.
- terrain (solid, cutout, translucent), water, entities, block entities;
- hand (solid, translucent), particles, weather, clouds;
- sky (basic, textured), beacon beam, armor glint, lines, text, spider eyes;
- shadow, deferred*, composite*, final.

## LOD
- Voxy joins the lod tier once it ships for the platform.
- ALC on 1.21.11: Voxy's End path fell back to compatibility after a patch compile failure, and a gaux4 binding question stayed open.
- Research Voxy's Iris integration on the 26.x build before writing any LOD pass.
- From PB:
  - Voxy-aware packs use colortex 18 and 19;
  - an in-medium fog fade over the last ~15 % of render distance also covers the LOD ring (playbook.md#55-config-level).

## Research
- Topics (draft v0):
  - TAA, AO, fog, post-processing, tonemapping, shadows, clouds, water;
  - Minecraft 26.x rendering (OIT), Iris internals, AMD RDNA3;
  - shader languages (GLSL now, Slang for Aperture), pipeline architecture.
- Trigger: the cost table names the expensive pass; research that pass first.
- Output: docs/research/<topic>.md, within the docs cap (workflow.md#docs-rules). Claims with sources, then what applies to Optilux and the measurement that would confirm it. Superseded text is deleted.
