# Next-generation candidates for D72
Status: Research for roadmap D72: what current Iris packs ship as next-generation, what each needs from Iris 1.11.7 on a 3.3 core context, its 4K cost here, its fit with determinism and Aperture, and the look target. Research only, not yet measured in Optilux.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
Read 2026-10-26. Iris facts are from GitHub branch 26.3 (the branch docs/platform.md#mc-263-verified read), not the pinned jar: each is [verify in jar].
- R1 Iris source (2026), https://github.com/IrisShaders/Iris/tree/26.3: FeatureFlags, IrisRenderSystem, GlImage, ShaderProperties.
- R2 Iris docs (vendor doc, 2026), https://shaders.properties/current/reference/: custom_images, ssbo, flags, at_midblock, voxeldistance and setup pages.
- R3 Aperture migration guide (vendor doc, "extremely outdated"): https://shaders.properties/aperture/migration/
- R4 Khronos specs: ARB_compute_shader "OpenGL 4.2 is required"; ARB_shader_storage_buffer_object needs 4.0, ARB_shader_image_load_store 3.0: https://registry.khronos.org/OpenGL/extensions/ARB/
- R5 Photon (pack source and README, 2026): https://github.com/sixthsurge/photon
- R6 Bliss (pack source, "an edit of chocapic v9"): https://github.com/X0nk/Bliss-Shader
- R7 Rethinking Voxels (pack page): https://modrinth.com/shader/kmwfVOoi
- R8 Pack pages, Modrinth API (2025-2026), https://api.modrinth.com/v2/project/<id>: solas-shader, bsl-shaders, kappa-shader, xEItlMn3 (Nostalgia), pam (PathMax), photon-shader, bliss-shader, lux-v1, complementary-unbound.
- R9 Photonics (mod page): https://modrinth.com/mod/photonics
- R10 SEUS PTGI E12 (Patreon post, 2020; 403, title from search): https://www.patreon.com/posts/32990443
- R11 Boisse et al., GI-1.0 (paper, AMD, arXiv 2023): https://arxiv.org/html/2310.19855
- R12 Therrien, Levesque, Gilet, Screen Space Indirect Lighting with Visibility Bitmask (paper, arXiv 2023): https://arxiv.org/html/2301.11376
- R13 Schied et al., SVGF (paper, HPG 2017): https://research.nvidia.com/publication/2017-07_spatiotemporal-variance-guided-filtering-real-time-reconstruction-path-traced
- R14 FidelityFX Brixelizer GI 1.0.1 (vendor doc): https://gpuopen.com/manuals/fidelityfx_sdk/techniques/brixelizer-gi/
- R15 Lysenko, Voxel lighting (blog, 2018): https://0fps.net/2018/02/21/voxel-lighting/
- R16 Mojang, Vibrant Visuals (vendor article, via search): https://www.minecraft.net/en-us/article/minecraft-vibrant-visuals
- R17 RX 7800 XT (spec database, secondary): 624.1 GB/s, 64 MB L3: https://technical.city/en/gpu/Radeon-RX-7800-XT
- R18 Unbound r5.9.3's license: reference/complementary-unbound-r5.9.3/License.txt, "Complementary License Agreement 1.7".

## Unbound r5.9.3
Studied under docs/shader.md#policy, license R18; paths under reference/complementary-unbound-r5.9.3/shaders/.
- Advanced Color Tracing (COLORED_LIGHTING, 4 to 32 chunks: lang/en_US.lang). The shadow vertex stage writes one block id per quad into a 3D r16ui image, placed through at_midBlock and cleared every frame (program/shadow.glsl, shaders.properties). A compute shadowcomp (program/shadowcomp.glsl; world0/shadowcomp.csh, #version 430) sets each open voxel to an attenuated mean of its six neighbours in last frame's volume, tinted by translucent blocks; emitters inject their colour. Two rgba16f 3D images swap roles by frameCounter % 2; the read is offset by the camera's whole-block move (previousCameraPosition). It skips voxels behind the camera and spreads each half of the volume on alternate frames. Needs shadow.culling = reversed and a shadow program in every dimension (world-1/shadow.vsh). Lighting samples the volume trilinearly; its reach is the smaller of the volume and twice shadowDistance (lib/voxelization/lightVoxelization.glsl). ACT turns itself off without shadows or the optional CUSTOM_IMAGES flag, and turns on colored light fog, connected glass and portal edges (lib/common.glsl). Option text: each chunk tier can cost over twice the last; light leaks around non-full or modded blocks.
- World-space reflections (needs ACT, capped at 16 chunks): face data in an SSBO, the block atlas as a custom texture, voxel-space AO (lib/materials/materialMethods/worldSpaceRef.glsl).
- Light shafts (LIGHTSHAFT_QUALI_DEFINE): a dithered march in composite1 (lib/atmospherics/volumetricLight/volumetricLight.glsl) that also draws the End beams, so OFF runs at Low in the End (lang). Pitfall: one update is gated on frameCounter modulo a count from the smoothed frame time, which BENCH_DETERMINISTIC forbids.
- The user's look: played (config/profiles/complementary-unbound-played.json) runs RP_MODE 0, ACT and WSR off (defaults), light shafts 0, style 4, shadows at 96 blocks, SSAO, bloom, TAA with sharpening, Potato water reflection: no next-generation feature. Its character comes from the tonemap (a modified Lottes curve with exposure, white path and dark desaturation: program/composite5.glsl, lib/common.glsl), per-time-of-day light and ambient colours (LIGHT_* and ATM_*), the style's clouds, fog (ATM_FOG_MULT 0.50), sky and night styles [inferred]. profile.COMPLEMENTARY sets ACT at 16 chunks, WSR and shafts High, and keeps IPBR (the default).

## Techniques
Scale: Unbound's played frames are 4.6-7.7 ms at 4K (ALC, MC 1.21.11: docs/shader.md#method). Unsourced ranges are [inferred] from the stated basis; source-measured marks a source's own timing.

### Colored block light by voxel floodfill
- Claim: the common next-generation feature. Unbound, Photon ("enabled with Ultra profile": R5), Solas (credits SixthSurge "for voxelization & light propagation algorithm": R8) and Bliss (credits Null for "the voxel floodfill colored lighting": R6) ship it. Photon's shaders.properties follows the same pattern: an r8ui id image (Unbound r16ui), two rgba16f volumes, setup and shadowcomp, reversed culling, a Nether shadow program only for it. Unbound's step is a diffusion; Minecraft-style flood fill drops a level per step, "a breadth-first search along the 6-faces of each cube" (R15). Either runs one Jacobi step a frame.
- Cost: resolution-independent but for the lighting fetch. At 8 chunks (256 x 128 x 256) a rgba16f volume is 67 MB; a step reads one, writes the other, reads and clears the 17 MB id image: about 170 MB, 0.27 ms at R17's peak, 0.15-0.4 ms with the skip and real efficiency, the volume above the 64 MB L3. Fetch at 4K 0.05-0.1 ms. The Nether adds a voxel-only shadow pass, 0.2-0.4 ms (shadow is 4 % of Unbound's frame: docs/shader.md#method); the End keeps its own. Totals: 0.25-0.5 ms Overworld plus the shadow pass's growth under reversed culling (unestimated); 0.45-0.9 ms Nether. Cost goes with volume: 4 chunks /8, 12 chunks x3.4; integer levels would cut traffic 2-4x [inferred].
- Quality: Off; Low 4 chunks; Medium 8 (about 150 MB VRAM in fp16, less in integers); High 12. voxelDistance covers the radius and shadowDistance cannot be below it (R2): Medium needs shadowDistance >= 128, above played's 96 [inferred].
- Determinism: no TAA, but the volume is temporal state. fp16 averaging rounds, so sessions whose volumes passed different transients may settle on different states, as TAA history does (docs/measurement.md#visual-protocol) [inferred]. Fix 1: clear it at the flush; its convergence (ln 255 over the per-step attenuation's log, doubled at half rate: 100-200 frames) joins N_conv [inferred]. Fix 2: integer max-minus-one levels per channel, reads clamped to the level range: the update is monotone and lowers any excess a level a step, so one exact fixed point from any start within 15 steps (30 at half rate), no flush [inferred; L3 test 1]. The parity swap (frameCounter mod 2) makes the pack cycle even. Pitfalls: a view-dependent skip leaves stale light in view (none under BENCH_DETERMINISTIC); a scrolled read outside the volume is undefined in texelFetch, so bounds-check it.
- Iris: CUSTOM_IMAGES (3D, at most 16: R2; zeroed at creation by glClearTexImage: R1), imageStore and at_midBlock in shadow.vsh (R2), COMPUTE_SHADERS for shadowcomp (fallback: fragment propagation over a 2D-tiled volume [inferred]), shadow.culling = reversed (SAFE_ZONE: R1) with the REVERSED_CULLING flag and voxelDistance (R2), previousCameraPosition. Iris checks capability: compute if glDispatchCompute resolves; images if glBindImageTexture resolves, GL 4.2, or the ARB or EXT extension plus ARB_buffer_storage (R1). Against: its docs say custom images "require OpenGL 4.2 support" (R2), ARB_compute_shader requires 4.2 (R4), and the context is "3.3.0 Core Profile Context" (docs/platform.md#mc-263-verified). For: Unbound's #version 400 shadow program loads and renders here (shadows off -10.76 %: docs/measurement.md#calibration) [inferred]. Only a probe launch settles it.
- Aperture: two explicitly swapped 3D images are the no-flipping pattern (docs/shader.md#pipeline-spec); voxelization needs a pass that writes images, while Aperture's shadow pass is an object shader over cascades and image variables are the stated exception to its read/write rule (R3): unconfirmed. Algorithms go in Iris-free includes.
- Recommendation: take back now: hooks in M4, built in M5 behind its option, if the probe passes.

### Voxel-traced block-light shadows and world-space reflections
- Claim: Rethinking Voxels has "coloured block light with sharp shadows"; "Occasional sudden brightness changes are a side-effect of the way it works" (R7); how it traces is [inferred]. PathMax samples block lights "with a shadow ray each" (R8).
- Cost: rays x lights per pixel at 4K; Unbound's WSR SSBO is about 200 MB at 8 chunks, 810 MB at 16 (shaders.properties). No source gives ms; 0.5-2 ms on cave, night, Nether and water views [inferred].
- Determinism: exact per frame if every light is traced each frame; stochastic light choice needs accumulation: A12, review only under E4's fallback (docs/design.md#8-open-decisions).
- Iris: the floodfill's needs; WSR adds an SSBO (code: indices 0-12, GL 4.4 or ARB_shader_storage_buffer_object plus ARB_buffer_storage: R1; docs: 0-8, OpenGL 4.3: R2) and a block-atlas customTexture. Aperture: buffers "significantly more powerful" (R3); ray queries undocumented.
- Recommendation: later (after 1.0), on the floodfill's volume; SSR with sky colour covers water first.

### Path-traced GI
- Claim: SEUS PTGI (OptiFine: R10), PathMax (MIT; a voxel copy "rebuilt every frame", GI "denoised in screen space", "OpenGL 4.6, compatibility profile": R8), Photonics (an Iris extension mod, ARR, alpha, no 26.x build: R9). Low-sample GI rests on temporal reuse: GI-1.0 reprojects its caches and denoises by "temporal accumulation and an adaptive spatial filter" (R11); Brixelizer GI likewise (R14).
- Cost: GI-1.0, on DXR 1.1 hardware ray queries, 1.93-3.12 ms at 1080p and 1/4 spp on an RX 6900 XT (R11's table, source-measured; its Figure 1 says 3.5 and 4.2 ms); SVGF "runs in just 10ms (+- 15%)" at 1920x1080 (R13, 2017 hardware). Linear in pixels, 4K gives 7.7-17 ms, high as the world cache does not scale with pixels [inferred]: Unbound's whole frame or more. OpenGL has no hardware tracing, so Iris needs a software voxel march of unknown cost [inferred].
- Determinism: wholly on A12: sequences on frameCounter mod a cycle dividing 720720 (2^4 x 45045, so power-of-two cycles up to 16), every reservoir and history cleared at the flush, N_conv from the slowest accumulator; review only under E4's fallback.
- Iris: compute, images, SSBOs, history ping-pong, previous matrices; Photonics would add a mod to the bench tier, an identity change (docs/platform.md#mod-tiers). Aperture: ray queries undocumented (R3).
- Recommendation: not for 1.0; revisit with the Aperture port.

### Screen-space GI
- Claim: Kappa and Nostalgia ship "screen-space path-tracing (SSPT)" (R8), under the not-yet list's ray and path tracing. The visibility bitmask extends horizon AO to one-bounce diffuse light behind thin surfaces (R12).
- Cost: R12 at 1920x1080, 16 samples, exponential steps, denoise included: 2.93 ms full, 1.07 ms half resolution (source-measured; GPU unnamed, its AO table's an RTX 2080). At 4K these are the half- and quarter-size-per-axis tiers: 1.5-2 and 0.6-0.8 ms, assuming an RTX 2080 and a 1.5-2x faster RX 7800 XT [inferred].
- Quality: Off; AO only (ao topic); Medium quarter, High half size per axis.
- Determinism: samples "jittered over multiple frames" (R12), TAA the denoiser [inferred]: the TAA-on look needs A12, review only under E4's fallback; TAA-off frames stay deterministic, so optimizations can still reach identical or near.
- Iris: full-screen passes and previous-frame colour, within the 3.3 baseline. Aperture: direct.
- Recommendation: later: AO's High level once AO lands (M5) and its cost row fits.

### Volumetric light shafts
- Claim: Unbound, Solas ("crepuscular rays"), BSL ("volumetric light"), Photon and Kappa ("Volumetric fog") ship them (R5, R8).
- Cost: PB put the End's shafts near 70 % of the End frame, ALC composite1 at 73 % of end_dragon (docs/playbook.md#4-design-defaults); Overworld shafts were off in ALC's rows and end_dragon's ms is in no doc, so 3-5 ms at full resolution is [inferred] from that share of 4.6-7.7 ms. At half size per axis with the depth-aware upsample (docs/playbook.md#51-structural): 0.4-1.2 ms [inferred], already paid in the End by the kept End-beam pass.
- Quality: Off; Low, Medium, High by step count, half size per axis.
- Determinism: dither from frameCounter mod the pack cycle, no smoothed uniform (Unbound's pitfall); TAA-on look needs A12, TAA-off frames deterministic.
- Iris: the shadow map in composite, nothing new. Aperture: a full-screen pass over the cascaded shadow maps (R3) into an explicit half-size texture.
- Recommendation: take back now (M5, with fog), sharing the End-beam march.

### PBR materials and POM
- Claim: labPBR (Photon, Kappa: R5, R8) and POM need a PBR resource pack (Unbound: RP_MODE 2, 3; POM's option text warns of a severe cost: lang/en_US.lang); IPBR-style derived normals (Unbound's default, RP_MODE 1) work on any pack.
- Cost: inside terrain, 40 % of Unbound's frame (docs/shader.md#method); derived normals 0.2-0.6 ms [inferred]; POM is a per-pixel height march.
- Determinism: exact per frame. Aperture: gbuffers code ports.
- Recommendation: not: Faithful 64x is the build and test pack (docs/shader.md#look-and-scope), its PBR maps unverified; the minimal material map stays.

### Pack survey
| Pack | License | Next-generation features | Versions |
|---|---|---|---|
| Complementary Unbound | Complementary License Agreement 1.7 | ACT, WSR, shafts, IPBR, POM | to 26.3 |
| Photon | Photon Shaders License, ARR unless stated | voxel colored light (Ultra), GTAO, volumetric fog, labPBR | to 26.3 |
| Bliss | Chocapic13, all rights reserved | floodfill colored light | to 26.3 |
| Rethinking Voxels | Complementary Agreement | colored block light, sharp block-light shadows | to 1.21.10 |
| Solas | ARR | colored block light, volumetrics | to 26.3 |
| BSL | ARR | volumetric light, specular and normal maps | to 26.3 |
| Lux V1 | ARR | BSL-based; features not stated | to 26.2 |
| Kappa, Nostalgia | ARR | SSPT, SSR, labPBR | to 1.21.4 |
| PathMax | MIT | voxel path tracing | to 26.3 |
| SEUS PTGI | Patreon, no public source | path-traced GI | OptiFine |

## For Optilux
### First version (for D72)
- Take back: colored block light by an integer floodfill (Medium 8 chunks), if the probe passes; light shafts at half size on the End-beam march.
- Later: SSGI as AO's High level; voxel-traced block-light shadows; WSR; colored light fog. Not: path tracing (cost, wholly A12), custom PBR and POM, IPBR+ extras, Photonics.
- Prerequisites: shadows on, shadowDistance >= voxelDistance; compute in L0, which refuses compute programs today (docs/offline.md#levels), or the fragment fallback.

### Budget hypothesis (4K, RX 7800 XT)
| Views | Floodfill (Medium) | Shafts |
|---|---|---|
| forest_noon, ocean_sunset, rain | 0.25-0.5 | 0.4-1.2 |
| cave, night, underwater, entities | 0.25-0.5 | 0-0.4 |
| nether_crimson, nether_soul | 0.45-0.9 | none |
| end_dragon, end_city | 0.25-0.5 (0.9 without End shadows) | End-beam pass |

- Frame budget for D72 [hypothesis]: default profile under 8.3 ms (120 fps) on every perf view, next-generation set under 1.5 ms mean (Unbound: 4.6-7.7 ms). Sodium targets 3840x2160@240 here (docs/platform.md#mc-263-verified): 4.17 ms, below every Unbound frame; the rate is the user's call.
- M6's ratio: kept on shared features: a taken-back feature Unbound has gets its iso switch matched (COLORED_LIGHTING with its extras set to Optilux's subset; LIGHTSHAFT_QUALI_DEFINE, End beams included); others are cost rows only.

### Look target
- Closed: Unbound is the only reference pack (docs/design.md#7-decisions-taken-user-2026-10-05), the side-by-side reference, not the target (roadmap D71). Within it, a third Unbound profile (played plus the taken-back features at matched levels) gives next-generation reference frames with no new pack.
- Other packs (Photon's sky and GTAO, Solas's volumetrics) and Vibrant Visuals (directional lighting, volumetric fog; Bedrock first, Java planned: R16) are art-direction images only, unless the user reopens that decision.

### Confirming measurements
- Probe: one launch, iris.features.required = COMPUTE_SHADERS CUSTOM_IMAGES SSBO REVERSED_CULLING, a one-voxel compute write, a shadow.vsh imageStore and a branch on MC_GL_ARB_compute_shader (docs/gpu-iris.md#programs-and-alpha-tests); shaders.reload ok or iris-compile-error; the L1 dump holds the compute program.
- Unbound cost rows before D72 closes (full mode, perf only: docs/measurement.md#verdicts-and-cost-rows): played vs + COLORED_LIGHTING 256 (once more with COLORED_LIGHT_FOG off, the floodfill alone), vs + LIGHTSHAFT_QUALI_DEFINE 2; WORLD_SPACE_REFLECTIONS 1 only over ACT (alone a no-op). Played's shadowDistance 96 caps ACT at 192 blocks across. Unbound drops ACT silently without CUSTOM_IMAGES: each ACT row needs an L1 dump showing shadowcomp.
- Every feature: cost rows on every view, tier review.
- Floodfill: TAA off, cave, night, nether_crimson and entities identical across two sessions; for the integer form, no flush.
- Shafts: TAA-off identical across sessions; TAA-on at review and the live pass.

### L3 golden tests
1. Floodfill step on a 16^3 volume (emitter, wall, tinted voxel): golden levels after k steps; the integer form's one fixed point from zero and random starts within 15 steps.
2. Scroll: a whole-block shift then a step equals a step then the shift, inside the volume; reads outside it return zero.
3. Voxel addressing round trip; the edge fade to the lightmap continuous.
4. Every frame-varying sequence's period divides 720720 (frameCounter 0 to 720719).
5. Shaft march, zero dither, lit shadow map, homogeneous medium: the analytic integral.

## Open questions
1. Do COMPUTE_SHADERS, CUSTOM_IMAGES, SSBO, #version 430 compute and glClearTexImage (R1) work on 26.3's 3.3.0 core context with AMD's driver, and does the pinned jar zero custom images? Decides: the probe; javap of FeatureFlags, IrisRenderSystem and GlImage.
2. What do ACT, shafts and WSR cost in Unbound here? Decides: the cost-row session.
3. Integer or averaged floodfill, for look and determinism? Decides: L3 test 1, then review frames at cave, night and Nether beside Unbound's ACT.
4. The look target, the frame budget and its rate (Sodium targets 240 Hz). Decides: the user, at M4's plan.
5. Can Aperture voxelize in a geometry pass, and does it expose ray queries? Decides: Aperture's docs when public.
6. Does Faithful 64x carry labPBR maps? Decides: a scan of the pinned zip for _n and _s textures.
