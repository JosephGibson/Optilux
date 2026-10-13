"""The statistics (docs/measurement.md#verdicts-and-cost-rows and #calibration; docs/plans/m2.md
M2.P07, M2.P10): pure functions over a record's captures and a calibration's null candidates;
nothing is read or written here.

- Bracketing: at a view, in the measured pass (pass 2), every candidate capture sits between two
  baseline captures (the schedule A, then (Ci, A), R rounds). ratio_r = its median GPUBusy over the
  mean of theirs; the view's ratio is the mean of ratio_r over the R rounds; delta = 100 x (ratio -
  1), in %, negative = faster. A round missing, a capture or an adjacent baseline invalid, or a
  candidate left GPU-bound leaves the view unjudged, and the reason is named.
- Thresholds: of n null |delta|s the k-th largest, k = floor(falseRate x (n + 1)) computed in
  exact fractions (20 nulls at 5 %: the largest, which a fresh exchangeable null exceeds with
  probability k / (n + 1) = 1/21), never under thresholdFloorPct; per view, and for the geo-mean
  over the exact view set a verdict uses, from each null candidate's per-view ratios.
- Verdicts on the geo-mean ratio's delta over the verdict's views: accept at or below -threshold,
  reject at or above +threshold, else inconclusive (quick mode: run full). Inconclusive too when a
  view is unjudged, or when the session's A/A twin lies at or beyond its threshold or could not be
  measured on a view. An accept within twice its threshold is confirmed in a second session. Per
  view: the delta, its threshold, both in ms at the baseline's median GPUBusy (the cost row), and
  a view at or beyond its own threshold flagged.
- The twin monitor: more than maxExceed of the last `window` twins beyond the geo-mean threshold
  under one calibration means recalibrating.
- A8 and A11 as plans/m2.md M2.P10 states them (a8_verdict, a11_verdict).
- The survey's readings (plans/m2.md M2.P08): each view's baseline GPU-bound (gpu_bound), its CPU
  floor from the passthrough pack (cpu_floors, D46) and D47's warm-up pass against the measured
  pass (warmup_agreement).
"""

import math
import statistics
from collections.abc import Callable, Iterable
from fractions import Fraction
from typing import Any

# The measured pass; pass 1 is the warm-up pass, never judged (measurement.md#session step 4).
MEASURED_PASS = 2
WARMUP_PASS = 1
# plans/m2.md D47: the warm-up pass is dropped when every view's warm-up capture lies within this
# of the measured pass's first baseline capture, in % of the latter's median GPUBusy.
WARMUP_WITHIN_PCT = 0.5
BASELINE = "baseline"
TWIN = "twin"
CANDIDATE = "candidate"
LEFT_GPU_BOUND = "leftGpuBound"
TIMERS_DROPPED = "timersDropped"
# Stored numbers: deltas and thresholds in % to 1e-4 (a 0.5 % threshold to 0.02 % of itself);
# each round's ratio to 1e-6. Verdicts are taken on the unrounded values.
PLACES = 4
RATIO_PLACES = 6


class StatsError(ValueError):
    """Numbers the statistics cannot judge (too few null candidates, a schedule that is not the
    bracketing one); the message names the fix."""


Value = Callable[[dict], Any]


def busy(capture: dict) -> Any:
    """A capture's median GPUBusy (ms), the primary metric (measurement.md#session step 8)."""
    return capture.get("gpuBusyMs")


def top_level(capture: dict) -> Any:
    """A timers-on capture's median top-level pass sum (ms)."""
    return (capture.get("timers") or {}).get("topLevelMs")


def residual(capture: dict) -> Any:
    """A timers-on capture's A11 residual (ms): the median over its frames of GPUBusy less the
    top-level pass sum."""
    return (capture.get("timers") or {}).get("residualMs")


def finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def positive(value: Any) -> bool:
    return finite(value) and value > 0


def number(value: Any) -> float | None:
    """A finite number as a float, else None."""
    return float(value) if finite(value) else None


def delta_pct(ratio: float) -> float:
    """delta = 100 x (ratio - 1), in %, negative = faster."""
    return 100.0 * (ratio - 1.0)


def geo_mean(ratios: Iterable[float]) -> float:
    """The geometric mean of positive ratios."""
    values = list(ratios)
    if not values or not all(positive(v) for v in values):
        raise StatsError(f"a geo-mean needs positive ratios, got {values}; fix: judge valid views")
    return math.exp(math.fsum(math.log(v) for v in values) / len(values))


