# Shader pack optimization playbook (Iris, RDNA3, 4K)

This playbook collects what one project learned from eight optimization rounds on a Complementary Reimagined fork. The setup was
Iris 1.10.7, Sodium 0.8, Minecraft 1.21.11, an RX 7800 XT (RDNA3, gfx1101) and 3840×2160, with Voxy for distant terrain.

The playbook is generic: the techniques, tools and pitfalls apply to any Iris pack. Where something is specific to Complementary
or to one machine, the text says so.

Three kinds of evidence back these notes. Read each claim with its kind in mind:
- **Measured**: A/B sessions on the real game with the per-pass attribution below.
- **Verified offline**: compiler output (RGA ISA and register counts), Iris bytecode, or a numeric check.
- **Blind**: built and reviewed but never timed. Most of the later rounds were blind. The user reported real gains in game, but
  no per-item numbers exist.

---

## 1. Workflow

### 1.1 Find where the frame goes before touching code
- **Attribute per pass.** Capture a frame in RenderDoc, replay it, and group draws by the pack program that drew them. Each
  family's share of the replayed frame times the live median GPU time gives an estimated cost. Replays run 1.2 to 2 times slower
  than live and stretch passes unevenly, so use the result to rank costs, not to bound them.
- **Ablate features.** Switch one setting off at a time (shadows, clouds, TAA, SSAO, AF and so on) and measure the live
  difference. Where the two numbers disagree, report both: switching TAA off also removes jitter effects elsewhere, so it can
  cost more than the TAA pass itself.
- **Rank hotspots by cost weighted by how often you play in each view,** not by the worst case.
- **Typical Overworld frame at 4K**, from the replay of a forest view:

  | Family | Share of frame |
  |---|---|
  | Cutout terrain (leaves, grass) | ~30 % |
  | Solid terrain | ~19 % |
  | deferred1 (SSAO, sky, clouds, fog) | ~12 % |
  | Shadow map | ~6 % |
  | TAA | ~5 % |
  | Bloom, tonemap, final | a few % each |

  Terrain is about half the frame, and leaf overdraw is its biggest single part.
- **The End and the Nether are dominated by single volumetric marches:** the End's light shafts took about 70 % of its frame,
  the Nether storm about 30 % of its.

### 1.2 Offline toolchain for when you cannot launch the game
Build these early. They found most of the wins in this project and caught most of its bugs.

1. **Preprocess and compile every stage.**
   - Run the pack's GLSL through a C preprocessor with the pack's settings and Iris's standard macros, then compile each stage
     with glslang. Do this for the shipped settings and for a matrix of variants: features on and off, other shader styles,
     Voxy or DH defined, each new toggle off.
   - Gbuffers stages may need `#version 150 compatibility` and Iris-injected inputs such as `mc_chunkFade` declared before
     they compile offline.
   - Supply every macro Iris defines at runtime (for example `MC_RENDER_STAGE_STARS`). A missing one shows up as a false
     failure.
2. **Compile with RGA (Radeon GPU Analyzer, OpenGL mode, for your GPU).**
   - Collect ISA, VGPR counts, estimated occupancy and the live-register map per program. Compile the vertex and fragment stages
     together, because some faults only appear at link time.
   - Read the live-register map: it tells you where the register peak is, and the peak sets the allocation for the whole
     program (see 2.2).
3. **Scan for per-lane work that depends only on uniforms.**
   - Walk the ISA. Mark a VGPR "uniform" when every source of its last write was an SGPR, a literal or another uniform VGPR.
     Treat lane masks (`vcc`, SGPR pairs written by vector compares) and every memory load as non-uniform.
   - The flagged instructions are work the CPU could do once per frame. It is approximate because branches are ignored, so
     confirm each candidate in the source.
4. **Check custom uniforms with Iris's own code** (details in 3.1).
   - Write a small Java harness against the Iris jar: `kroppeb.stareval.parser.Parser.parse` with `IrisOptions.options`, then
     `ExpressionResolver` with `IrisFunctions.functions`, then `Expression.evaluateTo`.
   - Run every new expression through it to prove it parses, type-resolves and evaluates. Then compare the values against the
     shader's own formula evaluated in float32 on random frames: random matrices, random sun angles, rain on and off.
