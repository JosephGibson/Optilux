# Shader
Status: the hello pack (shader/shaders/) and pipeline spec v0 (config/pipeline.json) built in M3.P03, held by `verify similarity` (M3.P02) and `check L0` (M3.P04); the rest is design.

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
- `optilux verify similarity` (plans/m3.md D55):
  - method: each GLSL file under shader/ (named by a stage suffix or .glsl; others are not read) against Unbound's in reference/, read once its tree hash matches config/similarity.json's pin. Tokens drop comments, whitespace and directives but keep a `#define`'s replacement unless it is a value (one token or a signed number: Unbound's options give 111 NUM in a row); identifiers become ID, numbers NUM, true and false BOOL. k-grams are winnowed in a window w = t - k + 1, and each shared fingerprint is extended over both files to its whole run: a run of t tokens or more is always flagged, naming both files and their lines; none under k is.
  - Threshold (config/similarity.json): k 20, t 72. Controls: Unbound against itself flags all 129 of its files of 72 tokens or more; the unrelated pack (Wisdom Shaders Build3300) shares at most 71 tokens with Unbound, over every k-gram: 18 sampler2D uniforms in a row. `verify similarity --controls` recomputes both.
  - Pitfall: unrelated packs share repetitions (declaration lists, offset tables, runs of constants); a long run of same-type declarations can be flagged, and is written another way (grouped, reordered).
  - The pre-commit hook runs it when shader/ or config/similarity.json is staged: the index's files and rule, not the working tree's, against this checkout's copy; without the copy it refuses, naming `optilux install`. CI has no reference copy and leaves it out.
- License: MIT. README credits Complementary Shaders as the inspiration (wording: design.md D7). No "Complementary" in any Optilux name.

