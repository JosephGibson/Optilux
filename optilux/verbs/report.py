"""`optilux report <run> [--json]` (docs/plans/m2.md D50): one static HTML page per run from its
record alone, results/raw/<run>/report.html, with no external asset; the record stays the ledger
(a committed page would copy what it holds).

The page: the run's status and reason, its verdicts as `run` wrote them (each candidate's, the
twin's check, the twin monitor), A8's and A11's entries, the variants, every capture with its
summaries and validity flags, the identity's keys and the session's time split. Printed beside
it, the record's summary in a few lines (the status, the parts, the calibration, the verdicts as
recorded, the items, the captures valid and each view with an invalid one), so a reader, or
optilux-bench, repeats a command's lines instead of reading the record.
"""

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, record
from optilux.verbs import Verb
from optilux.verbs.install import shown

PREFIX = "optilux report"
PAGE = "report.html"
# The capture columns: (heading, the record's key).
COLUMNS = (
    ("#", "index"),
    ("pass", "pass"),
    ("view", "view"),
    ("variant", "variant"),
    ("role", "role"),
    ("round", "round"),
    ("settle s", "settleS"),
    ("frames", "frames"),
    ("rows", "rows"),
    ("GPUBusy ms", "gpuBusyMs"),
    ("FrameTime ms", "frameTimeMs"),
    ("p95 ms", "frameTimeP95Ms"),
    ("GPULatency ms", "gpuLatencyMs"),
    ("busy/frame", "gpuBusyOverFrameTime"),
    ("halves %", "halvesPct"),
)
# A visual record's pairs (plans/m3.md D63): each frame's stamps and its sha256's first digits.
VISUAL_COLUMNS = (
    ("#", "index"),
    ("view", "view"),
    ("variant", "variant"),
    ("settle s", "settleS"),
    ("ready s", "readyS"),
    ("frames", "frameIndex"),
    ("sinceReload", "sinceReload"),
    ("pair s", "pairSeconds"),
    ("sha256", "sha256"),
)
# A capture record's captures (plans/m4.md D81): each .rdc's RenderDoc frame, size and sha256.
CAPTURE_COLUMNS = (
    ("#", "index"),
    ("view", "view"),
    ("variant", "variant"),
    ("settle s", "settleS"),
    ("ready s", "readyS"),
    ("frame", "frame"),
    ("MiB", "mib"),
    ("sha256", "sha256"),
)
STYLE = """
:root { --bg: #fbfbfa; --fg: #1d1d1b; --muted: #6b6b66; --line: #dcdcd6; --bad: #b3261e;
  --good: #1e6b33; --wait: #8a5a00; --head: #f0f0ec; }
@media (prefers-color-scheme: dark) { :root { --bg: #161615; --fg: #e8e8e3; --muted: #a0a09a;
  --line: #3a3a36; --bad: #f28b82; --good: #81c995; --wait: #fdd663; --head: #22221f; } }
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 1400px;
  padding: 16px; font: 14px/1.45 system-ui, sans-serif; }
h1 { font-size: 20px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 24px 0 8px; }
p, li { margin: 4px 0; } .muted { color: var(--muted); }
.ok, .pass, .accept { color: var(--good); } .bad, .FAIL, .reject { color: var(--bad); }
.waits, .inconclusive { color: var(--wait); }
.scroll { overflow-x: auto; } table { border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid var(--line); padding: 3px 8px; text-align: right;
  white-space: nowrap; } th { background: var(--head); position: sticky; top: 0; }
td.text, th.text { text-align: left; } tr.invalid td { color: var(--bad); }
code { font: 12px ui-monospace, monospace; }
"""


