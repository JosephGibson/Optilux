"""`optilux verify <target>`: static checks. `docs`: the doc rules of optilux.docs_check.
`records`: every committed record parses against its kind (plans/m2.md D51, F13). `similarity`:
shader/'s GLSL against the studied reference copy (plans/m3.md D55), `--controls` the figures
that set its threshold.

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
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, docs_check, platform, record, similarity
from optilux.verbs import Verb
from optilux.verbs.install import REFERENCE, SIMILARITY
from optilux.verbs.pack import PACK_DIR

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
    similar = targets.add_parser(
        "similarity",
        help="shader/'s GLSL against the studied reference copy",
        description=(
            "Exit 1 on a run of t normalized tokens or more that a GLSL file under shader/ "
            "shares with the studied copy under reference/ (config/similarity.json; "
            "plans/m3.md D55). --controls recomputes the figures that set t instead."
        ),
    )
    similar.add_argument(
        "--controls",
        action="store_true",
        help="the studied copy against itself and the control pack against it",
    )
    similar.add_argument("--json", action="store_true", help="print JSON instead of text")


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


# Similarity (docs/shader.md#policy, plans/m3.md D55).

# The pack's source: what `pack build` zips and the pre-commit hook reads from the index.
SHADER = PACK_DIR
POLICY = "docs/shader.md#policy"


class SimilarityError(RuntimeError):
    """The check cannot run: its config or a reference copy is missing or off its pin."""


@dataclass
class Similarity:
    """One check: the GLSL files and tokens on each side, k and t, every match of t or more."""

    files: int
    tokens: int
    reference: str
    references: int
    k: int
    t: int
    flagged: list[similarity.Match]

    def line(self) -> str:
        return (
            f"optilux verify similarity: {self.files} GLSL files under {SHADER}/ ({self.tokens} "
            f"tokens) against {self.references} of {self.reference} (k {self.k}, t {self.t}): "
            f"{len(self.flagged)} matches of {self.t} tokens or more"
        )


def similarity_config(root: Path) -> dict:
    """The working tree's config/similarity.json, parsed and checked (parse_config)."""
    try:
        text = (root / SIMILARITY).read_text(encoding="utf-8")
    except OSError as error:
        raise SimilarityError(f"{SIMILARITY}: {error}; fix: restore it from git") from None
    return parse_config(text)


def parse_config(text: str) -> dict:
    """config/similarity.json's text with k and t checked (whole numbers, 1 <= k <= t) and the
    studied copy's pin (its folder a plain name, its tree hash and file count)."""
    try:
        config = json.loads(text)
    except ValueError as error:
        raise SimilarityError(f"{SIMILARITY}: {error}; fix: restore it from git") from None
    if not isinstance(config, dict):
        raise SimilarityError(f"{SIMILARITY}: no JSON object; fix: restore it from git")
    k, t = config.get("k"), config.get("t")
    if not (isinstance(k, int) and isinstance(t, int) and 1 <= k <= t):
        raise SimilarityError(f"{SIMILARITY}: k {k!r} and t {t!r}; fix: whole numbers, k <= t")
    pin_of(config, "studied")
    return config


def pin_of(config: dict, role: str) -> dict:
    """A copy's pin in config/similarity.json: its folder under reference/, tree hash and
    file count."""
    pin = config.get(role)
    if not (
        isinstance(pin, dict)
        and isinstance(pin.get("folder"), str)
        and platform.plain_name(pin["folder"])
        and isinstance(pin.get("treeSha256"), str)
        and isinstance(pin.get("files"), int)
    ):
        raise SimilarityError(
            f"{SIMILARITY} {role}: no plain folder, treeSha256 and files; fix: restore it from git"
        )
    return pin


def reference_texts(root: Path, pin: dict) -> dict[str, str]:
    """A reference copy's GLSL texts by their path from the repository root, read only after
    its tree hash matches its pin (record.tree_hash; plans/m3.md D54), so an edit under
    reference/ never passes as Complementary's code."""
    home = root / REFERENCE / pin["folder"]
    shown = f"{REFERENCE}/{pin['folder']}/"
    if not home.is_dir():
        raise SimilarityError(f"{shown} is missing; fix: `uv run optilux install` unpacks it")
    try:
        digest, count = record.tree_hash(home)
    except record.RecordError as error:  # a link or an unreadable file: no copy install made
        raise SimilarityError(
            f"{shown}: {error}; fix: delete the folder and run `uv run optilux install`"
        ) from None
    if (digest, count) != (pin["treeSha256"], pin["files"]):
        raise SimilarityError(
            f"{shown}: tree sha256 {digest} ({count} files) differs from its pin "
            f"{pin['treeSha256']} ({pin['files']} files); fix: delete the folder and run "
            "`uv run optilux install`"
        )
    return {
        f"{shown}{path.relative_to(home).as_posix()}": text(path.read_bytes())
        for path in sorted(home.rglob("*"))
        if path.is_file() and similarity.is_source(path.name)
    }