# Bracketing.


def view_sequence(captures: list[dict], view: str) -> list[dict]:
    """A view's measured-pass captures in the order they were taken."""
    found = [c for c in captures if c.get("pass") == MEASURED_PASS and c.get("view") == view]
    return sorted(found, key=lambda c: c["index"])


def brackets(captures: list[dict], view: str) -> dict[str, dict[int, tuple]]:
    """Each non-baseline variant's captures at `view` by round, each with the captures just
    before and after it in the view's sequence (its bracketing baselines, or None at an end).
    StatsError for a variant measured twice in one round."""
    seq = view_sequence(captures, view)
    found: dict[str, dict[int, tuple]] = {}
    for i, capture in enumerate(seq):
        if capture.get("role") == BASELINE:
            continue
        before = seq[i - 1] if i > 0 else None
        after = seq[i + 1] if i + 1 < len(seq) else None
        rounds = found.setdefault(capture["variant"], {})
        if capture["round"] in rounds:
            raise StatsError(
                f"{capture['variant']} is measured twice in round {capture['round']} at {view}; "
                "fix: judge a record of one schedule (measurement.md#session step 7)"
            )
        rounds[capture["round"]] = (capture, before, after)
    return found


def checked_rounds(
    triples: dict[int, tuple], rounds: int, timers: bool = False
) -> tuple[list[tuple], str | None]:
    """Rounds 1..`rounds` of one variant at one view, each (capture, before, after); or the
    problem that leaves the view unjudged: a round missing, no baseline on either side, a capture
    or a bracketing baseline invalid, the candidate left GPU-bound; with `timers`, a capture whose
    timers dropped frames."""
    found = []
    for r in range(1, rounds + 1):
        if r not in triples:
            return [], f"round {r} was not measured"
        capture, before, after = triples[r]
        for side, base in (("before", before), ("after", after)):
            if base is None or base.get("role") != BASELINE:
                return [], f"round {r} has no baseline capture {side} #{capture['index']}"
        three = (capture, before, after)
        bad = [c for c in three if c.get("valid") is not True]
        if bad:
            named = ", ".join(
                f"#{c['index']} ({', '.join(c.get('flags') or ['no numbers'])})" for c in bad
            )
            return [], f"round {r}: capture {named} invalid"
        if LEFT_GPU_BOUND in (capture.get("flags") or []):
            return [], f"round {r}: capture #{capture['index']} left GPU-bound"
        dropped = [c["index"] for c in three if TIMERS_DROPPED in (c.get("flags") or [])]
        if timers and dropped:
            return [], f"round {r}: the timers dropped frames in #{dropped}"
        found.append(three)
    return found, None


def view_ratio(triples: dict[int, tuple], rounds: int, value: Value = busy) -> dict:
    """One variant's ratio at one view over rounds 1..`rounds`: each round's capture over the
    mean of its two bracketing baselines, the ratio their mean, the delta; or the problem."""
    found, problem = checked_rounds(triples, rounds)
    if problem:
        return {"problem": problem}
    values = []
    for capture, before, after in found:
        mine, first, second = (value(c) for c in (capture, before, after))
        if not (positive(mine) and positive(first) and positive(second)):
            where = f"round {capture['round']}: #{capture['index']}"
            return {"problem": f"{where} or a bracketing baseline lacks its number"}
        values.append(mine / ((first + second) / 2))
    ratio = math.fsum(values) / len(values)
    return {"ratio": ratio, "delta": delta_pct(ratio), "rounds": values, "problem": None}


def bracketed_difference(triples: dict[int, tuple], rounds: int, value: Value) -> dict:
    """The bracketing as a difference in ms (A11): per round the capture's value less the mean of
    its baselines', the mean over rounds; on captures whose timers kept every frame."""
    found, problem = checked_rounds(triples, rounds, timers=True)
    if problem:
        return {"problem": problem}
    differences = []
    for capture, before, after in found:
        mine, first, second = (value(c) for c in (capture, before, after))
        if not (finite(mine) and finite(first) and finite(second)):
            where = f"round {capture['round']}: #{capture['index']}"
            return {"problem": f"{where} or a bracketing baseline lacks its timers' number"}
        differences.append(mine - (first + second) / 2)
    return {"ms": math.fsum(differences) / len(differences), "problem": None}


