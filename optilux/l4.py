"""L4 (docs/offline.md#levels and #decision-powers, plans/m4.md M4.P05): a capture run's .rdc files
replayed in RenderDoc 1.46 through qrenderdoc's bundled Python (optilux/l4replay.py, plans/m4.md
P7), each held to its record's sha256 first:
- attribution (explain): per capture the frame's replayed GPU time (FetchCounters'
  EventGPUDuration) as shares per program and per Iris group, never ms (replay time follows the
  GPU clock); the share outside every group, and the cutout terrain draws' part of it (plans/m4.md
  P10, D82: E3's evidence);
- pass outputs (close: identical): per program its last draw's targets, decoded and compared
  between two captures of a view on the pixels their readers use: an integer target's where its
  pass's depth is below 1 (D75: Iris's float clear leaves it undefined on sky pixels), every pixel
  of the others; all equal closes that pass's visual tier as identical;
- replay A/B (predict): a program's stage replaced in the replay by a candidate source, by a no-op
  (the capture's own source rebuilt) and by a control (a second no-op build); the candidate's
  share against the no-op's, never the original's (a rebuild alone moves a frame).
Outside `run`'s imports, so outside the identity (plans/m4.md P4).
"""

import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from optilux import l4replay

ATTRIBUTION = "attribution"
OUTPUTS = "pass outputs"
REPLAY_AB = "replay A/B"
# docs/offline.md#decision-powers: what each method may do.
POWERS = {ATTRIBUTION: "explain", OUTPUTS: "close", REPLAY_AB: "predict"}
IDENTICAL = "identical"
DIFFERS = "differs"
UNDECIDED = "undecided"
UNGROUPED = "(no group)"
# Iris's and Sodium's cutout terrain programs (terrain_cutout, sodium_terrain_cutout), the main
# pass's and the shadow pass's (plans/m4.md P10).
CUTOUT = re.compile(r"(^|_)terrain_cutout$")
# What runs no program, by its kind (optilux/l4replay.py's KINDS).
KIND_LABELS = {
    "clear": "(clears)",
    "copy": "(copies)",
    "resolve": "(blits)",
    "mips": "(mipmaps)",
    "present": "(present)",
    "other": "(other)",
}
INTEGER = ("UInt", "SInt")
REPLAY_TIMEOUT = 900.0
EXIT_TIMEOUT = 30.0
POLL = 0.5
# SW_SHOWMINNOACTIVE: qrenderdoc's window starts minimized and never takes the focus.
SHOW_MINIMIZED = 7
FETCHES = 5
L4_DIR = "l4"
JOB = "job.json"


class L4Error(Exception):
    """A problem that stops L4, naming its fix."""


@dataclass(frozen=True)
class Event:
    """One timed action of a replayed frame (optilux/l4replay.py's `events`)."""

    event: int
    name: str
    kind: str
    groups: tuple[str, ...]
    program: str | None
    ms: float


def qrenderdoc(root: Path, pin: dict) -> Path:
    """qrenderdoc.exe beside the pinned renderdoccmd.exe under runtime/tools/."""
    exe = root / "runtime" / "tools" / pin["unpack"] / pin["exe"]
    found = exe.with_name("qrenderdoc.exe")
    if not found.is_file():
        raise L4Error(f"{found} is missing; fix: `uv run optilux install`")
    return found


