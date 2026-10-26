# Bloom and post
Status: research on bloom, sharpening, underwater distortion and output dither, their place in the composite chain, and the not-yet list's post items as D72 input. Nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
- R1 Jimenez, "Next Generation Post Processing in Call of Duty: Advanced Warfare", SIGGRAPH 2014 talk; page and author's comments read, not the 408 MB slides: http://www.iryoku.com/next-generation-post-processing-in-call-of-duty-advanced-warfare
- R2 Christensen, "Physically Based Bloom", LearnOpenGL (tutorial, 2022), implementing R1: https://learnopengl.com/Guest-Articles/2022/Phys.-Based-Bloom
- R3 Karis, "Tone mapping" (blog, 2013): https://graphicrants.blogspot.com/2013/12/tone-mapping.html
- R4 Rákos, "Efficient Gaussian blur with linear sampling" (blog, 2010): https://www.rastergrid.com/blog/2010/09/efficient-gaussian-blur-with-linear-sampling/
- R5 Intel, "An investigation of fast real-time GPU-based image blur algorithms" (vendor doc, 2014): https://www.intel.com/content/www/us/en/developer/articles/technical/an-investigation-of-fast-real-time-gpu-based-image-blur-algorithms.html
- R6 Bjørge, "Bandwidth-Efficient Rendering", SIGGRAPH 2015 talk (Arm); notes PDF unreadable, read via a summary (blog): https://qiita.com/UWATechnology/items/8b0eff5650d2c659c019
- R7 Epic, "Bloom in Unreal Engine" (vendor doc): https://dev.epicgames.com/documentation/en-us/unreal-engine/bloom-in-unreal-engine
- R8 Zero Density, "Standard Unreal Engine post processing pipeline" (third-party doc, UE 4.27): https://docs.zerodensity.tv/reality-4.27/appendices/b-standard-unreal-engine-post-processing-pipeline
- R9 AMD FidelityFX CAS (vendor doc and source, MIT, 2019): https://gpuopen.com/fidelityfx-cas/ and ffx_cas.h in https://github.com/GPUOpen-Effects/FidelityFX-CAS
- R10 AMD FSR 1, ffx_fsr1.h: RCAS, TEPD, grain (vendor source, MIT, 2021): https://github.com/GPUOpen-Effects/FidelityFX-FSR
- R11 Gjøl, "Banding in Games: A Noisy Rant", Playdead (talk, 2014; PDF unreadable), via Blender commit 852cdd476b5 (2020): https://archive.blender.org/lists/bf-blender-cvs/2020-February/135857.html
- R12 Sousa, "Generic Refraction Simulation", GPU Gems 2 ch. 19 (book, 2005): https://developer.nvidia.com/gpugems/gpugems2/part-ii-shading-lighting-and-shadows/chapter-19-generic-refraction-simulation
- R13 Iris source, https://github.com/IrisShaders/Iris, branches 26.1 and 26.3, read 2026-10-26: ShaderProperties, CompositeRenderer. Not the pinned 1.11.7 jar; the 26.3 head names 1.11.6 (docs/roadmap.md#findings-assigned F9).
- R14 shaders.properties reference, rendering (community doc): https://shaders.properties/current/reference/shadersproperties/rendering/
- R15 Complementary Unbound r5.9.3 (pack source), paths under reference/complementary-unbound-r5.9.3/shaders/; license 1.7: "Redistributing (parts of) The Pack" is not normal usage. Studied, never copied (docs/shader.md#policy).
- R16 ALC's ablations, config/profiles/complementary-unbound-played.json [m]: this GPU, 4K, MC 1.21.11, Iris 1.10.7 (docs/gpu-iris.md#sources-and-tags); keys recorded on Reimagined r5.9.2 as SHADER_STYLE 4 (its verify note): "the platform, pack build and views all differ" (docs/design.md#6-milestones).

## Unbound r5.9.3
Post chain (program/*.glsl, R15):
1. composite1: volumetrics, then the bloom-fog multiply (composite3's if world blur is on).
2. composite3: world blur (off; the pass still runs as a plain copy).
3. composite4: bloom tiles, motion blur (off).
4. composite5: bloom mix, tonemap, lens flare (off), saturation; written as LDR.
5. composite6: TAA.
6. composite7: FXAA, on by default; played's FXAA_DEFINE -1 disables the program (shaders.properties).
7. final: underwater distortion, chromatic aberration (off), sharpening, vignette, dither.

- Bloom tiles (composite4):
  - One full-screen pass writes seven padded tiles, 1/4 of a 1080p frame down to 1/256, into a corner of colortex3 (RGBA8; lib/pipelineSettings.glsl); past 1080p they keep their 1080p pixel size.
  - Each tile texel sums a 7x7 binomial kernel (49 bilinear taps) over colortex0's hardware mips (R11F_G11F_B10F, mips on by a const in the pass). At 4K the taps sit half a tile texel apart, so each level blurs half as far as at 1080p [inferred from the arithmetic].
  - HDR goes into 8 bits by a fourth-root curve over a fixed range; the consumer expands it.
  - The four widest tiles (1/32 to 1/256) are faded in the Overworld and the End, only the widest in the Nether; the fade scales the encoded value, so the bloom by its fourth power [inferred].
  - No scale directive: all 8.3 M pixels run the pass and write colortex3; at 4K the tiles cover about 2 % of the screen [inferred from the tile offsets].
- Mix (composite5): tiles read bilinearly, summed with equal weights totalling just under 1, lerped into the HDR colour by BLOOM_STRENGTH (default 0.12) plus a darkness boost, before the tonemap's exposure multiply: energy-conserving in form.
- Bloom fog (lib/atmospherics/fog/bloomFog.glsl): composite1 multiplies the scene by a factor growing with distance under rain, at night, underwater, in the Nether, and in caves with CAVE_FOG (off in played); composite5 divides it out before the mix, so far pixels bleed more: cheap haze. Off in the End. Inputs include custom uniforms Iris smooths (shaders.properties: rainFactor, eyeBrightnessM via smooth()). BLOOM_ENABLED=-1 also undefines BLOOM_FOG (lib/common.glsl).
- TAA runs after the tonemap, on sRGB-encoded LDR (composite6, lib/antialiasing/taa.glsl): bloom sees the jittered, unresolved frame.
- final.glsl:
  - Underwater distortion: with isEyeInWater 1 the read coordinate moves by a sine of the screen diagonal, scrolled by frameTimeCounter (wall clock), scaled by WATER_REFRACTION_INTENSITY; after TAA.
  - Sharpening: a fixed unsharp mask (boosted centre minus four cross neighbours), not contrast-adaptive, on encoded values; IMAGE_SHARPENING 5 of 10 by default, halved without TAA. Vertical taps sit 1/width away, about 0.56 px at 16:9 [read; effect inferred].
  - Vignette: on in played (the default defines VIGNETTE_R).
  - Output dither: static, from the pack's noise texture (texture.noise), no frame term; about two 8-bit steps peak to peak, mean about +0.5 step [inferred, texture mean 0.5 assumed].
- Cost (R16: mean over valid views; worst view):
  - BLOOM_ENABLED=-1: 0.128 ms (underwater 0.165), bloom fog included.
  - IMAGE_SHARPENING=0: 0.013 ms (end_dragon 0.055).
  - With bloom off composite4 still runs and colortex0's mips are still built, both outside the switch [read]: bloom alone adds a 4K mip chain, 0.06-0.1 ms (docs/gpu-iris.md#bandwidth), and a full-screen RGBA8 write, less bloom fog's share [inferred].
- ALC's composite4 VGPR findings (docs/gpu-iris.md#occupancy; docs/gpu-iris.md#transcendentals) likely concern this pass [inferred].

## Techniques
### Mip-chain bloom (CoD style)
- Claim: a 13-tap downsample (36 bilinear lookups) and a 3x3 tent upsample, added level by level, give a wide, stable bloom (R2). The first downsample weights each 2x2 group by 1/(1 + luma) (R3; R1's comments), so lone bright pixels do not pulse (R2). R2: 5 levels ("5 or 6 is usually good enough"), a lerp of 0.03-0.15 (about 0.04) before the tonemap; R1's author: "We expose after bloom".
- Cost: R1 and R2 give no ms. R5 timed a large Gaussian in a 1/4 x 1/4 buffer of a 2560x1600 frame at 0.17 ms on an R9-290X (kernel unstated); x2.0 pixels to 4K over an assumed 2-3x faster GPU: 0.11-0.17 ms, an order of magnitude only [inferred].
- Ladder: Low, Medium, High = 5, 6, 7 levels. Determinism: no frame term, no accumulation.
- Iris: a composite pass per level, each drawing a size.buffer target. R13: ShaderProperties parses size.buffer., scale., flip., blend.; CompositeRenderer sets the viewport from scale and offsets times the pass's draw-buffer size and flips every written buffer unless flip is false [verify in jar]. A pass writes the copy it does not read, so an earlier pass's region is gone after the next flip, and flip=false keeps writes where later passes cannot read them [inferred from R13, R14]: a chain needs a buffer per level.
- An in-place additive upsample (R2 blends ONE, ONE) needs composite blend: R13 applies the override there, R14 documents blend.<program> for gbuffers only, and the destination is the copy without the downsample [inferred; verify in jar].
- Aperture: down[k] and up[k] as separate textures, one writer each: 2N-1 textures, heavy on iris-gl's colortex0-15 (docs/gpu-iris.md#passes-and-buffers).

### Dual filter (dual Kawase)
- Claim (R6 summary): 5 downsample taps (centre 1/2, four half-texel diagonals 1/8), 8 upsample taps (1/6 and 1/12), 16 source texels a pass; the fastest blur tested on a Mali-T760. R5: Kawase blurs take "1.5x to 3.0x less computation time than the optimized Gauss blur".
- Cost: below the CoD chain, same structure, fewer taps [inferred]. Constraints: as the CoD chain.

### Mip-tile bloom (Unbound style)
- Claim: one pass builds every level from one source's hardware mips into one atlas that one consumer reads: two passes, one writer each, no reliance on flipping. Box-filtered mips may let a small bright source pulse under motion, which R1's filter targets [inferred].
- Cost: Unbound's 0.128 ms (bloom fog included) plus its hidden mip chain and write. Iris rebuilds a listed mip chain each time the pass runs (R13: generateMipmaps in renderAll; a TODO would skip it unless "we've written to the buffer") [verify in jar].
- Iris: a mipmap const, only in composite, deferred and final (docs/gpu-iris.md#passes-and-buffers), and scale.<pass> [verify in jar]. Aperture: one writer, later readers; its mip generation unknown [verify when public].

### Linear-sampling Gaussian
- Claim: a bilinear tap between two texels at their weight ratio gives an N-tap separable Gaussian in ceil(N/2) fetches per axis (R4: 9 in 5); in one 2D pass 49 taps become 16 (docs/playbook.md#54-sample-count-and-precision-trades, PB b). R4: about 60 % faster on a Radeon HD 5770, not bit-exact given hardware bilinear rounding.
- Tier: near or close expected, review per the playbook. Determinism: fixed offsets. Aperture: weights in an include. Cost: the tile pass only, a few % of the pixels [inferred].

### Tile layout and viewport scaling
- Claim: with scale.<pass> = s [offsetX offsetY] a pass writing one corner rasterizes only that corner (R14: "This does not affect the resolution of the output buffer"; docs/playbook.md#51-structural, PB b) [verify in jar], exact for every texel the consumer reads [inferred].
- Pitfalls:
  - In a size.buffer pass gl_FragCoord is in the small buffer, viewWidth and viewHeight full (docs/gpu-iris.md#passes-and-buffers); scale. moves only the vertex positions (R14), so texture coordinates span the scaled viewport [inferred]. Use textureSize.
  - Odd level sizes (2160/32 = 67.5) break the 2:1 mapping [inferred]; a half-pixel error shifts the whole field (docs/playbook.md#51-structural, of the half-resolution upsample). Pad tiles, clamp reads.
  - R14: "any individual program can only render to buffers with identical sizes": prefilter and atlas take separate passes.
- Tier: identical, by an L4 pass golden image and an A/B verdict.

### Bloom, exposure and tonemap
- A lerp with a normalized kernel keeps the frame's energy; an add brightens it. R7's Standard bloom sums five blurs, 1/2 to 1/32, each with its tint and size, and "is not conservative (it can result in an overall brightening of the image)". UE 4.27 blooms the TAA-resolved buffer and adds it in the tone mapper (R8).
- A lerp of a linear blur commutes with an exposure scale [inferred]. A threshold breaks that (set it in exposed units), and so do Karis weights, whose 1/(1 + luma) depends on the absolute level [inferred]. Unbound mixes before its exposure multiply (composite5).
- Bloom after an HDR TAA sees the resolved frame but needs an HDR history (RGB16F, padded to 8 bytes: docs/gpu-iris.md#bandwidth); RGB10_A2 is valid only after the tonemap (docs/playbook.md#54-sample-count-and-precision-trades).

### Sharpening: CAS and RCAS
- CAS (R9): a 5-tap cross (3x3 with CAS_BETTER_DIAGONALS), its amount set by local min and max, to "restore detail in images produced after TAA" (GPUOpen). ffx_cas.h: "This is designed to be a linear filter"; "It is best to run CAS after tonemapping"; it "does not function well on sRGB or gamma 2.2 non-linear data".
- RCAS (R10): the same cross; it solves for the largest negative lobe that does not clip 0-1, caps it, and has an optional noise guard; sharpness in stops, 0 the maximum. It takes EASU's output unconverted, EASU's input being "as if presenting to sRGB display or similar (e.g. Gamma 2.0)". Film grain goes after it.
- In TAA: Unbound reads its history through Catmull-Rom (lib/antialiasing/taa.glsl); a bilinear history filter blurred visibly (docs/playbook.md#6-did-not-work).
- Cost: 0.02-0.05 ms at 4K [inferred from Unbound's 0.013 ms 5-tap mask plus RCAS's min, max and reciprocal]; R9 and R10 give no ms.
- Determinism: no frame term. It reads TAA's output: A12 decides its TAA-on determinism, else its TAA-on look goes to review (docs/design.md#8-open-decisions). It scales TAA's unconverged residual by up to its absolute weight sum G, above the centre weight: keeping 1/255 needs G·w^n <= 1/255 (w the history weight), at most ceil(ln G / ln(1/w)) frames beyond N_conv [inferred].
- Iris: fragment-only [verify in jar]. Aperture: a pure function of five values in an include.

### Underwater distortion
- Claim: offset the read coordinate by a smooth periodic field, R12's screen-space refraction over the whole frame. R12's "leakage" (foreground pulled in) shows as the hand smearing; R12 masks the refractive area in alpha and keeps the original pixel where an offset sample leaves it.
- Placement: after TAA, so the history never sees the moving offset; before sharpening, which reads the displaced coordinates.
- Determinism: under BENCH_DETERMINISTIC the phase is a compile-time constant; the per-pixel sine stays, so the cost row measures the shipped code [inferred].
- Iris: isEyeInWater, in l1.IRIS_UNIFORMS (javap of the pinned jar, optilux/l1.py) [verify in jar]. Cost: a scalar branch; 0 out of water, under 0.02 ms underwater [inferred].

### Output dither
- Claim: dither before the last quantization with zero-mean triangular noise; R11: "GPUs are rounding before writting to framebuffer so we center the distribution around 0.0". R10's TEPD conserves energy over time given temporal blue noise. The step depends on the target, which config/pipeline.json calls "the game's own framebuffer, whose format the pack does not set".
- Tier: against undithered at most 1 step (near, maxAbsDiff 1 in config/suite.json); two patterns up to 2 apart (close or review) [inferred].
- Determinism: static under BENCH_DETERMINISTIC. A temporal dither needs a cycle dividing 720720 and accumulates nothing, as final runs after TAA.
- Iris: a PNG custom texture (texture.<stage>.<sampler>, R13) or a hash [verify in jar]. Cost: under 0.01 ms [inferred].
- The RGB10_A2 TAA history's write dither (±1/2 step, docs/playbook.md#54-sample-count-and-precision-trades) is the taa topic's.

### Not-yet list (D72 input only)
- Vignette: a few ALU ops per pixel, about 0 ms [inferred]; static; on in played.
- Chromatic aberration: two extra bilinear reads per pixel, 0.01-0.03 ms [inferred]; Unbound's follows TAA, precedes sharpening.
- Lens flare (lib/misc/lensFlare.glsl, composite5, before TAA): about 30 analytic shapes, some with nested pow, in every pixel, plus 8 depth taps at the sun's projected position; modes 1 and 3 skip it with the sun behind. It reads the TAA dither (frameCounter mod 3600) and the smoothed rainFactor. A few tenths of a ms at 4K [inferred: several hundred ALU slots a pixel, transcendentals at quarter rate (docs/gpu-iris.md#transcendentals)].
- Motion blur: 9 taps along a camera-only velocity from the previous-frame matrices (composite4, before TAA), each also reading depth when bloom is on; no velocity test, so it runs at static views too [read]. 0.1-0.3 ms at 4K in motion [inferred]. Its look needs motion paths (A6); its Bayer64 dither is likely the ~35-instruction pattern of docs/playbook.md#53-exact-trims [inferred].
- Depth of field: 18 taps from colortex0's mips at a LOD set by the circle of confusion, before TAA (composite3); autofocus reads centerDepthSmooth, smoothed, barred under BENCH_DETERMINISTIC. 0.2-0.6 ms at 4K plus a mip chain [inferred].
- Distant light bokeh (docs/shader.md#dropped-features) is no post pass in Unbound (deferred1, terrain): the lighting topic's.

## For Optilux
- First version. The final pass lands in M4 with the tonemap; bloom, sharpening and distortion in M5.
  1. bloom-prefilter: a 2:1 13-tap Karis-weighted downsample of the HDR scene into P (R11F_G11F_B10F, 1/2 size), mipmapped.
  2. bloom-tiles: levels 1/4 to 1/128 from P's mips, a 16-tap linear-sampled Gaussian per texel, into atlas T (R11F_G11F_B10F), viewport-scaled to its corner, padded.
  3. In the tonemap pass: tiles read bilinearly, weighted to sum to 1, lerped into the HDR colour before exposure and the curve.
  4. present (final): underwater distortion, RCAS-style sharpening, then a static triangular dither.
  - One writer per texture per frame, read after; nothing relies on blending or flip=false. If the live pass shows pulsing, v2 is the explicit chain, dual Kawase first.
- Options: BLOOM Off, Low (5 levels), Medium (6), High (7), Off removing both passes, the mix and the mip const (docs/playbook.md#55-config-level; docs/playbook.md#4-design-defaults); BLOOM_STRENGTH; SHARPENING (Off, or 0 to 1); UNDERWATER_DISTORTION (on, off). No dither option.
- Budget hypothesis, 4K, every view [inferred from R16, R5 scaled, docs/gpu-iris.md#bandwidth]: bloom 0.10-0.20 ms, mostly the prefilter's full-frame read and the mix's taps in every pixel; sharpening 0.02-0.05 ms; dither under 0.01 ms; distortion under 0.02 ms at underwater. Sharpening and dither likely sit inside the 0.5 % threshold floor (docs/measurement.md#calibration): they need timer rows, none yet (docs/measurement.md#verdicts-and-cost-rows).
- Dependencies: tonemap (mix before exposure; its output encoding sets sharpening's domain and the dither step); taa (bloom before or after it, sharpening after it, N_conv); fog-volumetrics (bloom fog); water (distortion beside refraction); lighting and sky (the HDR peaks that bloom).
- Confirmation: cost rows for bloom off against each level on all 11 views, sharpening off against on, distortion at underwater; viewport scaling identical; features to review against Unbound's played frames (docs/measurement.md#visual-protocol); live pass: pulsing bloom, sharpening halos.
- L3 golden tests (docs/offline.md#levels): linear-sampled weights reproduce the discrete kernel on an impulse within bilinear rounding (R4); DC gain 1; a lone firefly within the Karis bound; a ramp through each odd-sized level unshifted; tiles and mix satisfy f(k·x) = k·f(x), the Karis prefilter not, by design; sharpening with a zero lobe returns the input (RCAS's 0 stops is its maximum) and keeps [0, 1] in [0, 1], overshooting the neighbourhood's range by design; the dither has zero mean, stays within ±1 step and reads no frameCounter.

## Open questions
- Does pinned Iris 1.11.7 match branches 26.1 and 26.3 on scale., flips, mips rebuilt every pass and composite blend? javap on CompositeRenderer, ShaderProperties and RenderTargets.
- Does the mip-tile bloom pulse under motion? The live pass and a TAA-off motion sequence.
- Bloom before or after TAA? The taa and tonemap topics: cost rows of both history formats, the live pass.
- The final target's format and rounding, which set the dither step: an L4 RenderDoc capture.
- Sharpening on linear or encoded values (CAS or RCAS), how strong? Review frames with TAA on, once the tonemap's output encoding is set.
- Unbound's bloom alone (mip chain and write in, bloom fog out): L4 attribution shares, which only predict (docs/offline.md#decision-powers).
- Bloom fog as distance haze? The fog-volumetrics topic and D72's look target.
- Mask the hand from underwater distortion? Review frames and the live pass.