## Look and scope
- Look: Optilux's own, next-generation and heavily inspired by Complementary Unbound, starting from a similar tonemap (user, 2026-10-20). Unbound's reference frames (`played` profile) at perf and coverage views stay the side-by-side reference, not the target; the look target and the feature list come from roadmap.md#decisions D72.
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
- Everything else waits on the not-yet list (next section).
- Settings: most features Off / Low / Medium / High; fewer look knobs than Unbound. Option profiles are JSON (config/profiles/), written to the pack's settings file (shaderpacks/<pack>.txt) by the harness (M2); a variant with no profile or options takes the pack's defaults (run-record.md#run-spec).
- Textures: built and tested on Faithful 64x; no texture assets ship.

## Dropped features
The user's list of 2026-10-05, now a not-yet list (user, 2026-10-20): each feature stays out until roadmap.md#decisions D72 takes it back. Unbound's switch for each is in config/profiles/complementary-unbound-iso.json (v1: its `dropped` list, each switch set off in its `options` over played's; RAIN_STYLE and WEATHER_TEX_OPACITY at their defaults, as neither has an off value), every name and value held against r5.9.3 by `check L0`'s profile check.
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
- Format: config/pipeline.json, v0 as built with the hello pack (M3.P03, plans/m3.md D57), complete in M4:
  - top level: schema 0, pack, cycle (BENCH_DETERMINISTIC's, in frames: 1), views (the views file);
  - per pass: name (backend-neutral), program (the iris-gl backend's Iris program: gbuffers_*, shadow, deferred*, composite*, final), stage, dimensions, inputs (samplers, uniforms), outputs (buffer, format, scale), feature, option, budget (null until M4), views (until M4's coverage list, every view of its dimensions);
  - tests/test_pipeline.py keeps it equal to the pack: one pass per program file pair; its samplers and uniforms as its two stages declare them under the program's switches; its outputs from the fragment stage's RENDERTARGETS (the screen for final), at Iris's default RGBA8 when the pack sets no format; the option whose setting changes its code.
- Portability rules:
  - use explicit ping-pong textures instead of reading and writing one texture (Aperture has no buffer flipping);
  - keep algorithms in includes free of Iris built-in names, with thin per-backend glue.

## Determinism and TAA
- BENCH_DETERMINISTIC from M3's hello pack, the first with programs (measurement.md#visual-protocol; roadmap.md#decisions D9).
- As built in the hello pack (M3.P03; shaders/lib/options.glsl), on by default, cycle 1: nothing reads frameCounter, and no wall-clock or smoothed uniform is read (plans/m3.md P19). Under it:
  - gbuffers_particles, weather, lightning and clouds discard every fragment: their state moves with the ticks before /tick freeze and the stepped ones (P22). Off, each draws its surface: particles and weather texture x colour x light, lightning and clouds their vertex colour;
  - gbuffers_textured_lit discards the end crystals by entityId (entity.properties: entity.1 = minecraft:end_crystal): a crystal's spin starts at a random angle every launch;
  - the lightmap's block light flickers by a random step every client tick, /tick freeze or not (26.3: GameRenderer.tick, called while a level is loaded and the game is not paused, ticks LightmapRenderStateExtractor; blockFactor = flicker + 1.4). The pack reads only the lightmap's column without block light, which holds still, and adds block light at the flicker's rest (1.4) with vanilla's curve and default tint (#FFD88C, which no 26.3 dimension or biome overrides); vanilla's brightness curve is not applied to that part. Off, it reads vanilla's lightmap;
  - the texture matrix is not applied: it scrolls the enchantment glint by the wall clock (26.3's TextureTransform reads Util.getMillis());
  - only the edge fog is drawn, from far: fogStart and fogEnd are not read. 26.3 eases them by each frame's wall-clock length, under /tick freeze too: AtmosphericFogEnvironment's rain fog multiplier moves by (target - m) x getGameTimeDeltaTicks() x 0.2 a frame, the delta counted from Util.getMillis() whether frozen or not, and one instance carries it across views and dimensions; the water fog's end follows the player's water vision. Off, both fogs are drawn.
- Still moving and the session's to hold: animated textures (the static-textures pack, M3.P06), the End flash (the End's clock, which the End views' functions set: plans/m3.md D56), and fogColor in water: it follows the player's water vision, which a spectator gains 10 a tick up to 600 (LocalPlayer.aiStep; /tick freeze never freezes players), so it holds after 3 s in water, inside underwater's visual settle (suite.json capture). Iris clears colortex0 to fogColor.
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
- GLSL version: Iris 1.11.7 writes `#version 330 core` for Unbound's `#version 130` (spike V4) on a 3.3.0 Core Profile context; the hello pack is written in `#version 330 core` (plans/m3.md D56).
- Iris 1.11.7's core-profile path, read in the pinned jar with javap (M3.P03; plans/m3.md P14):
  - vertex inputs: vaPosition (vec3), vaColor (vec4: the vertex colour times ColorModulator), vaUV0 (vec2), vaUV1 and vaUV2 (ivec2: 26.3 binds UV1 and UV2 as RG16_SINT; vaUV2 is 16 x the block and the sky light level), vaNormal; uniforms modelViewMatrix, projectionMatrix (forward Z), textureMatrix, normalMatrix, chunkOffset; vaPosition + chunkOffset is the vertex relative to the camera. Sodium's terrain feeds the same names from its own attributes (vaUV2 its light bytes, textureMatrix the identity). In composite and final, vaPosition and vaUV0 are the full-screen quad's (0 to 1), modelViewMatrix the identity, projectionMatrix 0..1 to clip space;
  - no alpha test is injected into a core program: alphaTestRef holds the draw's cutoff (0, or GREATER than 1e-4, 0.1 or 0.5; a sentinel above 1 for entity-alpha draws), and the pack applies it, on the texture's alpha as vanilla 26.3 does;
  - samplers gtexture (also tex, texture), lightmap, colortex0 and up; a colortex the pack gives no format is RGBA8;
  - fog: fogColor, fogStart and fogEnd (the environment's fog, through Sodium: eased by the wall clock, Determinism and TAA), fogDensity, fogMode, fogShape. The render-distance fog is only in Iris's injected block: the pack rebuilds it from far (render distance x 16), ending at far after a band of clamp(far / 10, 4, 64), over max(length(xz), |y|), as 26.3's FogRenderer does;
  - entityId: in a vertex format with an overlay (entities) Iris replaces the uniform by the entity's id written into its vertices (entity.properties: entity.<int> = namespace:name ..., default namespace minecraft; an unlisted entity -1), the id kept with each deferred model submit and set again when it is drawn (MixinModelSubmit, MixinModelFeatureRenderer); elsewhere it is the uniform, 0 between entities;
  - glint: 26.3 draws an item's glint in one pass with an entity or the hand; Iris hands it to a core program only through mc_sampleGlint(), which the hello pack does not call, so only the separate glint draw shows it;
  - options: a bare `#define NAME` with only a comment after it is an on/off option once any file of the pack tests NAME; a define with a value and no [list] in its comment is none.
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
