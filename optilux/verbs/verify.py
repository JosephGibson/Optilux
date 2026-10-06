"""`optilux verify <target>`: static checks. `docs`: the doc rules of optilux.docs_check."""

import argparse
import json
from dataclasses import asdict

from optilux import REPO_ROOT, docs_check
from optilux.verbs import Verb


def configure(parser: argparse.ArgumentParser) -> None:
    targets = parser.add_subparsers(dest="target", metavar="<target>", title="targets")
    targets.required = True
    docs = targets.add_parser(
        "docs",
        help="doc sizes, TOC, cites, encoding and Status lines",
        description="Check every .md at the root, under docs/ (sources/ exempt) and .claude/.",
    )
    docs.add_argument("--json", action="store_true", help="print JSON instead of text")


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


TARGETS = {"docs": run_docs}


def run(args: argparse.Namespace) -> int:
    return TARGETS[args.target](args)


VERB = Verb(name="verify", help="static checks (docs: the doc rules)", run=run, configure=configure)