def held(path: Path, sha256: str) -> int:
    """The .rdc's size once its sha256 equals the record's; L4Error otherwise."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1 << 22):
                digest.update(chunk)
    except OSError as error:
        raise L4Error(f"{path}: {error}; fix: the run's raw folder as it wrote it") from None
    if digest.hexdigest() != sha256:
        raise L4Error(f"{path} is not the record's capture (sha256); fix: rerun the capture run")
    return path.stat().st_size


def replay(exe: Path, rdc: Path, out: Path, job: dict, version: str) -> dict:
    """optilux/l4replay.py on one capture in its own qrenderdoc, its window minimized: the job
    written to out/job.json, replay.json read back once written. L4Error on a timeout, an exit
    without it, a failed replay or another RenderDoc version than the pin's."""
    out.mkdir(parents=True, exist_ok=True)
    for name in (l4replay.REPLAY, l4replay.STAGE):
        (out / name).unlink(missing_ok=True)
    shutil.rmtree(out / l4replay.TARGETS, ignore_errors=True)
    (out / JOB).write_text(
        json.dumps({"capture": str(rdc), "out": str(out), **job}), encoding="utf-8"
    )
    env = dict(os.environ, **{l4replay.JOB_ENV: str(out / JOB)})
    command = [str(exe), "--python", str(Path(l4replay.__file__).resolve())]
    if sys.platform == "win32":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = SHOW_MINIMIZED
        proc = subprocess.Popen(command, env=env, startupinfo=info)  # noqa: S603 the pinned exe
    else:
        proc = subprocess.Popen(command, env=env)  # noqa: S603 the pinned exe
    started = time.monotonic()
    done = out / l4replay.REPLAY
    try:
        while not done.exists() and proc.poll() is None:
            if time.monotonic() - started > REPLAY_TIMEOUT:
                raise L4Error(
                    f"{rdc.name}: no replay in {REPLAY_TIMEOUT:g} s, last stage "
                    f"{stage_of(out)}; fix: open it in qrenderdoc by hand to see why"
                )
            time.sleep(POLL)
        proc.wait(EXIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass
    finally:
        if proc.poll() is None:
            proc.kill()
    try:
        found = json.loads(done.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise L4Error(
            f"{rdc.name}: qrenderdoc ended (exit {proc.returncode}) without a replay ({error}), "
            f"last stage {stage_of(out)}; fix: a dialog may block its scripts: open qrenderdoc "
            "once by hand and answer it"
        ) from None
    if not found.get("ok"):
        last = (found.get("error") or "no error given").strip().splitlines()[-1]
        raise L4Error(f"{rdc.name}: the replay failed: {last}; see {done}")
    if found.get("renderdoc") != version:
        raise L4Error(
            f"{rdc.name}: qrenderdoc reports RenderDoc {found.get('renderdoc')}, the pin "
            f"{version}; fix: `uv run optilux install`"
        )
    return found


def stage_of(out: Path) -> str:
    try:
        return json.loads((out / l4replay.STAGE).read_text(encoding="utf-8"))["stage"]
    except (OSError, ValueError, KeyError):
        return "none"


def parse_events(found: dict, where: str) -> list[Event]:
    """A replay's `events`, each checked: an int event id, once; a name, a kind, its groups (a
    list of names), a program (a draw's or a dispatch's label, else null) and a duration in ms."""
    raw = found.get("events")
    if not isinstance(raw, list) or not raw:
        raise L4Error(f"{where}: the replay holds no timed events; fix: rerun check L4")
    events = []
    seen = set()
    for index, item in enumerate(raw):
        place = f"{where}: event {index + 1}"
        if not isinstance(item, dict):
            raise L4Error(f"{place} is no object")
        number, groups, program, ms = (item.get(k) for k in ("event", "groups", "program", "ms"))
        if not isinstance(number, int) or number in seen:
            raise L4Error(f"{place}: event id {number!r} is no int or comes twice")
        if not isinstance(item.get("name"), str) or not isinstance(item.get("kind"), str):
            raise L4Error(f"{place}: name or kind is no text")
        if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
            raise L4Error(f"{place}: groups is no list of names")
        if program is not None and not isinstance(program, str):
            raise L4Error(f"{place}: program {program!r} is no label or null")
        if program is not None and item["kind"] not in l4replay.PROGRAMMED:
            raise L4Error(f"{place}: a {item['kind']} runs no program, yet names {program}")
        if isinstance(ms, bool) or not isinstance(ms, int | float) or not ms >= 0:
            raise L4Error(f"{place}: duration {ms!r} is no number of ms at or above 0")
        seen.add(number)
        events.append(Event(number, item["name"], item["kind"], tuple(groups), program, ms))
    return events


def label(event: Event) -> str:
    """Whom an event's time goes to: a draw's or dispatch's program, else its kind."""
    if event.kind in l4replay.PROGRAMMED:
        return event.program or "(no program)"
    return KIND_LABELS.get(event.kind, f"({event.kind})")


def shares(events: list[Event], key, total: float) -> list[dict]:
    """Events summed by `key`, largest first: name, ms and share of `total`."""
    sums: dict[str, float] = {}
    for event in events:
        name = key(event)
        sums[name] = sums.get(name, 0.0) + event.ms
    return [
        {"name": name, "ms": ms, "share": ms / total}
        for name, ms in sorted(sums.items(), key=lambda item: (-item[1], item[0]))
    ]


def attribution(events: list[Event]) -> dict:
    """A frame's shares (explain only): per program (by label), per outermost group and per
    group path; outside every group, with its programs; the cutout terrain draws, the groups
    holding them and their part of the ungrouped time."""
    total = sum(e.ms for e in events)
    if total <= 0:
        raise L4Error("the replay timed no GPU work; fix: rerun check L4")
    outside = [e for e in events if not e.groups]
    outside_ms = sum(e.ms for e in outside)
    cut = [e for e in events if e.kind == "draw" and e.program and CUTOUT.search(e.program)]
    cut_outside = sum(e.ms for e in cut if not e.groups)
    unlabelled = [
        e for e in events if e.program is not None and l4replay.UNLABELLED.match(e.program)
    ]
    return {
        "power": POWERS[ATTRIBUTION],
        "frameMs": total,
        "events": len(events),
        "draws": sum(e.kind == "draw" for e in events),
        "programs": shares(events, label, total),
        "groups": shares(events, lambda e: e.groups[0] if e.groups else UNGROUPED, total),
        "paths": shares(events, lambda e: " / ".join(e.groups) or UNGROUPED, total),
        "ungrouped": {
            "ms": outside_ms,
            "share": outside_ms / total,
            "entries": shares(outside, label, total),
        },
        "cutout": {
            "draws": len(cut),
            "ms": sum(e.ms for e in cut),
            "share": sum(e.ms for e in cut) / total,
            "groups": shares(cut, lambda e: " / ".join(e.groups) or UNGROUPED, total),
            "ungroupedMs": cut_outside,
            "ofUngrouped": cut_outside / outside_ms if outside_ms else None,
        },
        "unlabelled": sum(e.ms for e in unlabelled) / total,
    }


# Pass outputs: decoded targets compared on their used pixels.


def depth_values(data: bytes, form: dict, width: int, height: int) -> np.ndarray:
    """A depth target's values in [0, 1] per pixel, flat: RenderDoc's D32 (32-bit float, 26.3's
    main depth) or D16 (16-bit unorm). L4Error for another format."""
    pixels = width * height
    regular = form.get("type") == "Regular" and form.get("compCount") == 1
    width_b, comp = form.get("compByteWidth"), form.get("compType")
    if regular and width_b == 4 and comp in ("Float", "Depth") and len(data) == pixels * 4:
        return np.frombuffer(data, dtype="<f4")
    if regular and width_b == 2 and comp in ("UNorm", "Depth") and len(data) == pixels * 2:
        return np.frombuffer(data, dtype="<u2").astype(np.float32) / 65535.0
    raise L4Error(
        f"a depth target of format {form.get('name')} ({len(data)} bytes for {width}x{height}) "
        "is not read here; fix: teach optilux/l4.py's depth_values that format"
    )


def covered(depth: np.ndarray) -> np.ndarray:
    """The pixels geometry covered: those off the far value, which the target itself shows (the
    sky's pixels hold it exactly): 1.0 for forward depth, 0.0 for reversed (26.3 clears its main
    depth to 0, m4-capture-3's captures, though platform.md#mc-263 says Iris undoes it).
    Every pixel when neither occurs; L4Error when both do."""
    zero, one = bool((depth == 0.0).any()), bool((depth == 1.0).any())
    if zero and one:
        raise L4Error("its depth holds both 0 and 1, so which is far is unknown")
    if not zero and not one:
        return np.ones(depth.shape, dtype=bool)
    return depth != (1.0 if one else 0.0)


def target_pixels(data: bytes, width: int, height: int) -> np.ndarray:
    """A target's bytes as one row per pixel."""
    pixels = width * height
    if not pixels or len(data) % pixels:
        raise L4Error(f"{len(data)} bytes do not split into {width}x{height} pixels")
    return np.frombuffer(data, dtype=np.uint8).reshape(pixels, len(data) // pixels)


def used_mask(target: dict, data: bytes, depth: tuple[dict, bytes] | None) -> np.ndarray | None:
    """The pixels a target's readers use: for an integer target those its pass's depth shows
    covered (D75: deferred skips the sky by depth), else every pixel (None). L4Error for an
    integer target whose pass binds no depth."""
    if target["format"]["compType"] not in INTEGER:
        return None
    if depth is None:
        raise L4Error(
            f"{target['texture'] or target['resource']} is an integer target whose pass binds no "
            "depth, so its used pixels are unknown (D75)"
        )
    meta, values = depth
    if (meta["width"], meta["height"]) != (target["width"], target["height"]):
        raise L4Error(f"{target['texture']}: its pass's depth is another size")
    return covered(depth_values(values, meta["format"], meta["width"], meta["height"]))


def read_target(folder: Path, target: dict) -> bytes:
    data = (folder / target["file"]).read_bytes()
    if len(data) != target["bytes"]:
        raise L4Error(f"{folder / target['file']}: {len(data)} bytes, the replay wrote more")
    return data


def pass_depth(folder: Path, found: dict) -> tuple[dict, bytes] | None:
    meta = next((t for t in found["targets"] if t["slot"] == "depth"), None)
    return None if meta is None else (meta, read_target(folder, meta))


def compare_target(base: tuple[dict, bytes], cand: tuple[dict, bytes], masks: list) -> dict:
    """Two captures' copies of one target on its used pixels (the union of both captures'
    masks): identical when every used pixel's bytes are equal."""
    (bt, bd), (ct, cd) = base, cand
    shape = ("width", "height")
    if [bt[k] for k in shape] != [ct[k] for k in shape] or bt["format"] != ct["format"]:
        return {"tier": DIFFERS, "why": "another size or format", "differing": None}
    width, height = bt["width"], bt["height"]
    pixels = width * height
    differ = np.any(target_pixels(bd, width, height) != target_pixels(cd, width, height), axis=1)
    used = None
    if any(m is not None for m in masks):
        used = np.zeros(pixels, dtype=bool)
        for mask in (m for m in masks if m is not None):
            used |= mask
        differ &= used
    count = int(differ.sum())
    return {
        "tier": IDENTICAL if count == 0 else DIFFERS,
        "differing": count,
        "used": pixels if used is None else int(used.sum()),
        "pixels": pixels,
    }


def compare_passes(base: tuple[Path, list], cand: tuple[Path, list]) -> list[dict]:
    """Per program in either capture, its targets compared (compare_target, matched by slot and
    texture name): identical when every target is, which closes the pass's visual tier as
    identical; differs when one is not; undecided when a used-pixel mask is unknown; or only in
    one capture."""
    (bf, bpasses), (cf, cpasses) = base, cand
    by_base = {p["program"]: p for p in bpasses}
    by_cand = {p["program"]: p for p in cpasses}
    found = []
    for program in [*by_base, *(p for p in by_cand if p not in by_base)]:
        if program not in by_base or program not in by_cand:
            only = "baseline" if program in by_base else "candidate"
            found.append({"program": program, "tier": f"only in the {only}", "targets": []})
            continue
        bp, cp = by_base[program], by_cand[program]
        keys = [(t["slot"], t["texture"]) for t in bp["targets"]]
        if not keys and not cp["targets"]:
            found.append(
                {"program": program, "tier": UNDECIDED, "why": "no target read back", "targets": []}
            )
            continue
        if keys != [(t["slot"], t["texture"]) for t in cp["targets"]]:
            found.append(
                {"program": program, "tier": DIFFERS, "why": "other targets", "targets": []}
            )
            continue
        targets = []
        tier = IDENTICAL
        try:
            bdepth, cdepth = pass_depth(bf, bp), pass_depth(cf, cp)
            for bt, ct in zip(bp["targets"], cp["targets"], strict=True):
                bd, cd = read_target(bf, bt), read_target(cf, ct)
                masks = [used_mask(bt, bd, bdepth), used_mask(ct, cd, cdepth)]
                row = compare_target((bt, bd), (ct, cd), masks)
                targets.append({"slot": bt["slot"], "texture": bt["texture"], **row})
                if row["tier"] != IDENTICAL:
                    tier = DIFFERS
        except L4Error as error:
            found.append({"program": program, "tier": UNDECIDED, "why": str(error), "targets": []})
            continue
        found.append({"program": program, "tier": tier, "targets": targets})
    return found


def family(variant: dict) -> str:
    """Which captures' passes correspond: every Optilux build's, else one reference pack's."""
    return "optilux" if variant.get("build") is not None else variant["pack"]


def pairs(captures: list[dict], variants: dict[str, dict]) -> list[tuple[str, str, str]]:
    """Per view, each capture against the first of its pack family captured there: (view,
    baseline variant, candidate variant), in the record's order."""
    first: dict[tuple[str, str], str] = {}
    found = []
    for capture in captures:
        key = (capture["view"], family(variants[capture["variant"]]))
        if key in first:
            found.append((capture["view"], first[key], capture["variant"]))
        else:
            first[key] = capture["variant"]
    return found


def closures(
    comparisons: list[dict], perf: list[str], status: str | None
) -> tuple[list[dict], list[str]]:
    """What pass outputs close (docs/offline.md#decision-powers): per baseline and candidate,
    each pass identical at every view the two were compared at, those views covering every perf
    view; nothing from a record that did not end ok. The closures, and per pair closing nothing
    why."""
    by_pair: dict[tuple[str, str], dict[str, dict]] = {}
    for comp in comparisons:
        by_pair.setdefault((comp["baseline"], comp["candidate"]), {})[comp["view"]] = comp
    found, held = [], []
    for (base, cand), views in by_pair.items():
        missing = [v for v in perf if v not in views]
        if status != "ok":
            held.append(f"{cand} against {base}: the record ended {status}")
        elif not perf or missing:
            held.append(
                f"{cand} against {base}: compared at {len(views)} views, not at {len(missing)} "
                f"of the {len(perf)} perf views"
            )
        else:
            rows = [views[v]["passes"] for v in views]
            same = [p["program"] for p in rows[0] if p["tier"] == IDENTICAL]
            for name in same:
                if all(
                    any(p["program"] == name and p["tier"] == IDENTICAL for p in r) for r in rows
                ):
                    entry = closure(OUTPUTS, {"program": name, "tier": IDENTICAL})
                    found.append(
                        {**entry, "baseline": base, "candidate": cand, "views": len(views)}
                    )
    return found, held


def closure(method: str, entry: dict) -> dict:
    """The closure an L4 result may give (docs/offline.md#decision-powers): a pass whose outputs
    are identical closes its visual tier as identical; nothing else closes. L4Error for a replay
    A/B (it predicts), an attribution (it explains) or a pass not identical."""
    power = POWERS.get(method)
    if power != "close":
        raise L4Error(
            f"a {method} only {power}s (docs/offline.md#decision-powers), so it closes nothing"
        )
    if entry.get("tier") != IDENTICAL:
        raise L4Error(f"pass {entry.get('program')} {entry.get('tier')}: only identical closes")
    return {"method": OUTPUTS, "power": power, "verdict": IDENTICAL, "pass": entry["program"]}


def ab_summary(entry: dict) -> dict:
    """A replay A/B's rounds as shares (predict only): per role the median of the program's share
    of each fetched frame and the median frame; the candidate's share minus the no-op's, and the
    control's minus the no-op's (two builds of one source: the noise floor)."""
    if entry.get("notDrawn") or entry.get("error"):
        return {**entry, "power": POWERS[REPLAY_AB]}
    medians = {}
    for role, rounds in entry["rounds"].items():
        if not rounds or any(r["frameMs"] <= 0 for r in rounds):
            raise L4Error(f"{entry['program']}: the {role} rounds timed no frame")
        medians[role] = {
            "share": statistics.median(r["programMs"] / r["frameMs"] for r in rounds),
            "frameMs": statistics.median(r["frameMs"] for r in rounds),
        }
    return {
        "program": entry["program"],
        "stage": entry["stage"],
        "candidate": entry["candidate"],
        # The source the no-op rebuilt, beside the replay: the candidate's starting point.
        "own": entry.get("own"),
        "ownSha256": entry.get("ownSha256"),
        "draws": entry["draws"],
        "fetches": len(entry["rounds"]["noop"]),
        "power": POWERS[REPLAY_AB],
        "medians": medians,
        "predicted": medians["candidate"]["share"] - medians["noop"]["share"],
        "noise": medians["control"]["share"] - medians["noop"]["share"],
    }
