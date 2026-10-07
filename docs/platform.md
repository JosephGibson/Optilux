# Platform
Status: mc-26.3 pinned 2026-10-05; the spike's results in "mc-26.3 verified" are approved as written (user, 2026-10-06; plans/m1.md P22).

## Contents
Concept · mc-26.3 · Renderer transition · Mod tiers · Mod adapter surface · Install and launch · mc-26.3 verified · Platform change · Sources

## Concept
- A platform is everything that changes with the Minecraft version or renderer: MC version, Java major, loader; renderer backend; mod tiers (exact files + sha512); data and resource pack formats; world snapshot; the mod adapter; quirks to re-verify.
- Platform-independent: harness core, statistics, run-record schema; suite logic, docs, skills; the shader's pipeline spec; the exceptions at M1 in design.md#4-architecture.

## mc-26.3
- MC 26.3 released 2026-09-15 [S1]. Java 25 required since 26.1 (released 2026-03-24) [S2].
- Fabric Loader 0.19.5; Fabric API 0.161.0+26.3; Sodium 0.9.2; Iris 1.11.7. Iris 1.11.7 requires exactly Sodium 0.9.2 (Modrinth dependency).
- Renderer:
  - OpenGL is the default; the bench writes `preferredGraphicsBackend:"opengl"` (R3). The game creates a "3.3.0 Core Profile Context" (log line), with or without Iris.
  - Vulkan has been experimental since 26.2 (2026-06-16) as "Prefer Vulkan (Experimental)", with fallback to OpenGL [S3].