def baseline_ms(captures: list[dict], view: str) -> float | None:
    """The baseline's median GPUBusy at a view: the median over its valid measured-pass
    captures (the ms a % threshold or delta converts with)."""
    found = [
        busy(c)
        for c in view_sequence(captures, view)
        if c.get("role") == BASELINE and c.get("valid") is True and positive(busy(c))
    ]
    return statistics.median(found) if found else None


# Thresholds.


def order_level(values: list[float], false_rate: float) -> tuple[float, int]:
    """Of n values the k-th largest, k = floor(false_rate x (n + 1)) in exact arithmetic, and k:
    a fresh exchangeable null exceeds it with probability k / (n + 1) <= false_rate. StatsError
    when k is 0 (n too small for the rate)."""
    rate = Fraction(str(false_rate))
    k = math.floor(rate * (len(values) + 1))
    if k < 1:
        need = math.ceil(1 / rate) - 1
        raise StatsError(
            f"{len(values)} null candidates give no level at a false rate of {false_rate:g} (k = "
            f"floor({false_rate:g} x {len(values) + 1}) = 0); fix: calibrate {need} or more"
        )
    return sorted(values, reverse=True)[k - 1], k


def threshold(abs_deltas: list[float], false_rate: float, floor_pct: float) -> float:
    """measurement.md#calibration's threshold on null |delta|s: the order level, never under the
    floor."""
    level, _ = order_level(abs_deltas, false_rate)
    return max(level, floor_pct)


def thresholds(nulls: list[dict], views: list[str], false_rate: float, floor_pct: float) -> dict:
    """The thresholds a verdict over `views` uses: per view from the nulls' |delta| there, and the
    geo-mean's from each null's geo-mean ratio over exactly those views (the subset's own
    threshold, as `compare` derives it). StatsError for a null without a view's ratio."""
    if not views:
        raise StatsError("no views to judge; fix: name the verdict's views")
    for null in nulls:
        missing = [v for v in views if not positive(null["ratios"].get(v))]
        if missing:
            raise StatsError(
                f"null candidate {null.get('session')}/{null.get('twin')} holds no ratio at "
                f"{', '.join(missing)}; fix: calibrate the views a verdict uses"
            )
    per_view = {
        v: threshold([abs(delta_pct(n["ratios"][v])) for n in nulls], false_rate, floor_pct)
        for v in views
    }
    geo = [abs(delta_pct(geo_mean(n["ratios"][v] for v in views))) for n in nulls]
    _, k = order_level(geo, false_rate)
    return {
        "nulls": len(nulls),
        "k": k,
        "falseRate": false_rate,
        "floorPct": floor_pct,
        "geoMean": threshold(geo, false_rate, floor_pct),
        "perView": per_view,
    }


def calibration_thresholds(calibration: dict) -> dict:
    """The thresholds for a calibration's own views (its stored nulls, rate and floor)."""
    return thresholds(
        calibration["nulls"],
        list(calibration["views"]),
        calibration["falseRate"],
        calibration["floorPct"],
    )


def rounded(found: dict) -> dict:
    """thresholds() as a record holds them."""
    return {
        **found,
        "geoMean": round(found["geoMean"], PLACES),
        "perView": {v: round(t, PLACES) for v, t in found["perView"].items()},
    }


# Verdicts.


def verdict(delta: float, level: float) -> str:
    """measurement.md#verdicts-and-cost-rows: accept at or below -level, reject at or above +level,
    else inconclusive."""
    if delta <= -level:
        return "accept"
    if delta >= level:
        return "reject"
    return "inconclusive"


