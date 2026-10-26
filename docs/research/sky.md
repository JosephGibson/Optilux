# Sky and atmosphere
Status: research for the overworld atmosphere, sun, moon, stars, night nebula, Nether and End skies, End beams and flash, and the sky as fog and reflection fallback (M4, M5, D72 input). Nothing here is measured in Optilux yet.

## Contents
Sources · Unbound r5.9.3 · Techniques · For Optilux · Open questions

## Sources
- R1 Hillaire, "A Scalable and Production Ready Sky and Atmosphere Rendering Technique", EGSR 2020, https://doi.org/10.1111/cgf.14050 (paper); its PDF, so its timings, could not be read.
- R2 https://github.com/sebh/UnrealEngineSkyAtmosphere, MIT (R1's code, 2020): RenderSkyRayMarching.hlsl, RenderSkyCommon.hlsl, Game.cpp, Game.h, SkyAtmosphereCommon.h.
- R3 Bevy's R1 port, https://github.com/bevyengine/bevy/blob/main/crates/bevy_pbr/src/atmosphere/mod.rs (engine source, current).
- R4 https://github.com/AirGuanZ/AtmosphereRenderer, MIT (R1 in D3D11; README timings on a GTX 1060, resolution and samples unstated).
- R5 https://ebruneton.github.io/precomputed_atmospheric_scattering/ (Bruneton's code, 2017, BSD-3; paper Bruneton and Neyret, EGSR 2008): atmosphere/constants.h.
- R6 Hosek and Wilkie, "An Analytic Model for Full Spectral Sky-Dome Radiance", SIGGRAPH 2012 (paper), https://history.siggraph.org/?p=110574; code 1.4a: https://cgg.mff.cuni.cz/projects/SkylightModelling/, licence unconfirmed.
- R7 Preetham, Shirley and Smits, "A Practical Analytic Model for Daylight", SIGGRAPH 1999 (paper), https://history.siggraph.org/?p=116371.
- R8 Photon, https://github.com/sixthsurge/photon (pack source, Photon Shaders License Agreement: study only): shaders.properties, program/d0_sky_map.fsh, include/sky/atmosphere.glsl.
- R9 Iris docs, https://shaders.properties/current/reference/ (vendor docs, current): programs/overview, prepare, gbuffers; shadersproperties/features, flags, rendering, custom_uniforms; buffers/custom_textures; uniforms/world; macros/render_stages.
- R10 Iris source, branch 26.1, not the 1.11.7 tag, https://github.com/IrisShaders/Iris: IrisRenderSystem, RenderTarget, ShaderProperties.
- R11 OptiFine's shaders.properties doc, https://github.com/sp614x/optifine/blob/master/OptiFineDoc/doc/shaders.properties (vendor doc).
- R12 Yarn 1.21.11 SkyRendering, https://maven.fabricmc.net/docs/yarn-1.21.11+build.4/net/minecraft/client/render/SkyRendering.html (mappings, 1.21.11).
- R13 flytrap, 2D nebula shader, https://godotshaders.com/shader/2d-nebula-shader/ (shader source, CC0, 2022), credited by Unbound's nebula.
- R14 Mitchell, "Volumetric Light Scattering as a Post-Process", GPU Gems 3 ch. 13 (book chapter, 2007), https://developer.nvidia.com/gpugems/gpugems3/part-ii-light-and-shadows/chapter-13-volumetric-light-scattering-post-process.
- R15 Schuler, "An Approximation to the Chapman Grazing-Incidence Function for Atmospheric Scattering", GPU Pro 3 (book chapter, 2012), https://www.gameenginegems.com/gemsdb/article.php?id=1133.
- R16 Wilkie et al., "A Fitted Radiance and Attenuation Model for Realistic Atmospheres", SIGGRAPH 2021 (paper), https://cgg.mff.cuni.cz/publications/skymodel-2021/.

