# Iris capabilities on 26.3
Status: What Iris 1.11.7 on MC 26.3 (a 3.3.0 Core Profile context) gives a pack, read in Iris's source and docs and in Unbound, and what Aperture's model asks of the pass layout now. Research, not yet measured in Optilux; every source fact waits on javap of the pinned jar.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
Tags: docs/gpu-iris.md#sources-and-tags. Iris facts are R1's unless named, each [verify in jar] (docs/roadmap.md#findings-assigned F9); brackets name the javap class under net.irisshaders.iris.
- R1 Iris source at adc75283b, branch 26.3, LGPL-3.0; vendor source, 2026: https://github.com/IrisShaders/Iris/tree/adc75283b
- R2 Iris docs, vendor doc, 2026: https://shaders.properties/current/reference/overview/ (pages by path).
- R3 Iris changelogs to 1.11.7, vendor, 2026: https://api.modrinth.com/v2/project/iris/version. Only 1.11.4's depth transformer concerns packs.
- R4 Aperture migration guide, vendor doc, self-described "extremely outdated", 2026: https://shaders.properties/aperture/migration/
- R5 Aperture-Example-Pack, slang branch (pack.ts, iris.d.ts), vendor sample, 2026, no license file: https://github.com/IrisShaders/Aperture-Example-Pack/tree/slang
- R6 Complementary Unbound r5.9.3, pack source, Complementary License Agreement 1.7, studied only: reference/complementary-unbound-r5.9.3/shaders/
- R7 RX 7800 XT: "Up to 624 GB/s", 64 MB Infinity Cache; XFX spec page, 2023 card: https://xfxforce.com/shop/xfx-speedster-swft-210-radeon-tm-rx-7800-xt-core-edition
- R8 ALC and PB on this GPU at 4K (Iris 1.10.7, MC 1.21.11): docs/gpu-iris.md, config/profiles/complementary-unbound-played.json.
- R9 Khronos ARB specs (compute_shader, shader_storage_buffer_object, shader_image_load_store, texture_gather), vendor docs: https://registry.khronos.org/OpenGL/extensions/ARB/
- R10 Migrating to Slang from GLSL, vendor doc, read 2026: https://shader-slang.org/docs/coming-from-glsl/

