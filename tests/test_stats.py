"""The statistics (optilux/stats.py) on fixed numbers: the bracketing, the order statistic, the
thresholds per view and per view set, the verdicts and their inconclusive cases, the twin monitor,
and A8's and A11's verdicts as plans/m2.md M2.P10 states them, on fixture captures."""

import math

import pytest

from optilux import stats


def capture(index, view, variant, role, rnd, busy, flags=(), timers=None, pass_no=2) -> dict:
    """A capture as a record holds it: valid unless an invalidating flag is given."""
    invalid = {"cut", "fewFrames", "notNumbers", "halves", "presentMode", "cpuLimited", "event"}
    found = {
        "index": index,
        "pass": pass_no,
        "view": view,
        "variant": variant,
        "role": role,
        "round": rnd,
        "gpuBusyMs": busy,
        "flags": list(flags),
        "valid": not invalid & set(flags),
    }
    if timers is not None:
        found["timers"] = {"topLevelMs": timers[0], "residualMs": timers[1]}
    return found


def view_captures(view: str, base: list, others: list, rounds: int, start: int = 1) -> list[dict]:
    """measurement.md#session step 7's schedule at one view: A, then (Ci, A) for each other
    variant in order, R rounds. `base` gives the baselines' GPUBusy in order (or (busy, flags,
    timers) tuples), `others` (variant, role, [one value per round]) likewise."""
    found = []
    order = [("baseline", "baseline", 1, 0)]
    for r in range(1, rounds + 1):
        for n, (variant, role, _) in enumerate(others):
            order += [(variant, role, r, n), ("baseline", "baseline", r, None)]
    bases = iter(base)
    for i, (variant, role, rnd, n) in enumerate(order):
        value = next(bases) if role == "baseline" else others[n][2][rnd - 1]
        busy, flags, timers = value if isinstance(value, tuple) else (value, (), None)
        found.append(capture(start + i, view, variant, role, rnd, busy, flags, timers))
    return found


# Bracketing.


def test_a_candidate_is_bracketed_by_the_mean_of_its_two_adjacent_baselines() -> None:
    """ratio_r = Ci over the mean of its adjacent A captures; ratio = their mean over R rounds."""
    seq = view_captures(
        "v1",
        [10.0, 10.0, 10.0, 10.2, 10.0],
        [("cand", "candidate", [9.0, 9.1]), ("twin", "twin", [10.0, 10.1])],
        rounds=2,
    )
    found = stats.brackets(seq, "v1")
    cand = stats.view_ratio(found["cand"], 2)
    assert cand["rounds"] == [9.0 / 10.0, 9.1 / 10.1]
    assert cand["ratio"] == pytest.approx((0.9 + 9.1 / 10.1) / 2)
    assert cand["delta"] == pytest.approx(100 * ((0.9 + 9.1 / 10.1) / 2 - 1))
    twin = stats.view_ratio(found["twin"], 2)
    assert twin["rounds"] == [10.0 / 10.0, 10.1 / 10.1] and twin["delta"] == pytest.approx(0.0)


def test_the_warm_up_pass_is_never_bracketed() -> None:
    warm = [capture(1, "v1", "baseline", "baseline", 0, 7.0, pass_no=1)]
    seq = warm + view_captures("v1", [10.0, 10.0], [("twin", "twin", [10.5])], 1, start=2)
    assert stats.view_ratio(stats.brackets(seq, "v1")["twin"], 1)["ratio"] == 1.05


UNJUDGED = [
    # A round never measured: missing = fail.
    (None, {}, "round 2 was not measured"),
    # The candidate's own capture invalid.
    (4, {"valid": False, "flags": ["halves"]}, "#4 (halves) invalid"),
    # A Ci capture whose adjacent A is invalid is invalid too (measurement.md).
    (5, {"valid": False, "flags": ["cut"]}, "#5 (cut) invalid"),
    # Left GPU-bound: valid for the record, indicative for a verdict.
    (2, {"flags": ["leftGpuBound"]}, "left GPU-bound"),
    # A capture without its numbers.
    (3, {"gpuBusyMs": None}, "lacks its number"),
]