- 26.3 Snapshot 5: vanilla core shaders are compiled by ShaderC on OpenGL too; `#include` replaces `#moj_import` [S4]. Iris packs are unaffected: Unbound loads, and Iris's own patcher rewrites the pack's `#version 130` to `#version 330 core` (V4).
- Translucency: vanilla OIT is gated by the `improvedTransparency` option (GameRenderer.useImprovedTransparency); Iris sets it false whenever shaders are enabled (MixinDisableFabulousGraphics), so a pack never sees OIT. Translucent terrain and water go through Sodium's translucent pass to `gbuffers_water` (ShaderKey TERRAIN_TRANSLUCENT -> ProgramId.Water); IRIS_HAS_TRANSLUCENCY_SORTING is defined (R10).
- Depth: 26.2 switched vanilla rendering to a reversed depth buffer [S9]. Iris 1.11.7 undoes it while a pack renders the level (five UndoReverseZ mixins: clip control reported absent, compare ops mirrored, near and far swapped, clear depth 1 - d), so depthtex0/1/2 and shadowtex0 hold forward depth with no copy or transform pass (R11); the GUI still renders reversed.
- Save layout: dimensions/minecraft/<dim>/ (region, entities, poi), players/data/<uuid>.dat, data/minecraft/*.dat; no DIM-1 or DIM1, no Player tag in level.dat (S9, L1).
- World: a new 26.3 world, not a port of ALC's (user, 2026-10-05). The port procedure below applies to later platforms.

## Renderer transition
- 26.4 Snapshot 1 (2026-09-22) makes Vulkan the default ("Default" behaves as "Prefer Vulkan") and removes the automatic Graphics API fallback after a startup crash [S11]. OpenGL goes once Mojang is satisfied; no date [S5].
- Iris runs on OpenGL only: Iris 1.11.0+26.2, "Note that Vulkan is not supported" [S10]. Its successor, Aperture, is the Vulkan path [S6][S7][S8]:
  - runs on Vulkan with Sodium; uses Slang shaders and a programmable pipeline configuration; does not load old packs; is in private beta to shader developers.
- Policy:
  1. Stay on the newest MC version where OpenGL + Iris work. The bench forces OpenGL through suite.json's display.optionsTxt.
  2. Keep the pipeline spec backend-neutral (shader.md#pipeline-spec). An aperture backend then reuses passes, buffers, budgets, suite and run records.
  3. When Aperture is public, add a new platform (aperture backend) and port pass by pass. Each pass is compared against the iris-gl pass on the same views; identity differs, so it is a cost and look comparison, not a verdict.
- Aperture facts to recheck when public, from a migration guide marked outdated [S8]: no buffer flipping (a texture cannot be read and written at two positions); every texture is explicit except mainDepthTex and solidDepthTex; uniforms are `ap.*` structs; command lists merge composite and compute.

## Mod tiers
Data: config/platforms/mc-26.3.json (version, file, Modrinth id, sha512; the played tier's missing and excluded mods with their reasons). Signed off as pinned on 2026-10-05 (design.md D8).

| Tier | Adds to bench | Use |
|---|---|---|
| bench | fabric-api, sodium, iris, optilux-helper; resource pack faithful-64x | every measurement |
| played | cloth-config, entityculling, ferrite-core, immediatelyfast, lithium, modmenu, moreculling, scalablelux, placeholder-api | compatibility smoke, never shader perf evidence |
| debug | gfx-debuggers | RenderDoc attribution only |
| dev | viewfinder (its MCP server: offline.md#tools; tools in L2) | development and diagnostics with Claude Code; not evidence until measured (offline.md) |
| lod | voxy (pending a 26.3 build) | Voxy compatibility |
| jvm | chunky; lithium and c2me-fabric as axes | post-1.0 JVM track |

- World prep set (not a tier, never in a session): the platform file's `worldPrep`, bench + Chunky 1.5.3 (ALC typed the prep commands in chat).
- Shader perf evidence only on bench, with one declared exception, its tier in the identity: Viewfinder's per-pass timers on the dev tier after E5's overhead check and A11 (design.md#8-open-decisions). The JVM track's S4 runs on the played tier as JVM evidence (jvm.md#scenarios). ALC's reason for the rule: each extra mod changes the measured set (ModernFix startup, MoreCulling leaf geometry, ImmediatelyFast overlay cost, Voxy distant terrain).
- Dev tier: `enableDebugOptions=true` creates a KHR_debug context and, on a fresh sodium-options.json, a modal Iris dialog over Sodium's `use_no_error_g_l_context` (L2): write it false first. The dev quit's exit -8 after the save (L2 quit) is accepted as known, no shutdown step (user, 2026-10-06).
- ScalableLux and C2ME are alpha builds; re-pin when stable builds land.

## Mod adapter surface
What optilux-helper's adapter must provide on each platform (mod.md#4-architecture). Fragility is ALC's experience across versions; the mc-26.3 column holds what the spike and M1 read in the pinned jars.

| Capability | ALC hook (fragility) | mc-26.3 |
|---|---|---|
| frame begin/end, capture point | mixin on `GameRenderer.render` HEAD/RETURN + INVOKE `renderLevel` (high) | HEAD of `GameRenderer.render` (Iris ticks its frame counter there); capture after `applyPostEffects`; swap: `GpuSurface.present` in `Minecraft.renderFrame` |
| camera pose | `ServerPlayer.teleportTo` + client pose with previous-tick rotation (medium) | kept; a dimension through `/execute in` first; `/tp`'s rules: mod.md#6-time-and-determinism |
| server command | `Commands.performPrefixedCommand` at OWNER (low) | keep; level.dat allowCommands=1 gives the owner `LevelBasedPermissionSet.OWNER` (IntegratedServer.getProfilePermissions, PlayerList.isOp) |
| reload + result | `Iris.reload`, `getStoredError` (consumed once), `isFallback`, pipeline (medium) | in a world a failed load never reaches storedError: handleException sends a chat message when a player exists, stores the error only before one exists, and opens DebugLoadFailedGridScreen in debug mode; read `isFallback()` and hook handleException |
| frames since reload | ALC held the reload frame, never exposed it | `SystemTimeUniforms.COUNTER`: reset in `PipelineManager.preparePipeline` at every pipeline creation (reload, dimension change, join), wrap 720720 (R5) |
| history flush | none | one-frame `Hud.toggle()` on the render thread before `beginLevelRendering`: hideGUI is a PER_FRAME uniform from `Hud.isHidden()`, updated by `updateNotifier.onNewFrame()` there (R6); Options.hideGui is gone |
| per-pass timers | Iris `GLDebug.pushGroup/popGroup` (high) | Viewfinder's `profile_frames` first (V5); the static GLDebug methods are no-ops unless enableDebugOptions is on (KHRDebugState), and Sodium's terrain shows only as "Terrain solid" (no cutout or translucent group) |
| readiness | Sodium private fields by accessor (high) | `ChunkBuilder.isBuildQueueEmpty()`, `getScheduledJobCount()`, `getBusyThreadCount()`; `RenderSectionManager.buildResults`, `taskLists`, `pendingTask`, `needsGraphUpdate`, `thisFrameBlockingTasks`, `nextFrameBlockingTasks`, `deferredTasks` (R7); `RenderSection.runningJobs` via `regions` |
| effective options | none | `currentPack.getShaderPackOptions().getOptionValues()`; Viewfinder's list_shaderpacks returns the same map (V1) |
| shader dumps | `enableDebugOptions` + file poll | game/patched_shaders/, one numbered file set per program plus a .json each, rewritten on every build (V4) |
| input, HUD, focus | none | HEAD of MouseHandler.onMove (SDL3, relative and absolute), onButton, onScroll, KeyboardHandler.keyPress, textInput, textEditing, Minecraft.pauseGame; F1 `gui.hud.toggle()`; F3 `debugEntries.setOverlayVisible`, no option |
| tick time, GC, heap | none | Fabric server tick event + JMX; `jcmd GC.heap_info` works on the bench JVM (L1) |

## Install and launch
No launcher (lessons.md#game-control). Nothing is installed system-wide; no Microsoft account is used or read (singleplayer only).
- `install [--tier bench] [--refresh]` fills runtime/<platform>/ (suite.json's `platform`) from the network and re-hashes every file on every run; a hash off its pin is refused with the file named; game/saves/ and the option files are never touched:
  - Minecraft: Mojang's manifest -> version JSON (re-fetched when its SHA-1 moved) -> client jar, libraries, natives, asset index and assets through minecraft-launcher-lib 8.0 (it installs the local Fabric profile with inheritsFrom, repairs a SHA-1 mismatch, checks none of Fabric's libraries, and adds Mojang's unused java-runtime-epsilon under runtime/<platform>/runtime/); install's own pass then hashes every classpath jar, the asset index, every asset and the log config against the spec it built;
  - Fabric Loader: its profile JSON from meta.fabricmc.net under versions/; libraries from Fabric's Maven against the SHA-1 the profile carries, fabric-loader's own against Maven's .sha1;
  - mods and packs: the tier's Modrinth files (through `extends`) and the reference pack into the store runtime/<platform>/files/, against the platform file's sha512; resource and shader packs copied into game/resourcepacks/ and game/shaderpacks/;
  - Java: Temurin from the Adoptium API, against the archive sha256 pinned in config/java/bench.json, unpacked under runtime/java/<build>/;
  - tools: PresentMon's console build from its GitHub release, against config/tools.json, into runtime/tools/.
- The launch spec, config/platforms/<id>.launch.json (committed), is written by the first install and compared fact by fact by every later one (its three note keys excepted):
  - main class (Fabric's KnotClient), the classpath in order with each jar's SHA-1, the asset index id and SHA-1;
  - the JVM options and game-argument template from Mojang's and Fabric's JSON;
  - no Java path, heap or flags: those live in config/java/;
  - a difference exits 1 naming the facts; `install --refresh` rewrites the file. The spec's hash is run identity: a changed spec means recalibration (measurement.md#calibration) and is a platform change (below).
- Pre-launch files, written before every launch from suite.json display (identity; reasons in its `*Why` keys):
  - options.txt: the optionsTxt keys over the game's own lines; the file as written is recorded, its hash and every key the harness does not write;
  - sodium-options.json: sodiumOptionsFile for every tier, refused unless it hashes to sodiumOptions: has_edited_fullscreen_option (else Sodium flips exclusiveFullscreen) and use_no_error_g_l_context=false (Mod tiers, dev);
  - config/iris.properties, fresh: shaderPack, irisProperties, the tier's irisTiers; a saved shaderpacks/<pack>.txt is refused (defaults).
- `launch <world> [--tier] [--no-token] [--set k=v] [--quit-after S]`, refusing any mismatch:
  1. the gate (F2): no process from runtime/<platform>/, no optilux-* ETW session, no Gradle build; AMD's PresentMon-x64.exe and RSXTraceSession and the other JVMs (idle Gradle daemons) recorded, never stopped;
  2. the classpath jars, asset index and version JSON hashed against the spec, the packs against their pins;
  3. game/mods/ made to hold exactly the tier's jars plus optilux-helper from the store (sorted sha512: identity);
  4. Java from the profile, `-Doptilux.token=<fresh>` (not with `--no-token`), the spec's JVM options, KnotClient, `--gameDir runtime/<platform>/game`, `--accessToken 0 --offlineDeveloperMode` (no --clientId or --xuid: Main defaults both), `--quickPlaySingleplayer <world>`; JAVA_TOOL_OPTIONS and kin dropped;
  5. `--username optilux`, `--uuid` from the world's players/data/<uuid>.dat, else the platform file's `offlinePlayer` (F8); a snapshot follows the bench player's first join (ALC);
  6. the started command line (psutil) equal to the built one and to the profile and the spec, the token's value excepted (fresh per launch, never identity);
  7. the join in this session's latest.log within 120 s (F11), Fabric's mod list equal to the tier; a failed check ends the game; `--quit-after S` holds S s, quits through the mod's `quit` (WM_CLOSE without a mod session) and reads the files back: every written key, the Iris keys, Sodium's text (`--set` and `--no-token`: run-record.md#identity).
- Cross-check, once per platform: minecraft-launcher-lib's own command for the same versions must match the spec's main class, asset index and jars by content.

## mc-26.3 verified
The Phase -1 spike's results, approved as written (user, 2026-10-06); Platform change step 3 reruns these checks on a new platform. Evidence is quoted; the raw records live under runtime/ (ignored). 0.01.10 closed the deferred rows; the user's look review passed.

| Check | Result | Evidence |
|---|---|---|
| S1 Python | pass | venv on 3.12.10: minecraft-launcher-lib 8.0, nbtlib 2.0.4, pillow 12.3.0 (screenshots); uv.lock pins the lib from 0.01.02 |
| S2 Java | pass | Temurin jdk-25.0.4.1+1, zip sha256 00c847d8...9283; `java -version`: "Temurin-25.0.4.1+1 (build 25.0.4.1+1-LTS)" |
| S3 Game | pass | install in 29.9 s; 5,231 files SHA-1-equal to Mojang's and Fabric's values (82 jars, index 34, 5,147 assets, log config) |
| S4 Mods | pass | 6 files sha512-equal to the platform file and to Modrinth's metadata |
| S5 Launch spec | pass | KnotClient, 82 jars, asset index 34 (abfaa525...adbe); the lib's own command: same main class, `--assetIndex 34`, 82 jars equal by SHA-1 (its client jar is the copy under the Fabric version folder; rerun in 0.01.02) |
| S6 PresentMon | pass | 2.6.0 console build, sha256 b2a706bc...f1af (GitHub publishes none); `--help` lists every flag the harness uses; unelevated: "Started recording.", the session listed by `logman query -ets` and gone after exit |
| S7 Viewfinder | pass | .mcp.json; the server answered JSON-RPC in L2; 0.01.10: Claude Code's client, reconnected by the user, ran get_diagnostics (32 ms, errors []) |
| S8 AF_UNIX | pass | `hasattr(socket, "AF_UNIX")` is False on 3.12.10 |
| S9 World | pass | launch 0: server "Done (1.431s)!", `stop` on stdin, exit 0; level.dat Data.allowCommands Byte(0) -> Byte(1), GameType Int(3) kept, no Player, DataVersion 5023 |
| R1 Formats | pass | version.json: data 121.0, resource 97.1, world_version 5023, protocol 777 |
| R2 Gamerules, permission | pass | GameRules constants advance_time, advance_weather, spawn_mobs, random_tick_speed; owner permission as in the adapter table |
| R3 OpenGL key | pass | `preferredGraphicsBackend`, values default, opengl, vulkan (PreferredGraphicsApi); the datafixer rule above; Main also accepts `--graphicsBackend` (untested) |
| R4 Reload | pass, finding | Iris.reload(): irisConfig.initialize() re-reads iris.properties, destroyEverything(), loadShaderpack() reads shaderpacks/<pack>.txt and writes it back with the effective values; the error path as in the adapter table |
| R5 Frame state | pass | FrameCounter `(count + 1) % 720720` at render HEAD; Timer wall-clock ms / 1000, reset at 3600; both reset in preparePipeline for an uncached dimension and destroyPipeline() clears the cache; RenderTargets.fullClearRequired is true for a new pipeline, so its first frame runs clearPassesFull (every buffer); beginLevelRendering calls allChanged() once per new pipeline |
| R6 hideGUI | pass | `.uniform1b(PER_FRAME, "hideGUI", client.gui.hud::isHidden)`; updated at updateNotifier.onNewFrame() in beginLevelRendering |
| R7 Hooks | pass | GLDebug call sites: setPhase, composite 20 + ordinal, programs 20 x ordinal + i, final 990, shadowcomp 901, Clear textures 100, GUI 1000; `isTerrainRenderComplete()` = `getBuilder().isBuildQueueEmpty()` |
| R8 MC_VERSION | pass | formatVersionString(major + two-digit minor + two-digit patch) of the version name: 26.3 -> 260300; dumps are preprocessed, so the value is not visible there |
| R9 Offline | pass | `--offlineDeveloperMode` takes no value, `--accessToken` is required, `--uuid` optional (else createOfflinePlayerUUID); Minecraft: profileFuture completed locally, UserApiService.OFFLINE, ProfileKeyPairManager.EMPTY_KEY_MANAGER; the discovery client and Realms objects are still built |
| R10, R11 | pass | see mc-26.3; CompositeDepthTransformer only rewrites centerDepthSmooth |
| Iris source | note | no release tag for 1.10+; the 26.3 branch head says 1.11.6, the jar 1.11.7+mc26.3: read at commit adc75283b, confirmed in the pinned jar's bytecode (F9); Sodium at tag mc26.3-0.9.2 |
| L1 join | pass | 18.4 s from process start to "Loaded 1866 advancements"; "optilux[local:E:9375a0e8] logged in with entity id 11" |
| L1 offline session | pass | "Setting user: optilux"; 26.3 logs no UUID, the player file is players/data/51ff11bb-8719-3a7c-b3f6-cb4a2d1c5a79.dat (the platform file's value); TCP to 60 s in the world: one remote, api.minecraftservices.com:443 during startup; "Ignoring chat session from optilux due to missing Services public key" |
| L1 Iris loads Unbound | pass | "Using shaderpack: ComplementaryUnbound_r5.9.3.zip", "Creating pipeline for dimension minecraft:overworld", no failure line; "Using graphics backend OpenGL, using drivers: 3.3.0 Core Profile Context 26.9.2.260915" |
| L1 command line | pass | KnotClient, -Xms6144m -Xmx6144m, 82 jars equal to the spec by SHA-1, --quickPlaySingleplayer spike, --offlineDeveloperMode, the platform file's username and uuid |
| L1 PresentMon columns | pass | 23 v2 columns including PresentMode, CPUStartQPCTime, FrameTime, CPUBusy, GPULatency, GPUBusy; 2,510 rows, "Hardware: Independent Flip" on every row; medians FrameTime 7.07 ms, GPUBusy 7.06 (ratio 0.999), GPULatency 7.32 ms = 1.04 frames (ALC ~2.7) |
| L1 QPC | pass | every CPUStartQPCTime between the two reads; span 21.98 s; first row 4.0 s after the start, last 0.09 s before the stop read: absolute QPC ms, 4 s start latency |
| L1 PresentMon stop | finding | CTRL_C_EVENT to its own process group ignored for 6 s (Windows disables Ctrl+C in a CREATE_NEW_PROCESS_GROUP child); CTRL_BREAK_EVENT: exit 0, complete CSV, no optilux-spike session left; the CSV grew during the run (243 KB at 20 s, 441 KB at exit) |
| AMD PresentMon | finding | RadeonSoftware.exe starts `PresentMon-x64.exe -stop_existing_session -output_stdout -v1_metrics -qpc_time -session_name RSXTraceSession` with the game: a process, not only a session |
| L1 heap | lower bound | after GC.run, 60 s idle at spawn: "used 725195K" of "committed 6291456K"; private bytes 11,067 MiB; the bench heap stays provisional |
| L1 screenshot | pass | PrintWindow(PW_RENDERFULLCONTENT) returned a frame (not black); the capture process was not DPI-aware (2560x1440), fixed for L2 |
| L1 quit | pass | WM_CLOSE: "Stopping!", "Saving worlds", three dimensions saved, exit 0 in 1.9 s |
| L1 options | finding | Sodium: "Setting exclusive fullscreen to true by default, as the user is using a language that likely does not need an IME" and "Exclusive target 3840x2160@240"; the fancy preset set simulationDistance 12; "fabric" dropped from resourcePacks; every other key read back as written |
| L2 launch | pass, finding | 66 mods; "Viewfinder MCP server started at http://127.0.0.1:7150/mcp"; the modal Iris dialog blocked until WM_CLOSE (join 167.3 s with that wait); exclusiveFullscreen false held |
| L2 tools | pass | tools/list: 23 tools (reload_shaders, list_shaderpacks, switch_shaderpack, set_shader_options, capture_frame, profile_frames, set_scene, control_ticks, ...); no server-command tool |
| V1 | pass | CLOUD_QUALITY "2" -> file "CLOUD_QUALITY=0" + reload -> "0"; Iris rewrote the file with a date header; iris.properties shaderPack=...-copy.zip + reload -> current "ComplementaryUnbound_r5.9.3-copy.zip", CLOUD_QUALITY "2"; back -> original; reloads 1.72, 0.59, 0.61 s; pre-screen: clouds at 2, none at 0; pixel diffs are swamped by TAA and animation (control pair 56.7 % changed) |
| V3 | finding | 50 reloads, 0 failures, 0.54-0.61 s; heap after GC 674 -> 1,208 -> 1,703 MiB (20.6 MiB per reload); private bytes 11,987 -> 27,968 MiB (320 MiB per reload); dev tier with debug context and dumps (F4 re-measures on bench) |
| V4 | pass | patched_shaders/: 270 files, numbered per program with a .json each; `#version 330 core` in composite, composite1, final and terrain_solid where the source says `#version 130`; "// Generated by glsl-transformer" |
| V5 | pass | profile_frames(120): 26 passes, ns avg/min/max/latest, sampleCount 50, nesting deferred/deferred1; Terrain solid 3.38 ms, deferred1 1.85; no cutout or translucent terrain group even with water in view; Viewfinder reported 30 fps under the debug context (not evidence) |
| V6 | pass | set_scene to the water at (-533, 62, -368): "Singleplayer scene updated"; pre-screen: water through Unbound with reflections, no black translucency; glass and ice placed by /setblock in 0.01.10 |
| V2 | pass, finding | 0.01.10, through the mod's `command`: under /tick freeze particles neither spawn nor age, and a mob moved by /tp keeps its client position until ticks run (summon in place); cow mean abs diff 0.35 frozen, 2.41 across `/tick step 20` |
| L2 quit | finding | WM_CLOSE saved the world ("Saving worlds", three dimensions) but the shutdown watchdog fired: crash report "Client shutdown from post-main" with Viewfinder's "HTTP-Dispatcher" thread alive, exit code -8 after 17 s |

## Platform change
1. New platform file: pins + sha512.
2. install, which writes the new launch spec.
3. The checklist above: formats, gamerule names, the OpenGL option key, MC_VERSION; Iris reload, frame state, hideGUI, translucency, depth; the adapter surface in the pinned source; every [MC] item in lessons.md.
4. Port the world: copy the snapshot, open it on the new version, re-check every camera, re-snapshot and hash.
5. Recalibrate every mode.
6. Re-capture the reference baselines.
7. Code changes stay in the mod adapter, the shader backend and those exceptions.

## Sources
Secondary sources are marked; the spike confirmed what the bench depends on.
- [S1] https://syntaxmine.com/articles/what-breaks-in-minecraft-26-3 (secondary): release, mod versions, formats, OIT.
- [S2] https://minecraft.wiki/w/Java_Edition_26.1: Java 25, 26.1 release.
- [S3] https://syntaxmine.com/articles/minecraft-vulkan-renderer-26-2 (secondary): Vulkan experimental in 26.2/26.3, with fallback.
- [S4] https://www.minecraft.net/en-us/article/minecraft-26-3-snapshot-5: ShaderC and `#include`.
- [S5] https://www.gamingonlinux.com/2026/02/minecraft-java-is-switching-from-opengl-to-vulkan-for-the-vibrant-visuals-update/: OpenGL removal planned, no date.
- [S6] https://x.com/IrisShaders/status/2024298162564059576 and https://x.com/IrisShaders/status/2054389223231500347: Aperture, no old packs, beta on 26.2 Vulkan + Sodium.
- [S7] https://deepwiki.com/IrisShaders/docs/4-aperture-pipeline-(beta) (secondary): Aperture pipeline.
- [S8] https://shaders.properties/aperture/migration/: migration guide (outdated, moved to Slang).
- [S9] https://minecraft.wiki/w/Java_Edition_26.2: reversed depth buffer; the Graphics API option.
- [S10] https://api.modrinth.com/v2/project/iris/version (Iris changelogs): 1.11.0+26.2 "Note that Vulkan is not supported"; 1.11.4+26.2 depth transformer.
- [S11] https://minecraft.wiki/w/Java_Edition_26.4_Snapshot_1: Vulkan default, crash fallback removed; date from https://piston-meta.mojang.com/mc/game/version_manifest_v2.json (26.4-snapshot-1, 2026-09-22).
- Pins: Modrinth API v2 and meta.fabricmc.net, queried 2026-10-05. Source read 2026-10-06: github.com/IrisShaders/Iris branch 26.3 at adc75283b; github.com/CaffeineMC/sodium tag mc26.3-0.9.2.
