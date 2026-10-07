# Playbook
Status: rough, 2026-10-05.

## Contents
1 How to use · 2 Evidence · 3 Workflow · 4 Design defaults · 5 Candidates · 6 Did not work · 7 Pitfalls · 8 Checklists · 9 Not carried

## 1. How to use
- Curated from the user's shader-optimization playbook (sources/shader-optimization-playbook.md, "PB", kept verbatim) and ALC's measured record.
- Every item is a hypothesis until Optilux's loop measures it. Facts with tags are in gpu-iris.md.
- Optilux is written from scratch, so much of PB's optimization becomes design: built into the first version of a pass (section 4).
- The rest are candidates for the optimization phase (section 5), each with its evidence and the visual tier it needs.
- An item changes status only through Optilux evidence: a cost row or an A/B verdict (measurement.md).

## 2. Evidence
- PB's tags (m measured, v offline-verified, b built but never timed) are kept per item. PB says most of its later rounds were blind.
- Two PB headline claims conflict with ALC measurements (CONFLICT in gpu-iris.md):
  - occupancy: ALC cut 60 -> 24 VGPRs and measured it slower;
  - removing discard: ALC's alpha-test route measured slower.
- Exactness classes map to Optilux tiers:

  | PB class | Optilux tier |
  |---|---|
  | exact by construction | identical |
  | exact up to float rounding | near, else close |
  | visible trade | review |

## 3. Workflow
- Find the cost before touching code [PB, ALC]:
  - replay shares rank; ablations measure feature costs; A/B decides. Label every number with its kind.
  - Weight by how often each view is played, not by the worst case.
  - Overworld forest at 4K (PB replay): cutout terrain ~30 %, solid terrain ~19 %, deferred1 ~12 %, shadow ~6 %, TAA ~5 %.
  - ALC: terrain 40 % weighted, 54 % in forest_noon. Leaf overdraw is the largest single part.
- Offline toolchain: offline.md, levels L0-L5 and what each may close, predict or only explain. PB: it found most wins and caught most bugs. PB's items map onto it:
  - glslang over a variant matrix, supplying Iris's runtime macros and injected inputs (gpu-iris.md#toolchain-quirks) -> L0;
  - RGA with the live-register map -> L2;
  - uniform-work scan of the ISA (vector work whose sources are all scalar, literal or uniform; confirm each in the source) -> L2;
  - custom-uniform check in Iris's own engine (gpu-iris.md#custom-uniforms) -> L3;
  - pipeline audit: producer -> buffer -> reader and uniform -> reader, per option and dimension. It catches the stale-read and reads-0 bugs (section 7) -> L1;
  - the similarity check -> L0, line endings -> .gitattributes (`eol=lf`). They replace PB's upstream diff.
- Review every round [PB, ALC]:
  - critique the plan;
  - critique the diff, in small pieces;
  - a read-only reviewer checks each Iris assumption against the jar.
  - PB: every round found at least one real bug: a half-pixel upsample offset, a TAA history quantizing into its "invalid" sentinel, a disabled pass still read, a fallback that could pop.

## 4. Design defaults
Built into the first version of each pass.
- Uniform-only math lives in Iris custom uniforms, evaluated once per frame:
  - time-of-day chain; light, ambient and sky colours;
  - sun and up vectors from gbufferModelView columns; sun visibility; the shadow light vector;
  - loop counts.
  - PB: terrain 72 -> 60 VGPRs, water 84 -> 72 [PB v].
  - One formula, one place: PB found deferred1's night light colour differing from the gbuffers one.
- Scalar branches on uniforms gate effects that are usually off: rain, stars by day, held-item light, End flash.
- Flat varyings only in full-screen passes, never in terrain [ALC m, PB m].
- Clouds and End beams march at half resolution in their own pass, upsampled depth-aware in the consumer (5.1).
  - Cost basis: PB put the End's light shafts at ~70 % of the End frame; ALC measured composite1 at 73 % of end_dragon.
- Deferred sky: a cheap gradient in the sky draws; the real sky shaded once per visible pixel in deferred. Optilux keeps sun and moon styles, so it handles `gbuffers_skytextured` draws explicitly instead of overwriting them.
- Solid geometry gets programs without `discard` (`gbuffers_terrain_solid`, `shadow_solid`). Measure early: ALC's alpha-test route was slower.
- Fetch-heavy loops take their count from an int custom uniform (no full unroll); one loop rather than nested ones.
- No mip chain or pass that nothing reads; the pipeline audit proves it.
- `textureGather` for depth neighbourhoods (TAA, upsample).
- Allocation steps: check the live-register map whenever a path is added. Rare paths, such as fallback marches, go in their own pass.

## 5. Candidates
### 5.1 Structural
Half-resolution march with depth-aware upsample [PB b]:
- Representative pixel `rep(h) = int((h + 0.5) / halfScale)` (= 2h + 1). March with exactly that pixel's coordinates and dither.
- Upsample:
  - position on the texel grid at `x * halfScale - 0.5` (a wrong half-pixel offset shifts the whole field);
  - 4 texels, each weighted bilinear x depth similarity;
  - store opaque depth per texel (1/viewZ, sky = 0); keep sky apart; relative-depth tolerance ~3 %.
