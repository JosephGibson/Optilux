"""`verify records` (optilux/verbs/verify.py; plans/m2.md D51, F13) on fixture records of every
shape, on this repository's records, and through the CLI."""

import json
from pathlib import Path

import pytest

from optilux import REPO_ROOT, cli, record
from optilux.verbs import verify

IDENTITY = {key: {"sha256": key} for key in record.IDENTITY_KEYS}
EARLIER = {key: value for key, value in IDENTITY.items() if key != "harness"}
CID = "quick-" + "a" * 64
CAPTURE = {
    "index": 1,
    "pass": 2,
    "view": "v1",
    "variant": "baseline",
    "role": "baseline",
    "round": 1,
    "flags": [],
    "valid": True,
}


def base(name: str, kind: str = "measurement", **changes) -> dict:
    found = {
        "schema": 1,
        "name": name,
        "kind": kind,
        "spec": {"name": name},
        "notes": None,
        "status": "ok",
        "reason": None,
        "startedAt": "2026-10-13T01:00:00+00:00",
        "endedAt": "2026-10-13T01:03:00+00:00",
        "identity": IDENTITY,
        "recorded": {},
    }
    if kind != "acceptance":
        found.update(mode="quick", calibration=None, variants=[], captures=[CAPTURE])
    return {**found, **changes}


def acceptance(name: str, **changes) -> dict:
    items = [{"item": "A1", "pass": True, "evidence": {}}]
    return base(name, "acceptance", identity=EARLIER, variants=[], acceptance=items, **changes)


def judged(name: str, **changes) -> dict:
    verdicts = {"calibration": CID, "candidates": [], "twin": {"inside": True}}
    return base(name, calibration=CID, verdicts=verdicts, **changes)


def session(name: str, **changes) -> dict:
    found = judged(name, parts=[f"{name}-p1"], groups=[["v1"]], **changes)
    del found["captures"]
    return found


def part(name: str, session_name: str, **changes) -> dict:
    split = {"session": session_name, "part": 1, "parts": 1, "views": ["v1"]}
    return base(name, calibration=CID, split=split, **changes)


def write(root: Path, *records: dict) -> Path:
    folder = root / record.RECORDS
    folder.mkdir(parents=True, exist_ok=True)
    for found in records:
        (folder / f"{found['name']}.json").write_text(json.dumps(found), encoding="utf-8")
    return root


def test_records_of_every_shape_pass(tmp_path: Path) -> None:
    root = write(
        tmp_path,
        acceptance("m1-acceptance-1"),
        base("m2-budget-1"),
        judged("m2-judged-1"),
        session("m2-split-1"),
        part("m2-split-1-p1", "m2-split-1"),
        base("m2-failed-1", status="failed", reason="the quit exited 1", identity=None),
    )
    ledger = verify.check_records(root)
    assert (ledger.records, ledger.violations, ledger.reported) == (6, [], [])


BROKEN = [
    (lambda: {**base("m2-x-1"), "name": "m2-y-1"}, "name 'm2-y-1', its file says m2-x-1"),
    (lambda: base("m2-x-1", schema=2), "schema 2"),
    (lambda: base("m2-x-1", kind="bench"), "kind 'bench'"),
    (lambda: base("m2-x-1", identity=None), "an ok record without its identity"),
    (lambda: base("m2-x-1", status="failed"), "status failed without its reason"),
    (lambda: base("m2-x-1", identity={**IDENTITY, "gpu": {}}), "not run-record.md#identity's"),
    (lambda: base("m2-x-1", identity={**IDENTITY, "suite": {}}), "identity leaves suite empty"),
    (lambda: base("m2-x-1", captures=[{**CAPTURE, "valid": "yes"}]), "is no boolean"),
    (lambda: base("m2-x-1", captures=[{**CAPTURE, "role": "other"}]), "role 'other'"),
    (lambda: base("m2-x-1", captures=[{"index": 4}]), "capture 4 lacks pass"),
    (lambda: base("m2-x-1", mode="slow"), "mode 'slow'"),
    (lambda: base("m2-x-1", calibration="quick-1"), "is no calibration id"),
    (lambda: base("m2-x-1", captures=None), "no captures list"),
    (lambda: {**session("m2-x-1"), "captures": []}, "a split session holds captures"),
    (lambda: {**session("m2-x-1"), "parts": ["m2-x-1-p9"]}, "parts m2-x-1-p9 have no record"),
    (lambda: part("m2-x-1", "m2-s-1", verdicts={}), "a part holds verdicts"),
    (lambda: {**part("m2-x-1", "m2-s-1"), "split": {"session": "m2-s-1"}}, "split {'session'"),
    (lambda: {**judged("m2-x-1"), "calibration": None}, "verdicts not of the record's calibration"),
    (
        lambda: {
            **acceptance("m2-x-1"),
            "acceptance": [{"item": "A8", "pass": None, "evidence": {}}],
        },
        "a pass neither boolean nor null",
    ),
]


@pytest.mark.parametrize(("make", "says"), BROKEN)
def test_each_broken_record_is_a_violation(tmp_path: Path, make, says: str) -> None:
    folder = tmp_path / record.RECORDS
    folder.mkdir(parents=True)
    (folder / "m2-x-1.json").write_text(json.dumps(make()), encoding="utf-8")
    ledger = verify.check_records(tmp_path)
    assert any(says in v for v in ledger.violations), ledger.violations
    assert all(v.startswith(f"{record.RECORDS}/m2-x-1.json: ") for v in ledger.violations)


def test_an_aborted_run_of_m1s_items_holds_no_variants_and_passes(tmp_path: Path) -> None:
    """measure.orphan_record writes no variants for a run without a mode."""
    found = acceptance("m2-aborted-1", status="aborted", reason="killed")
    del found["variants"]
    assert verify.check_records(write(tmp_path, found)).violations == []


def test_a_file_that_is_no_json_is_a_violation(tmp_path: Path) -> None:
    (tmp_path / record.RECORDS).mkdir(parents=True)
    (tmp_path / record.RECORDS / "m2-x-1.json").write_bytes(b"{not json")
    assert "not UTF-8 JSON" in verify.check_records(tmp_path).violations[0]


def test_the_budget_refuses_a_measured_record_and_reports_an_acceptance_one(tmp_path) -> None:
    padding = "x" * verify.RECORD_BUDGET
    root = write(
        tmp_path,
        base("m2-big-1", notes=padding),
        acceptance("m1-big-1", notes=padding),
    )
    ledger = verify.check_records(root)
    assert len(ledger.violations) == 1 and "m2-big-1.json: 200," in ledger.violations[0]
    assert "over the 200,000-byte budget (D51)" in ledger.violations[0]
    assert len(ledger.reported) == 1 and ledger.reported[0].startswith("m1-big-1: 200,")


def test_this_repositorys_records_pass_and_m1s_full_acceptance_records_are_reported(capsys):
    """The exit's check (plans/m2.md M2.P07), and F13: m1-acceptance-9 and -10 at 238 KB."""
    ledger = verify.check_records(REPO_ROOT)
    assert ledger.violations == [] and ledger.records >= 15
    assert {r.split(":")[0] for r in ledger.reported} >= {"m1-acceptance-9", "m1-acceptance-10"}
    assert cli.main(["verify", "records"]) == 0
    assert "0 violations" in capsys.readouterr().out
    assert cli.main(["verify", "records", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