def judge_variant(
    captures: list[dict], variant: str, views: list[str], rounds: int, found: dict
) -> dict:
    """One variant against the baseline over `views` with the thresholds `found` (thresholds()):
    per view its delta, threshold, the two in ms at the baseline's median GPUBusy, whether it is
    at or beyond its threshold, or why it is unjudged; when every view is judged, the geo-mean
    delta, whether it lies inside the geo-mean threshold and the bare verdict on it (`exact`, the
    unrounded delta, never reaches a record)."""
    rows, ratios, unjudged = [], [], []
    for view in views:
        level = found["perView"][view]
        result = view_ratio(brackets(captures, view).get(variant, {}), rounds)
        base = baseline_ms(captures, view)
        if result["problem"]:
            unjudged.append(view)
            rows.append({"view": view, "threshold": round(level, PLACES), **result})
            continue
        ratios.append(result["ratio"])
        rows.append(
            {
                "view": view,
                "delta": round(result["delta"], PLACES),
                "threshold": round(level, PLACES),
                "beyond": abs(result["delta"]) >= level,
                "deltaMs": None if base is None else round(result["delta"] / 100 * base, PLACES),
                "thresholdMs": None if base is None else round(level / 100 * base, PLACES),
                "baselineMs": base,
                "rounds": [round(x, RATIO_PLACES) for x in result["rounds"]],
            }
        )
    judged: dict[str, Any] = {
        "variant": variant,
        "views": rows,
        "unjudged": unjudged,
        "geoMeanThreshold": round(found["geoMean"], PLACES),
        "geoMeanDelta": None,
        "inside": None,
        "bare": None,
        "exact": None,
        "exactThreshold": found["geoMean"],
    }
    if not unjudged:
        delta = delta_pct(geo_mean(ratios))
        judged.update(
            geoMeanDelta=round(delta, PLACES),
            inside=abs(delta) < found["geoMean"],
            bare=verdict(delta, found["geoMean"]),
            exact=delta,
        )
    return judged


def public(judged: dict) -> dict:
    """A judgment as a record holds it: without the bare verdict and the unrounded numbers."""
    return {k: v for k, v in judged.items() if k not in ("bare", "exact", "exactThreshold")}


def unjudged_text(judged: dict) -> str:
    return "; ".join(f"{r['view']}: {r['problem']}" for r in judged["views"] if r.get("problem"))


def twin_failure(twin: dict) -> str:
    """Why a session is inconclusive on its twin (measurement.md#validity)."""
    if twin["inside"] is None:
        return f"the A/A twin could not be measured ({unjudged_text(twin)}): the session fails"
    return (
        f"the A/A twin lies at {twin['geoMeanDelta']:+.4f} %, at or beyond the geo-mean threshold "
        f"{twin['geoMeanThreshold']:.4f} %: the session is inconclusive"
    )


def candidate_verdict(judged: dict, twin: dict, mode: str) -> dict:
    """A candidate's verdict (measurement.md#verdicts-and-cost-rows): inconclusive naming its
    unjudged views, or the twin's failure; else the bare verdict, an inside one in quick mode
    saying to run full; `confirm` when an accept lies within twice its threshold."""
    found = {**public(judged), "confirm": False}
    if judged["unjudged"]:
        return {**found, "verdict": "inconclusive", "why": f"unjudged: {unjudged_text(judged)}"}
    if twin["inside"] is not True:
        return {**found, "verdict": "inconclusive", "why": twin_failure(twin)}
    bare = judged["bare"]
    why = {
        "accept": "faster beyond the geo-mean threshold",
        "reject": "slower beyond the geo-mean threshold",
        "inconclusive": "inside the geo-mean threshold"
        + (": inconclusive, run full" if mode == "quick" else ""),
    }[bare]
    confirm = bare == "accept" and abs(judged["exact"]) <= 2 * judged["exactThreshold"]
    if confirm:
        why += "; within twice the threshold: re-measure in a second session before it ships"
    return {**found, "verdict": bare, "why": why, "confirm": confirm}


def session_variants(
    captures: list[dict], expected: list[dict] | None = None
) -> tuple[list[str], list[str]]:
    """A session's candidates and twins by id: the record's variants (`expected`, each with its
    id and role) when given, so a variant never measured is judged unjudged rather than left
    out; else those the measured pass holds, in the order first measured."""
    candidates: list[str] = []
    twins: list[str] = []
    if expected is not None:
        found = [(v["id"], v["role"]) for v in expected]
    else:
        ordered = sorted(captures, key=lambda c: c["index"])
        found = [(c["variant"], c.get("role")) for c in ordered if c.get("pass") == MEASURED_PASS]
    for vid, role in found:
        kind = {CANDIDATE: candidates, TWIN: twins}.get(str(role))
        if kind is not None and vid not in kind:
            kind.append(vid)
    return candidates, twins


def session_twin(
    captures: list[dict],
    views: list[str],
    rounds: int,
    found: dict,
    expected: list[dict] | None = None,
) -> dict:
    """The session's one A/A twin judged: `inside` True when its geo-mean delta lies inside the
    threshold, False at or beyond it, None when a view could not be measured (missing = fail).
    StatsError for no twin or more than one."""
    _, twins = session_variants(captures, expected)
    if len(twins) != 1:
        raise StatsError(
            f"a judged session holds one A/A twin, this one {len(twins)}; fix: judge a "
            "measurement or A8 and A11 run (a calibration run's twins are its nulls)"
        )
    return public(judge_variant(captures, twins[0], views, rounds, found))


