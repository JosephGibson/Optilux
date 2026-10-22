"""A visual run's frames judged by tier (optilux/visual.py, docs/plans/m3.md D63): the tiers on
fixture PNGs (equal, one level off, a FLIP case either side of close, a large change), suite.json
fidelity's thresholds; `compare` on fixture records: each pair, each candidate against the
baseline, each variant against another run's, its refusals in order, the frames held to their
recorded sha256, and review.html beside report.html."""

import hashlib
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from conftest import copy_config
from PIL import Image

from optilux import REPO_ROOT, cli, record, visual
from optilux.verbs import compare as compare_verb

SUITE = json.loads((REPO_ROOT / "config" / "suite.json").read_text(encoding="utf-8"))
FIDELITY = visual.fidelity(SUITE)
H, W = 96, 128
Y, X = np.mgrid[0:H, 0:W]


def base() -> np.ndarray:
    """A frame with gradients and seeded noise, RGBA as the game writes its PNGs."""
    rng = np.random.default_rng(263)
    frame = np.zeros((H, W, 4), np.uint8)
    frame[..., 0] = (X * 2) % 256
    frame[..., 1] = (Y * 2) % 256
    frame[..., 2] = ((X + Y) * 3 + rng.integers(0, 24, (H, W))) % 256
    frame[..., 3] = 255
    return frame


def added(frame: np.ndarray, where: np.ndarray, rgb: tuple[int, int, int]) -> np.ndarray:
    found = frame.astype(np.int16)
    found[where, :3] += np.array(rgb, np.int16)
    return np.clip(found, 0, 255).astype(np.uint8)


