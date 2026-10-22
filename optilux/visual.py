"""A visual run's frames judged by tier (docs/measurement.md#visual-protocol, docs/plans/m3.md
D63) and its review page.

Pure: it takes records and frame bytes and returns tiers, what `compare` prints and the page's
text; the `compare` verb reads the files and writes the page. It stays outside `run`'s imports
(record.module_closure from optilux.verbs.run), so a fix here moves no identity and needs no
recalibration (run-record.md#identity, harness). numpy and pillow decode and diff the frames;
flip-evaluator and scikit-image score the close tier (plans/m3.md D59), imported only for a pair
neither identical nor near.

The tiers, suite.json fidelity's: identical when every decoded value is equal; near when none
differs by more than near.maxAbsDiff; close when the mean FLIP error (LDR, sRGB inputs, its ppd)
is at most close.meanFlip, its 99.9th percentile at most close.p999Flip and SSIM at least
close.minSsim; else review. What a visual record holds is tiered three ways (plan): each pair, its
two frames 2 s apart (a pack whose frames repeat is identical there); each candidate's first frame
against the baseline's, the record's first variant; with another record, each variant's first
frame against the same variant's there, the identities equal key by key.
"""

import html
import io
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from PIL import Image

TIERS = ("identical", "near", "close", "review")
# A tier of one frame against another: the pair, a candidate against the baseline, a variant
# against itself in another run.
PAIR, BASELINE, AGAINST = "pair", "baseline", "against"


class VisualError(RuntimeError):
    """Frames or a fidelity block that cannot be judged; the message names the fix."""


@dataclass(frozen=True)
class Fidelity:
    """suite.json fidelity's thresholds: near's largest decoded difference, close's FLIP mean,
    FLIP 99.9th percentile and SSIM floor, FLIP's pixels per degree."""

    near: int
    mean_flip: float
    p999_flip: float
    min_ssim: float
    ppd: float


def fidelity(suite: dict) -> Fidelity:
    """suite.json fidelity read; VisualError naming the fix."""
    found = suite.get("fidelity") or {}
    try:
        near, close = found["near"], found["close"]
        values = (
            near["maxAbsDiff"],
            close["meanFlip"],
            close["p999Flip"],
            close["minSsim"],
            found["flip"]["ppd"],
        )
    except (KeyError, TypeError) as error:
        raise VisualError(
            f"suite.json fidelity lacks {error}; fix: near.maxAbsDiff, close.meanFlip, "
            "close.p999Flip, close.minSsim and flip.ppd"
        ) from None
    numbers = all(isinstance(v, int | float) and not isinstance(v, bool) for v in values)
    if not numbers or not isinstance(values[0], int) or min(values) < 0 or values[-1] <= 0:
        raise VisualError(
            f"suite.json fidelity's thresholds {values!r}; fix: near.maxAbsDiff a whole number "
            "from 0, the others numbers from 0, flip.ppd above 0 (FLIP exits on one at 0)"
        )
    return Fidelity(values[0], *(float(v) for v in values[1:]))


