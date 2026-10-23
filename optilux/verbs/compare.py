"""`optilux compare <run> [--calibration <id>] [--against <run>] [--json]`
(docs/run-record.md#comparison, docs/plans/m2.md M2.P07, docs/plans/m3.md D63): a measured record
re-judged from its captures alone, nothing written; a visual record's frames tiered.

The calibration is `--calibration`'s, else the one the record names; a record without one (D40's
calibration null) is refused naming `calibrate`. The identity is checked key by key first, then
the kind and the mode, then the status (ok) and the record's own calibration (D40: a
calibration-null run, a budget run or the survey among them, kept another schedule and has no
verdicts), and a refusal names the field. The verdicts are optilux/stats.py's, as `run` writes
them: each candidate's, the twin's check, the twin monitor over the calibration's judged twins
by its window; A8's and A11's entries for their acceptance runs. Exit 0 when judged.

A visual record (kind visual) takes no calibration: its status ok, and with `--against <run>`
the other visual record ok and of an identity equal key by key, sharing a variant id; then its
frames, each read under results/raw/ and held to the sha256 its record names, are tiered by
optilux/visual.py (each pair, each candidate against the baseline, each variant against itself
in the other run) and review.html is written beside report.html (D63).

An acceptance record of A5 (plans/m3.md D68) takes no calibration either: the waits of the launch
that ends its sequence and of the first launch it names (`remeasures`), of one identity and one
zip, each wait's first frame after the predicate against its reference by decoded pixels. `run`
hands it the record so far on stdin (`compare - --json`) before writing it.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, platform, record, stats
from optilux.verbs import Verb

PREFIX = "optilux compare"
# A visual run's review page, beside `report`'s report.html under results/raw/<run>/ (D63).
REVIEW = "review.html"
# A visual run's frame under its raw folder, as measure.visual_capture writes it:
# frames/<view>/<variant>/attempt-NNN/frame-NNNNN.png (the mod's capture layout).
FRAME_PATH = re.compile(r"frames/[a-z0-9_]{1,40}/[a-z0-9-]{1,40}/attempt-\d{3}/frame-\d{5}\.png")


class CompareError(RuntimeError):
    """A record `compare` refuses; the message names the field and the fix."""


def compare(root: Path, name: str, cid: str | None, against: str | None = None) -> dict:
    """The record `name` re-judged by the calibration `cid` (else its own): the refusals in
    order, identity key by key, kind, mode; then the verdicts, the twin monitor and A8's and A11's
    entries, and whether the record's own verdicts agree. A visual record is tiered instead
    (compare_visual), with `against` the visual record to tier it against."""
    found = record.read_record(root, name)
    if found.get("kind") == "acceptance" and record.a5_entry(found) is not None:
        if found.get("name") != name:  # its raw folder goes by the file's name
            raise CompareError(f"{name}'s record names {found.get('name')!r}; fix: restore it")
        if cid is not None or against is not None:
            raise CompareError(
                f"{name} carries A5, judged by its frames, never by a calibration or against "
                "another run; fix: drop --calibration and --against"
            )
        return compare_a5(root, found)
    if found.get("kind") == record.VISUAL:
        if found.get("name") != name:  # its raw folder and page go by the file's name
            raise CompareError(f"{name}'s record names {found.get('name')!r}; fix: restore it")
        if cid is not None:
            raise CompareError(
                f"{name} is a visual run, tiered by its frames, never by a calibration; fix: drop "
                "--calibration"
            )
        return compare_visual(root, found, against)
    if against is not None:
        raise CompareError(
            f"--against tiers one visual run's frames against another's, and {name} is a "
            f"{found.get('kind')} run; fix: drop --against"
        )
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
            f"`optilux calibrate --mode {mode}`, then a measurement run that names the id it prints"
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
    if found.get("status") != "ok":
        raise CompareError(
            f"{name}'s status is {found.get('status')} ({found.get('reason')}): a run that did "
            "not end ok has no verdicts; fix: rerun it under a new name"
        )
    if found.get("calibration") is None:
        raise CompareError(
            f"{name} ran calibration null (plans/m2.md D40: no verdicts, its schedule its own); "
            f"fix: a measurement run that names calibration {cid[:24]}..."
        )
    first = first_evidence(root, found)
    if first is not None and first.get("calibration") != cid:
        raise CompareError(
            f"{name} re-measures an A8 session judged by calibration "
            f"{str(first.get('calibration'))[:24]}...; fix: compare it under that calibration"
        )
    captures = record.session_captures(root, found)
    expected = found.get("variants") or None
    judged = stats.judge(captures, cal, mode, expected)
    history = record.judged_twins(root, cal["id"])
    own = (record.judged_twin(found) or (None, None))[0] == cid
    if judged["twin"]["inside"] is not None and not own:
        history.append(not judged["twin"]["inside"])  # a record not yet among the judged
    window = cal["twinMonitor"]
    judged["twinMonitor"] = stats.twin_monitor(history, window["window"], window["maxExceed"])
    result: dict[str, Any] = {"name": name, "calibration": cid, "kind": kind, "verdicts": judged}
    if kind == "acceptance":
        items = [e["item"] for e in found.get("acceptance") or []]
        timed_id = timed(found)
        result["acceptance"] = stats.judge_items(captures, cal, items, timed_id, first, expected)
    if own and found.get("verdicts"):
        keep = ("candidates", "twin", "session")
        recorded = {k: found["verdicts"].get(k) for k in keep}
        result["sameAsRecord"] = recorded == {k: judged[k] for k in keep}
    return result


def compare_visual(root: Path, found: dict, against: str | None) -> dict:
    """A visual record's frames tiered (optilux/visual.py, plans/m3.md D63) and its review page
    written: the refusals in order (its status; with `against`, the other record's kind and
    status, the identities key by key, a variant id they share); each frame read under
    results/raw/<run>/ and held to its record's sha256 before it is decoded, a view's frames
    released before the next view's are read. The result: the tiers by view, the page's path."""
    from optilux import visual  # the tiers' libraries load for a visual record alone

    name = found["name"]
    if found.get("status") != "ok":
        raise CompareError(
            f"{name}'s status is {found.get('status')} ({found.get('reason')}): a run that did not "
            "end ok has no whole set of frames; fix: rerun it under a new name"
        )
    other = None
    if against == name:
        raise CompareError(
            f"--against {name} tiers {name}'s frames against themselves; fix: --against another "
            "visual run of its identity"
        )
    if against is not None:
        other = record.read_record(root, against)
        if other.get("name") != against:
            raise CompareError(f"{against}'s record names {other.get('name')!r}; fix: restore it")
        if other.get("kind") != record.VISUAL or other.get("status") != "ok":
            raise CompareError(
                f"{against} is a {other.get('kind')} run that ended {other.get('status')}; fix: "
                "--against a visual run that ended ok"
            )
        differ = record.identity_differences(found.get("identity"), other.get("identity"))
        if differ:
            raise CompareError(
                f"{name} and {against} differ in identity: {', '.join(differ)}; fix: compare runs "
                "of one identity (run-record.md#comparison)"
            )
        mine = {v["id"] for v in found.get("variants") or []}
        if not mine & {v["id"] for v in other.get("variants") or []}:
            raise CompareError(
                f"{name} and {against} share no variant id; fix: name a variant alike in both"
            )
    try:
        fid = visual.fidelity(json.loads((root / platform.SUITE).read_text(encoding="utf-8")))
        items = visual.plan(found, other)
        if not items:
            raise CompareError(f"{name} holds no whole pair to tier; fix: rerun it")
        if other is not None and not any(item["kind"] == visual.AGAINST for item in items):
            raise CompareError(
                f"{name} and {against} hold no variant at a view in common; fix: --against a "
                "visual run of the same views"
            )
        pixels: dict[tuple[str, str], Any] = {}
        for item in items:
            if pixels and next(iter(pixels.values()))[1] != item["view"]:
                pixels.clear()  # one view's frames held at a time: a 4K frame is 33 MB
            arrays = []
            for frame in item["frames"]:
                key = (frame["run"], frame["path"])
                if key not in pixels:
                    pixels[key] = (
                        visual.decode(frame_bytes(root, frame), shown_frame(frame)),
                        item["view"],
                    )
                arrays.append(pixels[key][0])
            item["tier"] = visual.tier(arrays[0], arrays[1], fid)
    except visual.VisualError as error:
        raise CompareError(str(error)) from None
    folder = root / record.RAW / name
    result = {
        "name": name,
        "kind": record.VISUAL,
        "mode": found.get("mode"),
        "variants": [v["id"] for v in found.get("variants") or []],
        "against": against,
        "unmatched": visual.unmatched(found, other) if other is not None else {},
        "items": items,
        "page": (folder / REVIEW).relative_to(root).as_posix(),
    }
    folder.mkdir(parents=True, exist_ok=True)
    (folder / REVIEW).write_bytes(visual.page(result).encode("utf-8"))
    return result


def compare_a5(root: Path, found: dict) -> dict:
    """A5's verdict (mod.md#12-acceptance, plans/m3.md D68) over the record `found` and the first
    launch it names (`remeasures`): the refusals in order (its status; the first's name, its
    identity key by key and its zip; the waits of both, in order, the views file's A5 sequence
    whole; no other launch naming the first); then each wait's two frames read under
    results/raw/<run>/, held to their recorded sha256 and decoded, the first after the predicate
    against the reference; a wait whose capture is flagged is judged neither way. A record that
    ended ok, or failed on its own A5 verdict (a miss: `run` judges only an ok session), is judged.
    Passed when every wait's frames are equal. The result: pass, why, judged (the counts, the rate
    over the waits judged, the misses, the waits unjudged, each wait)."""
    from optilux import visual  # the frames' libraries load for an A5 record alone

    name = str(found.get("name"))
    entry = record.a5_entry(found) or {}
    own = record.as_dict(entry.get("evidence"))
    judged_here = isinstance(entry.get("pass"), bool) and "judged" in own
    if found.get("status") != "ok" and not judged_here:
        raise CompareError(
            f"{name}'s status is {found.get('status')} ({found.get('reason')}), and its A5 was "
            "never judged: its waits are not whole; fix: rerun A5 under new names"
        )
    spec = record.as_dict(found.get("spec"))
    views_id = spec.get("views")
    if not isinstance(views_id, str) or not record.VIEW_ID.fullmatch(views_id):
        raise CompareError(f"{name}'s spec names views {views_id!r}; fix: restore the record")
    launches: list[tuple[str, list]] = []
    first_name = spec.get("remeasures")
    if first_name is not None:
        if not isinstance(first_name, str) or not record.NAME.fullmatch(first_name):
            raise CompareError(f"{name}'s spec names remeasures {first_name!r}; fix: restore it")
        first = record.read_record(root, first_name)
        others = [n for n in record.a5_continued(root, first_name) if n != name]
        if others:
            raise CompareError(
                f"{first_name} is continued by {', '.join(others)} too: a first A5 launch is "
                "judged once (plans/m3.md D68); fix: compare the launch that continued it first"
            )
        if first.get("name") != first_name:
            raise CompareError(
                f"{first_name}'s record names {first.get('name')!r}; fix: restore it"
            )
        differ = record.identity_differences(found.get("identity"), first.get("identity"))
        if differ:
            raise CompareError(
                f"{name} and {first_name} differ in identity: {', '.join(differ)}; fix: both of "
                "A5's launches under one identity (run-record.md#comparison)"
            )
        zips = [[v.get("sha512") for v in r.get("variants") or []] for r in (first, found)]
        if zips[0] != zips[1]:
            raise CompareError(f"{name} and {first_name} loaded other zips; fix: one pack in both")
        theirs = record.as_dict((record.a5_entry(first) or {}).get("evidence"))
        launches.append((first_name, theirs.get("waits") or []))
    launches.append((name, own.get("waits") or []))
    views, _ = record.load_views(root, views_id)
    seq = record.a5_waits(views)
    waits = [(run, w) for run, held in launches for w in held if isinstance(w, dict)]
    got = [(w.get("lap"), w.get("view")) for _, w in waits]
    if got != seq or [w.get("wait") for _, w in waits] != list(range(1, len(seq) + 1)):
        raise CompareError(
            f"{' and '.join(r for r, _ in launches)} hold {len(waits)} A5 waits, not the "
            f"sequence's {len(seq)} in order (plans/m3.md D68); fix: A5's first launch, then a "
            "second naming it"
        )
    per = []
    for run, w in waits:
        held = {"wait": w["wait"], "run": run, "view": w["view"]}
        frames = w.get("frames") or []
        if not w.get("valid") or len(frames) != 2:
            per.append({**held, "equal": None, "flags": w.get("flags") or ["incomplete"]})
            continue
        try:
            arrays = [
                visual.decode(frame_bytes(root, {"run": run, **f}), shown_frame({"run": run, **f}))
                for f in frames
            ]
        except visual.VisualError as error:
            raise CompareError(str(error)) from None
        per.append({**held, **visual.difference(arrays[0], arrays[1])})
    equal = sum(1 for p in per if p["equal"] is True)
    misses = [f"{p['wait']} {p['view']}" for p in per if p["equal"] is False]
    unjudged = [f"{p['wait']} {p['view']}" for p in per if p["equal"] is None]
    judgeable = len(seq) - len(unjudged)  # the rate leaves out the waits judged neither way
    why = (
        f"{equal} of {len(seq)} waits' first frame after the predicate equal to its reference "
        f"(decoded pixels), in {', '.join(r for r, _ in launches)}"
        + (f"; misses: {', '.join(misses)}" if misses else "")
        + (f"; unjudged (flagged): {', '.join(unjudged)}" if unjudged else "")
    )
    judged = {
        "waits": len(seq),
        "equal": equal,
        "judgeable": judgeable,
        "rate": round(equal / judgeable, 4) if judgeable else None,
        "launches": [r for r, _ in launches],
        "misses": misses,
        "unjudged": unjudged,
        "perWait": per,
    }
    result: dict[str, Any] = {
        "name": name,
        "kind": "acceptance",
        "a5": {"pass": equal == len(seq), "why": why, "judged": judged},
    }
    if entry.get("pass") is not None:
        result["sameAsRecord"] = (entry.get("pass"), own.get("judged")) == (
            result["a5"]["pass"],
            judged,
        )
    return result


def a5_lines(result: dict) -> list[str]:
    """A5's verdict as text: the outcome and why, each view's waits equal of its waits."""
    a5, judged = result["a5"], result["a5"]["judged"]
    out = [f"{PREFIX} {result['name']}: A5 {'pass' if a5['pass'] else 'FAIL'}: {a5['why']}"]
    views: dict[str, list[dict]] = {}
    for p in judged["perWait"]:
        views.setdefault(p["view"], []).append(p)
    out.append(
        "  per view: "
        + ", ".join(
            f"{view} {sum(1 for p in held if p['equal'] is True)}/{len(held)}"
            for view, held in views.items()
        )
    )
    rate = "none" if judged["rate"] is None else f"{judged['rate']:.4f}"
    out.append(f"  rate {rate} ({judged['equal']} of the {judged['judgeable']} waits judged)")
    if "sameAsRecord" in result:
        out.append(
            "  the record's own A5 verdict: "
            + ("the same" if result["sameAsRecord"] else "DIFFERENT from this")
        )
    return out


def shown_frame(frame: dict) -> str:
    return f"{record.RAW}/{frame['run']}/{frame['path']}"


def frame_bytes(root: Path, frame: dict) -> bytes:
    """A recorded frame's file, refused when its path is not the shape a visual run writes
    (FRAME_PATH: so it never leaves its run's raw folder, in POSIX or Windows terms), when it is
    gone (raw folders are disposable) or when it is not the bytes the record hashed."""
    if not isinstance(frame["path"], str) or not FRAME_PATH.fullmatch(frame["path"]):
        raise CompareError(f"{frame['run']} records frame path {frame['path']!r}; fix: restore it")
    try:
        data = (root / record.RAW / frame["run"] / frame["path"]).read_bytes()
    except OSError:
        raise CompareError(
            f"{shown_frame(frame)} is gone (results/raw/ is disposable); fix: rerun the visual "
            "run under a new name"
        ) from None
    digest = hashlib.sha256(data).hexdigest()
    if digest != frame["sha256"]:
        raise CompareError(
            f"{shown_frame(frame)} hashes {digest[:12]}..., its record {frame['sha256'][:12]}...: "
            "a frame is tiered only as recorded; fix: rerun the visual run under a new name"
        )
    return data


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
    parser.add_argument(
        "name",
        metavar="run",
        help="a run's name: results/records/<run>.json, or - for an A5 record on stdin (`run`'s)",
    )
    parser.add_argument(
        "--calibration",
        help="the calibration's id (config/calibrations/<id>.json); default: the record's",
    )
    parser.add_argument(
        "--against",
        metavar="run",
        help="a visual run of the same identity to tier a visual run's frames against",
    )


def stdin_a5(root: Path) -> dict:
    """The record `run` hands on stdin before writing it: A5's (compare_a5)."""
    try:
        found = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError as error:
        raise CompareError(f"the record on stdin is no JSON ({error})") from None
    if not isinstance(found, dict) or record.a5_entry(found) is None:
        raise CompareError("the record on stdin carries no A5; fix: name a record instead")
    return compare_a5(root, found)


def run(args: argparse.Namespace) -> int:
    try:
        if args.name == record.STDIN:
            if args.calibration is not None or args.against is not None:
                raise CompareError("- judges A5 alone; fix: drop --calibration and --against")
            result = stdin_a5(REPO_ROOT)
        else:
            result = compare(REPO_ROOT, args.name, args.calibration, args.against)
    except (CompareError, record.RecordError, stats.StatsError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: refused: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, **result}))
    elif "a5" in result:
        print("\n".join(a5_lines(result)))
    elif result.get("kind") == record.VISUAL:
        from optilux import visual

        print("\n".join(visual.lines(result)))
    else:
        print("\n".join(lines(result)))
    return 0


VERB = Verb(
    name="compare",
    help="re-judge a measured record against a calibration, or tier a visual record's frames",
    run=run,
    configure=configure,
    structured=True,
)