def judge(
    captures: list[dict], calibration: dict, mode: str, expected: list[dict] | None = None
) -> dict:
    """A measured session's verdicts (run-record.md#fields) over the calibration's views, with
    its thresholds for exactly them: the twin's check, the session's state, each candidate's
    verdict; the variants the record's (`expected`) when given."""
    views, rounds = list(calibration["views"]), calibration["rounds"]
    found = calibration_thresholds(calibration)
    twin = session_twin(captures, views, rounds, found, expected)
    candidates, _ = session_variants(captures, expected)
    return {
        "calibration": calibration["id"],
        "views": views,
        "rounds": rounds,
        "thresholds": rounded(found),
        "twin": twin,
        "session": "ok" if twin["inside"] is True else "inconclusive",
        "why": None if twin["inside"] is True else twin_failure(twin),
        "candidates": [
            candidate_verdict(judge_variant(captures, c, views, rounds, found), twin, mode)
            for c in candidates
        ],
    }


# Calibration.


def nulls_of(
    captures: list[dict],
    views: list[str],
    rounds: int,
    session: str,
    expected: list[dict] | None = None,
    twins_wanted: int | None = None,
) -> dict:
    """A calibration session's null candidates: each twin's ratio per view over every view of the
    mode, the twins the record's variants (`expected`) when given, so a twin never measured is a
    problem rather than left out; or the problems that keep the session from counting (a twin
    unjudged on a view, fewer or more twins than `twins_wanted`)."""
    _, twins = session_variants(captures, expected)
    nulls, problems = [], []
    if not twins:
        problems.append("no twin was measured")
    if twins_wanted is not None and len(twins) != twins_wanted:
        problems.append(f"{len(twins)} twins, the calibration takes {twins_wanted} a session")
    for twin in twins:
        ratios = {}
        for view in views:
            result = view_ratio(brackets(captures, view).get(twin, {}), rounds)
            if result["problem"]:
                problems.append(f"{twin} at {view}: {result['problem']}")
            else:
                ratios[view] = result["ratio"]
        nulls.append({"session": session, "twin": twin, "ratios": ratios})
    return {"nulls": [] if problems else nulls, "problems": problems}


def twin_monitor(beyond: list[bool], window: int, max_exceed: int) -> dict:
    """measurement.md#calibration's monitor over the twins judged under one calibration, oldest
    first: of the last `window`, how many lay at or beyond the geo-mean threshold; recalibrate
    when more than `max_exceed` did (7.5 % odds by chance at 5 % with 20 and 2)."""
    last = beyond[-window:]
    exceeded = sum(1 for b in last if b)
    return {
        "window": window,
        "maxExceed": max_exceed,
        "twins": len(last),
        "exceeded": exceeded,
        "recalibrate": exceeded > max_exceed,
    }


# A8 and A11 (plans/m2.md M2.P10, mod.md#12-acceptance).