## Unbound r5.9.3
Complementary License Agreement 1.7 (License.txt): studied, never copied (docs/shader.md#policy). Paths under reference/complementary-unbound-r5.9.3/shaders/.
- Gradient: GetSky (lib/atmospherics/sky.glsl) blends up and middle colours by a power of view-up, adding a sun-weighted sunset band, a below-horizon ground colour, a sun or moon glare lobe and a 1/128 Bayer dither; GetLowQualitySky is a cheap twin. Colours (lib/colors/skyColors.glsl) come from skyColor, rain and day factors that lib/common.glsl computes per pixel as global initializers.
- program/gbuffers_skybasic.glsl shades gradient and stars on every fragment of vanilla's sky draws, discarding vanilla's stars by renderStage; at SUN_MOON_STYLE 2 and 3 it adds a procedural sun disc and a noise-textured moon phased by a second, offset sun vector.
- program/gbuffers_skytextured.glsl recolours vanilla's sun and moon at style 1, discards them at 2 and 3, and writes a flat colour in the End; played's SHADER_STYLE 4 defaults to style 2 (lib/common.glsl).
- program/deferred1.glsl at depth 1: aurora and nebula in the overworld; in the Nether netherColor, from fogColor and, at the default NETHER_COLOR_MODE 3, smooth()ed biome uniforms; in the End a flat colour plus hash stars (lib/atmospherics/enderStars.glsl).
- Stars (lib/atmospherics/stars.glsl): three hashes of a quantized planar projection drifting with worldTime and worldDay. Nebula (lib/atmospherics/nightNebula.glsl): three fbm value-noise layers (R13), off by default (NIGHT_NEBULAE -1), so played never paid for it.
- Reflections (lib/materials/materialMethods/reflectionBackground.glsl): behind SSR the gradient is re-evaluated per reflecting pixel (in played's gbuffers_water, GetLowQualitySky plus GGX), times a sky-light factor; border fog (fog/mainFog.glsl, off in played) uses GetSky.
- End beams (lib/atmospherics/volumetricLight/enderBeams.glsl): a noise field on an altitude band at every step of the End march (volumetricLight.glsl, whose near steps also fetch the shadow map), 30 near and 10 far steps to 1536 blocks at played's LIGHTSHAFT_QUALI_DEFINE 0. The wind reads frameTimeCounter; the flash pushes the beams toward endFlashPosition by endFlashIntensityM, a custom uniform with a smooth()ed decay (shaders.properties).
- Against docs/shader.md#determinism-and-taa, at least: rainFactor, biome factors and endFlashIntensityM are smooth()ed; beams and aurora read frameTimeCounter; dithers use frameCounter mod 3600.
- Cost [ALC replay shares, MC 1.21.11, played]: sky 6 % and composite1 11 % of 4.6-7.7 ms frames at 4K, composite1 73 % of end_dragon (docs/shader.md#method, docs/playbook.md#4-design-defaults); 6 % of that is 0.28-0.46 ms [inferred: a play-weighted share, not per view]. No ALC ablation row covers sky, stars, nebula or beams (config/profiles/complementary-unbound-played.json).

## Techniques

### T1 Deferred sky, vanilla sky draws off
- Claim: a sky shaded in gbuffers_skybasic pays for fragments terrain later covers; a deferred sky runs once per depth-1 pixel (docs/playbook.md#4-design-defaults). The draw order is [inferred]: R9 runs opaque gbuffers before deferred in no fixed order, and only weather, water and hand_water after it (programs/overview, gbuffers).
- Switches (R9 features; boolean directives in R10 ShaderProperties): Iris-only `sky=false` drops the disc, horizon and void, `stars=false` the star geometry (gbuffers_skybasic); `sun` and `moon` the textures (gbuffers_skytextured); whether `sky` drops the sunrise fan (MC_RENDER_STAGE_SUNSET) is unstated. All four off should leave the sky programs no draws [inferred]; the design default draws a cheap gradient there instead, measured below.
- Vanilla style: `sun` and `moon` on; gbuffers_skytextured writes the sprite to a cleared celestial buffer, split by MC_RENDER_STAGE_SUN and _MOON (R9 render_stages); deferred adds it times the view transmittance. Unbound works around Iris below IRIS_VERSION 10814 reporting the sun as MOON (program/gbuffers_skytextured.glsl), so L4 checks the stages. Optilux style: both off, discs in deferred (T6).
- Cost: 0.01-0.05 ms in an existing deferred pass at full sky coverage [inferred: 8.3 M pixels, one LUT fetch, about 30 ALU]; its own pass if it raises that pass's allocation step (docs/gpu-iris.md#occupancy).
- Det: no frame-varying term; Iris clears colortex0 to fogColor (docs/shader.md#determinism-and-taa), so deferred writes every depth-1 pixel. Iris: directives and stages on 26.3 [verify in jar]. Aperture: no gbuffers sky program; the celestial buffer is written once, read later.

### T2 Hillaire 2020 LUT atmosphere
- Claim: R1 renders the sky from small ray-marched LUTs (R2):
  - transmittance 256x64 RGBA16F, 40 samples ("Can go a low as 10 sample but energy lost starts to be visible");
  - multiple scattering 32x32 RGBA16F, 8x8 directions of 20 samples in a compute shader, orders summed as 1/(1-r) under a uniform phase;
  - sky-view 192x108 R11G11B10F, 30 samples, latitude squared toward the horizon;
  - aerial perspective 32x32x32.
- Bevy defaults: 256x128 (40 samples), 32x32 (64 directions, 20 samples), 400x200 (16), 32^3 (R3). R4: a 64x64 sky-view in 0.036 ms, a 64x64x32 aerial perspective in 0.03 ms, GTX 1060.
- For Optilux [inferred]: no aerial-perspective volume (render distance 16 is 256 blocks, config/suite.json; fog takes the sky-view colour); a fixed viewer altitude (384 blocks of build height, small against R8's 8.4 km and 1.25 km scale heights); a moon output beside the sky-view, scaled by moonPhase; rainStrength and thunderStrength raise Mie density and dim the sun, which a per-frame recompute follows and T3 cannot.
- Cost: about 16 k + 1 k + 21 k texels, 0.02-0.08 ms [inferred, loosely scaled from R4, its sample counts unknown]. Risk: one 32x32 fragment pass for multiple scattering is 16 wave64s, each looping 64 x 20 times with latency exposed, and may exceed that [inferred]; spread the directions over a larger pass and reduce, or use 16 directions; L4 times each.
- Quality: Low is T5 (no LUTs), Medium 192x108 at 30 samples, High 384x216 at 40 [inferred].
- Det: a pure function of uniforms each frame, no history: cycle 1.
- Iris [verify in jar]: `prepare` passes run after shadow and before gbuffers, at the size of the buffers they write (R9 prepare); integer `size.buffer` values are pixels (R9 rendering, R11; Photon uses `192 108`, R8), and gbuffers cannot write a resized buffer (R9 rendering); non-integer formats sample GL_LINEAR, CLAMP_TO_EDGE (R10 RenderTarget). No compute, SSBO or image load/store; 3-4 of colortex0-15 (docs/gpu-iris.md#passes-and-buffers).
- Aperture: each LUT written in one pass, read in later ones, never read-write; the maths in an Iris-free include.

### T3 Precomputed Bruneton tables
- A 4D scattering table packed into 3D (256x128x32), 256x64 transmittance and 64x16 irradiance tables (R5). Photon binds a precomputed ground-level scattering table as a raw RGB16F 3D texture (32x64x32) and renders a 192x108 sky map per frame "for reflections and SH lighting" (R8).
- Fit: few fetches, but a fixed atmosphere (weather means a rebuild) and a shipped binary, against "no texture assets ship" (docs/shader.md#look-and-scope); Iris loads raw 1D-3D textures via `texture.<stage>.<name>` or Iris-only `customTexture.<name>` (R9 custom_textures). Not for v1.

### T4 Analytic models
- Hosek-Wilkie "significantly improve the rendition of sunsets and high atmospheric turbidity setups", Preetham's weak points; both model the daytime sky (R6, R7). R16 adds post-sunset patterns from a fitted data file.
- night (time 18000, config/views/bench_263.json) needs a night sky they lack; ocean_sunset (12000) has a low sun [inferred]. Not recommended.

### T5 Fitted gradient (the Low level)
- An own zenith, horizon and sunset blend, each colour a custom uniform from sunAngle, rainStrength and moonPhase (docs/playbook.md#4-design-defaults). Cost about 0 [inferred]; T2's cost-row baseline.
- Det: cycle 1. Iris: custom uniforms run on the CPU (docs/gpu-iris.md#custom-uniforms) and cannot read entityColor, blockEntityId, fogMode, fogColor or chunkOffset (R9 custom_uniforms). Aperture: they live in shaders.properties; the port needs a CPU-side equivalent [inferred].

### T6 Sun and moon
- In 1.21.11 the sun, moon phases and End flash come from a celestial sprite atlas, and renderCelestialBodies takes separate sun, moon and star angles (R12); 26.3 [verify in jar]. So the moon uses moonPosition.
- Optilux style: discs at those directions, the moon lit by moonPhase, radiance times the transmittance LUT, peak clamped for TAA and bloom [inferred]. Cost: a coherent branch on view-sun > cos(radius), about 0 [inferred].
- Det: worldTime is pinned. Iris: sunPosition, moonPosition, sunAngle, moonPhase (R9 uniforms/world). Aperture: maths only.

### T7 Stars
- A hash per cell of a celestial sphere turned by a custom-uniform basis [inferred], so stars move with the sky, unlike Unbound's planar drift; 26.3's star angle [verify in jar] (T6).
- Footprint at least 1.5 px: fov 0.5 is 90 degrees (config/suite.json) [inferred], and a sub-pixel star aliases under jitter. A scalar branch skips stars by day (docs/playbook.md#4-design-defaults). Cost: about 15 ALU per sky pixel at night [inferred].
- Det: no wall-clock twinkle. Iris: the basis as custom uniforms (T11). Aperture: as T5.

### T8 Night nebula
- An own fbm in a celestial-space map (512x256 RGBA16F) written by a prepare pass, one fetch per sky pixel, added at full resolution after the cloud upsample (docs/playbook.md#51-structural).
- Cost: 131 k texels, at most 0.02 ms; per pixel on a sky-heavy night view 0.1-0.4 ms [inferred].
- Quality: Off; Low 512x256 at 5 octaves; High 1024x512 at 8 (Unbound's two counts). At 4K a 512-wide map spans about 20 px per texel, blurring the finest octaves [inferred].
- Det: moves only with worldTime and worldDay. Iris and Aperture: as T2.

### T9 Nether and End skies
- Nether: no sky draw [inferred]; sky pixels take fogColor, as Unbound's deferred1 does, without its smooth()ed biome mix (docs/measurement.md#visual-protocol). Det rests on fogColor holding still (Open questions).
- The LUT passes and their readers are off in the Nether and End (`program.<world>/<name>.enabled=false`, docs/gpu-iris.md#passes-and-buffers).
- End: vanilla draws a textured sky box and the flash sprite (R12); Optilux's deferred pass draws a base gradient, stars, the beam layer and the flash glow.

### T10 End beams and End flash
- If end_dragon's frame is in the 4.6-7.7 ms range, Unbound's composite1 there is about 3.4-5.6 ms [inferred]: the whole End march, shadow fetches included.
- Medium: an own beam field marched at half resolution, int-uniform step count 16, clipped to the band's slab, upsampled depth-aware (docs/playbook.md#51-structural): 0.3-0.7 ms [inferred: 2.07 M x 16 step-pixels against at most 8.3 M x 41, about 1/10, no shadow fetches; loose, as Unbound's march ends early on terrain].
- Low: a direction-only beam layer in a small End sky map, no parallax, at most 0.05 ms [inferred]. High: 32 steps.
- Flash: endFlashIntensity, endFlashPosition (view space), previousEndFlashIntensity (R9 uniforms/world, Iris-only) [verify in jar]. Iris-only `endFlashShadows` sets shadowLightPosition to endFlashPosition (R9 features): off unless the shadows topic wants it.
- Det: the End's clock drives the flash, set by the End views (docs/shader.md#determinism-and-taa); beams move on worldTime, frozen in a session [verify in jar: the End's worldTime]; a fixed spatial dither, cycle 1. Aperture: an explicit half-resolution target.

### T11 Time-of-day custom uniforms
- Sun, moon and up vectors; the celestial basis; day, twilight and night factors; star and nebula visibility; moon illuminance from moonPhase; rain and thunder blends. None uses smooth() (docs/measurement.md#visual-protocol).
- Ground sun colour from an analytic Chapman optical depth (R15; Photon's LUT-free transmittance uses one, R8), held to the transmittance LUT by an L3 test: one formula, one place.
- Matrices: R9 reads `m.<row>.<column>`; docs/gpu-iris.md#custom-uniforms says `.x` is a column [PB v]. The jar decides.

### T12 The sky as the reflection fallback
- One sky-view fetch at the reflected direction plus an analytic sun specular, times sky light so caves do not reflect daylight (as Unbound weights its fallback); the visible sky's formula. Photon's sky map also feeds SH ambient light (R8).
- The table must precede gbuffers_water; prepare also serves opaque gbuffers (R9 programs/overview). Cost: one fetch per reflecting pixel.

### D72 input: aurora and light shafts (not-yet list)
- Aurora: Unbound marches 25 planar layers, 3 noise fetches each, per sky pixel at night under a full moon in snowy biomes, on frameTimeCounter (lib/atmospherics/auroraBorealis.glsl); an aurora loop and a fallback march held a pass at 84 VGPRs, 48 without (docs/gpu-iris.md#occupancy). As a T8-style map with a fixed dither: cycle 1, TAA-independent, at most 0.05 ms against 0.3-1 ms per pixel [inferred]; it needs a coverage view.
- Light shafts (fog-volumetrics owns them): Unbound marches the shadow map at full resolution with frame-varying dithers (docs/shader.md#determinism-and-taa), so TAA-dependent: A12, or the review tier under E4's fallback. About 0.9-1.5 ms at full resolution with 11 steps (the End's 3.4-5.6 ms times 11/41), 0.2-0.5 ms at half [inferred]. R14's radial blur is cheaper, but "the shafts will flicker" as occluders cross the image edge. Played had them off: no ALC row.

## For Optilux
- M4: T11's uniform chain (lighting needs it); T5 as the sky; T1's switches and the coverage-list entries for gbuffers_skybasic and gbuffers_skytextured.
- M5: T2's three prepare passes (transmittance, multiple scattering, sky-view with sun and moon outputs); T1's composite; T6 in both styles; T7, T8; T9, T10 (beams at Medium); T12.

| Option | Off | Low | Medium | High |
|---|---|---|---|---|
| atmosphere | - | gradient (T5) | LUT 192x108 | LUT 384x216 |
| stars | off | on | - | - |
| nebula | off | 512x256 | - | 1024x512 |
| End beams | off | layer | half-res 16 steps | half-res 32 steps |

The sun/moon style is vanilla or Optilux, with no levels.

- Budget hypothesis at 4K, sky items only [inferred]: at most 0.08 ms on forest_noon, rain, entities, underwater and cave; 0.1 ms plus water's reflection fetches on ocean_sunset; 0.12 ms on night; 0.01 ms in the Nether; 0.3-0.7 ms in the End with beams at Medium, 0.06 ms at Low.
- Confirmations (docs/measurement.md#verdicts-and-cost-rows):
  - Forward sky against T1: cost rows on night and end_city, identical or near tier; coverage_beacon visual only, as no perf mode reads coverage views (docs/measurement.md#baseline-suite).
  - The switches against the gradient in the sky draws: an L4 replay with no gbuffers_skybasic draws, then the identical tier on every view.
  - T2 Medium against T5: a cost row on every overworld view, review tier.
  - The T8 map against a per-pixel nebula on night: close at best, else review.
  - Beams Off, Low, Medium: cost rows on end_dragon and end_city, review tier.
  - Every sky option on: the TAA-off static capture identical across launches (docs/measurement.md#visual-protocol).
- L3 golden tests (docs/offline.md#levels): transmittance against a numpy integration; the sky-view UV round trip, horizon row included; sky-view against a brute-force march near the horizon and sun; multiple scattering finite, non-negative, r < 1; custom uniforms in Iris's engine against the GLSL and world-space sunPosition; the Chapman sun colour against the LUT; the star hash stable, footprint at least 1.5 px; the nebula map invariant to camera rotation; beams finite, on the representative-pixel rule.

## Open questions
- Are `sky`, `stars`, `sun` and `moon` honoured on 26.3, does `sky` drop the sunrise fan, which program and renderStage draw the End box and flash? javap of ShaderProperties and the sky mixins; an L1 dump at end_dragon.
- Is compute exposed on the 3.3 context (R10: supportsCompute if the glDispatchCompute pointer is non-null)? IRIS_FEATURE_COMPUTE_SHADERS under `iris.features.optional` (R9 flags) in an L1 dump; only a compute multiple-scattering LUT needs it.
- Are skyColor and fogColor eased over time on 26.3? javap and a static capture after a biome move.
- Do rainStrength and thunderStrength hold still at rain under /tick freeze? Two static captures at rain.
- Physical sky (T2) or art-directed gradient: D72's look target, by side-by-side review against Unbound at ocean_sunset and night.
- Is Low's beam layer, without parallax, acceptable? Review.
- What fraction of each view is sky? Depth-1 pixel counts in L4 captures; it sets the budgets.
- Which clock does worldTime read in the End, and do 26.3's moon and star angles follow sunAngle? javap of Iris's time uniforms and 26.3's sky renderer.