def png(frame: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(frame, "RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


BASE = base()
# One level off on a stripe; a patch of 6 levels (FLIP and SSIM inside close); 2 levels over half
# the frame (SSIM and FLIP's 99.9th percentile inside close, its mean not); a 2-pixel spot changed
# hard (the mean and SSIM inside close, the 99.9th percentile not); half inverted.
NEAR = added(BASE, X < 20, (1, 0, 0))
PATCH = added(BASE, (X > 40) & (X < 44) & (Y > 40) & (Y < 44), (6, 0, 0))
WASH = added(BASE, X > 60, (2, 2, 2))
SPOT = added(BASE, (X >= 60) & (X < 62) & (Y >= 40) & (Y < 42), (120, -120, 120))
INVERTED = np.where((Y < 48)[..., None], 255 - BASE, BASE).astype(np.uint8)
INVERTED[..., 3] = 255
# A flat grey half, and a faint checkerboard laid on it: FLIP barely sees it, SSIM does.
FLAT = BASE.copy()
FLAT[:, 64:, :3] = 128
CHECKER = added(FLAT, (X >= 64) & (X < 112) & (Y < 48) & ((X + Y) % 2 == 0), (2, 2, 2))
CHECKER = added(CHECKER, (X >= 64) & (X < 112) & (Y < 48) & ((X + Y) % 2 == 1), (-2, -2, -2))


def judged(test: np.ndarray, reference: np.ndarray = BASE) -> dict:
    """The tier of `test` against `reference`, each through a PNG and back."""
    return visual.tier(visual.decode(png(reference), "a"), visual.decode(png(test), "b"), FIDELITY)


def test_the_tiers_on_fixture_pngs() -> None:
    assert judged(BASE) == {"tier": "identical", "maxAbsDiff": 0, "pixels": 0}
    assert judged(NEAR) == {"tier": "near", "maxAbsDiff": 1, "pixels": 20 * H}
    close = judged(PATCH)
    assert (close["tier"], close["maxAbsDiff"], close["pixels"]) == ("close", 6, 9)
    assert close["meanFlip"] <= 0.005 and close["p999Flip"] <= 0.10 and close["ssim"] >= 0.995
    wash = judged(WASH)  # FLIP's mean alone keeps it from close
    assert wash["tier"] == "review" and wash["maxAbsDiff"] == 2
    assert wash["meanFlip"] > 0.005 and wash["p999Flip"] <= 0.10 and wash["ssim"] >= 0.995
    spot = judged(SPOT)  # FLIP's 99.9th percentile alone
    assert spot["tier"] == "review" and spot["pixels"] == 4
    assert spot["meanFlip"] <= 0.005 and spot["p999Flip"] > 0.10 and spot["ssim"] >= 0.995
    checker = judged(CHECKER, FLAT)  # SSIM alone
    assert checker["tier"] == "review" and checker["maxAbsDiff"] == 2
    assert checker["meanFlip"] <= 0.005 and checker["p999Flip"] <= 0.10 and checker["ssim"] < 0.995
    large = judged(INVERTED)
    assert large["tier"] == "review" and large["maxAbsDiff"] == 255 and large["ssim"] < 0.995
    small = visual.decode(png(BASE[:48]), "c")
    assert visual.tier(BASE, small, FIDELITY) == {
        "tier": "review",
        "why": "sizes 128x96 and 128x48",
    }


def test_fidelitys_thresholds_come_from_suite_json() -> None:
    assert visual.Fidelity(1, 0.005, 0.1, 0.995, SUITE["fidelity"]["flip"]["ppd"]) == FIDELITY
    tighter = json.loads(json.dumps(SUITE))
    tighter["fidelity"]["close"]["meanFlip"] = 0.00001
    found = visual.tier(BASE, PATCH, visual.fidelity(tighter))
    assert found["tier"] == "review"  # the same pair, judged by the suite's numbers
    for section, key, value in (
        ("flip", "ppd", 0),  # flip-evaluator exits the process on a ppd at 0
        ("near", "maxAbsDiff", 1.0),
        ("close", "minSsim", -0.5),
        ("close", "meanFlip", "0.005"),
    ):
        bad = json.loads(json.dumps(SUITE))
        bad["fidelity"][section][key] = value
        with pytest.raises(visual.VisualError, match="maxAbsDiff a whole number from 0"):
            visual.fidelity(bad)
    del tighter["fidelity"]["near"]
    with pytest.raises(visual.VisualError, match="fidelity lacks 'near'; fix"):
        visual.fidelity(tighter)
    with pytest.raises(visual.VisualError, match="no image pillow reads"):
        visual.decode(b"GIF89a", "x.png")


# `compare` on fixture records.

VIEWS = ("forest_noon", "nether_crimson")
IDENTITY = {key: {"sha256": key} for key in record.IDENTITY_KEYS}


def write_visual(root: Path, name: str, frames: dict, **changes) -> dict:
    """A visual record whose pairs are `frames` ((view, variant) -> two arrays), its PNGs under
    results/raw/<name>/frames/ as the run writes them."""
    variants = list(dict.fromkeys(variant for _, variant in frames))
    captures = []
    for index, ((view, variant), pair) in enumerate(frames.items(), start=1):
        shown = []
        for n, frame in enumerate(pair, start=1):
            path = f"frames/{view}/{variant}/attempt-001/frame-{n:05d}.png"
            data = png(frame)
            target = root / record.RAW / name / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            stamps = {"frameIndex": 100 * n, "sinceReload": 90 * n, "qpcNs": n, "swapQpcNs": n}
            shown.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), **stamps})
        moving = shown[0]["sha256"] != shown[1]["sha256"]
        flags = ["moving"] if moving else []
        captures.append(
            {"index": index, "view": view, "variant": variant, "frames": shown}
            | {"flags": flags, "valid": True}
        )
    found = {
        "schema": record.SCHEMA,
        "name": name,
        "kind": "visual",
        "status": "ok",
        "reason": None,
        "identity": IDENTITY,
        "mode": "quick",
        "variants": [
            {"id": v, "role": "baseline" if i == 0 else "candidate"} for i, v in enumerate(variants)
        ],
        "captures": captures,
        **changes,
    }
    path = root / record.RECORDS / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(found), encoding="utf-8")
    return found