def a8_verdict(judged: dict, twin: dict, first: dict | None = None) -> dict:
    """A8 (plans/m2.md M2.P10): the timers-on candidate `judged` (judge_variant) against the
    baseline without them. It passes when the geo-mean delta lies inside its threshold and no view
    lies beyond its own in two sessions with the same sign: a view beyond it in the first session
    is re-measured in a second (11 views at 5 % each would flag one in about 43 % of null
    sessions). `first` is the first session's A8 evidence when this one re-measures it. `pass`
    True or False, or None while the verdict waits: a view to re-measure, or a session
    inconclusive on its twin or an unjudged view."""
    beyond = {r["view"]: r["delta"] for r in judged["views"] if r.get("beyond")}
    evidence: dict[str, Any] = {
        "variant": judged["variant"],
        "geoMeanDelta": judged["geoMeanDelta"],
        "geoMeanThreshold": judged["geoMeanThreshold"],
        "views": {
            r["view"]: {k: r[k] for k in ("delta", "threshold", "beyond", "problem") if k in r}
            for r in judged["views"]
        },
        "beyond": beyond,
    }
    if first is not None:
        evidence["first"] = {k: first.get(k) for k in ("geoMeanDelta", "beyond")}
    if judged["unjudged"]:
        return {"pass": None, **evidence, "pending": f"unjudged: {unjudged_text(judged)}"}
    if twin["inside"] is not True:
        return {"pass": None, **evidence, "pending": twin_failure(twin)}
    if not judged["inside"]:
        why = f"the geo-mean delta {judged['geoMeanDelta']:+.4f} % lies beyond its threshold"
        return {"pass": False, **evidence, "why": why}
    if first is None:
        if beyond:
            names = ", ".join(sorted(beyond))
            return {
                "pass": None,
                **evidence,
                "remeasure": sorted(beyond),
                "pending": f"{names} at or beyond their own threshold: re-measure in a second "
                "session (run spec `remeasures`)",
            }
        return {"pass": True, **evidence, "why": "the geo-mean and every view inside"}
    earlier = first.get("beyond") or {}
    same = {v: d for v, d in beyond.items() if v in earlier and (earlier[v] > 0) == (d > 0)}
    twice = {v: (earlier[v], d) for v, d in same.items()}
    if twice:
        named = ", ".join(f"{v} ({a:+.4f} %, {b:+.4f} %)" for v, (a, b) in sorted(twice.items()))
        return {"pass": False, **evidence, "why": f"beyond in both sessions, same sign: {named}"}
    return {
        "pass": True,
        **evidence,
        "why": "the geo-mean inside, and no view beyond its threshold in both sessions",
    }


def a11_verdict(
    captures: list[dict],
    views: list[str],
    rounds: int,
    found: dict,
    twin: dict,
    expected: list[dict] | None = None,
):
    """A11 (plans/m2.md M2.P10, mod.md#12-acceptance), every variant timed, on GPU-bound captures
    whose timers kept every frame: per view the threshold in ms (the view's threshold x the
    baseline's median GPUBusy); the residual (GPUBusy less the pass sum) of each variant,
    bracketed against the baseline's (the baseline's at 0), moves less than it between any two
    variants; each candidate's (shadows off's) delta from the timers' top-level sum matches its
    GPUBusy delta within it, both bracketed in ms; and the known positive shows: a candidate's
    GPUBusy delta at or beyond the threshold at some view (else nothing was there for the timers
    to match: identical variants, or timers reading zero, would agree). `pass` False on a failure
    measured on valid captures; None while the verdict waits (the session inconclusive on its
    twin, a view unjudged, no measured effect)."""
    candidates, twins = session_variants(captures, expected)
    rows, unjudged, failed, effect = [], [], [], []
    for view in views:
        level = found["perView"][view]
        base = baseline_ms(captures, view)
        row: dict[str, Any] = {"view": view, "threshold": round(level, PLACES)}
        rows.append(row)
        if base is None:
            unjudged.append(f"{view}: no valid baseline capture")
            continue
        limit = level / 100 * base
        row["thresholdMs"] = round(limit, PLACES)
        moved, matched = {}, {}
        held = brackets(captures, view)
        for variant in [*candidates, *twins]:
            triples = held.get(variant, {})
            res = bracketed_difference(triples, rounds, residual)
            if res["problem"]:
                unjudged.append(f"{view}: {variant}: {res['problem']}")
                continue
            moved[variant] = res["ms"]
            if variant not in candidates:
                continue
            timed = bracketed_difference(triples, rounds, top_level)
            gpu = bracketed_difference(triples, rounds, busy)
            if timed["problem"] or gpu["problem"]:
                unjudged.append(f"{view}: {variant}: {timed['problem'] or gpu['problem']}")
                continue
            gap = timed["ms"] - gpu["ms"]
            if abs(gpu["ms"]) >= limit:
                effect.append(f"{view}: {variant}")
            matched[variant] = {
                "timersMs": round(timed["ms"], PLACES),
                "gpuBusyMs": round(gpu["ms"], PLACES),
                "differenceMs": round(gap, PLACES),
            }
            if abs(gap) >= limit:
                failed.append(f"{view}: {variant}'s timers delta is {gap:+.4f} ms off GPUBusy's")
        if moved:  # every pair of variants, the baseline's residual at 0
            spread = max(0.0, *moved.values()) - min(0.0, *moved.values())
            if spread >= limit:
                named = ", ".join(f"{v} {ms:+.4f}" for v, ms in moved.items())
                failed.append(f"{view}: the residual spreads {spread:.4f} ms ({named})")
        row["residualMovesMs"] = {v: round(ms, PLACES) for v, ms in moved.items()}
        row["deltaFromTimers"] = matched
    evidence = {"views": rows, "failed": failed, "unjudged": unjudged, "effect": effect}
    if twin["inside"] is not True:
        return {"pass": None, **evidence, "pending": twin_failure(twin)}
    if failed:
        return {"pass": False, **evidence, "why": "; ".join(failed)}
    if unjudged:
        return {"pass": None, **evidence, "pending": "unjudged: " + "; ".join(unjudged)}
    if not effect:
        why = "no candidate's GPUBusy moved beyond a view's threshold: no effect for the timers"
        return {"pass": None, **evidence, "pending": why}
    return {"pass": True, **evidence, "why": "every residual and timers delta inside"}


