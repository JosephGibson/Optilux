"""`optilux verify <target>`: static checks. `docs`: the doc rules of optilux.docs_check.
`records`: every committed record parses against its kind (plans/m2.md D51, F13).

`records` reads results/records/*.json: each an object of the schema, named as its file, with a
kind, a status (a reason beside any but ok) and an identity of the record's era (null only when
it is not ok); an acceptance run's items; a measured run's mode, calibration, variants and
captures, a part's `split`, a split session's parts (each a record) and no captures, its
verdicts when it names a calibration. Measurement and calibration records stay within
RECORD_BUDGET bytes; an acceptance record over it is reported, never refused: committed records
are never edited. Kept out of the runner's import closure, so its rules never move the harness
identity (plans/m2.md D36). CI runs it, and the pre-commit hook when a record is staged.
"""

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, docs_check, record
from optilux.verbs import Verb

# run-record.md#record's budget, D51: ~200 KB a measurement or calibration record (frame-level
# samples live in results/raw/); M1's full acceptance records run to 238 KB (F13).
RECORD_BUDGET = 200_000
BUDGETED = ("measurement", "calibration")
# Records written before M2.P01 added `harness` (plans/m2.md D36) hold the other ten keys.
EARLIER_IDENTITY = tuple(key for key in record.IDENTITY_KEYS if key != "harness")
ROLES = ("baseline", "candidate", "twin")
CAPTURE_KEYS = ("index", "pass", "view", "variant", "role", "valid")
SPLIT_KEYS = ("session", "part", "parts", "views")


def configure(parser: argparse.ArgumentParser) -> None:
    targets = parser.add_subparsers(dest="target", metavar="<target>", title="targets")
    targets.required = True
    docs = targets.add_parser(
        "docs",
        help="doc sizes, TOC, cites, encoding and Status lines",
        description="Check every .md at the root, under docs/ (sources/ exempt) and .claude/.",
    )
    docs.add_argument("--json", action="store_true", help="print JSON instead of text")
    records = targets.add_parser(
        "records",
        help="every record parses against its kind, within its budget",
        description="Check results/records/*.json (plans/m2.md D51).",
    )
    records.add_argument("--json", action="store_true", help="print JSON instead of text")


def print_text(report: docs_check.Report) -> None:
    width = max(len(entry.file) for entry in report.files)
    print(f"{'file':<{width}}  {'bytes':>7}  {'cap':>7}  {'margin':>7}")
    for entry in report.files:
        cap = "-" if entry.cap is None else f"{entry.cap:,}"
        margin = "-" if entry.margin is None else f"{entry.margin:,}"
        print(f"{entry.file:<{width}}  {entry.size:>7,}  {cap:>7}  {margin:>7}")
    for violation in report.violations:
        print(violation.text())
    count = len(report.violations)
    print(f"optilux verify docs: {len(report.files)} files, {count} violations")


def run_docs(args: argparse.Namespace) -> int:
    report = docs_check.check_tree(REPO_ROOT)
    if args.json:
        files = [{**asdict(entry), "margin": entry.margin} for entry in report.files]
        violations = [asdict(violation) for violation in report.violations]
        print(json.dumps({"ok": not violations, "files": files, "violations": violations}))
    else:
        print_text(report)
    return 1 if report.violations else 0


# Records (D51).


@dataclass
class Ledger:
    """verify records' findings: the records read, each violation, each record over the budget
    that is only reported (an acceptance record)."""

    records: int = 0
    violations: list[str] = field(default_factory=list)
    reported: list[str] = field(default_factory=list)


def identity_problem(found: dict) -> str | None:
    identity = found.get("identity")
    if identity is None:
        return "an ok record without its identity" if found.get("status") == "ok" else None
    if not isinstance(identity, dict):
        return "identity is no object"
    if tuple(identity) not in (record.IDENTITY_KEYS, EARLIER_IDENTITY):
        return f"identity keys {list(identity)}, not run-record.md#identity's"
    empty = [key for key, value in identity.items() if value in (None, "", [], {})]
    return f"identity leaves {', '.join(empty)} empty" if empty else None


def capture_problem(capture: Any) -> str | None:
    if not isinstance(capture, dict):
        return "a capture is no object"
    missing = [key for key in CAPTURE_KEYS if key not in capture]
    if missing:
        return f"capture {capture.get('index')} lacks {', '.join(missing)}"
    if capture["pass"] not in (1, 2) or capture["role"] not in ROLES:
        return f"capture {capture['index']}: pass {capture['pass']!r}, role {capture['role']!r}"
    if not isinstance(capture["valid"], bool):
        return f"capture {capture['index']}: valid {capture['valid']!r} is no boolean"
    if "unsummarized" not in capture and not isinstance(capture.get("flags"), list):
        return f"capture {capture['index']} has neither flags nor why it has no numbers"
    return None


