# Handoff
Status: the latest stop: M3.P01 done, the offline tools and the reference copies pinned and installed, and what M3.P02 starts from.

## Contents
Outcome · What changed · Premises · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P01
- The exit holds, shown at 5d87e5b on 2026-10-20 10:55 ADT: `uv run optilux install` ok, exit 0, "tools: glslang-16.6.0-windows-x86_64-release.zip sha256-equal (equal), present at runtime/tools/glslang-16.6.0/bin/glslang.exe", "tools: rga-windows-x64-2.15.zip sha256-equal (equal), present at runtime/tools/rga-2.15/rga.exe", "reference (studied): reference/complementary-unbound-r5.9.3/ tree sha256-equal, 436 files (equal)", "reference (control): reference/Wisdom-Shaders-V3-Build3300.zip sha256-equal (equal); reference/wisdom-shaders-v3-build3300/ tree sha256-equal, 60 files (equal)", the launch spec equal; `glslang --version` "Glslang Version: 11:16.6.0"; `rga --version` "Radeon GPU Analyzer Version: 2.15.0.30 (10/02/2026)"; flip-evaluator 1.7, numpy 2.5.4, pillow 13.0.0 and scikit-image 0.26.0 import in the venv; `git status` clean after the commits.
- One stop on the way (section 7, a launch spec that differs): Mojang republished 26.3's version JSON on 2026-10-13 06:43 UTC, moving only asset index 34 (142 files under minecraft/lang/ changed, none added or removed; jar, libraries and arguments unchanged; the bench's en_us ships in the jar). 7aa3e2f handed it off; the user answered (2026-10-20): `install --refresh`, the spec committed alone, then the phase finished. The spec's hash is identity: M2's calibrations no longer match, and M3.P10 recalibrates.
- No game launch; runtime/ and reference/ written by `install` alone; no system setting. Nothing deferred.

## What changed
- config/tools.json: glslang 16.6.0 and RGA 2.15 (version, file, sha256, source, `unpack`, `exe`, why, sha256Why); `later` keeps RenderDoc alone (M4). `install` unpacks a zip with `unpack` into runtime/tools/<unpack>/ when it lacks `exe`, through a .part folder shared with Temurin's unpack, and refuses an unpack without its exe.
- config/similarity.json: the studied copy (slug, folder, treeSha256 e68482ed..., 436 files) and the control (Wisdom Shaders Build3300: file, sha256 5f3b0cfb..., source, license Apache-2.0, folder, treeSha256 ede1518f..., 60 files, why). `install` unpacks Unbound from the store and the control's zip, fetched into reference/, each tree-hashed (record.tree_hash) on every run; a copy off its pin is refused, never repaired, and a refused unpack leaves no folder.
- pyproject.toml and uv.lock: the four packages pinned exactly; scipy 1.18.1, networkx 3.7, imageio 2.38.1, tifffile 2026.10.15 and lazy-loader 0.6 come with scikit-image.
- config/platforms/mc-26.3.launch.json refreshed (4 facts); tests/fixtures/mc-26.3/26.3-11f1aefe.json, Mojang's newest JSON, sha1-checked; test_platform's diff test covers both republishes.
- Docs: offline.md#tools (the pins, paths and versions; Shadesmith unused per D58, its Verify row gone); measurement.md#tools's deps line (the candidate list superseded); platform.md#install-and-launch (the tools line, reference/; the cross-check folded into Platform change step 2, S5 holding its evidence); design.md#4-architecture's config/ and reference/ lines and the install row; AGENTS.md's config/ line ("gitignored" cut from the Shader rule, the Layout's Ignored list says it); CHANGELOG.md's 0.4.0 entry, two bullets.

## Premises
- P6-P9 hold as plans/m3.md states them, read on 2026-10-20 with `gh api` (releases, asset digests, Wisdom's license and fork flag) and PyPI's JSON (each package's newest with a cp312 win_amd64 wheel).
- The day's downloads, sha256 by `sha256sum` apart from `install`: rga-windows-x64-2.15.zip (268,732,151 bytes) 1dd6fc63..., glslang's 82bf434e..., the control's 5f3b0cfb..., each GitHub's asset digest. RGA's zip, listed by range requests before its one download, holds rga.exe at its root (842 MB unpacked); Unbound's zip shaders/ and License.txt at its root; the control's LICENSE.TXT (Apache 2.0), README.md and shaders/, its README crediting no pack.
- The tree pins: each zip unpacked into a scratchpad folder and hashed twice, by a manifest written out by hand and by record.tree_hash, both agreeing; `install`'s own unpack then matched them.

## Choices
Not named by the prompt or the plan, each the reading taken:
- "Refused off its pin" read as the zip's hash and the unpacked tree's: similarity.json pins treeSha256 and files, so an edit under reference/ is caught before `verify similarity` reads it.
- The control's zip kept at reference/<file> beside its folder, as Temurin's archive sits beside its home.
- RGA's zip listed by HTTP range requests, so its 269 MB came down once, by `install`.

## Checks
- Start (10:20 ADT): branch m3 clean at 7dfc2fa; 793 passed; verify docs 35 files, 0 violations.
- Before the last commit: 797 passed; ruff, ruff format and pyright clean; verify docs 35 files, 0 violations. Bytes: AGENTS.md 6,136 of 6,144; platform.md 24,520 and measurement.md 24,553 of 24,576.
- CI green on 776964c, 7aa3e2f, 5237ecb, 32845d9 and 5d87e5b, each watched to its end before the next push.

## Open questions
- D72 (roadmap.md#decisions): what next-generation means for Optilux (the look target, the features back from the not-yet list, a 4K frame-time budget, M6's ratio), the user's, at M4's Plan prompt. D71 set the direction after M3.P01 (user, 2026-10-20); M3 runs as planned.
- D66: the driver at M3.P10's go, as found (32.0.31041.3013) or updated first.
- What the ticks before /tick freeze leave varying at a perf view (M3.P09); spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- Identity moved before M3.P10's freeze: the launch spec (the re-pin) and the harness (install.py sits in the measured closure).
- Margins: AGENTS.md 8 bytes, measurement.md 23, platform.md 56, workflow.md 161; M3.P02's hook line in workflow.md cuts first.
- RGA takes 842 MB under runtime/tools/rga-2.15/.

## Commits and time
- 776964c the tool pins with `install`; 7aa3e2f the stop's handoff; 5237ecb the refreshed spec with its fixture; 32845d9 the dependencies with the lock; 5d87e5b the reference copies; then this handoff.
- 2026-10-20 10:20 to about 11:05 ADT: M3.P01 about 0.8 h against 1.5 h. Tripwire: actuals about 47.7 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.8), the trip at 174.6 h.

## Next
/optilux-next prints M3.P02's prompt: verify similarity, 2 h (L), machine none.
