"""`compare` and `report` (optilux/verbs/compare.py, report.py) on fixture records: compare's
refusals in order (no calibration, each identity key, the kind, the mode) and its verdicts
re-judged from the captures alone; report's static page from the record alone."""

import json
from pathlib import Path

import pytest

from optilux import cli, record, stats
from optilux.verbs import compare as compare_verb
from optilux.verbs import report as report_verb

IDENTITY = {key: {"sha256": f"{key}-0"} for key in record.IDENTITY_KEYS}
VIEWS = ["forest_noon", "nether_crimson", "end_dragon"]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A root with the repo's suite.json (compare reads its twin monitor)."""
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "suite.json").write_bytes((repo / "config" / "suite.json").read_bytes())
    (tmp_path / record.RECORDS).mkdir(parents=True)
    return tmp_path


def write_calibration(root: Path, identity: dict = IDENTITY, mode: str = "quick") -> dict:
    """20 null candidates within 0.3 % at the quick views: every threshold the 0.5 % floor."""
    digest = record.identity_hash(identity)
    nulls = [
        {
            "session": f"cal-{n // 2}",
            "twin": f"twin-{n % 2 + 1}",
            "ratios": {v: 1 + ((n % 7) - 3) / 1000 for v in VIEWS},
        }
        for n in range(20)
    ]
    data = {
        "schema": 1,
        "id": f"{mode}-{digest}",
        "generation": 1,
        "mode": mode,
        "createdAt": "2026-10-13T00:00:00+00:00",
        "identityHash": digest,
        "identity": identity,
        "resourcePacks": "standard",
        "views": VIEWS,
        "rounds": 1,
        "twinsPerSession": 2,
        "falseRate": 0.05,
        "floorPct": 0.5,
        "twinMonitor": {"window": 20, "maxExceed": 2},
        "baseline": {"pack": "pack.zip", "profile": "played"},
        "sessions": [f"cal-{n}" for n in range(10)],
        "nulls": nulls,
        "thresholds": {},
    }
    folder = root / record.CALIBRATIONS
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{data['id']}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def captures(cand: float, twin: float = 7.0) -> list[dict]:
    """A quick-mode session's measured pass at R 1: per view A, shadows off, A, the twin, A, the
    baselines at 7 ms; the warm-up pass's captures first."""
    found = [
        {
            "index": i + 1,
            "pass": 1,
            "view": v,
            "variant": "baseline",
            "role": "baseline",
            "round": 0,
        }
        for i, v in enumerate(VIEWS)
    ]
    for view in VIEWS:
        slots = (
            ("baseline", "baseline", 7.0),
            ("shadows-off", "candidate", cand),
            ("baseline", "baseline", 7.0),
            ("twin", "twin", twin),
            ("baseline", "baseline", 7.0),
        )
        for variant, role, busy in slots:
            found.append(
                {
                    "index": len(found) + 1,
                    "pass": 2,
                    "view": view,
                    "variant": variant,
                    "role": role,
                    "round": 1,
                    "gpuBusyMs": busy,
                    "frameTimeMs": round(busy + 0.01, 4),
                    "frames": 300,
                    "rows": 300,
                    "flags": [],
                    "valid": True,
                }
            )
    for warm in found[:3]:
        warm.update(gpuBusyMs=7.0, frameTimeMs=7.01, valid=True, flags=[])
    return found


