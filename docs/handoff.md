# Handoff
Status: the latest stop: M3's plan phase, the plan approved by the user, its prompt set written, and what the first phase starts from.

## Contents
Outcome · What changed · Premises · Review · Checks · Open questions · Left alone · Weak points · Commits and time · Next

## Outcome
Last phase: M3.P00
- docs/plans/m3.md approved by the user on 2026-10-18 (its section 10): eleven phases, M3.P01 to M3.P11, 25 h agent, about 146 launches and about 5 h of calibration sessions apart (its sections 5 and 8); decisions D54-D70, the user's answers of 2026-10-17 in D66-D68.
- docs/prompts/m3.md holds one prompt per phase and Resume; `optilux status` prints M3.P01's. VERSION 0.4.0 with CHANGELOG.md's `## 0.4.0 Visual loop`; M2 closed in the roadmap (one line), its three open rows for M3 now F25-F27. No game launch, nothing under runtime/, no system setting.

## What changed
- docs/plans/m3.md: premises P1-P23 read at their sources on 2026-10-17 (Premises below).
- docs/roadmap.md: M2's section one line, M2 phases gone (M2 had no QA table; its handoffs' rows for M3 became F25-F27: the 1 ms row loss, the quick slot bias, the driver's reload leak); the M3 visual loop and M3 phases sections from the plan; F17, F18 and F25-F27 citing their phases; Estimates with M2's actual and M3's 25 h.
- docs/prompts/m3.md: in the form of prompts/standing.md#phase-prompts.
- VERSION and CHANGELOG.md: 0.4.0 and its entry's goal.

## Premises
- The pinned files were fetched into the scratchpad, never runtime/: the 26.3 client jar (sha1 checked), Iris 1.11.7, Unbound r5.9.3 and Faithful 64x (sha512 checked) and the bench Temurin (sha256 checked) for `javap`.
- Read there: the .mcmeta lookup from the top pack down and one-frame sprites static (D62); Iris re-reading enableDebugOptions at every reload (D60); the core-profile route and the program fallbacks (D56); the End's own clock, clouds on game time, end crystals' random spin, Peaceful refusing monsters, the beacon's beam built in its tick (P22); Unbound's iso switches (P15).
- The researcher agent read glslang's and RGA's releases, PyPI, the control pack and winnowing; each pin, digest, license and wheel spot-checked with `gh api` and PyPI. Photon credits Complementary, so Wisdom Shaders is the control (P9).

## Review
- Two reviewer-agent passes on the draft, the facts against the repository and the phases' feasibility: 40 findings (3 high, 11 medium, 26 low, some shared), each read at its source and folded in, none rejected (plans/m3.md section 10). Two more found while verifying them: clouds follow game time and end crystals start with a random spin; BENCH_DETERMINISTIC discards both.
- /critique (gpt-6.1-sol, xhigh, artifact mode, 257 s): four medium findings, each read at its source and folded in: `run`'s L0 gate bound to the zip (M3.P04); a match extended over the tokens, `#define` bodies kept, the staged tree checked (M3.P02). Its raw output stays in the session's scratchpad.
- The reviewer agent on the prompt set and the roadmap's expansion against the plan and standing.md: 17 findings (4 medium, 13 low), each read at its source and folded in: M3.P10's trigger and exit as the plan's, its moved cap reviewed and listed; the Resume as standing.md's, without M2's record-instead-of-rerun exception; M3.P06's record, tiers and refusals in its steps; the roadmap's exits as the plan's.

## Checks
- Start (2026-10-17 05:08 ADT): branch m3 clean at effdecf, origin/main's tip and v0.3.0; 793 passed; verify docs 0 violations; `optilux status`'s one problem m3 not on origin.
- Before the commits: 793 passed; ruff clean; verify docs 35 files, 0 violations: the plan 39,186 of 40,960 bytes, the prompt set 39,519, the roadmap 29,969. The prompt set parses into M3.P01 to M3.P11 and Resume; every phase's estimate line parses (P01 M, P02-P05 L, P06 XL, P07-P09 L, P10 and P11 M).

## Open questions
- D66: the driver at M3.P10's go: as found (32.0.31041.3013) or updated by the user first, then one budget run.
- What else the ticks before /tick freeze leave varying at a perf view (the entities view's mobs, an end gateway at end_city): M3.P09's two sessions say; section 7 gives one fix.
- Spider eyes need a monster, which the Peaceful world refuses: the world's difficulty is the user's, for M4's coverage list.
- RGA's zip holding rga.exe and its command line printing a version: inferred from its sources, M3.P01 sees it.
- Carried from M2: underwater's untimed work and A11's guard (M4), `compare` refusing a failed A8 or A11 record (the user's call), NoMachine and pid 2228, forest_noon's lower level, the timers' unmatched pops; M2.P09's and M2.P08's lists (git 2927963's handoff).

## Left alone
- roadmap.md's M0 phases section, older than this phase.
- measurement.md#session step 9 keeps its every-release cost row until M3.P11 notes D67 there.

## Weak points
- Margins: the plan 1,774 bytes, the prompt set 1,441; AGENTS.md 8, measurement.md 20, platform.md 42, mod.md 52 and workflow.md 161, which M3's phases cut before they add (their prompts say so).
- The determinism exit rests on everything a session's unfrozen ticks leave varying being found; ALC's End terrain shift stayed undiagnosed (lessons.md#determinism).
- A5's two-record judgement and `optilux@<ref>` are new paths, met first in M3.P03 and M3.P09.

## Commits and time
- This phase: VERSION and the CHANGELOG entry; M2 closed in the roadmap with F25-F27; the plan with the roadmap's expansion; the prompt set; this handoff; each pushed alone, its CI watched to the end before the next.
- 2026-10-17 05:08-06:35 ADT (the premises, the draft, the reviews, the critique), then the wait for the approval, not counted; 2026-10-18 01:47 to about 02:20 after it. M3.P00 about 2.0 h against the Plan prompt's 1 h.
- Tripwire: M0-M3 summed 87.3 h, the trip at 174.6 h; actuals about 46.9 h (M0 3.3, M1 20.3, M2 about 21.3, M3.P00 about 2.0).

## Next
/optilux-next prints M3.P01's prompt: Tools and reference copies, 1.5 h (M), downloads.