class ReportError(RuntimeError):
    """A record `report` cannot render; the message names the fix."""


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def number(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return e(value)


def table(headings: list[str], rows: list[list[str]], classes: list[str] | None = None) -> str:
    """A table of already-escaped cells; the first column left-aligned."""
    head = "".join(
        f'<th class="text">{h}</th>' if i < 1 else f"<th>{h}</th>" for i, h in enumerate(headings)
    )
    body = []
    for n, row in enumerate(rows):
        cls = f' class="{classes[n]}"' if classes and classes[n] else ""
        cells = "".join(
            f'<td class="text">{c}</td>' if i < 1 else f"<td>{c}</td>" for i, c in enumerate(row)
        )
        body.append(f"<tr{cls}>{cells}</tr>")
    return f'<div class="scroll"><table><tr>{head}</tr>{"".join(body)}</table></div>'


def verdict_section(judged: dict) -> str:
    th, twin = judged["thresholds"], judged["twin"]
    out = [
        "<h2>Verdicts</h2>",
        f"<p>Calibration <code>{e(judged['calibration'])}</code>: {e(th['nulls'])} null "
        f"candidates, k {e(th['k'])}, geo-mean threshold {number(th['geoMean'])} % over "
        f"{e(', '.join(judged['views']))}.</p>",
        f'<p>Session <span class="{e(judged["session"])}">{e(judged["session"])}</span>'
        + (f": {e(judged['why'])}" if judged.get("why") else "")
        + f"; twin {number(twin.get('geoMeanDelta'))} %.</p>",
    ]
    monitor = judged.get("twinMonitor")
    if monitor:
        out.append(
            f"<p>Twin monitor: {e(monitor['exceeded'])} of the last {e(monitor['twins'])} twins "
            f"beyond (recalibrate above {e(monitor['maxExceed'])}): "
            + ('<span class="bad">recalibrate</span>' if monitor["recalibrate"] else "holds")
            + "</p>"
        )
    for c in judged["candidates"]:
        out.append(
            f'<p><b>{e(c["variant"])}</b>: <span class="{e(c["verdict"])}">{e(c["verdict"])}'
            f"</span>, geo-mean {number(c['geoMeanDelta'])} % against "
            f"{number(c['geoMeanThreshold'])} %: {e(c['why'])}</p>"
        )
        rows = [
            [
                e(r["view"]),
                number(r.get("delta")),
                number(r["threshold"]),
                number(r.get("deltaMs")),
                number(r.get("thresholdMs")),
                "beyond" if r.get("beyond") else e(r.get("problem") or ""),
            ]
            for r in c["views"]
        ]
        out.append(table(["view", "delta %", "threshold %", "delta ms", "threshold ms", ""], rows))
    return "".join(out)


def pair_cells(capture: dict) -> dict:
    """A visual pair's columns: its frames' stamps and sha256 prefixes joined, ready's seconds."""
    frames = capture.get("frames") or []
    return {
        **capture,
        "readyS": (capture.get("ready") or {}).get("seconds"),
        "frameIndex": ", ".join(str(f["frameIndex"]) for f in frames),
        "sinceReload": ", ".join(str(f["sinceReload"]) for f in frames),
        "sha256": ", ".join(f["sha256"][:12] for f in frames),
    }


def shown_mode(found: dict) -> str:
    """The record's mode as the page and the summary name it: `mode quick`, a visual or capture
    run's listed views, or `mode none`."""
    mode = found.get("mode")
    return (
        f"views {', '.join(map(str, mode))}" if isinstance(mode, list) else f"mode {mode or 'none'}"
    )


def capture_cells(capture: dict) -> dict:
    """A capture's columns: ready's seconds, its .rdc's RenderDoc frame, MiB and sha256 prefix."""
    rdc = capture.get("rdc") or {}
    return {
        **capture,
        "readyS": (capture.get("ready") or {}).get("seconds"),
        "frame": rdc.get("frame"),
        "mib": round(rdc["bytes"] / 1024**2, 1) if "bytes" in rdc else None,
        "sha256": (rdc.get("sha256") or "")[:12],
    }


def page(found: dict, captures: list[dict]) -> str:
    """The run's page, from its record."""
    name = found["name"]
    status = found.get("status")
    out = [
        f"<h1>{e(name)}</h1>",
        f'<p class="muted">{e(found.get("kind"))}, {e(shown_mode(found))}, '
        f"{e(found.get('startedAt'))} to {e(found.get('endedAt'))}</p>",
        f'<p>Status <span class="{"ok" if status == "ok" else "bad"}">{e(status)}</span>'
        + (f": {e(found['reason'])}" if found.get("reason") else "")
        + "</p>",
    ]
    visual = found.get("kind") in record.VIEWED
    capture = found.get("kind") == record.CAPTURE
    if found.get("parts"):
        out.append(f"<p>A split session: {e(', '.join(found['parts']))}.</p>")
    if found.get("mode") is not None and found.get("calibration") is None and not visual:
        out.append("<p>Calibration null (plans/m2.md D40): no verdicts.</p>")
    if found.get("verdicts"):
        out.append(verdict_section(found["verdicts"]))
    entries = found.get("acceptance") or []
    if entries:
        shown_pass = {True: "pass", False: "FAIL", None: "waits"}
        rows = []
        for entry in entries:
            ev = entry.get("evidence") or {}
            word = shown_pass.get(entry["pass"], "?")
            why = ev.get("why") or ev.get("pending") or ev.get("notRun") or ""
            rows.append([e(entry["item"]), f'<span class="{word}">{word}</span>', e(why)])
        out.append("<h2>Acceptance</h2>" + table(["item", "verdict", "evidence"], rows))
    variants = found.get("variants") or []
    if variants and visual:  # each of its own pack, its options in full (run-record.md#record)
        rows = [
            [
                e(v.get("id")),
                e(v.get("role")),
                e(v.get("pack")),
                e(v.get("profile")),
                e(len(v.get("options") or {})),
                e(((v.get("effective") or {}).get("sha256") or "")[:16]),
            ]
            for v in variants
        ]
        headings = ["variant", "role", "pack", "profile", "options written", "effective sha256"]
        out.append("<h2>Variants</h2>" + table(headings, rows))
    elif variants:
        rows = []
        for v in variants:
            effective = v.get("effective") or {}
            moved = effective.get("fromBaseline")
            rows.append(
                [
                    e(v.get("id", v.get("pack"))),
                    e(v.get("role", "")),
                    e(v.get("profile")),
                    e(v.get("timers", "")),
                    e(json.dumps(moved, sort_keys=True) if moved else ""),
                ]
            )
        headings = ["variant", "role", "profile", "timers", "options off the baseline's"]
        out.append("<h2>Variants</h2>" + table(headings, rows))
    if visual:  # its frames are tiered by `compare`, which writes review.html beside this page
        captures = [capture_cells(c) if capture else pair_cells(c) for c in captures]
    if captures:
        columns = [*COLUMNS, ("part", "part")] if any("part" in c for c in captures) else COLUMNS
        columns = (CAPTURE_COLUMNS if capture else VISUAL_COLUMNS) if visual else columns
        rows, classes = [], []
        for c in captures:
            flags = e(", ".join(c.get("flags") or []))
            rows.append([number(c.get(key)) for _, key in columns] + [flags])
            classes.append("" if c.get("valid") else "invalid")
        headings = [h for h, _ in columns] + ["flags"]
        valid = sum(1 for c in captures if c.get("valid"))
        out.append(f"<h2>Captures</h2><p>{valid} of {len(captures)} valid.</p>")
        out.append(table(headings, rows, classes))
    identity = found.get("identity")
    if isinstance(identity, dict):
        rows = [[e(k), f"<code>{e(record.sha256_of(v)[:16])}</code>"] for k, v in identity.items()]
        out.append("<h2>Identity</h2>" + table(["key", "sha256 of its value"], rows))
    split = ((found.get("session") or {}).get("timeSplit")) or {}
    if split:
        rows = [[e(k), number(v)] for k, v in split.items()]
        out.append("<h2>Time</h2>" + table(["phase", "seconds"], rows))
    body = "".join(out)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(name)} report</title><style>{STYLE}</style></head><body>{body}</body></html>\n"
    )