def write_record(root: Path, name: str, cal: dict | None, found: list[dict], **changes) -> dict:
    """A measurement record as `run` writes it, judged when `cal` is given."""
    data = {
        "schema": 1,
        "name": name,
        "kind": "measurement",
        "spec": {"name": name, "kind": "measurement", "mode": "quick"},
        "notes": None,
        "status": "ok",
        "reason": None,
        "startedAt": "2026-10-13T01:00:00+00:00",
        "endedAt": "2026-10-13T01:03:00+00:00",
        "identity": IDENTITY,
        "recorded": {},
        "mode": "quick",
        "calibration": cal["id"] if cal else None,
        "variants": [
            {"id": "baseline", "role": "baseline", "profile": "played", "options": {}},
            {"id": "shadows-off", "role": "candidate", "profile": "played", "options": {}},
            {"id": "twin", "role": "twin", "profile": "played", "options": {}},
        ],
        "captures": found,
        "session": {"timeSplit": {"launch": 19.1, "measuredPass": 51.1}},
    }
    if cal is not None:
        judged = stats.judge(found, cal, "quick")
        judged["twinMonitor"] = stats.twin_monitor([False], 20, 2)
        data["verdicts"] = judged
    data.update(changes)
    (root / record.RECORDS / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def refusal(capsys, *argv: str) -> str:
    assert cli.main(["compare", *argv]) == 1
    return capsys.readouterr().err


def test_a_record_without_a_calibration_is_refused_naming_calibrate(root, capsys, monkeypatch):
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    write_record(root, "m2-null-1", None, captures(6.3))
    err = refusal(capsys, "m2-null-1")
    assert "names no calibration (calibration null, plans/m2.md D40" in err
    assert "fix: `optilux calibrate --mode quick`, then a measurement run that names" in err
    missing = "quick-" + "0" * 64
    err = refusal(capsys, "m2-null-1", "--calibration", missing)
    assert "fix: `optilux calibrate --mode quick`" in err


@pytest.mark.parametrize("key", record.IDENTITY_KEYS)
def test_a_record_of_another_identity_is_refused_naming_the_key(root, capsys, monkeypatch, key):
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    moved = {**IDENTITY, key: {"sha256": f"{key}-1"}}
    write_record(root, "m2-moved-1", None, captures(6.3), identity=moved, calibration=cal["id"])
    err = refusal(capsys, "m2-moved-1")
    assert f"differ in identity: {key}.sha256;" in err and "fix:" in err


def test_an_m1_record_without_harness_is_refused_on_that_key(root, capsys, monkeypatch) -> None:
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    m1 = {k: v for k, v in IDENTITY.items() if k != "harness"}
    write_record(root, "m1-like-1", None, [], identity=m1, kind="acceptance", mode=None)
    err = refusal(capsys, "m1-like-1", "--calibration", cal["id"])
    assert "differ in identity: harness (in one only)" in err


def test_two_identities_without_the_same_key_do_not_differ_on_it() -> None:
    m1 = {k: v for k, v in IDENTITY.items() if k != "harness"}
    assert record.identity_differences(m1, dict(m1)) == []
    assert record.identity_differences(m1, IDENTITY) == ["harness (in one only)"]


def test_the_kind_then_the_mode_are_checked_after_the_identity(root, capsys, monkeypatch):
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    write_record(root, "cal-quick-x-1", None, captures(7.0), kind="calibration")
    err = refusal(capsys, "cal-quick-x-1", "--calibration", cal["id"])
    assert "kind is calibration, which carries no verdicts" in err
    write_record(root, "m2-full-1", None, captures(6.3), mode="full")
    err = refusal(capsys, "m2-full-1", "--calibration", cal["id"])
    assert "m2-full-1's mode is full" in err and "fix: the full calibration" in err


def test_compare_re_judges_from_the_captures_and_agrees_with_the_record(root, capsys, monkeypatch):
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    write_record(root, "m2-shadows-1", cal, captures(6.3))
    result = compare_verb.compare(root, "m2-shadows-1", None)
    shadows = result["verdicts"]["candidates"][0]
    assert (shadows["verdict"], shadows["geoMeanDelta"]) == ("accept", -10.0)
    assert result["verdicts"]["twin"]["inside"] is True and result["sameAsRecord"] is True
    assert result["verdicts"]["twinMonitor"]["twins"] == 1  # its own twin, counted once
    assert cli.main(["compare", "m2-shadows-1"]) == 0
    out = capsys.readouterr().out
    assert "shadows-off: accept, geo-mean -10.0000 %" in out and "the same" in out
    assert "forest_noon: -10.0000 % (-0.7000 of 7.0 ms), threshold 0.5000 %  BEYOND" in out
    assert cli.main(["compare", "m2-shadows-1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_a_twin_beyond_makes_compare_inconclusive_too(root, monkeypatch) -> None:
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    write_record(root, "m2-noisy-1", None, captures(6.3, twin=7.1), calibration=cal["id"])
    result = compare_verb.compare(root, "m2-noisy-1", None)
    assert result["verdicts"]["session"] == "inconclusive"
    assert result["verdicts"]["candidates"][0]["verdict"] == "inconclusive"
    assert "sameAsRecord" not in result  # the record holds no verdicts of its own


def test_a_record_that_did_not_end_ok_or_ran_calibration_null_is_refused(root, monkeypatch):
    """After the identity, kind and mode: a run that did not end ok has no verdicts, nor one that
    ran calibration null (plans/m2.md D40: a budget run or the survey kept its own schedule)."""
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    write_record(root, "m2-failed-1", cal, captures(6.3), status="failed", reason="quit 1")
    with pytest.raises(compare_verb.CompareError, match=r"status is failed \(quit 1\): a run that"):
        compare_verb.compare(root, "m2-failed-1", None)
    write_record(root, "m2-null-2", None, captures(6.3), spec={"heap": True})
    with pytest.raises(compare_verb.CompareError, match="ran calibration null"):
        compare_verb.compare(root, "m2-null-2", cal["id"])


def test_a_second_a8_session_is_compared_under_its_first_sessions_calibration(root) -> None:
    cal = write_calibration(root)
    first = {"item": "A8", "pass": None, "evidence": {"calibration": "full-" + "b" * 64}}
    write_record(root, "m2-a8-1", None, [], kind="acceptance", acceptance=[first])
    spec = {"name": "m2-a8-2", "remeasures": "m2-a8-1"}
    item = {"item": "A8", "pass": True, "evidence": {"calibration": cal["id"]}}
    write_record(
        root, "m2-a8-2", cal, captures(7.0), kind="acceptance", spec=spec, acceptance=[item]
    )
    with pytest.raises(compare_verb.CompareError, match="re-measures an A8 session judged by"):
        compare_verb.compare(root, "m2-a8-2", None)


# report (plans/m2.md D50).


def test_report_writes_one_static_page_from_the_record(root, monkeypatch, capsys) -> None:
    monkeypatch.setattr(report_verb, "REPO_ROOT", root)
    cal = write_calibration(root)
    found = captures(6.3)
    found[1].update(valid=False, flags=["halves"])  # a warm-up capture: no verdict reads it
    write_record(root, "m2-shadows-1", cal, found, reason="a <b>reason</b> & more")
    assert cli.main(["report", "m2-shadows-1"]) == 0
    assert "results/raw/m2-shadows-1/report.html" in capsys.readouterr().out
    page = (root / record.RAW / "m2-shadows-1" / "report.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "<title>m2-shadows-1 report</title>" in page
    assert "a &lt;b&gt;reason&lt;/b&gt; &amp; more" in page  # escaped, never markup
    assert "Verdicts" in page and 'class="accept">accept' in page
    assert page.count('<tr class="invalid">') == 1 and "halves" in page
    assert "src=" not in page and "href=" not in page and "http" not in page  # no external asset
    assert "prefers-color-scheme: dark" in page


def test_report_shows_an_acceptance_records_items_and_a_null_calibration(root, monkeypatch):
    monkeypatch.setattr(report_verb, "REPO_ROOT", root)
    items = [
        {"item": "A8", "pass": None, "evidence": {"pending": "re-measure end_dragon"}},
        {"item": "A11", "pass": True, "evidence": {"why": "every residual inside"}},
    ]
    write_record(root, "m2-a8-1", None, captures(7.0), kind="acceptance", acceptance=items)
    page = report_verb.page(record.read_record(root, "m2-a8-1"), captures(7.0))
    assert 'class="waits">waits' in page and "re-measure end_dragon" in page
    assert 'class="pass">pass' in page and "Calibration null (plans/m2.md D40)" in page
    with pytest.raises(record.RecordError, match="no record"):
        report_verb.report(root, "m2-none-1")
