"""The reload budget (docs/plans/m2.md D43, M2.P06): from budget runs' records, per bench heap the
largest number of reloads one launch may hold, the heap that holds the most, and the calibration
size that fits it. Pure: the records come in as parsed JSON.

- Per heap H from HEAP_FROM MiB in HEAP_STEP steps below the physical memory: the cap is the
  largest multiple of record.RELOAD_EVERY reloads up to which the heap after GC stays within
  LIMIT x H and the private bytes within LIMIT x the physical memory. The record's own rows answer
  up to its last one (the growth is not linear: VRAM overflowing into shared memory steepens it);
  past it, the steepest growth between two rows extends it. A run at another heap commits H minus
  its own Xmx more private bytes throughout (Xms = Xmx).
- The drift (user, 2026-10-13): never past the last multiple of RELOAD_EVERY before the first
  measured-pass baseline capture more than DRIFT_PCT off its view's warm-up capture. A run
  without windows reads no drift and sets no drift cap; at least one run must read it.
- The worse run per heap counts. The heap with the largest cap wins, the smallest on a tie: D43
  names no tie-break, and a bigger heap only commits more private bytes.
"""

from dataclasses import dataclass
from itertools import pairwise

from optilux import record

HEAP_FROM = 6144
HEAP_STEP = 1024
LIMIT = 0.75
# D43's drift limit (user, 2026-10-13).
DRIFT_PCT = 2.0
# measurement.md#calibration: at least 20 null candidates per mode.
NULL_CANDIDATES = 20
# Section 7's case: the twin and one candidate.
TWIN_AND_ONE = 2


class BudgetError(ValueError):
    """A record the rule cannot read, or runs it cannot judge."""


@dataclass(frozen=True)
class Run:
    """One budget run as D43 reads it: its name, Xmx, heap rows (reloads, heap after GC, private
    bytes), the physical memory, the first drifting reload, and whether its captures could show a
    drift at all."""

    name: str
    xmx: int
    rows: tuple[tuple[int, float, float], ...]
    physical: int
    drift: int | None
    drift_read: bool


def drift_onset(found: dict, limit: float = DRIFT_PCT) -> tuple[int | None, bool]:
    """The reload of the first measured-pass baseline capture more than `limit` % off its view's
    warm-up capture (capture i is reload record.ACCEPTANCE_RELOADS + i), None when none is; and
    whether any such capture had a warm-up to compare with (False: no drift was read)."""
    warm = {
        c["view"]: c["gpuBusyMs"]
        for c in found["captures"]
        if c["pass"] == 1 and c.get("gpuBusyMs")
    }
    read = False
    for c in found["captures"]:
        if c["pass"] != 2 or c["role"] != "baseline" or not c.get("gpuBusyMs"):
            continue
        base = warm.get(c["view"])
        if not base:
            continue
        read = True
        if abs(100 * (c["gpuBusyMs"] / base - 1)) > limit:
            return record.ACCEPTANCE_RELOADS + c["index"], True
    return None, read


def read_run(found: dict) -> Run:
    """A record's heap rows and drift as D43 reads them; BudgetError without two rows or more."""
    table = found.get("heapTable")
    if not table or len(table.get("rows", [])) < 2:
        raise BudgetError(f"{found.get('name')}: no heap table of two rows or more")
    drift, read = drift_onset(found)
    return Run(
        name=found["name"],
        xmx=found["identity"]["java"]["heap"]["xmx"],
        rows=tuple((r["reloads"], r["heapUsedMiB"], r["privateMiB"]) for r in table["rows"]),
        physical=table["physicalMiB"],
        drift=drift,
        drift_read=read,
    )


def within(name: str, points: list[tuple[int, float]], limit: float) -> int:
    """The largest multiple of RELOAD_EVERY up to which every measured point stays within `limit`,
    past the last point the steepest growth between two points extending it; 0 when the first
    point is over. BudgetError when the points never grow (no growth gives no cap)."""
    every = record.RELOAD_EVERY
    over = [n for n, value in points if value > limit]
    if over:
        return max(0, (over[0] - 1) // every * every)
    steepest = max((b - a) / (m - n) for (n, a), (m, b) in pairwise(points))
    if steepest <= 0:
        raise BudgetError(f"{name}: no growth between its rows, so no cap past them")
    last, value = points[-1]
    return int((last + (limit - value) / steepest) // every * every)


def caps(run: Run, heap: int) -> dict:
    """One run's caps at the heap `heap` MiB: by the heap, by the private bytes (shifted by the
    heap's difference from the run's Xmx), by the drift when the run read one, and the cap, their
    smallest."""
    shift = heap - run.xmx
    found = {
        "heap": within(run.name, [(n, h) for n, h, _ in run.rows], LIMIT * heap),
        "private": within(run.name, [(n, p + shift) for n, _, p in run.rows], LIMIT * run.physical),
    }
    if run.drift is not None:
        every = record.RELOAD_EVERY
        found["drift"] = (run.drift - 1) // every * every
    found["cap"] = min(found.values())
    return found


def rule(runs: list[Run]) -> dict:
    """D43 over the runs: per heap the worse run's caps, the heap with the largest cap (the
    smallest such heap) and that cap."""
    if not runs:
        raise BudgetError("no budget run to read")
    if not any(r.drift_read for r in runs):
        raise BudgetError("no run read the drift (D43): one needs windows and its warm-up pass")
    physical = min(r.physical for r in runs)
    table = []
    heap = HEAP_FROM
    while heap < physical:
        each = {r.name: caps(r, heap) for r in runs}
        table.append({"heap": heap, "cap": min(c["cap"] for c in each.values()), "runs": each})
        heap += HEAP_STEP
    if not table:
        raise BudgetError(f"no heap from {HEAP_FROM} MiB lies below {physical} MiB of memory")
    best = max(row["cap"] for row in table)
    chosen = next(row for row in table if row["cap"] == best)
    return {"heap": chosen["heap"], "cap": best, "table": table}


def holds_twin_and_one(cap: int, views: int, rounds: int) -> bool:
    """Whether a session of `views` views at R `rounds` with the twin and one candidate fits the
    cap (plans/m2.md section 7 stops when full mode's does not, at every heap)."""
    return record.planned_reloads(views, TWIN_AND_ONE, rounds) <= cap


def calibration_fit(cap: int, views: int, rounds: int) -> dict | None:
    """The most twins a calibration session of `views` views at R `rounds` holds within `cap`
    (selftest's reload counted) and the sessions that make NULL_CANDIDATES; None when not one
    twin fits."""
    twins = 0
    while record.planned_reloads(views, twins + 1, rounds) <= cap:
        twins += 1
    if twins == 0:
        return None
    return {"twinsPerSession": twins, "minSessionsPerMode": -(-NULL_CANDIDATES // twins)}
