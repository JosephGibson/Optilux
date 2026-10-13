"""D43's rule (optilux/budget.py) over fixture tables: the pair's own heap rows, and made-up ones
at the edges."""

import pytest

from optilux import budget, record

# m2-budget-full-1's and m2-budget-overworld-1's heap rows: (reloads, heap after GC, private).
FULL_ROWS = [
    (2, 589.6, 11739.7),
    (10, 843.7, 15910.7),
    (20, 1189.6, 20923.9),
    (30, 1409.6, 25500.0),
    (40, 1612.8, 29396.8),
    (50, 1919.6, 33835.2),
    (60, 2255.4, 36121.5),
]
OVERWORLD_ROWS = [
    (2, 590.7, 11719.6),
    (10, 816.2, 15890.7),
    (20, 986.6, 21133.2),
    (30, 1166.3, 24996.0),
    (40, 1389.1, 28986.4),
]


def found(
    name: str,
    rows: list[tuple[int, float, float]],
    drift_at: int | None = None,
    xmx: int = 6144,
    windows: bool = True,
) -> dict:
    """A budget record: its heap rows, and one view's warm-up capture followed by measured-pass
    baseline captures at 7.0 ms to reload 41, from reload `drift_at` 13 % slower; without windows
    no capture has a GPUBusy."""
    captures = [{"index": 1, "pass": 1, "view": "v", "role": "baseline", "gpuBusyMs": 7.0}]
    for index in range(2, 40):
        reload = record.ACCEPTANCE_RELOADS + index
        busy = 7.0 * 1.13 if drift_at is not None and reload >= drift_at else 7.0
        captures.append(
            {"index": index, "pass": 2, "view": "v", "role": "baseline", "gpuBusyMs": busy}
        )
    captures.append({"index": 40, "pass": 2, "view": "v", "role": "twin", "gpuBusyMs": 99.0})
    if not windows:
        captures = [{k: v for k, v in c.items() if k != "gpuBusyMs"} for c in captures]
    return {
        "name": name,
        "identity": {"java": {"heap": {"xms": xmx, "xmx": xmx, "unit": "MiB"}}},
        "heapTable": {
            "every": 10,
            "physicalMiB": 32691,
            "rows": [{"reloads": n, "heapUsedMiB": h, "privateMiB": p} for n, h, p in rows],
        },
        "captures": captures,
    }


FULL = found("full", FULL_ROWS, drift_at=23)
OVERWORLD = found("overworld", OVERWORLD_ROWS, drift_at=24)


def test_the_drift_onset_is_the_first_baseline_beyond_2_percent() -> None:
    assert budget.drift_onset(FULL) == (23, True)
    assert budget.drift_onset(found("flat", FULL_ROWS)) == (None, True)
    assert budget.drift_onset(FULL, limit=20.0) == (None, True)  # 13 % is inside 20 %
    assert budget.drift_onset(found("bare", FULL_ROWS, windows=False)) == (None, False)
    assert budget.read_run(OVERWORLD).drift == 24


@pytest.mark.parametrize(("onset", "cap"), [(20, 10), (21, 20), (30, 20), (31, 30)])
def test_the_drift_caps_at_the_last_tenth_before_its_onset(onset: int, cap: int) -> None:
    run = budget.read_run(found("d", [(2, 600, 2000), (10, 610, 2010)], drift_at=onset))
    assert budget.caps(run, 6144)["drift"] == cap


def test_the_pair_caps_6144_at_20_by_its_rows_and_its_drift() -> None:
    """At 6144 MiB both records' private bytes pass 75 % of 32,691 MiB (24,518.25) between
    reloads 20 and 30 (25,500.0 and 24,996.0 at 30), and both drift from 23 and 24; the heap past
    the rows grows at the steepest segment (full 34.59 a reload from 20 to 30's 10-20)."""
    runs = [budget.read_run(FULL), budget.read_run(OVERWORLD)]
    assert budget.caps(runs[0], 6144) == {"heap": 120, "private": 20, "drift": 20, "cap": 20}
    assert budget.caps(runs[1], 6144) == {"heap": 150, "private": 20, "drift": 20, "cap": 20}
    result = budget.rule(runs)
    assert (result["heap"], result["cap"]) == (6144, 20)  # 6144 to 9216 tie at 20: the smallest
    caps = {row["heap"]: row["cap"] for row in result["table"]}
    assert [caps[h] for h in (6144, 9216, 10240, 14336, 15360)] == [20, 20, 10, 10, 0]
    assert max(caps) == 31744  # every 1024 MiB step below the physical memory


