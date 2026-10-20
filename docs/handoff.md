# Handoff
Status: the latest stop: M3.P02 done, `verify similarity` and its pre-commit hook built with the threshold set from both controls, and what M3.P03 starts from.

## Contents
Outcome · What changed · Review · Choices · Checks · Open questions · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P02
- The exit holds, shown on 2026-10-20 between 11:55 and 12:00 ADT on the code of 650be15:
  - `uv run optilux verify similarity --controls`: "self: 129 of 129 files of 72 tokens or more flagged"; "control: longest 71 tokens, reference/wisdom-shaders-v3-build3300/shaders/CompositeUniform.glsl.frag:17-40 matches reference/complementary-unbound-r5.9.3/shaders/lib/uniforms.glsl:73-92 (71 tokens)"; 0 problems.
  - A planted run of 72 tokens cut verbatim from Unbound (lib/util/spaceConversion.glsl lines 24-35) was staged in a throwaway repo in the scratchpad, its core.hooksPath this checkout's .githooks/, so the hook read this checkout's reference/. `git commit` exited 1: "pre-commit: similarity: shader/shaders/planted.fsh:1-12 matches reference/complementary-unbound-r5.9.3/shaders/lib/util/spaceConversion.glsl:24-35 (72 tokens), t 72; fix: write it fresh in your own structure (docs/shader.md#policy)", and the repo had no commit. The same run cut to 71 tokens gave no finding (`hooks.similarity_findings` and `hooks.pre_commit`, called without a commit). The repo was then deleted, and nothing from Unbound was committed anywhere.
  - `uv run optilux verify similarity`: "0 GLSL files under shader/ (0 tokens) against 408 of reference/complementary-unbound-r5.9.3/ (k 20, t 72): 0 matches of 72 tokens or more", exit 0. shader/ still holds only the placeholder's shaders.properties.
- No game launch. Nothing written under runtime/. reference/ was only read, and never by a third-party model (the reviewer agent was told not to read it, and did not). No system setting. Nothing deferred.