5. **Check the pack's own formulas numerically.**
   - Extract the preprocessed global initializers and evaluate them with a small GLSL-subset evaluator.
   - Compare them with the CPU expressions over thousands of random frames. Expect relative errors around 1e-14 in double,
     1 to 2 ulps in float32.
6. **Diff against upstream.**
   - Check that every upstream line survives byte-for-byte (difflib "delete" or "replace" opcodes against the base tree).
   - Check that line endings are consistent per file. Many packs use CRLF, and some editing tools silently write LF or drop
     trailing newlines.

### 1.3 Change discipline
- **One toggle per idea.**
  - Off must mean the upstream path, byte-identical.
  - Never edit an upstream line. Wrap it: `#ifdef NEW ... #else` upstream lines `#endif`. Mark every added line as part of a
    region (`// TAG: what` … `// TAG: end`) so the diff is auditable.
  - In `shaders.properties` the comment leader is `#`.
- **Derive an `*_ACTIVE` define per toggle in one shared header.** It holds the toggle plus every condition the change needs
  (Iris only, dimension, other toggles, settings).
  - Make the `shaders.properties` condition for any uniform or pass the change relies on a superset of that GLSL condition.
    The GLSL side should be stricter, never looser (see 6.3).
- **Classify every change in the notes and the config** as "exact by construction", "exact up to float rounding" or "minor
  visible trade". Be honest about which: a reviewer will check.
- **Keep earlier rounds' text as history.** When a later round changes an earlier decision, record the change in the newest
  section rather than rewriting the old one.

### 1.4 Review every round
- **Critique the plan before building,** using an independent second model if you can.
- **Critique the diff after building.** Keep each review artifact small enough for the reviewer; split by feature if needed.
- **Run a read-only reviewer** that checks each Iris-side assumption against the Iris jar's bytecode (`javap -c -p`).
- **In this project every review round found at least one real bug.** Examples:
  - a half-pixel grid offset in an upsample;
  - a near-black TAA history quantizing into the "invalid" sentinel;
  - a pass disabled in properties while the shader still read its output;
  - an upstream line edited instead of wrapped;
  - a fallback that could pop.

  Budget time for review and apply the findings.

---

## 2. GPU facts that drove the wins (RDNA3; most apply to any modern GPU)

### 2.1 Uniform math is not free
- **RDNA3 (gfx11) has no scalar floating-point ALU.** RDNA3.5 added one. A uniform-only expression such as
  `normalize(gbufferModelView[1].xyz)` or a time-of-day `pow` chain therefore runs once per lane, in every pixel.
  - Packs compute a lot this way through global initializers: sun vector, up vector, sun visibility, light, ambient and sky
    colours, highlight colour. In this project the terrain prologue alone spent about 70 instructions and 7 transcendentals
    per pixel on them.
- **Moving that work out of the pixel shader:**
  - Best: an Iris custom uniform, evaluated once per frame on the CPU, which lives in scalar registers.
  - For full-screen passes only: compute it in the vertex stage and pass a `flat` varying. That runs 3 or 4 vertices instead of
    8 million pixels.
  - Do not use flat varyings for terrain. Terrain has millions of vertices, so the work moves per vertex instead of
    disappearing. A measured experiment that moved four vectors into terrain's vertex stage came out neutral.
  - A flat varying also costs a vector register for as long as it is live. Converting deferred1's flat inputs to uniforms was
    part of its 84 → 48 register drop.
- **Branches on uniforms are scalar branches.** `if (rainFactor > 0.0)` costs almost nothing and skips whole blocks for every
  lane. Use them to gate effects that are usually off: rain fog, stars by day, the aurora, held-item light, rainbows.

### 2.2 Occupancy is set by the worst path
- **Waves per SIMD scale inversely with allocated VGPRs.** In RGA's wave64 model for gfx1101, allocations step in 12s:

  | Allocated VGPRs | 48 | 60 | 72 | 84 | 96 | 120 |
  |---|---|---|---|---|---|---|
  | Waves per SIMD | 16 | 12 | 10 | 9 | 8 | 6 |

  Being one register over a step costs a whole step.