@pytest.mark.parametrize(("index", "change", "says"), UNJUDGED)
def test_a_view_is_unjudged_and_says_why(index: int | None, change: dict, says: str) -> None:
    seq = view_captures("v1", [10.0] * 3, [("cand", "candidate", [9.0, 9.0])], rounds=2)
    seq = seq[:3] if index is None else [{**c, **change} if c["index"] == index else c for c in seq]
    found = stats.view_ratio(stats.brackets(seq, "v1").get("cand", {}), 2)
    assert says in found["problem"]


def test_a_variant_measured_twice_in_a_round_is_no_schedule() -> None:
    seq = view_captures("v1", [10.0] * 3, [("cand", "candidate", [9.0, 9.0])], rounds=2)
    seq[3]["round"] = 1
    with pytest.raises(stats.StatsError, match="measured twice in round 1"):
        stats.brackets(seq, "v1")


# Thresholds.


def test_the_order_statistic_is_exactly_the_kth_largest() -> None:
    """k = floor(rate x (n + 1)): 20 nulls at 5 % take the largest, 39 the second largest, 18
    none; 99 values at 29 % take the 29th, where float arithmetic gives floor(28.999...) = 28."""
    values = [float(v) for v in range(1, 21)]
    assert stats.order_level(values, 0.05) == (20.0, 1)
    assert stats.order_level([float(v) for v in range(1, 40)], 0.05) == (38.0, 2)
    assert stats.order_level([float(v) for v in range(1, 20)], 0.05) == (19.0, 1)
    assert math.floor(0.29 * 100) == 28  # the float product falls short of 29
    assert stats.order_level([float(v) for v in range(1, 100)], 0.29) == (71.0, 29)
    with pytest.raises(stats.StatsError, match="calibrate 19 or more"):
        stats.order_level([float(v) for v in range(1, 19)], 0.05)


def null(n: int, v1: float, v2: float) -> dict:
    return {"session": f"s{n // 2}", "twin": f"twin-{n % 2 + 1}", "ratios": {"v1": v1, "v2": v2}}


# 20 null candidates: v1 at most 0.8 % off, v2 at most 0.3 %; the largest geo-mean pairs both.
D1 = [0.8, -0.7, 0.6, -0.5, 0.4, -0.3, 0.2, -0.1, 0.0, 0.1]
D1 += [-0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.75, 0.05, -0.05, 0.15]
D2 = [0.3, -0.3, 0.2, -0.2, 0.1, -0.1, 0.0, 0.0, 0.1, -0.1]
D2 += [0.2, -0.2, 0.3, -0.25, 0.15, -0.15, 0.05, -0.05, 0.25, -0.1]
NULLS = [null(n, 1 + a / 100, 1 + b / 100) for n, (a, b) in enumerate(zip(D1, D2, strict=True))]


def test_thresholds_per_view_and_for_the_exact_view_set() -> None:
    found = stats.thresholds(NULLS, ["v1", "v2"], 0.05, 0.5)
    assert (found["nulls"], found["k"]) == (20, 1)
    assert found["perView"]["v1"] == pytest.approx(0.8)  # the largest |delta| at v1
    assert found["perView"]["v2"] == 0.5  # 0.3 at most: the floor
    pairs = zip(D1, D2, strict=True)
    geo = max(abs(100 * (math.sqrt((1 + a / 100) * (1 + b / 100)) - 1)) for a, b in pairs)
    assert found["geoMean"] == pytest.approx(geo) and geo > 0.5
    # The subset's own threshold (`compare` over one view): its geo-mean is the view's ratio.
    alone = stats.thresholds(NULLS, ["v1"], 0.05, 0.5)
    assert alone["geoMean"] == pytest.approx(0.8)
    with pytest.raises(stats.StatsError, match="holds no ratio at v3"):
        stats.thresholds(NULLS, ["v1", "v3"], 0.05, 0.5)


# Verdicts.