def test_a_row_over_the_limit_caps_where_the_mean_growth_would_not() -> None:
    """The full record's mean private growth (420.4 a reload, rows 2 to 60) would reach 30 at
    6144; its row at 30 is already over."""
    run = budget.read_run(found("full", FULL_ROWS))
    assert budget.caps(run, 6144) == {"heap": 120, "private": 20, "cap": 20}


def test_past_the_rows_the_steepest_growth_extends_them() -> None:
    run = budget.read_run(found("x", [(2, 600, 2000), (10, 700, 2100), (20, 900, 2200)]))
    # Heap: 12.5, then 20 a reload; 900 + 20 (n - 20) <= 4608 -> n <= 205.4.
    # Private: 12.5, then 10; 2200 + 12.5 (n - 20) <= 24518.25 -> n <= 1805.5.
    assert budget.caps(run, 6144) == {"heap": 200, "private": 1800, "cap": 200}


def test_a_run_at_another_heap_shifts_its_private_bytes_by_the_difference() -> None:
    rows = [(2, 600, 13000), (10, 700, 14600), (20, 800, 16600)]
    at_8192 = budget.read_run(found("big", rows, xmx=8192))
    # At 6144: 14552 + 200 (n - 20) <= 24518.25 -> n <= 69.8; at 8192: 16600 + ... -> 59.6.
    assert budget.caps(at_8192, 6144)["private"] == 60
    assert budget.caps(at_8192, 8192)["private"] == 50


def test_a_first_row_over_the_limit_caps_at_0() -> None:
    run = budget.read_run(found("over", [(2, 600, 25000), (10, 700, 25100)]))
    assert budget.caps(run, 6144)["private"] == 0


def test_runs_the_rule_cannot_judge_are_refused() -> None:
    bare = {**FULL, "heapTable": {**FULL["heapTable"], "rows": FULL["heapTable"]["rows"][:1]}}
    with pytest.raises(budget.BudgetError, match="no heap table of two rows"):
        budget.read_run(bare)
    with pytest.raises(budget.BudgetError, match="no budget run"):
        budget.rule([])
    windowless = budget.read_run(found("switches", FULL_ROWS, windows=False))
    with pytest.raises(budget.BudgetError, match="no run read the drift"):
        budget.rule([windowless])
    assert budget.rule([windowless, budget.read_run(FULL)])["cap"] == 20
    flat = budget.read_run(found("flat", [(2, 600, 2000), (10, 600, 2000)], drift_at=50))
    with pytest.raises(budget.BudgetError, match="flat: no growth between its rows"):
        budget.caps(flat, 6144)


def test_full_mode_needs_112_reloads_for_the_twin_and_one_candidate() -> None:
    assert not budget.holds_twin_and_one(20, 11, 2)  # 2 + 11 + 11 x 9 = 112
    assert budget.holds_twin_and_one(112, 11, 2) and not budget.holds_twin_and_one(67, 11, 1)
    assert budget.holds_twin_and_one(20, 3, 1)  # quick: 2 + 3 + 3 x 5 = 20
    # D43's split: a 2-view launch at R 2 without the warm-up pass, 2 + 2 x 9 = 20.
    assert budget.holds_twin_and_one(20, 2, 2, warmup=False)
    assert not budget.holds_twin_and_one(20, 2, 2)
    assert not budget.holds_twin_and_one(19, 2, 2, warmup=False)


def test_the_calibration_fits_twins_in_the_cap_and_sessions_to_20_nulls() -> None:
    # Full mode, 11 views at R 2: one twin plans 68, so a 20-reload cap holds none.
    assert budget.calibration_fit(20, 11, 2) is None
    assert budget.calibration_fit(68, 11, 2) == {"twinsPerSession": 1, "minSessionsPerMode": 20}
    # Quick mode, 3 views at R 1: 8 + 6 x twins <= 20 holds 2; 10 sessions make 20 nulls.
    assert budget.calibration_fit(20, 3, 1) == {"twinsPerSession": 2, "minSessionsPerMode": 10}
    assert budget.calibration_fit(288, 11, 2) == {"twinsPerSession": 6, "minSessionsPerMode": 4}
    # Full mode split into 2-view launches without the warm-up pass: 2 + 2 (1 + 4 twins) <= 20.
    assert budget.calibration_fit(20, 2, 2, warmup=False) == {
        "twinsPerSession": 2,
        "minSessionsPerMode": 10,
    }