- **The allocation is the maximum over all paths, including paths that almost never run.** The biggest single win in this
  project was finding that a full-screen pass sat at 84 VGPRs because of two rarely taken paths:
  - an aurora loop that only shows on full-moon nights in snowy biomes;
  - a fallback march for rare pixels.

  Removing those peaks took it to 48 (16 waves).
- **Use the live-register map,** not static instruction counts, to find the peak and what is live there.
- **Compilers fully unroll constant-count loops that contain texture fetches** and issue every fetch at once: fifteen fetches in
  flight means fifteen-plus live registers.
  - Fix: take the loop count from an **int custom uniform** that holds the same constant. The compiler can no longer unroll it,
    and the results are identical.
  - A single 16-iteration loop beats nested 4×4 loops for this.
- **Long-lived per-pixel values in loops are the other source of pressure.** Anything uniform that is held across a loop (light
  colours, vectors) should be a uniform so it sits in scalar registers.

### 2.3 Latency: dependent fetch chains
- **A typical PCF shadow tap is a dependent chain:** shadowtex0 compare → wait → shadowtex1 compare (only if partly
  shadowed) → wait → shadowcolor fetch (only if translucent) → wait. A pair of taps done one after the other is two chains.
- **Restructure so independent taps issue together:** both depth compares, then both translucent compares under the combined
  condition, then both colours.
  - Keep each tap's arithmetic and the order of the adds, so the result stays bit-exact.
  - It costs a few registers. Check that it does not push the allocation over a step.

### 2.4 Depth testing and discard
- **Any reachable `discard` makes the hardware defer depth writes until after the shader.** Early depth testing against
  geometry already drawn still happens, but fragments of the same draw cannot reject each other early.
  - This applies even when the discard sits behind a branch that never fires for this geometry, such as an entity-only fade in
    the shadow program.