## What changed
- optilux/similarity.py, which is pure:
  - Normalized tokens: comments, whitespace and directives dropped. A `#define`'s replacement is kept without its name and parameters, unless it is a value (Review 5). Identifiers become ID, numbers NUM, true and false BOOL; keywords and punctuators are kept.
  - Karp-Rabin hashes of k-grams, winnowed (each window's rightmost minimum).
  - `matches()` checks each shared fingerprint token by token and extends it over both sequences to its maximal run. Fingerprints on one run give one match (a pair inside a run already found on its diagonal is skipped).
  - GLSL files are known by suffix: Iris's stage suffixes, .glsl and glslang's stage suffixes.
- `optilux verify similarity [--controls] [--json]` (optilux/verbs/verify.py):
  - Reads the studied copy only after its tree hash matches its pin.
  - Exit 1 on a run of t tokens or more, naming both files and their lines.
  - `--controls` recomputes both figures. It fails when a figure breaks the rule or differs from config/similarity.json.
- config/similarity.json gains k 20, t 72 (each with its why) and `controls` (self 129 of 129; control longest 71 and where).
- The pre-commit hook (optilux/hooks.py):
  - Runs when shader/ or config/similarity.json is staged, typechanges included.
  - Reads both from the index (GIT_INDEX_FILE inside a commit), and checks them against this checkout's copy.
  - A missing copy is refused, naming `optilux install`.
- Tests: tests/test_similarity.py (22 tests); tests/test_hooks.py (+6 tests); similarity_home in tests/conftest.py.
- Docs: shader.md#policy, the method, threshold, controls, pitfall and hook as built; workflow.md#hooks-and-guards, the pre-commit line (cut first: the commit-msg rule's examples, which Git repeats; margin 161 -> 199); design.md's verify row; CHANGELOG.md's 0.4.0 entry, one bullet.

## Review
The reviewer agent read similarity.py, the verb, the hook and the tests for correctness, without reference/. It raised 9 findings (1 medium, 8 low). It found no copy of t tokens or more that passes and no shorter run that is flagged. Each finding was read at its source:
- Fixed:
  - 1 (medium): the hook took k, t and the pin from the working tree. It now reads the index's config/similarity.json.
  - 2: a commit staging only the config ran no check. It now does.
  - 3: a typechange under shader/ ran no check. `staged()` now takes ACMRT.
  - 5, confirmed: Unbound's lib/common.glsl gave 111 NUM in a row from its option defines, so a fresh options list of 72 values would fail. A value replacement (one token, or a signed number) now gives no token. Unbound's longest NUM run is now 1, and the controls are unchanged (129 of 129, 71).
  - 6: a link under reference/ or a pin without its fields escaped as a traceback. Both are now refused with their fix.
  - 8, partly: the staged-texts test covers a path with a space and non-ASCII characters, and its comment says GIT_INDEX_FILE is set by hand. The committed-threshold test's docstring says it checks the recorded figures only.
- Reported, no change:
  - 4: files with another suffix (an `.inc` include, properties, lang) are not read. Optilux names its GLSL by stage suffix or .glsl, as shader.md#policy now says.
  - 7: the positive control is close to trivial, since a file always matches itself. The w = t - k + 1 boundary is proven by the fixture tests, and live by the 71-and-72 pair above.
  - 9 (unverified): commits made by rebase, cherry-pick or merge may skip pre-commit. This workflow makes none (PRs are rebase-merged on GitHub).

## Choices
Neither the prompt nor the plan names these. Each is the reading taken:
- t = 72 is the control's longest run plus one, with no margin: the strictest check D55 allows. A false positive costs a rewrite of a declaration list, and is named with both files and their lines.
- k = 20 only sets the window (w 53), because t alone decides. The control shares runs under 20 tokens by the thousand (34,247 of its 34,746 runs of 10 or more).
- The control's figure is exact: it is computed over every k-gram (w = 1), not the winnowed set.
- The hook checks the index's shader/ tree as a whole, not only the changed files, against this checkout's reference/ (`home`).
- Value-only `#define`s are dropped (Review 5). This narrows the plan's "a `#define`'s replacement kept" to replacements that hold code.
- `--controls` is a flag of the verb, so the figures can be reproduced.

## Checks
- Start (11:24 ADT): branch m3 clean at 7f92a93; 797 passed; verify docs 35 files, 0 violations.
- Before each commit: 825 passed; ruff, ruff format and pyright clean; verify docs 0 violations; verify records 223 records, 0 violations. Bytes: workflow.md 24,377, shader.md 11,312, design.md 17,879.
- CI green on 474260f and 650be15, each watched to its end before the next push.

## Open questions
- D72 (roadmap.md#decisions): what next-generation means for Optilux. That is the user's call, at M4's Plan prompt.
- D66: the driver at M3.P10's go, as found (32.0.31041.3013) or updated first.
- What the ticks before /tick freeze leave varying at a perf view (M3.P09); spider eyes and the world's difficulty (M4); M2's carried list (git 7dfc2fa's handoff).

## Weak points
- The negative control is one pack. Its longest runs are repetitions every pack writes: 18 sampler2D uniforms in a row, offset tables, runs of constants. Optilux's own declaration lists could reach 72 tokens. The fix is writing them another way (shader.md#policy, Pitfall).
- No live commit has gone through `commit -a` or `commit <path>`. The temporary index is tested with GIT_INDEX_FILE set by hand.
- Margins: AGENTS.md 8 bytes; measurement.md 23; platform.md 56; workflow.md 199.

## Commits and time
- 474260f: the similarity core, the verb, the config and the tests. 650be15: the hook with its tests. Then this handoff.
- 2026-10-20 11:24 to about 12:10 ADT: M3.P02 took about 0.8 h against 2 h. Tripwire: actuals about 48.5 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0, M3.P01 about 0.8, M3.P02 about 0.8); the trip is at 174.6 h.

## Next
/optilux-next prints M3.P03's prompt: the hello pack and pipeline spec v0, 2.5 h (L), 1 launch, with the machine left alone (A2 sends input). From here, `verify similarity` passes before each shader commit, by the hook.
