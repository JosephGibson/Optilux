# Changelog

User-facing changes per release, newest first. Versions are MAJOR.MINOR.PATCH from 0.2.0 on; the first release was v0.00.06.

## 0.3.0 Perf loop
The goal: a performance verdict on a shader change. The harness times calibrated sessions on the bench world's views, restores the world before each run and says whether a change is faster, slower or inside the noise. The plan fixes the details; this entry grows with what ships.

## 0.2.0 Game control
The harness installs the pinned Minecraft, Fabric, mods, Java and tools hash-checked, launches the game directly, and drives it through the rewritten helper mod. Still nothing to run for a shader user: the first real pack arrives in a later release.
- `optilux install` fetches Minecraft 26.3, Fabric Loader 0.19.5, Fabric API, Sodium 0.9.2, Iris 1.11.7, Temurin 25 and PresentMon 2.6.0, each checked against its pinned hash, and checks the launch command against Mojang's and Fabric's metadata.
- `optilux launch <world>` writes the bench display settings (exclusive fullscreen at the desktop's 3840x2160, which `run` requires, vsync off, frame rate unlimited), refuses to start beside a game already running from Optilux's install, a Gradle build or an Optilux trace session, starts the game directly and waits for the world.
- The helper mod, optilux-helper 0.1.0, is a full rewrite. Without the launch's one-time token it stays inert. With it, it serves 17 commands over a local, user-only named pipe: world and state queries, server commands, ticks, exact camera placement, readiness, shader reloads that report compile errors, frame captures with a hashed manifest, input blocking, the HUD, a selftest and quit. `optilux mod build` and `optilux mod test` build it and run its tests.
- `optilux run <spec>` runs an acceptance session and writes a JSON run record, with everything that can move a measurement, under results/records/. The mod's acceptance checks pass on unmodified Complementary Unbound in a provisional world: inert without the token, captures byte-identical to F2 screenshots, exact `/tp` placement, compile errors reported (on a deliberately broken copy), input blocked, frames matched to PresentMon's clock, and the selftest; with a table of memory use over 50 shader reloads.
- The bench world (seed 263) and its eleven views were chosen with the user.
- CI runs the tests, ruff and pyright on Windows, and checks on every pull request the release its merge will create.
- Versions are now MAJOR.MINOR.PATCH, kept in the file VERSION: this release is 0.2.0, each later milestone before 1.0 a minor release (0.3.0 next) and a patch release only for a fix. Releases are titled `Optilux <version>: <name>`.

## 0.00 Foundation
Foundation. Nothing to run yet: no shader pack to install and no benchmark to start.
- Repository: the design, measurement, platform, shader and mod documents, the roadmap and the M0 plan.
- Harness skeleton: the `optilux` command (`test`, `verify docs`, `status`, `milestone start`, `pack build`, `pack release`) with its tests, doc checks and git hooks; CI runs the tests and builds the zip on every push and pull request.
- Release path: every merged milestone creates a private GitHub release carrying optilux-<version>.zip, built the same way on every machine (one tree gives one sha256).
- Placeholder pack: the zip holds a shaders.properties with one comment line and no programs, next to the MIT license and the README with the credit. The first real pack arrives with M3.
