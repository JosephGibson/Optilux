"""`optilux report <run> [--json]` (docs/plans/m2.md D50): one static HTML page per run from its
record alone, results/raw/<run>/report.html, with no external asset; the record stays the ledger
(a committed page would copy what it holds).

The page: the run's status and reason, its verdicts as `run` wrote them (each candidate's, the
twin's check, the twin monitor), A8's and A11's entries, the variants, every capture with its
summaries and validity flags, the identity's keys and the session's time split.
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


def page(found: dict, captures: list[dict]) -> str:
    """The run's page, from its record."""
    name = found["name"]
    status = found.get("status")
    out = [
        f"<h1>{e(name)}</h1>",
        f'<p class="muted">{e(found.get("kind"))}, mode {e(found.get("mode") or "none")}, '
        f"{e(found.get('startedAt'))} to {e(found.get('endedAt'))}</p>",
        f'<p>Status <span class="{"ok" if status == "ok" else "bad"}">{e(status)}</span>'
        + (f": {e(found['reason'])}" if found.get("reason") else "")
        + "</p>",
    ]
    if found.get("mode") is not None and found.get("calibration") is None:
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
    if variants:
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
    if captures:
        rows, classes = [], []
        for c in captures:
            rows.append(
                [number(c.get(key)) for _, key in COLUMNS] + [e(", ".join(c.get("flags") or []))]
            )
            classes.append("" if c.get("valid") else "invalid")
        headings = [h for h, _ in COLUMNS] + ["flags"]
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


def report(root: Path, name: str) -> Path:
    """results/raw/<name>/report.html written from the record; its path."""
    found = record.read_record(root, name)
    text = page(found, found.get("captures") or [])
    folder = root / record.RAW / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PAGE
    path.write_bytes(text.encode("utf-8"))
    return path


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", metavar="run", help="a run's name: results/records/<run>.json")


def run(args: argparse.Namespace) -> int:
    try:
        path = report(REPO_ROOT, args.name)
    except (ReportError, record.RecordError, OSError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    where = shown(path, REPO_ROOT)
    print(json.dumps({"ok": True, "page": where}) if args.json else f"{PREFIX}: {where}")
    return 0


VERB = Verb(
    name="report",
    help="one static HTML page per run from its record, under results/raw/<run>/",
    run=run,
    configure=configure,
    structured=True,
)