def invalid_named(captures: list[dict]) -> str:
    return ", ".join(
        f"#{c['index']} ({', '.join(c.get('flags') or ['no numbers'])})" for c in captures
    )


def gpu_bound(captures: list[dict], views: list[str], minimum: float) -> dict:
    """measurement.md#validity on the baseline, per view of `views` (the mode's: one never
    measured is named, never left out) over both passes: each baseline capture's GPUBusy over
    FrameTime (median over median) against `minimum` (suite.json validity.gpuBoundMin), the
    lowest and the median; `bound` when none is under it or without the ratio, `valid` when every
    one is valid (the invalid named with their flags); a view without a baseline capture is
    neither. Over all views: `bound` and `valid` when every view's is."""
    rows = {}
    for view in views:
        base = sorted(
            (c for c in captures if c["view"] == view and c.get("role") == BASELINE),
            key=lambda c: c["index"],
        )
        ratios = [number(c.get("gpuBusyOverFrameTime")) for c in base]
        known = [r for r in ratios if r is not None]
        below = [c["index"] for c, r in zip(base, ratios, strict=True) if r is None or r < minimum]
        bad = [c for c in base if c.get("valid") is not True]
        rows[view] = {
            "captures": len(base),
            "lowest": round(min(known), PLACES) if known else None,
            "median": round(statistics.median(known), PLACES) if known else None,
            "below": below,
            "invalid": invalid_named(bad),
            "bound": bool(base) and not below,
            "valid": bool(base) and not bad,
        }
    every = bool(rows)
    return {
        "minimum": minimum,
        "views": rows,
        "bound": every and all(r["bound"] for r in rows.values()),
        "valid": every and all(r["valid"] for r in rows.values()),
    }


def cpu_floors(captures: list[dict], views: list[str], variant: str) -> dict:
    """The CPU floor per view of `views` (measurement.md#validity, plans/m2.md D46): over the
    passthrough variant's measured-pass captures at the view, all valid and all left GPU-bound
    (CPU-limited: a GPU-bound one's FrameTime only bounds the floor from above, kept as
    `upperBoundMs`), the median FrameTime (ms), beside the median GPULatency in ms and in frames
    (over the FrameTime; roadmap.md F10), GPUBusy and GPUBusy over FrameTime. A view where it is
    missing, invalid, without its numbers or GPU-bound has no floor and names why; `complete` when
    every view has one."""
    keys = ("frameTimeMs", "gpuLatencyMs", "gpuBusyMs", "gpuBusyOverFrameTime")
    rows: dict[str, dict] = {}
    for view in views:
        mine = [c for c in view_sequence(captures, view) if c.get("variant") == variant]
        bad = [c for c in mine if c.get("valid") is not True]
        given = {key: [number(c.get(key)) for c in mine] for key in keys}
        values = {
            key: [v for v in found if v is not None and v > 0] for key, found in given.items()
        }
        row: dict = {"captures": [c["index"] for c in mine], "floorMs": None}
        rows[view] = row
        if not mine:
            row["problem"] = f"{variant} was not measured in the measured pass"
            continue
        if bad:
            row["problem"] = f"capture {invalid_named(bad)} invalid"
            continue
        if any(len(found) != len(mine) for found in values.values()):
            row["problem"] = f"a capture of {variant} lacks a number"
            continue
        median = {key: statistics.median(found) for key, found in values.items()}
        bound = [c["index"] for c in mine if LEFT_GPU_BOUND not in (c.get("flags") or [])]
        row.update(
            gpuLatencyMs=round(median["gpuLatencyMs"], PLACES),
            gpuLatencyFrames=round(median["gpuLatencyMs"] / median["frameTimeMs"], PLACES),
            gpuBusyMs=round(median["gpuBusyMs"], PLACES),
            gpuBusyOverFrameTime=round(median["gpuBusyOverFrameTime"], PLACES),
            problem=None,
        )
        if bound:
            row["upperBoundMs"] = round(median["frameTimeMs"], PLACES)
            row["problem"] = f"capture {bound} GPU-bound: its FrameTime bounds the floor from above"
        else:
            row["floorMs"] = round(median["frameTimeMs"], PLACES)
    complete = bool(rows) and all(r["problem"] is None for r in rows.values())
    return {"variant": variant, "views": rows, "complete": complete}