def test_the_verdict_takes_the_threshold_with_opposite_signs() -> None:
    assert stats.verdict(-0.5, 0.5) == "accept"
    assert stats.verdict(0.5, 0.5) == "reject"
    assert stats.verdict(-0.4999, 0.5) == stats.verdict(0.4999, 0.5) == "inconclusive"


# Every threshold at the floor: 20 nulls within 0.2 % at both views.
FLOORED = {
    "id": "quick-test",
    "views": ["v1", "v2"],
    "rounds": 1,
    "falseRate": 0.05,
    "floorPct": 0.5,
    "nulls": [null(n, 1 + (n % 5) / 1000, 1 - (n % 3) / 1000) for n in range(20)],
}


def session(cand: dict[str, float], twin: dict[str, float] | None = None, **changes) -> list[dict]:
    """A one-round session at v1 and v2 (baselines 10 ms) of a candidate and the twin."""
    twin = twin or {"v1": 10.0, "v2": 10.0}
    found = []
    for view in ("v1", "v2"):
        others = [("cand", "candidate", [cand[view]]), ("twin", "twin", [twin[view]])]
        bases = changes.get(view, [10.0, 10.0, 10.0])
        found += view_captures(view, bases, others, 1, len(found) + 1)
    return found


def test_a_faster_candidate_is_accepted_and_a_slower_one_rejected() -> None:
    found = stats.judge(session({"v1": 9.0, "v2": 9.5}), FLOORED, "full")
    assert found["session"] == "ok" and found["twin"]["inside"] is True
    cand = found["candidates"][0]
    assert cand["verdict"] == "accept" and cand["confirm"] is False
    assert cand["geoMeanDelta"] == pytest.approx(100 * (math.sqrt(0.9 * 0.95) - 1), abs=1e-4)
    assert [(r["view"], r["delta"], r["beyond"]) for r in cand["views"]] == [
        ("v1", -10.0, True),
        ("v2", -5.0, True),
    ]
    assert cand["views"][0]["deltaMs"] == -1.0 and cand["views"][0]["thresholdMs"] == 0.05
    slower = stats.judge(session({"v1": 10.2, "v2": 10.2}), FLOORED, "full")["candidates"][0]
    assert (slower["verdict"], slower["confirm"]) == ("reject", False)


def test_an_accept_within_twice_its_threshold_is_confirmed_in_a_second_session() -> None:
    cand = stats.judge(session({"v1": 9.93, "v2": 9.93}), FLOORED, "full")["candidates"][0]
    assert cand["verdict"] == "accept" and cand["confirm"] is True
    assert "second session" in cand["why"]


def test_inside_the_noise_is_inconclusive_and_quick_mode_says_run_full() -> None:
    full = stats.judge(session({"v1": 9.97, "v2": 10.0}), FLOORED, "full")["candidates"][0]
    assert full["verdict"] == "inconclusive" and "run full" not in full["why"]
    quick = stats.judge(session({"v1": 9.97, "v2": 10.0}), FLOORED, "quick")["candidates"][0]
    assert quick["verdict"] == "inconclusive" and "inconclusive, run full" in quick["why"]
    # A view beyond its own threshold is flagged while the geo-mean stays inside.
    flagged = stats.judge(session({"v1": 9.94, "v2": 10.03}), FLOORED, "full")["candidates"][0]
    assert flagged["verdict"] == "inconclusive"
    assert [r["beyond"] for r in flagged["views"]] == [True, False]


def test_a_twin_beyond_its_threshold_makes_the_whole_session_inconclusive() -> None:
    found = stats.judge(session({"v1": 9.0, "v2": 9.0}, {"v1": 10.1, "v2": 10.1}), FLOORED, "full")
    assert found["session"] == "inconclusive" and found["twin"]["inside"] is False
    assert "beyond the geo-mean threshold" in found["why"]
    assert found["candidates"][0]["verdict"] == "inconclusive"


