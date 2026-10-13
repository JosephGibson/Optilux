"""`optilux compare <run> [--calibration <id>] [--json]` (docs/run-record.md#comparison,
docs/plans/m2.md M2.P07): a measured record re-judged from its captures alone; nothing written.

The calibration is `--calibration`'s, else the one the record names; a record without one (D40's
calibration null) is refused naming `calibrate`. The identity is checked key by key first, then
the kind and the mode, and a refusal names the field. The verdicts are optilux/stats.py's, as
`run` writes them: each candidate's, the twin's check, the twin monitor over the calibration's
judged twins; A8's and A11's entries for their acceptance runs. Exit 0 when judged.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, record, stats
from optilux.verbs import Verb

PREFIX = "optilux compare"
SUITE = "config/suite.json"


class CompareError(RuntimeError):
    """A record `compare` refuses; the message names the field and the fix."""


def compare(root: Path, name: str, cid: str | None) -> dict:
    """The record `name` re-judged by the calibration `cid` (else its own): the refusals in
    order, identity key by key, kind, mode; then the verdicts, the twin monitor and A8's and A11's
    entries, and whether the record's own verdicts agree."""
    found = record.read_record(root, name)
    split = found.get("split")
    if split:
        raise CompareError(
            f"{name} is part {split['part']} of session {split['session']}; fix: `optilux compare "
            f"{split['session']}` (its session record joins the parts)"
        )
    cid = cid or found.get("calibration")
    if cid is None:
        mode = found.get("mode") or "quick"
        raise CompareError(
            f"{name} names no calibration (calibration null, plans/m2.md D40: no verdicts); fix: "
            f"`optilux calibrate --mode {mode}` for its identity, then `optilux compare {name} "
            "--calibration <its id>`"
        )
    cal = record.load_calibration(root, cid)
    differ = record.identity_differences(found.get("identity"), cal["identity"])
    if differ:
        raise CompareError(
            f"{name} and calibration {cid[:24]}... differ in identity: {', '.join(differ)}; fix: "
            "compare a run of the calibration's identity (another identity is recalibrated: "
            f"`optilux calibrate --mode {cal['mode']}`)"
        )
    kind, mode = found.get("kind"), found.get("mode")
    if kind == "calibration" or mode is None:
        raise CompareError(
            f"{name}'s kind is {kind}{'' if mode else ' without a mode'}, which carries no "
            "verdicts; fix: compare a measurement run, or an A8 and A11 acceptance run"
        )
    if mode != cal["mode"]:
        raise CompareError(
            f"{name}'s mode is {mode}, calibration {cid[:24]}... is {cal['mode']} mode's; fix: "
            f"the {mode} calibration"
        )
    captures = record.session_captures(root, found)
    suite = json.loads((root / SUITE).read_text(encoding="utf-8"))
    monitor = suite["statistics"]["twinMonitor"]
    judged = stats.judge(captures, cal, mode)
    history = record.judged_twins(root, cal["id"])
    own = (found.get("verdicts") or {}).get("calibration") == cid
    if judged["twin"]["inside"] is not None and not own:
        history.append(not judged["twin"]["inside"])  # a record not yet among the judged
    judged["twinMonitor"] = stats.twin_monitor(history, monitor["window"], monitor["maxExceed"])
    result: dict[str, Any] = {"name": name, "calibration": cid, "kind": kind, "verdicts": judged}
    if kind == "acceptance":
        items = [e["item"] for e in found.get("acceptance") or []]
        first = first_evidence(root, found)
        result["acceptance"] = stats.judge_items(captures, cal, items, timed(found), first)
    if own:
        keep = ("candidates", "twin", "session")
        recorded = {k: found["verdicts"].get(k) for k in keep}
        result["sameAsRecord"] = recorded == {k: judged[k] for k in keep}
    return result


def timed(found: dict) -> str | None:
    """A8's timers-on candidate in a record's variants: equal to the baseline but timed."""
    variants = found.get("variants") or []
    if not variants:
        return None
    base = variants[0]
    for v in variants[1:]:
        same = (v.get("profile"), v.get("options")) == (base.get("profile"), base.get("options"))
        if v.get("timers") and v.get("role") == "candidate" and same:
            return v["id"]
    return None


def first_evidence(root: Path, found: dict) -> dict | None:
    """The first A8 session's evidence a second one names (`remeasures`)."""
    name = (found.get("spec") or {}).get("remeasures")
    if not name:
        return None
    first = record.read_record(root, name)
    entry = next((e for e in first.get("acceptance") or [] if e.get("item") == "A8"), {})
    return entry.get("evidence")


def lines(result: dict) -> list[str]:
    """The re-judged verdicts as text."""
    judged = result["verdicts"]
    th = judged["thresholds"]
    twin = judged["twin"]
    out = [
        f"{PREFIX} {result['name']}: calibration {result['calibration'][:24]}... ({th['nulls']} "
        f"null candidates, k {th['k']}, geo-mean threshold {th['geoMean']:.4f} %)",
        f"  session {judged['session']}: twin "
        + (
            f"{twin['geoMeanDelta']:+.4f} %, {'inside' if twin['inside'] else 'NOT inside'}"
            if twin["inside"] is not None
            else f"not measured ({stats.unjudged_text(twin)})"
        ),
    ]
    for c in judged["candidates"]:
        delta = "unjudged" if c["geoMeanDelta"] is None else f"{c['geoMeanDelta']:+.4f} %"
        out.append(f"  {c['variant']}: {c['verdict']}, geo-mean {delta}: {c['why']}")
        for r in c["views"]:
            if r.get("problem"):
                out.append(f"    {r['view']}: unjudged: {r['problem']}")
                continue
            mark = "  BEYOND" if r["beyond"] else ""
            ms = "" if r["deltaMs"] is None else f" ({r['deltaMs']:+.4f} of {r['baselineMs']} ms)"
            level = f"threshold {r['threshold']:.4f} %{mark}"
            out.append(f"    {r['view']}: {r['delta']:+.4f} %{ms}, {level}")
    m = judged["twinMonitor"]
    out.append(
        f"  twin monitor: {m['exceeded']} of the last {m['twins']} twins beyond (window "
        f"{m['window']}, recalibrate above {m['maxExceed']}): "
        + ("RECALIBRATE" if m["recalibrate"] else "holds")
    )
    shown_pass = {True: "pass", False: "FAIL", None: "waits"}
    for e in result.get("acceptance") or []:
        detail = e["evidence"].get("why") or e["evidence"].get("pending") or ""
        out.append(f"  {e['item']}: {shown_pass[e['pass']]}: {detail}")
    if "sameAsRecord" in result:
        out.append(
            "  the record's own verdicts: "
            + ("the same" if result["sameAsRecord"] else "DIFFERENT from these")
        )
    return out


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", metavar="run", help="a run's name: results/records/<run>.json")
    parser.add_argument(
        "--calibration",
        help="the calibration's id (config/calibrations/<id>.json); default: the record's",
    )


def run(args: argparse.Namespace) -> int:
    try:
        result = compare(REPO_ROOT, args.name, args.calibration)
    except (CompareError, record.RecordError, stats.StatsError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: refused: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, **result}))
    else:
        print("\n".join(lines(result)))
    return 0


VERB = Verb(
    name="compare",
    help="re-judge a measured record against a calibration, refusing another identity",
    run=run,
    configure=configure,
    structured=True,
)