- Colour is premultiplied RGBA16F.
- Alpha-independent additive terms (night nebula) stay full resolution and are added after the upsample.
- Secondary outputs (cloud depth) are blended with the same weights; picking the top texel makes them jump.
- Low-confidence pixels (weight under ~1/4): blend toward a distance-weighted 4x4 search with a coverage fade. Never a full-resolution fallback march in the main pass.
- Viewport scaling for passes that write one corner (bloom tiles). [PB b]

### 5.2 CPU side
- Still-camera flag: all 16 modelview and projection entries and the position unchanged. TAA reprojection then returns the pixel, and Catmull-Rom collapses to one texelFetch. Gains only while standing still. [PB b]

### 5.3 Exact trims
ALC measured trims like these at 0.1-0.3 %, below threshold, so only on hot paths [ALC m].
- Zero-weight skips: branch where a mix weight is 0 over large areas. [PB b]
- Lighting skips: shadowed fragments skip specular; unlit blocks skip block-light pows; no held light skips its code. [PB b]
- Watch code your change makes live: an existing dither reused in a new spot made a 64-level Bayer pattern live in terrain (~35 instructions per pixel). Use a cheap hash. [PB v]

### 5.4 Sample-count and precision trades
TAA blends these; tier review.
- Shadows: half the PCF tap pairs with per-frame rotation; one hardware-filtered tap past ~48 blocks with a dithered switch distance and uncorrelated noise; particles one tap. [PB b]
- Batched PCF taps, bit-exact (gpu-iris.md#latency). [PB v]
- SSAO: half the sample pairs per frame, alternating. [PB b]
- Clouds: cap far-ray steps and stretch the step, scaling opacity; skip the finest octave past a dithered distance. [PB b]
- Packed 3D noise: red shifted by the slice step stored in alpha, so one bilinear fetch reads both slices. [PB b]
- Bloom: linear-sampling Gaussian, 16 taps instead of 49. [PB b]
- TAA history in RGB10_A2 [PB b]:
  - only valid when TAA runs after the tonemap (values in [0, 1]);
  - dither the write by +-1/2 step;
  - keep invalid history at exactly 0 and valid history at least 1/1023.
- 64x textures: anisotropic filtering from a partial mip at 4x; shadow alpha at LOD - 2 on solid and cutout only. [PB b]

### 5.5 Config level
- Removing in-medium fog: keep a fade over the last ~15 % of the render distance, or the edge becomes a wall. With LOD mods it also covers the LOD ring. [PB b]
- Heavy optional effects: check what the pass-enable conditions do when the effect is off. [PB]

## 6. Did not work
- Flat varyings in terrain: neutral [PB m], slower [ALC m].
- Bilinear TAA history filter: visible blur for little time. [PB]
- TAA depth tests in raw depth: TAA is memory-bound. [PB]
- Adaptive AF tap count: 64x textures shimmer. [PB]
- FP16: precision risk [PB]; doubled VGPRs [ALC v].
- Variable-rate shading: not exposed on AMD OpenGL. [PB]
- Rain: pure overdraw, no shader-side fix. [PB]
- Fusing identities across approximation helpers. [PB]
- ALC, all measured: the alpha-test override, the occupancy cut, Nether storm skips, cloud-march early exit, AF algebra, squaring chains. [ALC m]
- Open for Optilux:
  - Deferred lighting for cutout terrain: PB calls it the only real fix for leaf overdraw, too large to do blind. For a from-scratch pack it is a design question, decided by measurement in M4 (design.md E2).
  - MoreCulling (played tier) already cuts leaf overdraw outside the shader. [PB]

## 7. Pitfalls
- A declared uniform Iris never defines reads 0.
- A disabled producer pass leaves its consumer reading stale data.
- The properties condition for a uniform or pass must be a superset of the GLSL condition that uses it. [PB]
- A directive given twice: the last wins silently. A shader `#undef` does not reach properties. Includes are not deduplicated. [PB]
- A later change can invalidate an earlier assumption (a fallback becomes the register peak). Re-review interactions every round. [PB]
- Static instruction counts mislead; use the live-register map and timing. [PB, ALC]
- Offline compilers fail for tooling reasons; investigate every new failure. [PB]
- Exactness claims state their input domain (NaN, negatives). Restructured sums keep their accumulation order. [PB]
- Line endings: Git Bash `sed` strips CR; PowerShell here-strings can drop trailing newlines. [PB, ALC]
- Comments and tooltips stay in step with behaviour (PB's final review found half a dozen stale ones).
- Option dependencies are documented where the user flips them. [PB]

## 8. Checklists
Before a change:
- Is the target hot? Check the cost row or the attribution, weighted by play.
- What sets the pass's allocation? Check the live-register map.
- Is the work uniform-only (move it to the CPU), gateable by a scalar branch, or independent but serialized (batch it)?
- Which Iris behaviour does it rely on? Verify it in the jar.
- Plan written with its tier; critiqued.

After a change:
- Compiles across the variant matrix.
- RGA shows the expected change, with no step regression elsewhere.
- Custom uniforms evaluate in Iris's engine and match numerically.
- Pipeline audit and similarity check pass.
- Diff reviewed.
- Measured (cost row or verdict); tier recorded.

Packaging:
- Settings grouped and documented with their dependencies.
- Notes say which items are measured.
- The zip uses forward slashes and matches the tree.

## 9. Not carried
- Fork-only discipline:
  - byte-identical upstream lines and wrapped edits;
  - tagged regions;
  - toggles whose off state equals upstream.
- "Keep earlier rounds' text as history": Optilux deletes superseded text, and git keeps the history (workflow.md#docs-rules).