def test_a_twin_that_could_not_be_measured_fails_never_passes() -> None:
    bad = [10.0, 10.0, (10.0, ("cpuLimited",), None)]  # v2's baseline after the twin
    found = stats.judge(session({"v1": 9.0, "v2": 9.0}, v2=bad), FLOORED, "full")
    assert found["twin"]["inside"] is None and found["session"] == "inconclusive"
    assert "could not be measured" in found["why"] and "v2" in found["why"]
    assert found["candidates"][0]["verdict"] == "inconclusive"


def test_a_candidate_unjudged_on_one_view_is_inconclusive_and_names_it() -> None:
    left = [10.0, 10.0, 10.0]
    captures = session({"v1": 9.0, "v2": 9.0}, v1=left)
    captures[1]["flags"] = ["leftGpuBound"]  # v1's candidate capture
    cand = stats.judge(captures, FLOORED, "full")["candidates"][0]
    assert cand["verdict"] == "inconclusive" and cand["unjudged"] == ["v1"]
    assert "v1: round 1: capture #2 left GPU-bound" in cand["why"]
    assert cand["geoMeanDelta"] is None


def test_a_judged_session_holds_one_twin() -> None:
    captures = [c for c in session({"v1": 9.0, "v2": 9.0}) if c["role"] != "twin"]
    with pytest.raises(stats.StatsError, match="one A/A twin, this one 0"):
        stats.judge(captures, FLOORED, "full")


# Calibration's nulls and the twin monitor.


def test_a_calibration_sessions_twins_are_its_null_candidates() -> None:
    seq = []
    for view in ("v1", "v2"):
        twins = [("twin-1", "twin", [10.05]), ("twin-2", "twin", [9.98])]
        seq += view_captures(view, [10.0, 10.0, 10.0], twins, 1, len(seq) + 1)
    found = stats.nulls_of(seq, ["v1", "v2"], 1, "cal-quick-1")
    assert found["problems"] == []
    assert [(n["twin"], n["ratios"]) for n in found["nulls"]] == [
        ("twin-1", {"v1": pytest.approx(1.005), "v2": pytest.approx(1.005)}),
        ("twin-2", {"v1": pytest.approx(0.998), "v2": pytest.approx(0.998)}),
    ]
    seq[-1]["valid"] = False  # v2's last baseline: twin-2 there is unjudged
    found = stats.nulls_of(seq, ["v1", "v2"], 1, "cal-quick-1")
    assert found["nulls"] == [] and "twin-2 at v2" in found["problems"][0]


def test_more_than_two_of_the_last_20_twins_beyond_means_recalibrating() -> None:
    two = [True, True] + [False] * 18
    assert stats.twin_monitor(two, 20, 2)["recalibrate"] is False
    three = [True, *two]
    assert stats.twin_monitor(three, 20, 2) == {
        "window": 20,
        "maxExceed": 2,
        "twins": 20,
        "exceeded": 2,
        "recalibrate": False,
    }  # the oldest left the window
    assert stats.twin_monitor([True, True, True], 20, 2)["recalibrate"] is True


# A8 (plans/m2.md M2.P10): the timers-on candidate inside its geo-mean threshold, and no view
# beyond its own in two sessions with the same sign.


def a8(timed: dict[str, float], twin: dict | None = None, first: dict | None = None) -> dict:
    captures = session(timed, twin)
    entry = stats.judge_items(captures, FLOORED, ["A8"], "cand", first)[0]
    return {"pass": entry["pass"], **entry["evidence"]}


def test_a8_passes_inside_every_threshold_in_one_session() -> None:
    found = a8({"v1": 10.01, "v2": 9.99})
    assert found["pass"] is True and found["beyond"] == {} and found["twin"] is True


def test_a8_fails_when_its_geo_mean_lies_beyond() -> None:
    found = a8({"v1": 10.08, "v2": 10.08})
    assert found["pass"] is False and "geo-mean delta +0.8000 %" in found["why"]


