# Changelog

User-facing changes per release. Versions are 0.MM.PP (milestone, phase).

## 0.00
Foundation. Nothing to run yet: no shader pack to install and no benchmark to start.
- Repository: the design, measurement, platform, shader and mod documents, the roadmap and the M0 plan.
- Harness skeleton: the `optilux` command (`test`, `verify docs`, `status`, `milestone start`, `pack build`) with its tests, doc checks and git hooks.
- Release path: every merged milestone creates a private GitHub release carrying optilux-<version>.zip, built the same way on every machine (one tree gives one sha256).
- Placeholder pack: the zip holds a shaders.properties with one comment line and no programs, next to the MIT license and the README with the credit. The first real pack arrives with M3.