def summary(found: dict, captures: list[dict]) -> list[str]:
    """The record in a few lines, from what the page shows: the status, the parts, the
    calibration, the verdicts as recorded (`compare` re-judges them), each acceptance item's entry
    (its why, when its evidence holds one), the captures valid and, per view with an invalid
    capture, how many and their flags."""
    out = [
        f"{PREFIX} {found['name']}: {found.get('kind')}, {shown_mode(found)}, "
        f"{found.get('startedAt')} to {found.get('endedAt')}",
        f"  status {found.get('status')}" + (f": {found['reason']}" if found.get("reason") else ""),
    ]
    parts = found.get("parts") or []
    visual = found.get("kind") in record.VIEWED
    if parts:
        out.append(f"  split session: {len(parts)} parts, {parts[0]} to {parts[-1]}")
    if found.get("mode") is not None and not visual:
        cid = found.get("calibration")
        out.append(f"  calibration {cid[:24]}..." if cid else "  calibration null: no verdicts")
    if found.get("kind") == record.CAPTURE:
        rdcs = [c["rdc"] for c in captures]
        mib = sum(r["bytes"] for r in rdcs) / 1024**2
        out.append(f"  .rdc: {len(rdcs)}, {mib:.1f} MiB under raw/ (`check L4` reads them)")
    elif visual:
        moving = [f"{c['view']}/{c['variant']}" for c in captures if "moving" in c["flags"]]
        out.append(f"  pairs moving: {', '.join(moving) or 'none'} (`optilux compare` tiers them)")
    judged = found.get("verdicts")
    if judged:
        twin = judged["twin"]
        inside = {True: "inside", False: "NOT inside", None: "not measured"}[twin["inside"]]
        delta = "" if twin.get("geoMeanDelta") is None else f"{twin['geoMeanDelta']:+.4f} %, "
        out.append(f"  verdicts as recorded: session {judged['session']}, twin {delta}{inside}")
        for c in judged["candidates"]:
            geo = "unjudged" if c["geoMeanDelta"] is None else f"{c['geoMeanDelta']:+.4f} %"
            beyond = ", ".join(r["view"] for r in c["views"] if r.get("beyond")) or "none"
            out.append(
                f"    {c['variant']}: {c['verdict']}, geo-mean {geo}; views beyond: {beyond}"
            )
    shown_pass = {True: "pass", False: "FAIL", None: "waits"}
    for entry in found.get("acceptance") or []:
        ev = entry.get("evidence") or {}
        why = ev.get("why") or ev.get("pending") or ev.get("notRun")
        word = shown_pass.get(entry["pass"], "?")
        out.append(f"  {entry['item']}: {word}" + (f": {why}" if why else ""))
    if captures:
        valid = sum(1 for c in captures if c.get("valid"))
        out.append(f"  captures: {valid} of {len(captures)} valid")
        views: dict[str, list[dict]] = {}
        for c in captures:
            views.setdefault(str(c.get("view")), []).append(c)
        for view, group in views.items():
            bad = [c for c in group if not c.get("valid")]
            if bad:
                flags = sorted({f for c in bad for f in c.get("flags") or []})
                shown_flags = f" ({', '.join(flags)})" if flags else ""
                out.append(f"    {view}: {len(bad)} of {len(group)} invalid{shown_flags}")
    return out


def report(root: Path, name: str) -> tuple[Path, list[str]]:
    """results/raw/<name>/report.html written from the record; its path and the summary."""
    found = record.read_record(root, name)
    split = found.get("split")
    if split:
        raise ReportError(
            f"{name} is part {split['part']} of session {split['session']}; fix: `optilux report "
            f"{split['session']}` (its session record joins the parts)"
        )
    captures = record.session_captures(root, found)
    text = page(found, captures)
    folder = root / record.RAW / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PAGE
    path.write_bytes(text.encode("utf-8"))
    return path, summary(found, captures)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", metavar="run", help="a run's name: results/records/<run>.json")


def run(args: argparse.Namespace) -> int:
    try:
        path, lines = report(REPO_ROOT, args.name)
    except (ReportError, record.RecordError, OSError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    where = shown(path, REPO_ROOT)
    if args.json:
        print(json.dumps({"ok": True, "page": where, "summary": lines}))
    else:
        print("\n".join([*lines, f"  page: {where}"]))
    return 0


VERB = Verb(
    name="report",
    help="one static HTML page per run from its record, under results/raw/<run>/",
    run=run,
    configure=configure,
    structured=True,
)