@pytest.fixture
def visual_root(tmp_path: Path) -> Path:
    """A root with the repo's config and two visual records of one identity: the hello pack's
    pairs equal and a moving reference pack in the first, the hello pack alone in the second with
    one view's frame a patch off."""
    root = tmp_path / "root"
    copy_config(root)
    first = {}
    for view in VIEWS:
        first[(view, "hello")] = (BASE, BASE)
        first[(view, "unbound")] = (INVERTED, WASH)
    write_visual(root, "m3-visual-a", first)
    second = {("forest_noon", "hello"): (BASE, BASE), ("nether_crimson", "hello"): (PATCH, PATCH)}
    write_visual(root, "m3-visual-b", second)
    return root


def test_compare_tiers_each_pair_and_each_candidate_against_the_baseline(
    visual_root, monkeypatch, capsys
) -> None:
    root = visual_root
    monkeypatch.setattr(compare_verb, "REPO_ROOT", root)
    assert cli.main(["compare", "m3-visual-a"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == "optilux compare m3-visual-a: visual, quick mode, variants hello, unbound"
    assert cli.main(["compare", "m3-visual-a", "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["ok"] is True and shown["kind"] == "visual" and len(shown["items"]) == 6
    assert cli.main(["compare", "m3-visual-a", "--calibration", "quick-" + "0" * 64]) == 1
    assert "drop --calibration" in capsys.readouterr().err
    result = compare_verb.compare(root, "m3-visual-a", None)
    tiers = [(i["view"], i["kind"], i["variant"], i["tier"]["tier"]) for i in result["items"]]
    assert tiers == [
        (view, kind, variant, tier)
        for view in VIEWS
        for kind, variant, tier in (
            ("pair", "hello", "identical"),
            ("pair", "unbound", "review"),
            ("baseline", "unbound", "review"),
        )
    ]
    lines = visual.lines(result)
    assert lines[0] == "optilux compare m3-visual-a: visual, quick mode, variants hello, unbound"
    assert lines[1:4] == [
        "  forest_noon:",
        "    hello pair: identical",
        lines[3],
    ] and lines[3].startswith("    unbound pair: REVIEW (max |d| 255,")
    assert lines[-1] == "  page: results/raw/m3-visual-a/review.html"
    page = (root / record.RAW / "m3-visual-a" / "review.html").read_text(encoding="utf-8")
    for view in VIEWS:
        for variant in ("hello", "unbound"):
            src = f"frames/{view}/{variant}/attempt-001/frame-00001.png"
            assert f'<img src="{src}"' in page
        # A pair that moved shows its second frame too; one that repeats, its first alone.
        assert f'<img src="frames/{view}/unbound/attempt-001/frame-00002.png"' in page
        assert f'<img src="frames/{view}/hello/attempt-001/frame-00002.png"' not in page
    assert page.count("<figure>") == 6 and "frame 2 of its pair" in page
    assert "unbound vs hello" in page and "http" not in page


def test_compare_against_another_run_tiers_each_variant_against_itself(visual_root) -> None:
    root = visual_root
    result = compare_verb.compare(root, "m3-visual-b", None, "m3-visual-a")
    against = [(i["view"], i["tier"]["tier"]) for i in result["items"] if i["kind"] == "against"]
    assert against == [("forest_noon", "identical"), ("nether_crimson", "close")]
    lines = visual.lines(result)
    assert lines[0].endswith("variants hello; against m3-visual-a")
    # The other run's pairs this one lacks are named, never left out unsaid.
    assert result["unmatched"] == {
        "m3-visual-b": [],
        "m3-visual-a": ["forest_noon/unbound", "nether_crimson/unbound"],
    }
    assert lines[1] == (
        "  unmatched (no tier): only in m3-visual-a: forest_noon/unbound, nether_crimson/unbound"
    )
    page = (root / record.RAW / "m3-visual-b" / "review.html").read_text(encoding="utf-8")
    other = "../m3-visual-a/frames/nether_crimson/hello/attempt-001/frame-00001.png"
    assert f'<img src="{other}"' in page and "(m3-visual-a)" in page


def test_compares_refusals_name_their_fix(visual_root) -> None:
    root = visual_root

    def refused(name: str, calibration: str | None = None, against: str | None = None) -> str:
        with pytest.raises(compare_verb.CompareError) as error:
            compare_verb.compare(root, name, calibration, against)
        assert "fix:" in str(error.value)
        return str(error.value)

    assert "drop --calibration" in refused("m3-visual-a", "quick-" + "0" * 64)
    path = root / record.RECORDS / "m2-measured.json"
    path.write_text(json.dumps({"name": "m2-measured", "kind": "measurement"}), encoding="utf-8")
    assert "drop --against" in refused("m2-measured", against="m3-visual-a")
    write_visual(root, "m3-visual-c", {("forest_noon", "hello"): (BASE, BASE)}, status="failed")
    assert "status is failed" in refused("m3-visual-c")
    assert "a visual run that ended ok" in refused("m3-visual-a", against="m3-visual-c")
    assert "a visual run that ended ok" in refused("m3-visual-a", against="m2-measured")
    moved = {**IDENTITY, "views": {"sha256": "other"}}
    write_visual(root, "m3-visual-d", {("forest_noon", "hello"): (BASE, BASE)}, identity=moved)
    assert "differ in identity: views.sha256" in refused("m3-visual-a", against="m3-visual-d")
    write_visual(root, "m3-visual-e", {("forest_noon", "other"): (BASE, BASE)})
    assert "share no variant id" in refused("m3-visual-a", against="m3-visual-e")
    write_visual(root, "m3-visual-f", {("end_dragon", "hello"): (BASE, BASE)})
    assert "no variant at a view in common" in refused("m3-visual-a", against="m3-visual-f")
    assert "against themselves" in refused("m3-visual-a", against="m3-visual-a")
    other = json.loads((root / record.RECORDS / "m3-visual-f.json").read_text(encoding="utf-8"))
    (root / record.RECORDS / "m3-visual-g.json").write_text(json.dumps(other), encoding="utf-8")
    assert "m3-visual-g's record names 'm3-visual-f'" in refused("m3-visual-g")
    assert "m3-visual-g's record names" in refused("m3-visual-a", against="m3-visual-g")
    short = {**other, "name": "m3-visual-h", "captures": [{**other["captures"][0], "frames": []}]}
    (root / record.RECORDS / "m3-visual-h.json").write_text(json.dumps(short), encoding="utf-8")
    assert "holds no whole pair to tier" in refused("m3-visual-h")
    frame = root / record.RAW / "m3-visual-b" / "frames/forest_noon/hello/attempt-001"
    (frame / "frame-00002.png").write_bytes(png(NEAR))
    assert "a frame is tiered only as recorded" in refused("m3-visual-b")
    shutil.rmtree(root / record.RAW / "m3-visual-b")
    assert "is gone (results/raw/ is disposable)" in refused("m3-visual-b")
    path = root / record.RECORDS / "m3-visual-a.json"
    found = json.loads(path.read_text(encoding="utf-8"))
    # Only the shape a visual run writes: no climb out of its raw folder in either path flavour.
    for bad in ("../m3-visual-b/x.png", "..\\..\\x.png", "C:/x.png", "frames/../../x.png"):
        found["captures"][0]["frames"][0]["path"] = bad
        path.write_text(json.dumps(found), encoding="utf-8")
        assert f"records frame path {bad!r}" in refused("m3-visual-a")


def test_an_invalid_capture_is_named_beside_its_tier(visual_root) -> None:
    root = visual_root
    path = root / record.RECORDS / "m3-visual-a.json"
    found = json.loads(path.read_text(encoding="utf-8"))
    found["captures"][0].update(flags=["event"], valid=False)
    path.write_text(json.dumps(found), encoding="utf-8")
    result = compare_verb.compare(root, "m3-visual-a", None)
    first = result["items"][0]
    assert first["invalid"] == ["m3-visual-a/hello"]
    assert visual.judged(first) == "identical [invalid capture: m3-visual-a/hello]"


def test_visual_stays_outside_the_runs_imports() -> None:
    """D63: the tiers' module is no measured module, so a tier's fix moves no identity."""
    closure = record.module_closure(REPO_ROOT)
    assert "optilux.visual" not in closure and "optilux.verbs.compare" not in closure