def test_a8_re_measures_a_view_beyond_its_threshold_in_a_second_session() -> None:
    first = a8({"v1": 9.99, "v2": 10.08})  # v2 +0.8 %, the geo-mean +0.35 %
    assert first["pass"] is None and first["remeasure"] == ["v2"]
    assert first["beyond"] == {"v2": pytest.approx(0.8)} and "remeasures" in first["pending"]
    same = a8({"v1": 10.0, "v2": 10.07}, first=first)
    assert same["pass"] is False and "v2 (+0.8000 %, +0.7000 %)" in same["why"]
    opposite = a8({"v1": 10.0, "v2": 9.93}, first=first)
    assert opposite["pass"] is True and opposite["first"]["beyond"] == {"v2": pytest.approx(0.8)}
    inside = a8({"v1": 10.0, "v2": 10.02}, first=first)
    assert inside["pass"] is True


def test_a8_waits_on_a_session_inconclusive_on_its_twin() -> None:
    found = a8({"v1": 10.0, "v2": 10.0}, twin={"v1": 10.2, "v2": 10.2})
    assert found["pass"] is None and "the A/A twin" in found["pending"]


# A11 (plans/m2.md M2.P10): every variant timed; the residual moves less than the view's threshold
# in ms between variants, and shadows off's delta from the timers matches GPUBusy's.


def a11(shadows: tuple, flags: tuple = ()) -> dict:
    """Baselines and the twin at 10 ms GPUBusy, 9 ms of passes, a 1 ms residual; shadows off
    (busy, top-level sum, residual) at both views; the view's threshold 0.5 %: 0.05 ms."""
    captures = []
    timed = (10.0, (), (9.0, 1.0))
    busy, top, rest = shadows
    for view in ("v1", "v2"):
        others = [
            ("shadows", "candidate", [(busy, flags, (top, rest))]),
            ("twin", "twin", [timed]),
        ]
        captures += view_captures(view, [timed] * 3, others, 1, len(captures) + 1)
    entry = stats.judge_items(captures, FLOORED, ["A11"], None)[0]
    return {"pass": entry["pass"], **entry["evidence"]}


def test_a11_passes_when_residuals_hold_and_the_timers_agree() -> None:
    found = a11((8.0, 7.0, 1.0))
    assert found["pass"] is True
    row = found["views"][0]
    assert row["thresholdMs"] == 0.05 and row["residualMovesMs"] == {"shadows": 0.0, "twin": 0.0}
    assert row["deltaFromTimers"]["shadows"] == {
        "timersMs": -2.0,
        "gpuBusyMs": -2.0,
        "differenceMs": 0.0,
    }


def test_a11_fails_on_a_moving_residual_or_timers_off_gpubusy() -> None:
    moved = a11((8.0, 7.0, 1.2))
    assert (
        moved["pass"] is False
        and "v1: the residual spreads 0.2000 ms (shadows +0.2000" in (moved["why"])
    )
    off = a11((8.0, 6.9, 1.0))
    assert off["pass"] is False and "timers delta is -0.1000 ms off" in off["why"]


def test_a11_waits_on_dropped_timer_frames() -> None:
    found = a11((8.0, 7.0, 1.0), flags=("timersDropped",))
    assert found["pass"] is None and "the timers dropped frames" in found["pending"]


def test_a11_compares_every_pair_of_variants_not_each_with_the_baseline_alone() -> None:
    """mod.md#12-acceptance: the residual moves less than the threshold between the variants:
    shadows off at -0.03 ms and the twin at +0.03 ms are each inside 0.05 ms of the baseline's,
    0.06 ms apart."""
    captures = []
    for view in ("v1", "v2"):
        others = [
            ("shadows", "candidate", [(8.0, (), (7.03, 0.97))]),
            ("twin", "twin", [(10.0, (), (8.97, 1.03))]),
        ]
        captures += view_captures(view, [(10.0, (), (9.0, 1.0))] * 3, others, 1, len(captures) + 1)
    entry = stats.judge_items(captures, FLOORED, ["A11"], None)[0]
    assert entry["pass"] is False and "the residual spreads 0.0600 ms" in entry["evidence"]["why"]