def measured_problems(root: Path, found: dict) -> list[str]:
    """A measured record's own fields by its shape: a split session's, a part's, a launch's."""
    problems = []
    if found.get("mode") not in record.MODES:
        problems.append(f"mode {found.get('mode')!r}")
    cid = found.get("calibration")
    if cid is not None and not (isinstance(cid, str) and record.CALIBRATION_ID.fullmatch(cid)):
        problems.append(f"calibration {cid!r} is no calibration id")
    if not isinstance(found.get("variants"), list):
        problems.append("no variants list")
    if "parts" in found:
        parts = found["parts"]
        if not isinstance(parts, list) or not isinstance(found.get("groups"), list):
            return [*problems, "a split session without its parts and groups lists"]
        if "captures" in found:
            problems.append("a split session holds captures (its parts keep them)")
        absent = [name for name in parts if name not in record.record_names(root)]
        if absent:
            problems.append(f"parts {', '.join(map(str, absent))} have no record")
    else:
        captures = found.get("captures")
        if not isinstance(captures, list):
            return [*problems, "no captures list"]
        problems += [p for c in captures if (p := capture_problem(c)) is not None][:3]
        split = found.get("split")
        if split is not None and (not isinstance(split, dict) or tuple(split) != SPLIT_KEYS):
            problems.append(f"split {split!r}: not {', '.join(SPLIT_KEYS)}")
    judged = found.get("verdicts")
    if judged is not None:
        if found.get("split") is not None:
            problems.append("a part holds verdicts (its session record does)")
        elif not isinstance(judged, dict) or judged.get("calibration") != cid:
            problems.append("verdicts not of the record's calibration")
        elif not isinstance(judged.get("candidates"), list) or "twin" not in judged:
            problems.append("verdicts without candidates and the twin")
    return problems


def record_problems(root: Path, name: str, text: bytes) -> tuple[list[str], str | None]:
    """One record's violations, and its report when it is an acceptance record over the
    budget."""
    try:
        found = json.loads(text.decode("utf-8"))
    except ValueError as error:
        return [f"not UTF-8 JSON: {error}"], None
    if not isinstance(found, dict):
        return ["no JSON object"], None
    problems = []
    if found.get("schema") != record.SCHEMA:
        problems.append(f"schema {found.get('schema')!r}, not {record.SCHEMA}")
    if found.get("name") != name:
        problems.append(f"name {found.get('name')!r}, its file says {name}")
    kind, status = found.get("kind"), found.get("status")
    if kind not in record.KINDS:
        return [*problems, f"kind {kind!r}"], None
    if status not in record.STATUSES:
        problems.append(f"status {status!r}")
    elif status != "ok" and not (isinstance(found.get("reason"), str) and found["reason"]):
        problems.append(f"status {status} without its reason")
    if not isinstance(found.get("startedAt"), str) or not isinstance(found.get("spec"), dict):
        problems.append("no startedAt or spec")
    problem = identity_problem(found)
    if problem:
        problems.append(problem)
    if kind == "acceptance" or "acceptance" in found:
        try:
            record.check_acceptance(found.get("acceptance"))
        except record.RecordError as error:
            problems.append(str(error))
    if found.get("mode") is not None or kind != "acceptance":
        problems += measured_problems(root, found)
    elif "variants" in found and not isinstance(found["variants"], list):
        problems.append("variants is no list")  # an aborted run of M1's items holds none
    over = len(text) > RECORD_BUDGET
    if over and kind in BUDGETED:
        problems.append(f"{len(text):,} bytes, over the {RECORD_BUDGET:,}-byte budget (D51)")
    report = f"{name}: {len(text):,} bytes ({kind})" if over and kind not in BUDGETED else None
    return problems, report


def check_records(root: Path) -> Ledger:
    """Every record under results/records/ checked (record_problems)."""
    ledger = Ledger()
    for name in record.record_names(root):
        ledger.records += 1
        path = root / record.RECORDS / f"{name}.json"
        if not record.NAME.fullmatch(name):
            ledger.violations.append(f"{record.RECORDS}/{path.name}: no run name")
            continue
        problems, report = record_problems(root, name, path.read_bytes())
        ledger.violations += [f"{record.RECORDS}/{path.name}: {p}" for p in problems]
        if report is not None:
            ledger.reported.append(report)
    return ledger


def ledger_line(ledger: Ledger) -> str:
    line = f"optilux verify records: {ledger.records} records, {len(ledger.violations)} violations"
    if ledger.reported:
        line += (
            f"; over the {RECORD_BUDGET:,}-byte budget, reported (acceptance records are never "
            f"edited): {'; '.join(ledger.reported)}"
        )
    return line


def run_records(args: argparse.Namespace) -> int:
    ledger = check_records(REPO_ROOT)
    if args.json:
        print(json.dumps({"ok": not ledger.violations, **asdict(ledger)}))
    else:
        for violation in ledger.violations:
            print(violation)
        print(ledger_line(ledger))
    return 1 if ledger.violations else 0


TARGETS = {"docs": run_docs, "records": run_records}


def run(args: argparse.Namespace) -> int:
    return TARGETS[args.target](args)


VERB = Verb(
    name="verify",
    help="static checks (docs: the doc rules; records: the run records)",
    run=run,
    configure=configure,
)