def text(data: bytes) -> str:
    # A byte outside UTF-8 sits in a comment in practice; as U+FFFD elsewhere it is one token.
    return data.decode("utf-8", errors="replace")


def shader_texts(root: Path) -> dict[str, str]:
    """The working tree's files under shader/, by their path from the repository root."""
    folder = root / SHADER
    if not folder.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): text(path.read_bytes())
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def check_similarity(
    root: Path, texts: Mapping[str, str], config: dict | None = None
) -> Similarity:
    """The GLSL files among `texts` (the working tree's shader/ or the index's) against the
    studied copy under root, winnowed with w = t - k + 1: every run of t tokens or more is
    flagged. `config` is the parsed config/similarity.json to judge by (the hook's is the
    index's); None reads root's."""
    config = config if config is not None else similarity_config(root)
    k, t = config["k"], config["t"]
    candidates = similarity.sources(texts)
    references = similarity.sources(reference_texts(root, config["studied"]))
    found = similarity.matches(candidates, references, k, t - k + 1)
    return Similarity(
        files=len(candidates),
        tokens=sum(len(source.tokens) for source in candidates),
        reference=f"{REFERENCE}/{config['studied']['folder']}/",
        references=len(references),
        k=k,
        t=t,
        flagged=[match for match in found if match.length >= t],
    )


def flagged_text(match: similarity.Match, t: int) -> str:
    return f"{match.text()}, t {t}; fix: write it fresh in your own structure ({POLICY})"


def control_figures(root: Path) -> dict:
    """The figures that set t (D55): the studied copy against itself, winnowed as the check
    runs, flags every file of t tokens or more; the control pack against the studied copy over
    every k-gram (w = 1), so its longest run is exact whenever it reaches k tokens."""
    config = similarity_config(root)
    k, t = config["k"], config["t"]
    studied = similarity.sources(reference_texts(root, config["studied"]))
    control = similarity.sources(reference_texts(root, pin_of(config, "control")))
    long = {source.name for source in studied if len(source.tokens) >= t}
    own = similarity.matches(studied, studied, k, t - k + 1)
    flagged = {match.candidate for match in own if match.length >= t}
    shared = similarity.matches(control, studied, k, 1)
    return {
        "self": {"files": len(long), "flagged": len(long & flagged)},
        "control": {
            "longest": shared[0].length if shared else 0,
            "at": shared[0].text() if shared else None,
        },
    }


def control_problems(figures: dict, config: dict) -> list[str]:
    """The rule the figures must keep, and their difference from config/similarity.json."""
    t = config["t"]
    problems = []
    if figures["self"]["flagged"] != figures["self"]["files"]:
        problems.append(
            f"the studied copy against itself flags {figures['self']['flagged']} of its "
            f"{figures['self']['files']} files of {t} tokens or more, not every one"
        )
    if figures["control"]["longest"] >= t:
        problems.append(
            f"the control pack shares {figures['control']['longest']} tokens with the studied "
            f"copy, not under t {t}: a rule change is the user's (plans/m3.md section 7)"
        )
    recorded = config.get("controls") or {}
    for group, values in figures.items():
        for key, value in values.items():
            if (recorded.get(group) or {}).get(key) != value:
                problems.append(
                    f"controls.{group}.{key} is {(recorded.get(group) or {}).get(key)!r} in "
                    f"{SIMILARITY}, measured {value!r}; fix: record the measured figure"
                )
    return problems


def run_similarity(args: argparse.Namespace) -> int:
    try:
        if args.controls:
            config = similarity_config(REPO_ROOT)
            figures = control_figures(REPO_ROOT)
            problems = control_problems(figures, config)
            if args.json:
                print(json.dumps({"ok": not problems, **figures, "problems": problems}))
                return 1 if problems else 0
            own, shared = figures["self"], figures["control"]
            print(
                f"self: {own['flagged']} of {own['files']} files of {config['t']} tokens or "
                "more flagged"
            )
            print(f"control: longest {shared['longest']} tokens, {shared['at']}")
            for problem in problems:
                print(problem)
            print(f"optilux verify similarity --controls: {len(problems)} problems")
            return 1 if problems else 0
        found = check_similarity(REPO_ROOT, shader_texts(REPO_ROOT))
    except SimilarityError as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}))
        else:
            print(f"optilux verify similarity: {error}")
        return 1
    if args.json:
        print(json.dumps({"ok": not found.flagged, **asdict(found)}))
    else:
        for match in found.flagged:
            print(flagged_text(match, found.t))
        print(found.line())
    return 1 if found.flagged else 0


TARGETS = {"docs": run_docs, "records": run_records, "similarity": run_similarity}


def run(args: argparse.Namespace) -> int:
    return TARGETS[args.target](args)


VERB = Verb(
    name="verify",
    help="static checks (docs: the doc rules; records: the run records; similarity: shader/)",
    run=run,
    configure=configure,
)