def test_a11_fails_on_a_measured_failure_though_another_view_is_unjudged() -> None:
    captures = []
    for view, flags in (("v1", ()), ("v2", ("timersDropped",))):
        others = [
            ("shadows", "candidate", [(8.0, flags, (7.0, 1.2))]),
            ("twin", "twin", [(10.0, (), (9.0, 1.0))]),
        ]
        captures += view_captures(view, [(10.0, (), (9.0, 1.0))] * 3, others, 1, len(captures) + 1)
    entry = stats.judge_items(captures, FLOORED, ["A11"], None)[0]
    assert entry["pass"] is False and entry["evidence"]["unjudged"]


def test_an_accept_at_exactly_twice_its_threshold_is_still_confirmed() -> None:
    """measurement.md: an accept within 2x threshold, on the unrounded numbers."""
    judged = {
        "variant": "cand",
        "views": [],
        "unjudged": [],
        "geoMeanThreshold": 0.5,
        "geoMeanDelta": -1.0,
        "inside": False,
        "bare": "accept",
        "exact": -1.0,
        "exactThreshold": 0.5,
    }
    found = stats.candidate_verdict(judged, {"inside": True}, "full")
    assert found["confirm"] is True and "exact" not in found and "exactThreshold" not in found
    beyond = stats.candidate_verdict({**judged, "exact": -1.0001}, {"inside": True}, "full")
    assert beyond["confirm"] is False


def test_a_variant_the_record_names_but_never_measured_is_unjudged_not_left_out() -> None:
    expected = [
        {"id": "baseline", "role": "baseline"},
        {"id": "cand", "role": "candidate"},
        {"id": "late", "role": "candidate"},
        {"id": "twin", "role": "twin"},
    ]
    found = stats.judge(session({"v1": 9.0, "v2": 9.0}), FLOORED, "full", expected)
    late = found["candidates"][1]
    assert late["variant"] == "late" and late["verdict"] == "inconclusive"
    assert late["unjudged"] == ["v1", "v2"] and "round 1 was not measured" in late["why"]
    assert len(stats.judge(session({"v1": 9.0, "v2": 9.0}), FLOORED, "full")["candidates"]) == 1


def test_a11_waits_without_a_measured_effect_for_the_timers_to_match() -> None:
    """The critique's finding 2: identical variants, or timers reading zero, agree with GPUBusy
    trivially; A11 needs a candidate's GPUBusy delta beyond a view's threshold."""
    same = a11((10.0, 9.0, 1.0))
    assert same["pass"] is None and "no effect for the timers" in same["pending"]
    zero = []
    for view in ("v1", "v2"):
        others = [
            ("shadows", "candidate", [(10.0, (), (0.0, 10.0))]),
            ("twin", "twin", [(10.0, (), (0.0, 10.0))]),
        ]
        zero += view_captures(view, [(10.0, (), (0.0, 10.0))] * 3, others, 1, len(zero) + 1)
    entry = stats.judge_items(zero, FLOORED, ["A11"], None)[0]
    assert entry["pass"] is None and "no effect" in entry["evidence"]["pending"]
    assert a11((8.0, 7.0, 1.0))["effect"] == ["v1: shadows", "v2: shadows"]


def test_a_calibration_twin_never_measured_keeps_its_session_from_counting() -> None:
    """The critique's finding 3: a twin found only in the record's variants, none of its captures
    taken, is a problem, never one null fewer."""
    seq = []
    for view in ("v1", "v2"):
        seq += view_captures(view, [10.0, 10.0], [("twin-1", "twin", [10.05])], 1, len(seq) + 1)
    expected = [
        {"id": "baseline", "role": "baseline"},
        {"id": "twin-1", "role": "twin"},
        {"id": "twin-2", "role": "twin"},
    ]
    found = stats.nulls_of(seq, ["v1", "v2"], 1, "cal-quick-1", expected, 2)
    assert found["nulls"] == [] and "twin-2 at v1: round 1 was not measured" in found["problems"]
    short = stats.nulls_of(seq, ["v1", "v2"], 1, "cal-quick-1", expected[:2], 2)
    assert short["nulls"] == [] and "1 twins, the calibration takes 2" in short["problems"][0]
