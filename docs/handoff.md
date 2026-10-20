# Handoff
Status: the latest stop: M3.P01 stopped at plans/m3.md section 7's launch-spec stop, the tool pins committed and the rest of the phase waiting on the user's re-pin.

## Contents
Outcome · What changed · Premises · The stop · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P00
- M3.P01 stopped at plans/m3.md section 7, "a launch spec that differs (the user re-pins)": the phase's first `uv run optilux install` (2026-10-20 10:30 ADT) fetched and checked the new tools, then exited 1, as Mojang republished 26.3's version JSON on 2026-10-13 and the spec differs in four facts (The stop).
- Done: step 1, config/tools.json's glslang and RGA with `install` unpacking zipped tools, committed and pushed. Not done: step 2 (the image dependencies), step 3 (config/similarity.json and the reference copies), the exit and its handoff. No game launch; runtime/ written by `install` alone; reference/ not yet made; no system setting.

## What changed
- config/tools.json: glslang 16.6.0 and RGA 2.15, each with version, file, sha256, source, `unpack` (its folder under runtime/tools/), `exe`, why and sha256Why; `later` keeps RenderDoc alone (M4).
- optilux/verbs/install.py: `unpack`, one .part-then-rename helper for Temurin and the tools; a zip with `unpack` unpacked when its folder lacks `exe`, refused when the unpack lacks it; the report names the exe. tests/test_install.py: a zip tool in the fake world and a test of its refusals and re-unpack.
- docs/offline.md#tools: the pins, RGA 2.15's path and version; Shadesmith unused (D58), its Verify row gone. docs/platform.md#install-and-launch: the tools line; the cross-check bullet folded into Platform change step 2 (S5 holds its evidence). CHANGELOG.md's 0.4.0 entry: the tools.

## Premises
- Read on 2026-10-20 with `gh api` and PyPI's JSON, each as plans/m3.md states it: P6 (glslang 16.6.0, digest 82bf434e...), P7 (RGA 2.15, rga-windows-x64-2.15.zip, 268,732,151 bytes, digest 1dd6fc63...), P8 (pillow 13.0.0, numpy 2.5.4, flip-evaluator 1.7, scikit-image 0.26.0, scipy 1.18.1, each with a cp312 win_amd64 wheel), P9 (Wisdom Shaders Build3300, Apache-2.0, not a fork, digest 5f3b0cfb...).
- The day's downloads: glslang's and the control's zips into the scratchpad, each sha256 equal to GitHub's digest; RGA's by `install` alone, sha256-equal to its pin. Layouts: RGA's zip (listed by range requests first) holds rga.exe at its root, 881 MB unpacked; glslang's bin/glslang.exe; Unbound's shaders/ and License.txt at its root; the control's LICENSE.TXT, README.md and shaders/.
- `glslang --version`: "Glslang Version: 11:16.6.0"; `rga --version`: "Radeon GPU Analyzer Version: 2.15.0.30 (10/02/2026)", which answers the last handoff's question on RGA.

## The stop
- `install`'s four facts: sources.versionJson.url and .sha1 702fe591... -> 11f1aefe...; assetIndex.sha1 and .url 1e4e4a68... -> e787e8af.... Mojang's manifest: 26.3's entry time 2026-10-13T06:43:38Z, still the newest release.
- A key-by-key diff of both JSONs and both indexes (the session's scratchpad, specdiff/): only asset index 34 moved (totalSize 483,888,065 -> 484,829,952); 142 of its 5,147 objects changed, all under minecraft/lang/, none added or removed. Client jar, libraries, arguments, logging and mainClass unchanged. The bench reads lang:en_us (options.txt), which ships in the client jar (assets/minecraft/lang/en_us.json), not in the index.
- `install` put the new JSON, index and language files under runtime/mc-26.3/ (146 downloads), as it is built to; config/platforms/mc-26.3.launch.json is unchanged. Until it is re-pinned, `launch` refuses (the asset index differs from the spec) and every `install` exits 1.
- Recommendation, as D20 in M1: `uv run optilux install --refresh` and the new spec committed alone. Nothing the bench loads moved; the spec's hash is identity, so M2's calibrations stop matching, but M3.P10 recalibrates on a new identity anyway (resourcePacks; harness, as install.py is in the measured closure and changed here). Keeping the old index pinned keeps a file Mojang replaced, and every install fails on it.

## Checks
- Start (2026-10-20 10:20 ADT): branch m3 clean at 7dfc2fa; 793 passed; verify docs 35 files, 0 violations.
- Before the commit: 794 passed; ruff and pyright clean; verify docs 35 files, 0 violations; platform.md 24,478 of 24,576 bytes. CI on 776964c green.

## Open questions
- The re-pin (The stop): the user's.
- Carried: D66, the driver at M3.P10's go; what the ticks before /tick freeze leave varying (M3.P09); spider eyes and the world's difficulty (M4); M2's list (git 7dfc2fa's handoff).

## Weak points
- install.py sits in the measured closure (session.py imports it): this phase moves the harness identity, before M3.P10's freeze.
- Margins: platform.md 98 bytes, AGENTS.md 8; step 3's reference lines cut first.
- RGA takes 881 MB under runtime/tools/rga-2.15/.

## Commits and time
- 776964c: the tool pins with `install`; then this handoff.
- 2026-10-20 10:20 to about 10:55 ADT: about 0.6 h of M3.P01's 1.5 h. Tripwire: actuals about 47.5 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.6 so far), the trip at 174.6 h.

## Next
The user's call on the re-pin; then the Resume prompt (docs/prompts/m3.md), which carries on from M3.P01's step 2.