## Unbound r5.9.3
In my own words (R6):
- Wrappers in world0, world-1 and world1 define the dimension and include program/*.glsl: one `shadow`, one `gbuffers_terrain` (no solid split), deferred1, composite, composite1, composite3-7, final.
- lib/pipelineSettings.glsl: formats for 13 colortex buffers, clear flags for 12, shadow hardware filtering; TAA history colortex2 is RGB16F, Clear false. size.buffer halves colortex1 and colortex7; five mip flags sit in deferred1 and composites.
- TAA (program/composite6.glsl), colortex2's only writer, reads and writes it in one pass, relying on Iris's flip and end-of-frame copy, and reprojects with the previous matrices and camera delta (lib/antialiasing/taa.glsl).
- shaders.properties: separateAo, alphaTest on eight programs, pass enable conditions, five optional flags (not SEPARATE_HARDWARE_SAMPLERS), PNG textures; no scale, no raw texture.
- Compute (world0/shadowcomp.csh, `#version 430 compatibility`), 3D images, SSBOs up to 810 MB and `shadow.culling = reversed` serve only not-yet features (colored light, world-space reflections, puddle voxels), off at COLORED_LIGHTING's default 0, which played keeps.
- Custom uniforms take frameCounter modulo 2, 4, 8 and 600 (600 does not divide 720720) and many smooth() terms: probably not deterministic as shipped (docs/measurement.md#visual-protocol).

## Techniques
Each lists facts, then D (determinism), I (Iris 1.11.7 on 3.3 core), A (Aperture), C (cost at 4K here).

### Programs, order, dimensions
- Order [pipeline.IrisRenderingPipeline, shadows.ShadowRenderer; R2 programs/overview]: setup -> begin -> shadow -> shadowcomp -> prepare -> opaque gbuffers -> depthtex1 copy -> deferred -> translucent gbuffers -> composite -> final; depthtex2 is copied before the hand; setup, compute only, runs at creation and on resize.
- Composite-style groups take up to 100 programs, a pass up to 27 computes, `_a` to `_z` read until the first gap [shaderpack.programs.ProgramSet; R2].
- Sodium [pipeline.programs.ShaderKey, shaderpack.loading.ProgramId]: solid terrain -> terrain_solid (no alpha test), cutout -> terrain_cutout, translucent -> water; shadow keys -> shadow_solid, shadow_cutout, shadow_water, falling back to shadow. The discard-free split (docs/playbook.md#4-design-defaults) is there in both passes, used by neither Unbound nor the hello pack.
- `program.<world>/<name>.enabled` takes an option expression whose condition must match every consumer (docs/gpu-iris.md#passes-and-buffers).
- Dimension folders never merge and get no macro (docs/offline.md#levels); hasCeiling, hasSkylight, ambientLight and cloudHeight are per-frame [uniforms.IrisExclusiveUniforms].
- D: none. I: present. A: R5's SCREEN_SETUP, PRE_RENDER, POST_SHADOW, PRE_TRANSLUCENT, POST_RENDER and combination pass map to setup, begin, shadowcomp and prepare, deferred, composite, final [inferred].
- C: VGPRs are a pass's maximum over its paths (docs/gpu-iris.md#occupancy), so heavy single-dimension code belongs in that folder, not behind a uniform branch [inferred].

### Buffers, flips, mipmaps
- 32 colortex [gl.IrisLimits]; default RGBA8, Clear true, clear colour 0 but colortex0 fogColor and colortex1 1 (R2 buffers/colortex; docs/gpu-iris.md#frame-counters-and-reload). R2 buffers/image_format marks 3-component formats (RGB16F, RGB32F, RGB8) not image-capable, unexplained.
- Gbuffers cannot sample colortex0-3: "colortex0,1,2,3 are only able to be sampled from fullscreen passes" [samplers.IrisSamplers]; R2: they read the atlas.
- size.buffer: integers pixels, floats screen fractions (R2 shadersproperties/rendering); gbuffers cannot write a resized buffer (R2 buffers/colortex). scale.<program> sets viewport size and offset [pipeline.CompositeRenderer].
- Flips [CompositeRenderer, targets.BufferFlipper]: a buffer a pass draws to flips after it unless `flip.<pass>.<buf>=false`, so a pass reading and writing one buffer reads one side and writes the other; a flip toggles. At frame end each buffer left flipped and not cleared is copied alt to main by glCopyTexSubImage2D, "we merely copy it from alt to main" [pipeline.FinalPassRenderer]: a Clear=false buffer written an odd number of times a frame costs a hidden full-screen copy every frame.
- `colortexNMipmapEnabled` in a begin, prepare, deferred, composite [CompositeRenderer] or final [FinalPassRenderer] program regenerates the chain before it, unchecked for staleness; a later write does not [inferred]. R2 and docs/gpu-iris.md#passes-and-buffers (1.10.7) list fewer programs.
- D: every Clear=false buffer is history. I: present. A: no flipping, every texture explicit (R4); textures take mipmap and clear, command lists generateMips and copy (R5).
- C: an RGBA16F 4K copy moves 133 MB, 0.21 ms at R7's 624 GB/s; ALC replayed the depthtex1 and depthtex2 copies, 133 MB at 4 bytes [inferred], at ~0.29 ms (read as their total [inferred]), replay running ~1.7x live (docs/gpu-iris.md#passes-and-buffers, docs/offline.md#tools). So 0.15-0.3 ms per RGBA16F copy, half at 4 bytes [inferred]; an unread mip chain 0.06-0.1 ms [ALC m, PB m] (docs/gpu-iris.md#bandwidth).

### History and previous-frame data
- gbufferPreviousModelView and gbufferPreviousProjection [uniforms.MatrixUniforms]; previousCameraPosition, shifted with cameraPosition by 30,000 blocks (past 30,000 or after a 1,000-block jump) so their difference holds, plus unshifted Int/Fract forms [uniforms.CameraUniforms]. No previous shadow matrices; no previous depth found.
- Each program keeps its own previous matrix, the first update returning identity [MatrixUniforms, gl.program.ProgramUniforms]; updated only when used [inferred], so a gbuffers program not drawn every frame holds a stale one [inferred]: reproject in full-screen passes or custom uniforms.
- Ping-pong: (a) one buffer read and written: flipped, copied; (b) `cur` written, then `prev` by a later pass that reads `cur`: `prev` still flips once a frame and is copied, so (a)'s cost plus a full-screen read and write [inferred]; (c) two buffers picked by frameCounter % 2, written by imageStore (colorimgN or custom images): no flip or copy, but fragment image load/store (Open questions 1), and Iris issues glMemoryBarrier only after computes [CompositeRenderer]: a fragment imageStore read the next frame needs a barrier Iris may not issue, so (c) waits on a probe that writes and reads alternating images and checks the values, not one that only compiles [inferred].
- D: zero marks history invalid; a reload clears it; the flush frame invalidates it (docs/shader.md#determinism-and-taa). Every Clear=false buffer read a frame later needs that test.
- I: present. A: (b) and (c) port unchanged, (a) does not. C: (c) saves (a)'s copy; (b) adds a full-screen read and write for portability [inferred].

### Compute, SSBOs, images
- Support [features.FeatureFlags, gl.IrisRenderSystem]: COMPUTE_SHADERS if glDispatchCompute resolves; SSBO on GL 4.4 or ARB SSBO + buffer_storage; CUSTOM_IMAGES on glBindImageTexture, GL 4.2, or ARB/EXT image_load_store + buffer_storage.
- R9: ARB_compute_shader requires GL 4.2 and ARB SSBO GL 4.0, so a 3.3 context should expose neither; image load/store needs GL 3.0 and GLSL 1.30 [inferred].
- Declared to be used (R2 shadersproperties/flags): CUSTOM_IMAGES, SSBO, HIGHER_SHADOWCOLOR, SEPARATE_HARDWARE_SAMPLERS, TESSELLATION_SHADERS, FADE_VARIABLE, TEXTURE_FILTERING; not COMPUTE_SHADERS. Required refuses the pack where unsupported; optional defines IRIS_FEATURE_<flag>.
- Compute keeps its #version and becomes core [pipeline.transform.TransformPatcher]; computes are read and built with no support check [ProgramSet, IrisRenderingPipeline], so a refused one fails the load. bufferObject.* without SSBO support throws at pipeline creation: guard it with IRIS_FEATURE_SSBO.
- The context reports 3.3.0 Core (docs/platform.md#mc-263-verified); whether the driver still exposes these or compiles `#version 430 core` is unknown. Optilux has built no compute; L0 refuses it (docs/offline.md#levels).
- image.<name>: sampler, formats, type, clear, relative, 1D-3D size, at most 16 [shaderpack.properties.ShaderProperties]; colorimgN and shadowcolorimgN expose targets as images [samplers.IrisImages]; bufferObject.<i>: bytes, optionally relative with two scales, i up to 12 in R1 but 0-8 in R2 buffers/ssbo (CONFLICT). A pass's computes run before its draw, then one barrier [CompositeRenderer].
- D: accumulating compute is history. I: unverified here. A: createCompute, createBuffer, image textures (R5). C: unmeasured; by Unbound's example nothing in scope needs these.

### Textures and noise
- texture.<stage>.<sampler> replaces a sampler, customTexture.<name> adds one [ShaderProperties; R2 buffers/custom_textures]: PNG (nearest, repeat, unless a .mcmeta says otherwise), resource and atlas locations, the lightmap, or raw 1D-3D data (bilinear, clamp).
- Default noisetex: Random(0) white noise, linear, repeat [targets.backed.NativeImageBackedNoiseTexture, IrisSamplers].
- D: static. I: present; Unbound uses PNGs only. A: importPNGTexture, importRawTexture (R5). C: small, cache-resident [inferred]; shipping one is Open questions 4.

### Shadow pass
- Defaults [shaderpack.properties.PackShadowDirectives]: resolution 1024, distance 160, interval 2, render-distance multiplier -1, entityShadowDistanceMul 1 (Unbound 0.125), orthographic; shadowcolor0-7 cleared to 1, past 2 needing HIGHER_SHADOWCOLOR (R2 shadersproperties/flags); terrain, translucent, entity and block-entity shadows on, player and light-block-entity off.
- SEPARATE_HARDWARE_SAMPLERS adds shadowtex0HW/1HW compare samplers for hardware-filtered maps, leaving shadowtex0/1 raw [IrisSamplers].
- Order [ShadowRenderer]: opaque and cutout terrain, entities and block entities, the copy into shadowtex1, translucent terrain, shadow mips, shadowcomp.
- shadow.culling [ShaderProperties, ShadowRenderer]: `false` distance only, `true` advanced, `reversed` safe zone; unset, advanced unless the shadow program has a geometry stage or the pack uses images, then distance only.
- Sun and shadow light read EnvironmentAttributes at the tick delta [uniforms.CelestialUniforms]; endFlashShadows aims shadowLightPosition at the End flash; separateAo needs the shadow pass (R2 shadersproperties/features).
- D: ShadowRenderer reads no Random or clock. I: present. A: cascades in a sampler2DArray (R4, R5): keep the shadow lookup behind one function.
- C: Unbound's shadows, pass and lookups, cost 0.667 ms mean, 1.120 ms worst (rain), at 2048^2, 96 blocks, entity shadows off (R8).

### Uniforms and determinism
- Custom uniforms: float, int, bool or vec2-4 expressions over Iris uniforms except entityColor, blockEntityId, fogMode, fogColor, chunkOffset (R2 shadersproperties/custom_uniforms), evaluated on the CPU once a frame [IrisRenderingPipeline].
- IDs: entityId comes per vertex in entity draws, -1 when unlisted (docs/shader.md#facts; not R2 uniforms/id's 65535); blockEntityId is a ONCE -1 [uniforms.CommonUniforms], its 26.3 feed unread; heldItemId and heldBlockLightValue are per frame [uniforms.IdMapUniforms].
- Never under BENCH_DETERMINISTIC: frameTime, frameTimeCounter [uniforms.SystemTimeUniforms]; currentDate, currentTime, currentYearTime [uniforms.IrisTimeUniforms]; eyeBrightnessSmooth, wetness [CommonUniforms]; centerDepthSmooth (R2 constants/centerdepthhalflife); the smoothed hard-coded rainStrengthS, isDry, starter, frameTimeSmooth and others [uniforms.HardcodedCustomUniforms]; smooth(), decaying by the last frame time [parsing.SmoothFloat]; random() and randomInt(), from an unseeded Random [parsing.IrisFunctions]; fogStart, fogEnd (docs/shader.md#determinism-and-taa).
- Stable only while game state holds [inferred]: sunAngle, celestial positions, shadow matrices, thunderStrength, cloudHeight at the tick delta [CelestialUniforms, IrisExclusiveUniforms] (skyColor, nightVision [unverified]); PER_TICK rainStrength, cloudTime, endFlashIntensity, refreshed when level.getGameTime() moves [ProgramUniforms], which /tick freeze should hold [inferred]. The hello pack reads none, so M3's exit tested none (config/pipeline.json).
- Allowed: frameCounter % N, N dividing 720720 = 2^4 x 3^2 x 5 x 7 x 11 x 13 (16 yes, 32 no); hideGUI, the flush signal (docs/platform.md#mod-adapter-surface). `weather=false` (CAN_DISABLE_WEATHER) drops rain and snow (R2 shadersproperties/features) [inferred: a weather discard].
- A: ap.* structs (R4); neither R4 nor R5 shows an expression language [inferred]: give each formula one name so pack.ts ports it under the same goldens.
- C: CPU only; moving such maths to custom uniforms took terrain from 72 to 60 VGPRs [PB v] (docs/playbook.md#4-design-defaults).

### GLSL version
- MC_GL_VERSION from GL_VERSION, MC_GLSL_VERSION from GL_SHADING_LANGUAGE_VERSION, MC_<name> per listed extension [gl.shader.StandardMacros]. L0 uses MC_GL_VERSION 330 (docs/offline.md#levels); `#extension` lines survive the patcher (docs/gpu-iris.md#programs-and-alpha-tests), which raises other stages to at least 330 core [TransformPatcher].
- textureGather and fragment image load/store work from GLSL 1.30 with their ARB extensions (R9), in core from 4.00 and 4.20 [unverified]; MC_GLSL_VERSION picks 330 core with guarded extensions or a higher #version.
- D, C: none. A: R10 maps GLSL's row-vector product v * a to mul(a, v), as "vectors are treated as column vectors in Slang"; a column-vector M * v stays mul(M, v) while the matrix keeps its logical layout, and R10 says nothing of row- or column-major storage. So the port fixes construction, upload layout and vector convention first, checks them on a non-symmetric transform with rotation and translation (L3), and keeps matrix maths behind one helper [inferred].

### Aperture
- R5: RendererConfig (shadow cascades, resolution, sunPathRotation, ambientOcclusionLevel); configurePipeline's textures, buffers, object shaders and per-stage command lists; exportBool/Int/Float and defineGlobally for options; TextureReference.pointTo [inferred: a history swap].
- R4: no flipping; only mainDepthTex (was depthtex0) and solidDepthTex (was depthtex1) are implicit; object shaders read VertexData (blockId, midBlock, ao).
- Layout now: resource names, not colortex numbers, in pipeline.json and includes; one writer per texture per pass; history as an explicit prev/cur pair; option values passed into includes; no reliance on colortex0's fog clear, the depthtex2 copy, flips or the colortex0-3 rule (solidDepthTex and VertexData.ao cover depthtex1 and separateAo).

## For Optilux
### First version
- M4 uses what Iris provides and Unbound exercises here (it loads on 1.11.7: docs/platform.md#mc-263-verified): fragment programs, explicit formats, Clear=false history, mip flags, size.buffer, custom uniforms, PNG textures, dimension wrappers.
- Provided but exercised by neither Unbound nor the hello pack: scale, terrain_solid and shadow_solid, separate hardware samplers, raw textures.
- Compute, SSBOs and images only after the probe (Open questions 1), each an option with a fragment path.
- One custom uniform for history validity (flush frame, first frames), read by every history consumer [inferred].
- A check rule: under BENCH_DETERMINISTIC nothing from the never list, and every frameCounter modulus divides 720720.
- pipeline.json gains resource names and a history flag per output. No capability option faces the player.
### Budget hypothesis
- A count, not a ceiling [inferred]: Iris's depthtex1 and depthtex2 copies (~0.29 ms replayed, above), two mip chains (0.12-0.2 ms) and the TAA history pair: with (c) nothing more, 0.4-0.5 ms in all; with (a) a 0.15-0.3 ms copy, 0.55-0.8; with (b) that copy plus a 0.15-0.3 ms read and write, 0.7-1.1. Resolution sets their bytes, but content, cache state and scheduling still move their time: cost rows on every perf view (docs/research/synthesis.md#budget).
### Measurements
- Capability probe: one pack per flag, each with a stage using it, plus one failing below MC_GLSL_VERSION 430; the mod's shaders.reload answers ok or iris-compile-error (docs/roadmap.md#findings-assigned F5). One launch, no visual tier; R9 predicts compute and SSBOs fail. Images (c) also need a functional probe: imageStore and reads alternating across frames, the values checked.
- Copy and mip cost: history Clear false against true, a mip flag on against off; cost rows, so frames above the CPU floor or timer rows (docs/measurement.md#verdicts-and-cost-rows).
- Ping-pong (a) against (b): an optimization verdict, tier identical; (b) expected slower by a full-screen read and write.
- Tick-delta and PER_TICK uniforms: the TAA-off check, perf views identical across 2 sessions, on the M4 base (docs/design.md#8-open-decisions E4).
- The flush: A12's two flush and capture cycles reached from different histories on purpose (another view or a camera move before each flush), at one phase, and the same across two sessions (docs/mod.md#12-acceptance); the TAA-off check cannot test it [inferred].
- Stale previous matrices: L4 RenderDoc reads of a gbuffers program's uniform in consecutive captures (explain only).
### L3 goldens
- Custom uniforms in Iris's engine against the GLSL in float32: the sun vector from gbufferModelView; the history-valid truth table over hideGUI and frameCounter 0-2; frameCounter % N across the 720719 -> 0 wrap.
- The reprojection include on synthetic matrices, forward depth (docs/platform.md#mc-263): a still camera returns its own pixel; equal shifts of both camera positions change nothing.

## Open questions
1. Does the driver compile `#version 430 core` compute and fragment image load/store on the 3.3.0 Core context, and expose ARB compute, SSBO, buffer storage, image and gather? The probe decides compute, images and the GLSL version.
2. Iris history: flip and copy, a fused prev/cur write, or image parity? A cost row on the M5 TAA, after 1.
3. Do tick-delta and PER_TICK uniforms repeat across sessions under /tick freeze? The TAA-off check on the M4 base.
4. Is a generated noise texture a "texture asset" (docs/shader.md#look-and-scope)? The user, at M4's plan; if so, hash noise, or a bake in setup after 1.
5. How does 26.3 feed blockEntityId? javap of the block-entity mixins and a coverage capture.
6. F12: can a per-frame, option-driven uniform (glintAlpha, chunkFadeTimeInv, screenBrightness) carry the flush with the GUI shown, without side effects [inferred]? M5.
7. Can an Aperture TextureReference swap every frame from pack.ts (the example exports beginFrame, iris.d.ts declares none)? When Aperture is public (docs/platform.md#renderer-transition).