def warmup_agreement(
    captures: list[dict], views: list[str], within_pct: float = WARMUP_WITHIN_PCT
) -> dict:
    """plans/m2.md D47, per view of `views`: the warm-up pass's baseline capture against the
    measured pass's first baseline capture, the same place in a visit (the view reached, the
    baseline reloaded); the delta of their median GPUBusy in % of the measured one's, beside the
    measured pass's baseline spread (largest less smallest over their mean, in %), the noise it
    meets. Both settles are kept: at a launch's first view the two passes can arrive from
    different dimensions, so `sameSettle` false names a pair that differs in its settle and its
    dimension change too, judged all the same. `drop` true when every view's |delta| lies within
    `within_pct`, false when one lies beyond it, None when a view lacks either capture valid with
    its number (undecided, never dropped)."""
    rows: dict[str, dict] = {}
    for view in views:
        warm = [
            c
            for c in captures
            if c["view"] == view and c.get("pass") == WARMUP_PASS and c.get("role") == BASELINE
        ]
        measured = [c for c in view_sequence(captures, view) if c.get("role") == BASELINE]
        if len(warm) != 1 or not measured:
            rows[view] = {"problem": f"{len(warm)} warm-up and {len(measured)} measured baselines"}
            continue
        pair = (warm[0], measured[0])
        bad = [c for c in pair if c.get("valid") is not True or not positive(busy(c))]
        if bad:
            rows[view] = {"problem": f"capture {invalid_named(bad)} invalid or without GPUBusy"}
            continue
        usable = [busy(c) for c in measured if c.get("valid") is True and positive(busy(c))]
        delta = delta_pct(busy(pair[0]) / busy(pair[1]))
        rows[view] = {
            "warmup": pair[0]["index"],
            "measured": pair[1]["index"],
            "warmupMs": busy(pair[0]),
            "measuredMs": busy(pair[1]),
            "warmupSettleS": pair[0].get("settleS"),
            "measuredSettleS": pair[1].get("settleS"),
            "sameSettle": pair[0].get("settleS") == pair[1].get("settleS"),
            "deltaPct": round(delta, PLACES),
            "spreadPct": round(
                100 * (max(usable) - min(usable)) / statistics.fmean(usable), PLACES
            ),
            "within": abs(delta) <= within_pct,
            "problem": None,
        }
    undecided = not rows or any(r["problem"] is not None for r in rows.values())
    drop = None if undecided else all(r["within"] for r in rows.values())
    return {"withinPct": within_pct, "views": rows, "drop": drop}


def judge_items(
    captures: list[dict],
    calibration: dict,
    items: Iterable[str],
    timed: str | None,
    first: dict | None = None,
    expected: list[dict] | None = None,
) -> list[dict]:
    """A measured acceptance run's entries (item, pass, evidence) judged by the calibration: A8
    on the timers-on candidate `timed` (its re-measured first session's evidence `first`), A11
    on every variant (the record's, `expected`, when given)."""
    views, rounds = list(calibration["views"]), calibration["rounds"]
    found = calibration_thresholds(calibration)
    twin = session_twin(captures, views, rounds, found, expected)
    entries = []
    for item in items:
        if item == "A8":
            if timed is None:
                raise StatsError("A8 needs its timers-on candidate; fix: name one in the spec")
            judged = judge_variant(captures, timed, views, rounds, found)
            result = a8_verdict(judged, twin, first)
        else:
            result = a11_verdict(captures, views, rounds, found, twin, expected)
        passed = result.pop("pass")
        entries.append(
            {
                "item": item,
                "pass": passed,
                "evidence": {**result, "calibration": calibration["id"], "twin": twin["inside"]},
            }
        )
    return entries