- **Split programs by pass** so solid geometry runs a variant with no discard (see 3.4 for Iris's program IDs and alpha tests):
  - `gbuffers_terrain_solid`;
  - `shadow_solid`.

### 2.5 Texture cache and bandwidth
- **High-resolution resource packs (64x) sampled at mip 0 thrash the texture cache** wherever the screen or shadow-map footprint
  covers many texels. Two places this hit:
  - **Manual AF:** this pack's 4x path took all taps from mip 0, while its 8x and 16x paths used a partial mip level. Using the
    partial mip at 4x too was cheaper, at the cost of slightly softer distant textures. Taking one tap where the AF footprint is
    under one texel (magnification) was cheaper again.
  - **Shadow-pass alpha:** reading at the hardware level of detail minus 2 instead of mip 0 keeps leaf holes at least 4× finer
    than the shadow map's texels for a fraction of the traffic. Restrict it to the solid and cutout passes so water and stained
    glass keep their coloured shadows.
- **Full-screen bandwidth at 4K is real.** A frame is 8.3 M pixels, so each RGBA16F target written is about 66 MB. TAA was found
  to be bound by memory traffic, not arithmetic. Levers:
  - **Smaller history format:** RGB16F is padded to 8 bytes, RGB10_A2 is 4 (see 4.4 for the caveats).
  - **Skip mip chains nothing samples:** remove `colortexNMipmapEnabled` where every reader uses `texelFetch` at level 0. This
    one was measured.
  - **Skip passes whose output nothing reads,** after an audit. Also measured.
  - **Shade only the viewport region a pass actually writes,** for example bloom tiles in one corner via
    `scale.compositeN=0.5`.
- **Gather instead of fetch:** `textureGather` (`GL_ARB_texture_gather`) loads a 2×2 block in one instruction. A 3×3 depth
  neighbourhood takes 4 gathers instead of 9 fetches; in TAA, two depth textures took 8 gathers instead of 16 fetches.

### 2.6 Transcendentals
`pow`, `exp`, `log`, `sqrt`, `rsq`, `sin` and `cos` run at quarter rate (`pow` is a log and an exp), so trim them on hot paths:
- **Integer exponents:** use squaring chains, e.g. `x5 = (x²)²·x`, then `x^10 = x5·x5`.
- **Normalized vectors:** `length(normalize(v))` is 1.
- **Dead mixes:** skip a `pow` whose result is mixed with weight 0.
- **Uniform-only `pow`s:** move them to the CPU.
- **Check approximations before fusing.** Packs often define helpers such as `pow1_5(x) = x - x(1-x)^2` that are
  approximations, not powers, so identities like `pow(pow1_5(x), e) = pow(x, 1.5e)` do not hold.

---

## 3. Iris facts (verified against the Iris 1.10.7 jar)

Re-verify these on your Iris version; they are easy to check with `javap -c -p` on the jar.

### 3.1 Custom uniforms (`uniform.<type>.<name>` and `variable.<type>.<name>` in shaders.properties)
- **Evaluation:** once per frame on the CPU, in `beginLevelRendering`, after Iris has captured the frame's `gbufferModelView`
  and projection matrices. Camera trackers advance first. So `gbufferPreviousModelView` and `previousCameraPosition` hold the
  last frame's values, and nothing lags a frame.
- **Types:** `float`, `int`, `bool`, `vec2`, `vec3`, `vec4`. Variables (`variable.*`) can be used by later expressions, and
  forward references resolve.
- **Inputs available:**
  - matrices as mat4: `gbufferModelView`, `gbufferProjection`, their `Previous`/`Inverse` variants, shadow matrices;
  - `cameraPosition` and `previousCameraPosition` as float vec3;
  - `sunAngle`, `worldTime` (int), `frameCounter`, `screenBrightness`, `skyColor`;
  - the pack's own custom uniforms (`rainFactor` and so on).
- **Not available:** per-draw dynamic uniforms such as `fogColor`. Keep anything derived from them in the shader.
- **Matrix access:** `.x`/`.y`/`.z`/`.w` (also `.0` to `.3` and `.r`/`.s` …) return a matrix **column** as a vec4, the same as
  GLSL `m[i]`. Store it in a `variable.vec4` and take its components; avoid long chained accesses.
- **Functions:** `frac`, `if(c, a, b)`, `sin`, `cos`, `pow`, `sqrt`, `exp`, `log`, `clamp`, `min`, `max`, `abs`, `floor`,
  `smooth`, `vec2`/`vec3`/`vec4`; `&&`, `||` and comparisons work.
- **Negative literals:** this project wrote them as `(0.0 - x)` after operators as a precaution; that form is known to parse.
- **Upload:** a custom uniform reaches every program that declares it, half-size passes included. A uniform the shader declares
  but Iris never defines reads 0: black clouds, skipped loops. Keep the conditions on both sides aligned (6.3).
- **Precision:** float32 throughout, the same as the GPU. Expect a difference of 1 to 2 ulps.

### 3.2 Composite and deferred passes
- **Pass size:** a composite or deferred pass whose draw buffers all share one size (`size.buffer.colortexN = 0.5 0.5`) is drawn
  at that size. `viewWidth`/`viewHeight` stay full-size and `gl_FragCoord` is in the small buffer. That is how half-resolution
  passes work.
- **Flips:** after a pass writes a buffer, Iris flips it, so the next pass samples the new contents. `colortex0`–`colortex15`
  are available (recent Iris accepts more; Voxy-aware packs use 18 and 19).
- **Directive parsing:**
  - `RENDERTARGETS`/`DRAWBUFFERS` comments and `const` directives are parsed from the C-preprocessed source. Comments are kept,
    and comments in inactive branches are dropped.
  - So `#ifdef`-guarded format lists and `const bool colortexNClear` work.
  - For the same directive, the last one parsed wins, silently, with no error.
- **Program enabling:** `program.<world>/<name>.enabled=false` in properties disables a pass. The enable condition must match
  every consumer of that pass's output.
- **Depth copies:** Iris copies depth for `depthtex1` and `depthtex2` unconditionally. The pack cannot avoid that cost.

### 3.3 Properties preprocessing
- **Preprocessor:** shaders.properties goes through a C preprocessor (JCPP). Boolean options are defined when on, value options
  are macros, and `IS_IRIS` and Iris's standard macros are defined. `#if`/`#ifdef` nesting works.
- **Option registration:** Iris registers a boolean option only if some shader `#ifdef`/`#ifndef` references it.
- **The shader preprocessor sees options differently from properties.** If the shader `#undef`s an option (for example forcing
  a fog off), the properties preprocessor still sees the user's value. Any properties condition that depended on that option
  must account for your override.

### 3.4 Program IDs and Sodium passes
- **Program IDs and fallbacks:**
  - `gbuffers_terrain_solid` and `gbuffers_terrain_cutout` fall back to `gbuffers_terrain`.
  - `shadow_solid`, `shadow_cutout` and `shadow_water` fall back to `shadow`.
- **Sodium's passes:**
  - SHADOW → ShadowSolid (used by nothing else);
  - SHADOW_CUTOUT → ShadowCutout (the vanilla `SHADOW_TERRAIN_CUTOUT` key also reaches it, e.g. falling blocks and pistons);
  - SHADOW_TRANS → ShadowWater.
- **Alpha tests Iris injects unless `alphaTest.<program>` overrides them:**

  | Pass | Alpha test |
  |---|---|
  | Solid terrain, solid shadow | none |
  | Cutout terrain, cutout shadow | `> 0.5` |
  | Translucent | non-zero |

- **Extensions:** Iris defines `MC_<extension>` for every GL extension the driver exposes, e.g. `MC_GL_ARB_texture_gather`.
  Guard extension use with them.
- **Linking:** vertex outputs the fragment stage does not read link fine. A fragment input without a vertex output does not.
- **Includes:** `#include` is not deduplicated. Guard any file that can be reached twice.

---

## 4. Technique catalog

Each entry gives the idea, the class of change and the trap to avoid. Rough impact is ranked within each group.

### 4.1 Structural changes (biggest wins)
1. **Half-resolution volumetrics and clouds.**
   - **Setup:** march in a separate pass drawn at half size on each axis (a quarter of the pixels). Compile it from the main
     pass's own source with a mode define, so the prologue, dither and march are literally the same code.
   - **Representative pixels:** texel `h` stands for screen pixel `rep(h) = int((h + 0.5) / halfScale)` (= `2h+1`). Run the
     march for exactly that pixel's coordinates and dither, so a representative gets its own value back exactly.
   - **Upsample in the consumer:**
     - Position the pixel on the texel grid at `x·halfScale − 0.5`; getting this half-pixel offset wrong shifts the whole field.
     - Weight each of the 4 texels by its bilinear weight times a depth-similarity weight.
     - Store opaque depth per texel (e.g. `1/viewZ`, with 0 for sky) so the upsample does not refetch depth.
     - Keep sky apart from all geometry.
     - Use a tight relative-depth tolerance (about 3 %). A loose one lets a farther sample's clouds show over nearer terrain.
   - **Storage:** keep colour premultiplied (`rgb·a`, `a`) in RGBA16F. Blend premultiplied, then un-premultiply.
   - **Additive terms** that are independent of alpha (aurora, nebula) stay at full resolution and are added after the upsample.
   - **Secondary outputs** such as cloud depth for later consumers: blend them with the same weights so they move continuously.
     Picking the highest-weight texel makes them jump.
   - **Low-confidence pixels** (matched weight under about a quarter, e.g. thin sky gaps): blend towards a distance-weighted
     search of matching texels in a 4×4 block, with its own coverage fade so nothing pops.
     - Do **not** keep a full-resolution march as the fallback inside the main pass. It holds the main pass's register
       allocation for every pixel.
   - **Measured cost before the change:** the End's light shafts were about 70 % of the End frame and the Nether storm about
     30 % of the Nether frame. The Overworld clouds were up to 0.65 ms at 4K.
2. **Deferred sky.** The vanilla sky draws (2 or 3 per frame) shade every fragment, and terrain then covers most of them.
   - Write a cheap gradient in the sky draws and shade the real sky once per visible pixel in the deferred pass, as most packs
     already do for the End and the Nether.
   - **Trap:** anything `gbuffers_skytextured` draws, such as a custom-sky resource pack or the vanilla sun and moon, gets
     overwritten. Enable this only where the pack discards those draws.
3. **Specialized programs without discard** for solid geometry (2.4).
4. **Skip unread passes and mip chains** after an audit of every read (measured wins).
5. **Viewport scaling** for passes that only write part of the screen (bloom tiles).

### 4.2 CPU-side work (custom uniforms)
- **What moved, in rough order of payoff:**
  - the time-of-day chain;
  - light, ambient and sky gradient colours;
  - camera basis and sun vectors from `gbufferModelView` columns, plus sun elevation, sun visibility, shadow time and the light
    vector;
  - the highlight colour;
  - cloud colours (watch for per-pass variants of the same formula: deferred1's night light colour differed from the gbuffers
    one);
  - loop counts;
  - a still-camera flag.
- **Payoff:** the main gains are in registers more than instructions.
  - Terrain 72 → 60 VGPRs, water 84 → 72.
  - The deferred pass 84 → 48, together with the loop-count fix.
- **Still-camera shortcut:**
  - The flag is 1 when all 16 entries of the modelview and of the projection equal last frame's and the camera position is
    unchanged. Compare all 16 projection entries, not just the obvious ones.
  - TAA's reprojection then returns the pixel itself and Catmull-Rom history collapses to one `texelFetch`.
  - It only gains while standing still, and only once view bobbing has settled.

### 4.3 Exact arithmetic trims
- **Zero-weight skips:** where `mix(a, expensive, w)` has `w == 0` over large areas, branch on `w > 0`. Examples: a
  distant-light bokeh weight that is zero within 60 blocks; a tonemap dark lift that is zero above 10 % luminance.
- **Lighting skips:**
  - Shadowed fragments skip specular (with shadow = 0 the product is +0).
  - Unlit blocks skip block-light `pow`s.
  - No held light means the held-light code is skipped (a uniform branch).
- **Watch for code your own change makes live.** Using an existing dither in a new spot made a 64-level Bayer computation live
  in terrain (about 35 instructions per pixel) that upstream never actually ran. Use a cheap hash for your own needs.

### 4.4 Sample-count and precision trades (visible at noise level; TAA blends them)
- **Shadows:**
  - Halve the PCF tap pairs under TAA, with rotation noise varying every frame.
  - Take one hardware-filtered tap beyond about 48 blocks, with the switch distance dithered, using noise that moves every
    frame and is uncorrelated with the PCF noise.
  - Particles get one tap.
- **SSAO:** take half the sample pairs per frame, alternating odd and even, so all radii are covered across two frames.
- **Clouds:** cap far rays at a step count and stretch their step, scaling opacity by the stretch; skip the finest noise octave
  past a dithered distance.
- **Packed 3D noise:** store red shifted by the slice step in alpha (iq's layout), so `Noise3D` reads both slices in one
  bilinear fetch.
- **Bloom blur:** a linear-sampling Gaussian (bilinear taps placed between texel pairs) gives 16 taps instead of 49.
- **TAA history in RGB10_A2:**
  - It works because packs that run TAA after the tonemap blend values in [0, 1].
  - Dither the write by ±½ of a 10-bit step so blending never stalls.
  - **Keep any sentinel exact.** If TAA treats a zero history as "invalid", force valid history to at least one step
    (`max(temp + noise, 1/1023)`) and keep invalid pixels at exactly 0.
  - FXAA's dark-pixel test on the history can flicker with dithered history.

### 4.5 Config-level trades (user-visible)
- **Fog:**
  - Packs often have no off switch for atmospheric fog (the multiplier has a floor), so `#undef` the internal defines.
  - When removing "in-medium" fog (water, lava, powder snow), keep a short fade over the last ~15 % of the render distance.
    Packs paint everything past the render edge in the medium's colour, and without the fog that edge becomes a wall. With
    LOD mods it also covers the whole LOD ring.
- **Heavy optional effects** (storms, aurora, nebulae): turning them off removes whole passes. Check what the pass-enable
  conditions in properties do when the effect is off.

---

## 5. Things that did not work, or were left out on purpose
- **Flat varyings from the terrain vertex stage:** measured neutral. Per-vertex cost on millions of vertices pays back the
  per-pixel saving.
- **A cheaper TAA history filter** (bilinear instead of Catmull-Rom): visible blur in motion for almost no time saved.
- **Rewriting TAA's depth tests in raw-depth space:** TAA is bound by memory traffic, so the arithmetic saving would not show.
- **Adaptive AF tap count:** face-on distant 64x textures would shimmer.
- **FP16 math** (`GL_AMD_gpu_shader_half_float`): precision risk for an uncertain gain.
- **Variable rate shading:** not exposed in OpenGL on AMD.
- **Deferred lighting for cutout terrain:** the only real fix for leaf overdraw, but far too large to do blind.
- **A non-shader option:** a leaf-culling mod cuts leaf overdraw directly.
- **Rain:** pure overdraw (two fetches and a discard per fragment, depth at the near plane), with no shader-side fix.
- **Fusing `pow(pow1_5(x), e)`:** not exact, because the helper is an approximation (2.6).

---

## 6. Pitfalls and how to catch them

### 6.1 Measurement and evidence
- **Static instruction counts mislead.** A change can add static instructions (a new branch) and still cut the dynamic count.
  Use the live-register map and real timing.
- **Use the number that matches the question:** replay shares rank costs, ablations measure feature costs, A/B sessions decide.
  Say which kind every number is.
- **Offline compilers can fail for tooling reasons** (missing runtime macros), and a failing build can hide a real error.
  Investigate every new failure, and keep a list of known offline-only failures.

### 6.2 Exactness
- **Distinguish the three kinds:**
  - "exact by construction": same arithmetic, same order;
  - "exact up to float rounding": CPU float vs GPU, `length(normalize(v))` vs 1, different evaluation order;
  - "visible trade".

  Reviewers will hold you to the label.
- **Preserve accumulation order** when restructuring sums, if you claim bit-exactness.
- **Reformulations that are exact for valid inputs** can differ on NaN or negative inputs, such as a `pow` of a negative value
  multiplied by a zero weight. State the input domain.

### 6.3 Consistency across files and rounds
- **Every custom uniform and every pass enable has a GLSL `*_ACTIVE` condition that reads it.** The properties side must define
  the uniform or enable the pass whenever the GLSL side is active.
  - A missing uniform reads 0.
  - A disabled producer pass leaves its consumer reading stale data.
- **Before shipping, list every producer–consumer pair** (pass → buffer → reader) and every uniform → reader, and check each
  under toggle-off, other settings and other dimensions.
- **A later change can invalidate an earlier one's assumption.** Examples:
  - forcing a fog off while a properties condition still keyed on the fog option;
  - a fallback that was right when written becoming the register peak later.

  Re-review the interactions every round, not only the new diff.
- **Toggles that silently depend on others** must be documented where the user turns them off.

### 6.4 Editing hygiene
- **Line endings:**
  - Keep each file's endings and check for mixed endings after every edit.
  - Git Bash `sed` strips CR.
  - PowerShell here-strings can drop trailing newlines and glue a marker comment onto the next directive. That broke every
    stage once in this project.
- **Change upstream lines only by wrapping,** never by replacing. Run the byte-for-byte upstream diff (1.2, step 6) before
  packaging.
- **Guard includes that can be reached twice,** since Iris does not deduplicate them.
- **Keep comments and tooltips in step with behaviour.** A final review found half a dozen that described earlier rounds.

---

## 7. Checklists

### Before writing a change
- [ ] Is the target hot? Check per-pass attribution and ablation, weighted by how often you play each view.
- [ ] What sets the target pass's register allocation? Find the peak in the live-register map.
- [ ] Is the work uniform-only (CPU), invisible under some uniform condition (scalar branch), or independent and serialized
      (batch it)?
- [ ] Which Iris behaviour does the change rely on? Verify it in the jar.
- [ ] Write the plan with its exactness class and get it critiqued.

### After writing a change
- [ ] Every stage compiles under the shipped settings and the variant matrix, including each new toggle off.
- [ ] RGA shows the expected register and instruction change, with no step regression elsewhere.
- [ ] New custom uniforms parse, resolve and evaluate in Iris's own engine and match the shader formula numerically.
- [ ] GLSL `*_ACTIVE` conditions and the properties conditions match (superset on the properties side).
- [ ] Upstream lines byte-identical; line endings consistent; regions marked.
- [ ] Diff critiqued; Iris-side assumptions reviewed against the jar; findings applied.

### Packaging
- [ ] The settings file lists every toggle explicitly, grouped by measured / exact / visible trade / user request.
- [ ] The notes say which items are measured and which blind, what each visible trade looks like, and which switch undoes it.
- [ ] Dependencies between toggles are documented where the user flips them.
- [ ] The zip opens cleanly (forward-slash paths) and its file count matches the tree.