def decode(data: bytes, where: str) -> np.ndarray:
    """A PNG's decoded pixels as RGBA, height x width x 4 of uint8; VisualError for a file pillow
    cannot read."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            return np.asarray(image.convert("RGBA"))
    except (OSError, ValueError) as error:
        raise VisualError(f"{where}: no image pillow reads ({error})") from None


def scores(reference: np.ndarray, test: np.ndarray, ppd: float) -> dict:
    """close's figures of two equal-size frames: the mean FLIP error and its 99.9th percentile
    (LDR, sRGB inputs, `ppd`; measurement.md#tools) and SSIM over RGB."""
    import flip_evaluator
    from skimage.metrics import structural_similarity

    ref, tst = reference[..., :3], test[..., :3]
    error_map, mean, _ = flip_evaluator.evaluate(
        ref.astype(np.float32) / 255.0,
        tst.astype(np.float32) / 255.0,
        "LDR",
        inputsRGB=True,
        applyMagma=False,
        computeMeanError=True,
        parameters={"ppd": ppd},
    )
    # Without full or gradient, structural_similarity returns the mean SSIM alone.
    ssim = cast(float, structural_similarity(ref, tst, channel_axis=2, data_range=255))
    return {  # unrounded: the tier is decided on these
        "meanFlip": float(mean),
        "p999Flip": float(np.percentile(error_map, 99.9)),
        "ssim": float(ssim),
    }


def tier(reference: np.ndarray, test: np.ndarray, fid: Fidelity) -> dict:
    """`test` against `reference` (measurement.md#visual-protocol's tiers): the tier and what
    decided it, the largest decoded difference and the pixels that differ, and for a pair neither
    identical nor near close's figures. Frames of two sizes are review."""
    if reference.shape != test.shape:
        sizes = " and ".join(f"{a.shape[1]}x{a.shape[0]}" for a in (reference, test))
        return {"tier": "review", "why": f"sizes {sizes}"}
    if np.array_equal(reference, test):
        return {"tier": "identical", "maxAbsDiff": 0, "pixels": 0}
    diff = np.abs(reference.astype(np.int16) - test.astype(np.int16)).max(axis=-1)
    found: dict[str, Any] = {"maxAbsDiff": int(diff.max()), "pixels": int(np.count_nonzero(diff))}
    if found["maxAbsDiff"] <= fid.near:
        return {"tier": "near", **found}
    found.update(scores(reference, test, fid.ppd))
    close = (
        found["meanFlip"] <= fid.mean_flip
        and found["p999Flip"] <= fid.p999_flip
        and found["ssim"] >= fid.min_ssim
    )
    return {"tier": "close" if close else "review", **found}


def first_frames(found: dict) -> dict[tuple[str, str], dict]:
    """A visual record's captures by (view, variant)."""
    return {(c["view"], c["variant"]): c for c in found.get("captures") or []}


def plan(found: dict, other: dict | None = None) -> list[dict]:
    """What `compare` tiers in a visual record, view by view in its capture order: each variant's
    pair, each candidate's first frame against the baseline's (the record's first variant), and
    with `other` each variant's first frame against the same variant's there. Each item: its kind,
    view, variant, the frames it compares as (run, path, sha256), and a capture the record marks
    invalid named, so its tier is never read as a verdict."""
    name = found["name"]
    captures = first_frames(found)
    variants = [v["id"] for v in found.get("variants") or []]
    there = first_frames(other) if other is not None else {}
    views = list(dict.fromkeys(view for view, _ in captures))
    items = []

    def frame(run: str, capture: dict, n: int) -> dict:
        shown = capture["frames"][n]
        return {"run": run, "path": shown["path"], "sha256": shown["sha256"]}

    def invalid(*held: tuple[str, dict]) -> list[str]:
        return [f"{run}/{c['variant']}" for run, c in held if not c.get("valid")]

    for view in views:
        base = captures.get((view, variants[0])) if variants else None
        for vid in variants:
            capture = captures.get((view, vid))
            if capture is None or len(capture["frames"]) < 2:
                continue
            items.append(
                {
                    "kind": PAIR,
                    "view": view,
                    "variant": vid,
                    "frames": [frame(name, capture, 0), frame(name, capture, 1)],
                    "invalid": invalid((name, capture)),
                }
            )
            if base is not None and vid != variants[0] and base["frames"]:
                items.append(
                    {
                        "kind": BASELINE,
                        "view": view,
                        "variant": vid,
                        "frames": [frame(name, base, 0), frame(name, capture, 0)],
                        "invalid": invalid((name, base), (name, capture)),
                    }
                )
            theirs = there.get((view, vid))
            if other is not None and theirs is not None and theirs["frames"]:
                items.append(
                    {
                        "kind": AGAINST,
                        "view": view,
                        "variant": vid,
                        "frames": [frame(other["name"], theirs, 0), frame(name, capture, 0)],
                        "invalid": invalid((other["name"], theirs), (name, capture)),
                    }
                )
    return items


def unmatched(found: dict, other: dict) -> dict[str, list[str]]:
    """The pairs (view/variant) with a frame that one of two visual records holds and the other
    lacks, by record: `compare --against` names them rather than leave them out unsaid."""
    mine = {key for key, c in first_frames(found).items() if c["frames"]}
    theirs = {key for key, c in first_frames(other).items() if c["frames"]}
    return {
        found["name"]: [
            f"{view}/{vid}" for view, vid in first_frames(found) if (view, vid) in mine - theirs
        ],
        other["name"]: [
            f"{view}/{vid}" for view, vid in first_frames(other) if (view, vid) in theirs - mine
        ],
    }


def unmatched_text(result: dict) -> str | None:
    """The pairs only one run holds, as `compare` prints them; None when every pair has its
    counterpart."""
    shown = [
        f"only in {run}: {', '.join(pairs)}"
        for run, pairs in (result.get("unmatched") or {}).items()
        if pairs
    ]
    return "; ".join(shown) or None


def lines(result: dict) -> list[str]:
    """`compare`'s text for a visual record: per view each tier with what decided it; with
    --against the pairs one run lacks."""
    head = f"optilux compare {result['name']}: visual, {result['mode']} mode, variants "
    head += ", ".join(result["variants"])
    if result.get("against"):
        head += f"; against {result['against']}"
    out = [head]
    missing = unmatched_text(result)
    if missing:
        out.append(f"  unmatched (no tier): {missing}")
    views: dict[str, list[dict]] = {}
    for item in result["items"]:
        views.setdefault(item["view"], []).append(item)
    for view, items in views.items():
        out.append(f"  {view}:")
        out.extend(f"    {label(item, result)}: {judged(item)}" for item in items)
    out.append(f"  page: {result['page']}")
    return out


def label(item: dict, result: dict) -> str:
    if item["kind"] == PAIR:
        return f"{item['variant']} pair"
    if item["kind"] == BASELINE:
        return f"{item['variant']} vs {result['variants'][0]}"
    return f"{item['variant']} vs {result['against']}'s"


def judged(item: dict) -> str:
    """A tier as printed: the tier, then what decided it, then an invalid capture named."""
    found = item["tier"]
    words = [found["tier"].upper() if found["tier"] == "review" else found["tier"]]
    if "why" in found:
        words.append(f"({found['why']})")
    elif found["tier"] != "identical":
        detail = f"max |d| {found['maxAbsDiff']}, {found['pixels']:,} pixels"
        if "meanFlip" in found:  # seven digits: a figure printed never rounds onto its threshold
            detail += (
                f"; FLIP mean {found['meanFlip']:.7g}, p99.9 {found['p999Flip']:.7g}; "
                f"SSIM {found['ssim']:.7g}"
            )
        words.append(f"({detail})")
    if item["invalid"]:
        words.append(f"[invalid capture: {', '.join(item['invalid'])}]")
    return " ".join(words)


STYLE = """
:root { --bg: #fbfbfa; --fg: #1d1d1b; --muted: #6b6b66; --line: #dcdcd6; --bad: #b3261e;
  --good: #1e6b33; --wait: #8a5a00; }
@media (prefers-color-scheme: dark) { :root { --bg: #161615; --fg: #e8e8e3; --muted: #a0a09a;
  --line: #3a3a36; --bad: #f28b82; --good: #81c995; --wait: #fdd663; } }
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 1800px; padding: 16px;
  font: 14px/1.45 system-ui, sans-serif; }
h1 { font-size: 20px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 24px 0 8px; }
p, li { margin: 4px 0; } .muted { color: var(--muted); }
.identical, .near { color: var(--good); } .close { color: var(--wait); }
.review { color: var(--bad); }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); }
figure { margin: 0; border: 1px solid var(--line); padding: 6px; }
figure img { width: 100%; height: auto; display: block; }
figcaption { font-size: 13px; margin-top: 4px; }
"""


def page(result: dict) -> str:
    """review.html, beside report.html under results/raw/<run>/ (D63): per view, each variant's
    first frame side by side, a pair's second frame beside it when the two are not identical, the
    other run's with --against, each captioned with its tiers; every image a link to the frame
    under results/raw/, nothing else loaded."""
    e = html.escape
    name = result["name"]
    against = result.get("against")
    out = [
        f"<h1>{e(name)} review</h1>",
        f'<p class="muted">visual run, {e(result["mode"])} mode; variants '
        f"{e(', '.join(result['variants']))}"
        + (f"; against {e(against)}" if against else "")
        + ". Tiers: suite.json fidelity (measurement.md#visual-protocol); Claude pre-screens the "
        "frames and marks suspects, the user decides.</p>",
    ]
    missing = unmatched_text(result)
    if missing:
        out.append(f'<p class="review">Unmatched, no tier: {e(missing)}.</p>')
    views: dict[str, list[dict]] = {}
    for item in result["items"]:
        views.setdefault(item["view"], []).append(item)
    for view, items in views.items():
        # One figure per frame shown: each run's first frame of a variant, this run's captioned
        # with its tiers, and a pair's second frame when it is not identical to the first.
        figures: dict[tuple[str, str, int], tuple[str, list[dict]]] = {}
        for item in items:
            own = item["frames"][0 if item["kind"] == PAIR else 1]
            key = (own["run"], item["variant"], 1)
            figures.setdefault(key, (own["path"], []))[1].append(item)
            if item["kind"] == PAIR and item["tier"]["tier"] != "identical":
                second = item["frames"][1]
                figures.setdefault((second["run"], item["variant"], 2), (second["path"], []))
            if item["kind"] == AGAINST:
                theirs = item["frames"][0]
                figures.setdefault((theirs["run"], item["variant"], 1), (theirs["path"], []))
        out.append(f'<h2>{e(view)}</h2><div class="grid">')
        for (run, vid, n), (path, tiered) in figures.items():
            href = path if run == name else f"../{run}/{path}"
            tiers = "".join(
                f'<li>{e(label(i, result))}: <span class="{e(i["tier"]["tier"])}">'
                f"{e(judged(i))}</span></li>"
                for i in tiered
            )
            out.append(
                f'<figure><a href="{e(href)}"><img src="{e(href)}" alt="{e(vid)} at {e(view)}" '
                f'loading="lazy"></a><figcaption><b>{e(vid)}</b>'
                + ("" if run == name else f" ({e(run)})")
                + (" frame 2 of its pair" if n == 2 else "")
                + f"<ul>{tiers}</ul></figcaption></figure>"
            )
        out.append("</div>")
    body = "".join(out)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(name)} review</title><style>{STYLE}</style></head><body>{body}</body></html>\n"
    )
