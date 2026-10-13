"""The run record (docs/run-record.md): the run spec and its checks, the views file, the identity,
the machine's facts, the world's tree hash and the record itself.

`run` (optilux/verbs/run.py) validates a spec here before anything launches, and every refusal
names its fix. The identity is built before the launch from the files the session will use
(plans/m2.md M2.P01: a failed launch records it), the launch's facts then held against it, and
matched key by key later (IDENTITY_KEYS, run-record.md#identity); the system facts are read from
the machine as D22 says: the resolution from the written options and a DPI-aware
EnumDisplaySettings, never from WMI; HAGS as applied from D3DKMT's WDDM 2.7 caps (plans/m2.md
D38), only read. A record is written once under its run's name and never overwritten; a missing
identity value refuses the write instead of passing.
"""

import ast
import ctypes
import hashlib
import json
import math
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from optilux import platform, presentmon

RECORDS = "results/records"
RAW = "results/raw"
VIEWS = "config/views"
# A world snapshot: snapshots/<world id>/, a copy of a world folder (docs/plans/m1.md D23).
SNAPSHOTS = "snapshots"
SCHEMA = 1

# The run spec (run-record.md#run-spec).
NAME = re.compile(r"[a-z0-9-]{1,40}")
SPEC_REQUIRED = ("name", "kind", "views", "world", "variants", "tier", "resourcePacks")
# items: an acceptance run's; mode: a measured schedule's (measurement and calibration runs, and
# acceptance runs of A8 and A11); calibration: the calibration a measured run is judged by, or
# null (plans/m2.md D40: no verdicts); heap: the heap read every RELOAD_EVERY reloads (M2.P06);
# rounds, dimensions, keepViews, alone and windows: a budget run's (BUDGET); remeasures: the A8
# session whose views beyond their threshold this one re-measures (plans/m2.md M2.P10);
# treatment: declared treatments (after 1.0); reloads: F4's table (plans/m1.md 0.01.09).
SPEC_OPTIONAL = (
    "items",
    "notes",
    "mode",
    "calibration",
    "heap",
    *("rounds", "dimensions", "keepViews", "alone", "windows"),
    "remeasures",
    "treatment",
    "reloads",
)
# A budget run (plans/m2.md M2.P06, F14's controlled pair and its diagnosis): a measurement run
# with heap true may set its rounds, keep only some dimensions' views or some views by id, reload
# the baseline alone in every slot (no pack switch, no twin) and leave out its windows (each
# capture's reload and options check alone); its heap table sets the budget, no verdict reads its
# captures (calibration null).
BUDGET = ("rounds", "dimensions", "keepViews", "alone", "windows")
KINDS = ("measurement", "calibration", "acceptance")
MODES = ("quick", "full")
ITEMS = tuple(f"A{number}" for number in range(1, 13))
# The items `run` performs in M1 (docs/plans/m1.md 0.01.08 and 0.01.09), in the record's order.
RUNNABLE = ("A1", "A2", "A3", "A4", "A7", "A9", "A10")
# The items a measured schedule carries (plans/m2.md M2.P05, M2.P10): the timers' overhead and
# their agreement with GPUBusy, judged by M2.P07's statistics.
MEASURED_ITEMS = ("A8", "A11")
# The resource-pack set launch writes (suite.json resourcePacks; M3 adds the deterministic one).
PACK_SET = "standard"
# An acceptance session reloads twice: selftest's reload and the start-of-run reload; A4 twice
# more (the broken copy, then the recovery). A measured session starts with the same two.
ACCEPTANCE_RELOADS = 2
A4_RELOADS = 2
# A measured run's variants (plans/m2.md M2.P05): an id, the pack, a profile of
# config/profiles/ or null, option values over it, the per-pass timers on or off. The twins'
# ids are the runner's (measure.py), never a spec's.
VARIANT_REQUIRED = ("id", "pack", "profile")
VARIANT_OPTIONAL = ("options", "timers")
TWIN = "twin"
PROFILES = "config/profiles"
OPTION_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
# F4's table (roadmap.md#findings-assigned): heap after GC and private bytes every RELOAD_EVERY
# reloads.
RELOAD_EVERY = 10

# The views file (measurement.md#baseline-suite): config/views/<world id>.json.
VIEW_KEYS = ("id", "dim", "x", "y", "z", "yaw", "pitch", "time", "weather")
VIEW_ID = re.compile(r"[a-z0-9_]{1,40}")
DIMENSIONS = ("minecraft:overworld", "minecraft:the_nether", "minecraft:the_end")
WEATHERS = ("clear", "rain", "thunder")

# The identity (run-record.md#identity), in the doc's order; a test keeps the two equal.
IDENTITY_KEYS = (
    "platform",
    "launchSpec",
    "mods",
    "world",
    "views",
    "resourcePacks",
    "settings",
    "suite",
    "java",
    "system",
    "harness",
)
# The suite sections that are identity, and the note and ALC-context keys stripped from them.
SUITE_SECTIONS = ("display", "modes", "capture", "validity", "statistics")
# The platform file's sections no session loads (plans/m2.md D39): the reference pack is a
# variant's (its sha512 goes into variants and the calibration file), world prep's mods never
# reach a session.
PLATFORM_OUT = (platform.REFERENCE_PACKS, "worldPrep")
# The measured session's entry: `harness` hashes the optilux modules it imports (D36).
PACKAGE = "optilux"
RUNNER = "optilux.verbs.run"
ACCEPTANCE_KEYS = ("item", "pass", "evidence")
STATUSES = ("ok", "invalid", "failed", "aborted")


class RecordError(RuntimeError):
    """A spec, a snapshot or a record that cannot be used; the message names the fix."""


# The world's tree hash.


def tree_files(folder: Path) -> list[tuple[str, str]]:
    """Every file under `folder` as (relative POSIX path, sha256 of its bytes), sorted by path;
    RecordError for a link (a snapshot is plain files) or a missing folder."""
    if not folder.is_dir():
        raise RecordError(f"no folder {folder}; fix: copy the world there (docs/plans/m1.md D23)")
    found = []
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise RecordError(f"{path} is a link; fix: copy the world as plain files")
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            found.append((path.relative_to(folder).as_posix(), digest))
    return sorted(found, key=lambda item: item[0].encode("utf-8"))


def tree_text(files: list[tuple[str, str]]) -> str:
    """The tree's manifest: one `<sha256>  <path>` line per file, in path order, LF."""
    return "".join(f"{digest}  {path}\n" for path, digest in files)


def tree_hash(folder: Path) -> tuple[str, int]:
    """The tree hash of a folder (docs/plans/m1.md 0.01.08): sha256 over its sorted relative paths
    and contents, as the sha256 of its manifest; and the file count."""
    digest, count, _ = tree(folder)
    return digest, count


def tree(folder: Path) -> tuple[str, int, str]:
    """tree_hash's hash and count, and the manifest they come from, from one read."""
    files = tree_files(folder)
    text = tree_text(files)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(files), text


# The views file.


def finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def load_views(root: Path, world_id: str) -> tuple[dict, Path]:
    """config/views/<world_id>.json checked: its id, and each view's fields (VIEW_KEYS, an
    optional `why`), a known dimension and weather, finite numbers, pitch in -90..90, an integer
    time from 0; ids unique."""
    path = root / VIEWS / f"{world_id}.json"
    name = f"{VIEWS}/{path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise RecordError(
            f"no views file {name}; fix: add it (measurement.md#baseline-suite)"
        ) from None
    except ValueError as error:
        raise RecordError(f"{name} is not JSON ({error}); fix: repair it") from None
    if not isinstance(data, dict) or data.get("id") != world_id:
        raise RecordError(f"{name} does not say id {world_id!r}; fix: set its id")
    views = data.get("views")
    if not isinstance(views, list) or not views:
        raise RecordError(f"{name} lists no views; fix: add one per dimension")
    seen = set()
    for index, view in enumerate(views):
        where = f"{name} view {index + 1}"
        if not isinstance(view, dict):
            raise RecordError(f"{where} is no object; fix: give its fields")
        missing = [key for key in VIEW_KEYS if key not in view]
        extra = [key for key in view if key not in (*VIEW_KEYS, "why")]
        if missing or extra:
            raise RecordError(
                f"{where}: missing {missing or 'none'}, unknown {extra or 'none'}; fix: give "
                f"exactly {', '.join(VIEW_KEYS)} (and a why)"
            )
        if not isinstance(view["id"], str) or not VIEW_ID.fullmatch(view["id"]):
            raise RecordError(f"{where}: id {view['id']!r} is not [a-z0-9_]{{1,40}}; fix: rename")
        if view["id"] in seen:
            raise RecordError(f"{where}: id {view['id']} is listed twice; fix: rename one")
        seen.add(view["id"])
        if view["dim"] not in DIMENSIONS:
            raise RecordError(f"{where}: dim {view['dim']!r}; fix: one of {', '.join(DIMENSIONS)}")
        bad = [key for key in ("x", "y", "z", "yaw", "pitch") if not finite(view[key])]
        if bad:
            raise RecordError(f"{where}: {', '.join(bad)} not a finite number; fix: give one")
        if not -90 <= view["pitch"] <= 90:
            raise RecordError(f"{where}: pitch {view['pitch']} is outside -90..90; fix: clamp it")
        if isinstance(view["time"], bool) or not isinstance(view["time"], int) or view["time"] < 0:
            raise RecordError(f"{where}: time {view['time']!r} is no tick count; fix: give one")
        if view["weather"] not in WEATHERS:
            raise RecordError(f"{where}: weather {view['weather']!r}; fix: one of {WEATHERS}")
    return data, path


# The run spec.


@dataclass(frozen=True)
class Spec:
    """A checked run spec (run-record.md#run-spec). A measured run (`mode` set: measurement and
    calibration runs, acceptance runs of A8 and A11) carries its variants as checked, the
    mode's views in the views file's order, its rounds and its planned reloads."""

    name: str
    kind: str
    views: str
    world: str
    pack: str
    tier: str
    resource_packs: str
    items: tuple[str, ...]
    notes: str | None
    data: dict
    reloads: int = 0
    mode: str | None = None
    calibration: str | None = None
    heap: bool = False
    variants: tuple[dict, ...] = ()
    view_ids: tuple[str, ...] = ()
    planned: int = 0
    rounds: int = 0
    alone: bool = False
    windows: bool = True
    cal: dict | None = None  # the calibration `calibration` names, loaded (load_calibration)
    first: dict | None = None  # A8's evidence in the session `remeasures` names


def candidates(kind: str, variants: tuple[dict, ...] | list[dict], suite: dict) -> int:
    """Ci, the candidates per round beside the baseline (measurement.md#session): a calibration
    session's twins (statistics.calibration.twinsPerSession), else the spec's candidates and the
    A/A twin."""
    if kind == "calibration":
        return suite["statistics"]["calibration"]["twinsPerSession"]
    return len(variants)  # the candidates after the baseline, and the twin


def planned_reloads(views: int, ci: int, rounds: int, warmup: bool = True) -> int:
    """A measured session's reloads (measurement.md#session, plans/m2.md P12): selftest's and the
    start-of-run reload, the warm-up pass's one per view, then per view the schedule's
    1 + 2 x R x Ci."""
    return ACCEPTANCE_RELOADS + (views if warmup else 0) + views * (1 + 2 * rounds * ci)


def mode_views(suite: dict, mode: str, views: dict) -> tuple[str, ...]:
    """The mode's views (suite.json modes.<mode>.views, "all" for every view) in the views file's
    order; RecordError for a view the file lacks."""
    listed = [view["id"] for view in views["views"]]
    wanted = suite["modes"][mode]["views"]
    if wanted == "all":
        return tuple(listed)
    unknown = [vid for vid in wanted if vid not in listed]
    if unknown:
        raise RecordError(
            f"suite.json modes.{mode}.views names {', '.join(unknown)}, which {VIEWS}/"
            f"{views['id']}.json lacks; fix: the mode's views or the views file"
        )
    return tuple(vid for vid in listed if vid in wanted)


def profile_options(root: Path, suite: dict, name: str) -> dict[str, str | bool]:
    """A profile's option values (config/profiles/<reference pack>-<name>.json, its `options`), as
    the pack's settings file takes them: a number keeps its text in the file ("0.50" stays
    "0.50", the value the pack's option lists; Iris ignores a value outside them), a boolean
    stays a boolean. RecordError naming the fix."""
    known = suite["reference"]["profiles"]
    if name not in known:
        raise RecordError(f"profile {name!r}; fix: one of {', '.join(known)} (suite.json)")
    path = root / PROFILES / f"{suite['reference']['pack']}-{name}.json"
    shown_path = f"{PROFILES}/{path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=str, parse_int=str)
    except OSError:
        raise RecordError(f"no profile file {shown_path}; fix: add it") from None
    except ValueError as error:
        raise RecordError(f"{shown_path} is not JSON ({error}); fix: repair it") from None
    options = data.get("options") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("id") != name or not isinstance(options, dict):
        raise RecordError(
            f"{shown_path} is no profile {name} with an options object; fix: give id and options"
        )
    return check_options(shown_path, options)


def check_options(where: str, options: Any) -> dict[str, str | bool]:
    """Option values as a settings file holds them: names a pack can define, each value a text of
    one printable line without a backslash, or a boolean."""
    if not isinstance(options, dict):
        raise RecordError(f"{where}: options is no object; fix: give name-value pairs")
    for key, value in options.items():
        if not OPTION_NAME.fullmatch(key):
            raise RecordError(f"{where}: option {key!r} is no option name; fix: the pack's name")
        if isinstance(value, bool):
            continue
        if not isinstance(value, str) or not value.isprintable() or "\\" in value or not value:
            raise RecordError(
                f"{where}: {key} is {value!r}; fix: write the value as the pack's own text, e.g. "
                '"-1" or "0.50" (a JSON number would lose "0.50"\'s zero), or true or false'
            )
    return dict(options)


def check_variants(root: Path, data: dict, suite: dict, pack: str) -> tuple[dict, ...]:
    """A measured run's variants: objects of id, pack, profile and optionally options and timers;
    the first the baseline, ids unique and never a twin's; each pack the reference pack `pack`
    (the passthrough pack comes with M2.P08); a calibration run holds the baseline alone, as the
    runner adds its twins. Each checked variant's options: the profile's with the spec's over
    them."""
    variants = data["variants"]
    kind = data["kind"]
    if not isinstance(variants, list) or not variants:
        raise RecordError("variants lists none; fix: the baseline first, then the candidates")
    if kind == "calibration" and len(variants) != 1:
        raise RecordError(
            f"a calibration run measures the baseline against its twins, and lists {len(variants)} "
            "variants; fix: the baseline alone (the runner adds the twins)"
        )
    found = []
    for index, variant in enumerate(variants):
        where = f"variant {index + 1}"
        if not isinstance(variant, dict):
            raise RecordError(f"{where} is no object; fix: give id, pack and profile")
        missing = [key for key in VARIANT_REQUIRED if key not in variant]
        extra = [key for key in variant if key not in (*VARIANT_REQUIRED, *VARIANT_OPTIONAL)]
        if missing or extra:
            known = ", ".join((*VARIANT_REQUIRED, *VARIANT_OPTIONAL))
            raise RecordError(
                f"{where}: missing {missing or 'none'}, unknown {extra or 'none'}; fix: use {known}"
            )
        vid = variant["id"]
        if not isinstance(vid, str) or not NAME.fullmatch(vid) or vid.startswith(TWIN):
            raise RecordError(
                f"{where}: id {vid!r} is not [a-z0-9-]{{1,40}} or starts with {TWIN} (the runner's "
                "twins); fix: rename it"
            )
        if vid in (v["id"] for v in found):
            raise RecordError(f"{where}: id {vid} is listed twice; fix: rename one")
        if variant["pack"] != pack:
            raise RecordError(
                f"{where}: pack {variant['pack']!r}; fix: the reference pack {pack} (the "
                "passthrough pack comes with M2.P08)"
            )
        profile = variant["profile"]
        if profile is not None and not isinstance(profile, str):
            raise RecordError(f"{where}: profile {profile!r}; fix: a profile's name, or null")
        options = profile_options(root, suite, profile) if profile is not None else {}
        options.update(check_options(where, variant.get("options", {})))
        timers = variant.get("timers", False)
        if not isinstance(timers, bool):
            raise RecordError(f"{where}: timers {timers!r}; fix: true or false")
        if timers and kind == "calibration":
            raise RecordError(
                f"{where}: timers on in a calibration run would calibrate timer twins, M4's "
                "(plans/m2.md section 2); fix: timers false"
            )
        found.append(
            {"id": vid, "pack": pack, "profile": profile, "options": options, "timers": timers}
        )
    return tuple(found)


def check_measured_items(items: tuple[str, ...], variants: tuple[dict, ...]) -> None:
    """A8 and A11's variants (plans/m2.md M2.P10): A8 a baseline without timers and a candidate
    equal to it with them; A11 every variant with timers on."""
    base = variants[0]
    if "A8" in items:
        same = [
            v
            for v in variants[1:]
            if v["timers"] and (v["profile"], v["options"]) == (base["profile"], base["options"])
        ]
        if base["timers"] or not same:
            raise RecordError(
                "A8 compares the baseline with timers off against itself with them on; fix: the "
                "baseline without timers, a candidate equal to it with timers true"
            )
    if "A11" in items and not all(v["timers"] for v in variants):
        raise RecordError("A11 times every variant; fix: timers true on each one")


def check_spec(
    root: Path,
    data: Any,
    plat: platform.Platform,
    suite: dict,
    saves: Path,
    pack: str,
    fresh: bool = True,
) -> Spec:
    """A run spec checked before anything launches (run-record.md#run-spec): its fields, a
    single-use name, the kind, the bench tier, the views file and its snapshot, the world under
    `saves`, the standard resource-pack set and the session's reload budget. An acceptance run
    without a mode: one variant of the reference pack `pack` at its defaults, items `run`
    performs, F4's reload count (`reloads`, a multiple of RELOAD_EVERY). A measured run (`mode`
    quick or full; measurement, calibration, or acceptance of A8 and A11): its variants
    (check_variants), `calibration` written null (plans/m2.md D40: M2.P07 brings calibrations),
    `heap` true or false, a budget run's rounds and dimensions (check_budget), no treatment and
    no reloads. Each refusal names its fix. `fresh` False skips the single-use name (`calibrate`
    builds the identity before naming a session)."""
    if not isinstance(data, dict):
        raise RecordError("the spec is no JSON object; fix: give its fields as an object")
    missing = [key for key in SPEC_REQUIRED if key not in data]
    if missing:
        raise RecordError(f"the spec lacks {', '.join(missing)}; fix: add them (run-record.md)")
    unknown = [key for key in data if key not in (*SPEC_REQUIRED, *SPEC_OPTIONAL)]
    if unknown:
        known = ", ".join((*SPEC_REQUIRED, *SPEC_OPTIONAL))
        raise RecordError(f"the spec has unknown {', '.join(unknown)}; fix: use only {known}")
    name = data["name"]
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise RecordError(f"name {name!r} is not [a-z0-9-]{{1,40}}; fix: rename the run")
    for taken in (root / RECORDS / f"{name}.json", root / RAW / name) if fresh else ():
        if taken.exists():
            raise RecordError(
                f"run {name} exists ({taken.relative_to(root).as_posix()}); fix: pick a new name "
                "(run names are single-use)"
            )
    kind = data["kind"]
    if kind not in KINDS:
        raise RecordError(f"kind {kind!r}; fix: one of {', '.join(KINDS)}")
    mode = data.get("mode")
    if kind != "acceptance" and mode is None:
        raise RecordError(f"a {kind} run measures a mode's schedule; fix: mode quick or full")
    if mode is not None and mode not in MODES:
        raise RecordError(f"mode {mode!r}; fix: one of {', '.join(MODES)}")
    if data.get("treatment") is not None:
        raise RecordError(
            "treatment: declared treatments come with the JVM track (run-record.md#comparison); "
            "fix: drop it"
        )
    if data["tier"] != "bench":
        raise RecordError(
            f"tier {data['tier']!r}: runs use the bench tier, the one every measurement uses; "
            "fix: set tier bench"
        )
    views = data["views"]
    if not isinstance(views, str) or not VIEW_ID.fullmatch(views):
        raise RecordError(f"views {views!r} names no views file; fix: a config/views/ stem")
    views_file, _ = load_views(root, views)
    if not (root / SNAPSHOTS / views).is_dir():
        raise RecordError(
            f"no snapshot {SNAPSHOTS}/{views}/; fix: copy the world there and hash it (D23)"
        )
    world = data["world"]
    if (
        not isinstance(world, str)
        or Path(world).name != world
        or world in (".", "..")
        or not (saves / world / "level.dat").is_file()
    ):
        raise RecordError(
            f"world {world!r} is no folder of {saves.as_posix()}/ with a level.dat; fix: name the "
            "snapshot's live copy"
        )
    sets = suite.get("resourcePacks", {})
    if data["resourcePacks"] != PACK_SET:
        known = ", ".join(key for key, value in sets.items() if isinstance(value, list))
        raise RecordError(
            f"resourcePacks {data['resourcePacks']!r}: launch writes the {PACK_SET} set only "
            f"(of {known}); fix: set {PACK_SET} (M3 adds the deterministic set)"
        )
    notes = data.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise RecordError("notes must be text; fix: write them as one string")
    items = data.get("items", [] if mode is not None else None)
    cap = suite["capture"]["reloadCap"]
    if mode is None:
        return check_acceptance_spec(data, suite, pack, views, world, notes, items, cap)
    allowed = MEASURED_ITEMS if kind == "acceptance" else ()
    if not isinstance(items, list) or (kind == "acceptance" and not items):
        raise RecordError(
            f"items {items!r}: a measured {kind} run takes "
            + (f"some of {', '.join(allowed)}" if allowed else "none")
            + "; fix: "
            + (f"name some of {', '.join(allowed)}" if allowed else "drop items or write []")
        )
    if len(set(items)) != len(items) or any(item not in allowed for item in items):
        raise RecordError(
            f"items {items}: a measured {kind} run takes "
            + (f"{', '.join(allowed)}, each once" if allowed else "none")
            + "; fix: drop the others (M1's items run without a mode)"
        )
    for key in ("reloads",):
        if data.get(key) is not None:
            raise RecordError(f"{key} is F4's acceptance table; fix: heap true reads the heap")
    if "calibration" not in data:
        raise RecordError(
            "the spec does not name its calibration; fix: the id `optilux calibrate` printed, or "
            "null (plans/m2.md D40: no verdicts, and `compare` refuses the record)"
        )
    heap = data.get("heap", False)
    if not isinstance(heap, bool):
        raise RecordError(f"heap {heap!r}; fix: true or false")
    if heap and (kind == "calibration" or data["calibration"] is not None):
        raise RecordError(
            "heap true runs a GC every 10 reloads, which no measured run it would judge runs; "
            "fix: heap false (the budget runs read it, calibration null: plans/m2.md M2.P06)"
        )
    variants = check_variants(root, data, suite, pack)
    order = tuple(item for item in MEASURED_ITEMS if item in items)
    check_measured_items(order, variants)
    ids = mode_views(suite, mode, views_file)
    rounds, ids, alone, windows = check_budget(
        data, kind, heap, suite["modes"][mode]["rounds"], ids, views_file, variants
    )
    cal = check_calibration(root, data, kind, mode)
    first = check_remeasures(root, data, order)
    planned = planned_reloads(len(ids), candidates(kind, variants, suite), rounds)
    # A budget run (heap true, calibration null) measures the leak past the cap and judges
    # nothing; F4's 2 GiB guard stops it before the machine pages (plans/m2.md D43, M2.P06).
    budget = kind == "measurement" and heap and data["calibration"] is None
    if planned > cap and not budget:
        raise RecordError(
            f"the session plans {planned} reloads (selftest's and the start-of-run, the warm-up "
            f"pass, {len(ids)} views x the schedule), over capture.reloadCap {cap}; fix: quick "
            "mode or fewer candidates (a session over the cap splits into launches of views, "
            "plans/m2.md D43, not built yet)"
        )
    return Spec(
        name,
        kind,
        views,
        world,
        pack,
        "bench",
        PACK_SET,
        order,
        notes,
        data,
        mode=mode,
        calibration=data["calibration"],
        heap=heap,
        variants=variants,
        view_ids=ids,
        planned=planned,
        rounds=rounds,
        alone=alone,
        windows=windows,
        cal=cal,
        first=first,
    )


def check_calibration(root: Path, data: dict, kind: str, mode: str) -> dict | None:
    """The calibration a measured run is judged by (measurement.md#calibration, plans/m2.md D40),
    loaded: none for a calibration run, which is judged by none; null allowed for a measurement
    run, which then has no verdicts; named for A8 and A11, which are judged. A named one exists,
    is the spec's mode's and covers its resource-pack set; its identity is matched once the run's
    is built (`run`'s prepare)."""
    cid = data["calibration"]
    if cid is None:
        if kind == "acceptance":
            raise RecordError(
                "A8 and A11 are judged by a calibration, and the spec names none; fix: the full "
                "calibration's id (`optilux calibrate --mode full`)"
            )
        return None
    if kind == "calibration":
        raise RecordError(
            f"a calibration run is judged by no calibration, and names {cid!r}; fix: null"
        )
    cal = load_calibration(root, cid)
    if cal["mode"] != mode:
        raise RecordError(
            f"calibration {cid[:24]}... is {cal['mode']} mode's, the spec runs {mode}; fix: the "
            f"{mode} calibration's id"
        )
    if cal["resourcePacks"] != data["resourcePacks"]:
        raise RecordError(
            f"calibration {cid[:24]}... covers the {cal['resourcePacks']} resource-pack set, the "
            f"spec runs {data['resourcePacks']}; fix: a calibration of that set"
        )
    return cal


def check_remeasures(root: Path, data: dict, items: tuple[str, ...]) -> dict | None:
    """`remeasures`: the A8 session whose views beyond their own threshold this run re-measures
    (plans/m2.md M2.P10); its A8 entry waits on them (`remeasure`) under the spec's calibration.
    The first session's A8 evidence."""
    name = data.get("remeasures")
    if name is None:
        return None
    if "A8" not in items:
        raise RecordError("remeasures is A8's second session; fix: drop it, or run A8")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise RecordError(f"remeasures {name!r}; fix: the first A8 session's run name")
    first = read_record(root, name)
    entry = next((e for e in first.get("acceptance") or [] if e.get("item") == "A8"), None)
    evidence = (entry or {}).get("evidence") or {}
    if entry is None or entry.get("pass") is not None or not evidence.get("remeasure"):
        raise RecordError(
            f"{name}'s A8 waits on no view to re-measure; fix: name the session whose A8 entry "
            "says `remeasure`"
        )
    if evidence.get("calibration") != data["calibration"]:
        raise RecordError(
            f"{name}'s A8 was judged by another calibration; fix: the same calibration"
        )
    return evidence


def check_budget(
    data: dict,
    kind: str,
    heap: bool,
    rounds: int,
    ids: tuple[str, ...],
    views: dict,
    variants: tuple[dict, ...],
) -> tuple[int, tuple[str, ...], bool, bool]:
    """A budget run's rounds, views, `alone` and `windows` (BUDGET): the spec's rounds, a
    positive count, else the mode's; the mode's views in the spec's dimensions, else all of them,
    then those `keepViews` names; `alone` (the baseline in every slot) only without candidates;
    `windows` false only without timers. Each refused outside a measurement run with heap true."""
    given = [key for key in BUDGET if data.get(key) is not None]
    if given and (kind != "measurement" or not heap):
        raise RecordError(
            f"{', '.join(given)}: a budget run's (plans/m2.md M2.P06), whose heap table sets the "
            "reload cap; fix: drop them, or run kind measurement with heap true"
        )
    if data.get("rounds") is not None:
        rounds = data["rounds"]
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise RecordError(f"rounds {rounds!r}; fix: a positive count, or leave it out")
    dims = data.get("dimensions")
    if dims is not None:
        if (
            not isinstance(dims, list)
            or not dims
            or any(not isinstance(dim, str) for dim in dims)
            or len(set(dims)) != len(dims)
            or any(dim not in DIMENSIONS for dim in dims)
        ):
            raise RecordError(
                f"dimensions {dims!r}; fix: some of {', '.join(DIMENSIONS)}, each once"
            )
        dim_of = {view["id"]: view["dim"] for view in views["views"]}
        ids = tuple(vid for vid in ids if dim_of[vid] in dims)
        if not ids:
            raise RecordError(
                f"dimensions {dims}: none of the mode's views lies there; fix: another dimension"
            )
    kept = data.get("keepViews")
    if kept is not None:
        if (
            not isinstance(kept, list)
            or not kept
            or any(not isinstance(vid, str) for vid in kept)
            or len(set(kept)) != len(kept)
            or any(vid not in ids for vid in kept)
        ):
            raise RecordError(
                f"keepViews {kept!r}; fix: some of the mode's views here ({', '.join(ids)}), "
                "each once"
            )
        ids = tuple(vid for vid in ids if vid in kept)
    alone, windows = data.get("alone", False), data.get("windows", True)
    for key, value in (("alone", alone), ("windows", windows)):
        if not isinstance(value, bool):
            raise RecordError(f"{key} {value!r}; fix: true or false, or leave it out")
    if alone and len(variants) > 1:
        raise RecordError(
            "alone reloads the baseline in every slot, so no candidate is measured; fix: list "
            "the baseline only"
        )
    if not windows and any(v["timers"] for v in variants):
        raise RecordError(
            "windows false measures no window for the timers to read; fix: timers false"
        )
    return rounds, ids, alone, windows


def check_acceptance_spec(
    data: dict,
    suite: dict,
    pack: str,
    views: str,
    world: str,
    notes: str | None,
    items: Any,
    cap: int,
) -> Spec:
    """An acceptance run without a mode (M1's items): one variant, items, F4's reloads."""
    for key in ("calibration", "heap", *BUDGET):
        if key in data:
            raise RecordError(f"{key} is for measured runs; fix: drop it from an acceptance run")
    variants = data["variants"]
    wanted = [{"pack": pack, "profile": None}]
    if variants != wanted:
        raise RecordError(
            f"variants {json.dumps(variants)}: an acceptance run without a mode has one variant, "
            f"the reference pack at its defaults; fix: {json.dumps(wanted)}"
        )
    runnable = ", ".join(RUNNABLE)
    if not isinstance(items, list) or not items:
        raise RecordError(f"items lists no acceptance item; fix: name some of {runnable}")
    if len(set(items)) != len(items):
        raise RecordError(f"items {items} names one item twice; fix: name each once")
    for item in items:
        if item not in ITEMS:
            raise RecordError(f"item {item!r} is no acceptance item; fix: one of A1..A12")
        if item in MEASURED_ITEMS:
            raise RecordError(f"item {item} runs on a measured schedule; fix: give a mode")
        if item not in RUNNABLE:
            raise RecordError(f"item {item} comes in a later milestone; fix: drop it")
    reloads = data.get("reloads", 0)
    if (
        isinstance(reloads, bool)
        or not isinstance(reloads, int)
        or reloads < 0
        or reloads % RELOAD_EVERY
    ):
        raise RecordError(
            f"reloads {reloads!r} is no count of F4's reloads; fix: a multiple of {RELOAD_EVERY} "
            "(the table's row step), or leave it out"
        )
    planned = ACCEPTANCE_RELOADS + (A4_RELOADS if "A4" in items else 0) + reloads
    if planned > cap:
        raise RecordError(
            f"the session plans {planned} reloads, over capture.reloadCap {cap}; fix: fewer "
            "reloads (the cap is plans/m2.md D43's)"
        )
    order = tuple(item for item in RUNNABLE if item in items)
    return Spec(
        data["name"],
        data["kind"],
        views,
        world,
        pack,
        "bench",
        PACK_SET,
        order,
        notes,
        data,
        reloads,
        planned=planned,
    )


# The identity.


def canonical(value: Any) -> bytes:
    """JSON bytes that do not depend on key order or spacing: what an identity hash covers."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def is_note(key: str) -> bool:
    """A note or ALC-context key (run-record.md#identity), never identity."""
    return (
        key in ("why", "status")
        or key.endswith("Why")
        or key.startswith("estMinutes")
        or key.startswith("alc")
    )


def strip_notes(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_notes(item) for key, item in value.items() if not is_note(key)}
    if isinstance(value, list):
        return [strip_notes(item) for item in value]
    return value


def suite_identity(suite: dict) -> dict:
    """The hash of display, modes, capture, validity and statistics with the notes stripped."""
    sections = {key: strip_notes(suite[key]) for key in SUITE_SECTIONS}
    return {"sha256": sha256_of(sections), "sections": list(SUITE_SECTIONS)}


def platform_identity(plat: platform.Platform, tier: str) -> dict:
    """The hash of the platform file's loaded sections: every top-level key but PLATFORM_OUT, the
    tiers cut to the tier's chain; and the tier. The whole file's hash is recorded apart, never
    matched."""
    loaded = {key: value for key, value in plat.data.items() if key not in PLATFORM_OUT}
    loaded["tiers"] = {name: plat.data["tiers"][name] for name in plat.chain(tier)}
    # Notes stripped as the suite's are: a reworded `why` never forces a recalibration.
    stripped = strip_notes(loaded)
    return {"sha256": sha256_of(stripped), "tier": tier, "tiers": plat.chain(tier)}


def file_sha256(path: Path) -> str:
    return platform.sha256(path)  # streamed: a world region or the A4 zip is never held whole


def java_identity(java_home: Path, java_profile: dict) -> dict:
    """The JVM, read before the launch: the runtime build, its version and the sha256 of the
    JDK's release file, the heap and the profile's flags. `run` holds the version against the
    one the running game reports (hello)."""
    path = java_home / "release"
    if not path.is_file():
        raise RecordError(f"no release file in {java_home.name}; fix: run `optilux install`")
    release = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            release[key] = value.strip().strip('"')
    version = release.get("JAVA_RUNTIME_VERSION")
    if not version:
        raise RecordError(
            f"{java_home.name}'s release file names no JAVA_RUNTIME_VERSION; fix: run "
            "`optilux install`"
        )
    heap = java_profile["heap"]
    return {
        "runtime": java_profile["runtime"]["build"],
        "version": version,
        "release": file_sha256(path),
        "heap": {"xms": heap["size"], "xmx": heap["size"], "unit": heap["unit"]},
        "args": list(java_profile.get("flags", [])),
    }


def settings_identity(settings: dict, options_file: dict) -> dict:
    """`settings` (plans/m2.md D37, D39): the launch's settings facts (launch.settings_facts) with
    the options.txt keys the harness does not write, as the game reads them, and the
    iris.properties keys but shaderPack (the pack is a variant's)."""
    iris = {key: value for key, value in settings["iris"].items() if key != "shaderPack"}
    return {**settings, "iris": iris, "unwritten": options_file["unwritten"]}


# The harness (plans/m2.md D36).


def module_path(root: Path, name: str) -> Path | None:
    """The file of an optilux module name (a module, or a package's __init__.py); None for a name
    that is no module, as `from optilux import REPO_ROOT` names an attribute."""
    base = root.joinpath(*name.split("."))
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    return None


def imported(tree: ast.Module, name: str, package: bool) -> set[str]:
    """The optilux names a module imports anywhere in its code (a deferred import inside a
    function included), each with its parent packages; `from m import n` names m and m.n, m.n
    kept only where it is a module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # relative: from the module's own package up
                parts = name.split(".") if package else name.split(".")[:-1]
                parts = parts[: len(parts) - node.level + 1]
                base = ".".join([*parts, base] if base else parts)
            names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
        else:
            continue
        for full in names:
            parts = full.split(".")
            if parts[0] == PACKAGE:
                found.update(".".join(parts[:end]) for end in range(1, len(parts) + 1))
    return found


def module_closure(root: Path, start: str = RUNNER) -> dict[str, Path]:
    """Every optilux module `start` imports, directly or through another, read with ast and never
    run: `start` itself, its parent packages and each import's module, by module name. A verb
    the runner does not import (status, cli's registry) is outside it."""
    if module_path(root, start) is None:
        raise RecordError(f"no module {start} under {root}; fix: name the runner's module")
    parts = start.split(".")
    queue = [".".join(parts[:end]) for end in range(1, len(parts) + 1)]
    found: dict[str, Path] = {}
    while queue:
        name = queue.pop()
        path = module_path(root, name)
        if name in found or path is None:
            continue
        found[name] = path
        tree = ast.parse(path.read_bytes(), filename=str(path))
        queue.extend(imported(tree, name, path.name == "__init__.py") - found.keys())
    return found


def harness_identity(root: Path, presentmon_exe: Path) -> dict:
    """`harness` (plans/m2.md D36): the sha256 of every module in module_closure, by path, and
    PresentMon's file, sha256 and arguments (the run's pid, CSV and session as placeholders). The
    commit and the dirty flag are recorded, never matched: a docs commit would otherwise force a
    recalibration."""
    modules = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in module_closure(root).values()
    }
    session = f"{presentmon.SESSION_PREFIX}<run>"
    return {
        "modules": dict(sorted(modules.items())),
        "presentMon": {
            "file": presentmon_exe.name,
            "sha256": file_sha256(presentmon_exe),
            "arguments": presentmon.arguments("<pid>", "<csv>", session),
        },
    }


def window_mode(options: dict[str, str]) -> str:
    """The window mode the written options give (suite.json display.windowWhy)."""
    if options.get("fullscreen") != "true":
        return "windowed"
    if options.get("exclusiveFullscreen") == "true":
        return "exclusive fullscreen"
    return "borderless fullscreen"


def identity(
    *,
    plat: platform.Platform,
    tier: str,
    spec_path: Path,
    mods: list[str],
    world: dict,
    views_path: Path,
    packs: list[dict],
    settings: dict,
    suite: dict,
    java: dict,
    system: dict,
    harness: dict,
) -> dict:
    """The identity of one session, keyed as IDENTITY_KEYS; the launch spec and the views file
    hashed when it is built, before the launch."""
    return {
        "platform": platform_identity(plat, tier),
        "launchSpec": {"file": spec_path.name, "sha256": file_sha256(spec_path)},
        "mods": sorted(mods),
        "world": world,
        "views": {"file": views_path.name, "sha256": file_sha256(views_path)},
        "resourcePacks": {"set": PACK_SET, "packs": packs},
        "settings": settings,
        "suite": suite_identity(suite),
        "java": java,
        "system": system,
        "harness": harness,
    }


def launch_differences(found: dict, facts: dict) -> list[str]:
    """The identity keys a started game contradicts: the identity is built before the launch, so
    the launch's placed jars, resource packs and settings facts (launch.launch's `facts`) are
    held against it (`run` also holds the Java `hello` reports and the config files re-read)."""
    packs = [
        {"file": p["file"], "sha512": p["sha512"]}
        for p in facts["hashes"]["packs"]
        if p["kind"] == "resourcePack"
    ]
    launched = {
        "mods": sorted(facts["mods"]["sha512"]),
        "resourcePacks": {"set": PACK_SET, "packs": packs},
        "settings": settings_identity(facts["settings"], facts["optionsFile"]),
    }
    return [key for key, value in launched.items() if found[key] != value]


def check_identity(found: Any) -> None:
    """RecordError unless `found` holds exactly IDENTITY_KEYS, each with a value: an identity
    with a missing measurement is never written (AGENTS.md)."""
    if not isinstance(found, dict):
        raise RecordError("the identity is no object; fix: build it with record.identity")
    missing = [key for key in IDENTITY_KEYS if key not in found]
    extra = [key for key in found if key not in IDENTITY_KEYS]
    empty = [key for key in IDENTITY_KEYS if key in found and found[key] in (None, "", [], {})]
    if missing or extra or empty:
        raise RecordError(
            f"the identity lacks {missing or 'none'}, adds {extra or 'none'}, leaves "
            f"{empty or 'none'} empty; fix: build it with record.identity (run-record.md#identity)"
        )


# The machine (D22): the system facts, read without WMI.

# DISPLAY_DEVICE.StateFlags (wingdi.h): attached to the desktop; the primary display.
ATTACHED = 0x1
PRIMARY = 0x4
ENUM_CURRENT_SETTINGS = -1
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2: a DPI-unaware thread may be shown scaled pixels.
PER_MONITOR_AWARE_V2 = -4
DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
GRAPHICS_DRIVERS = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
CURRENT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
# HAGS as applied (plans/m2.md D38, P15): KMTQAITYPE_WDDM_2_7_CAPS (d3dkmthk.h) answers
# D3DKMT_WDDM_2_7_CAPS, whose low bits are HwSchSupported, HwSchEnabled, HwSchEnabledByDefault
# and IndependentVidPnVSyncControl. HwSchMode in the registry is only the requested state (id6).
WDDM_2_7_CAPS = 70
HWSCH_SUPPORTED = 0x1
HWSCH_ENABLED = 0x2
HWSCH_ENABLED_BY_DEFAULT = 0x4


class Luid(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class OpenAdapterFromGdiDisplayName(ctypes.Structure):
    """D3DKMT_OPENADAPTERFROMGDIDISPLAYNAME."""

    _fields_ = [
        ("DeviceName", ctypes.c_wchar * 32),
        ("hAdapter", ctypes.c_uint32),
        ("AdapterLuid", Luid),
        ("VidPnSourceId", ctypes.c_uint32),
    ]


class QueryAdapterInfo(ctypes.Structure):
    """D3DKMT_QUERYADAPTERINFO."""

    _fields_ = [
        ("hAdapter", ctypes.c_uint32),
        ("Type", ctypes.c_int),
        ("pPrivateDriverData", ctypes.c_void_p),
        ("PrivateDriverDataSize", ctypes.c_uint32),
    ]


class CloseAdapter(ctypes.Structure):
    """D3DKMT_CLOSEADAPTER."""

    _fields_ = [("hAdapter", ctypes.c_uint32)]


def wddm27_caps(name: str, kmt: Any) -> tuple[int, str]:
    """D3DKMT_WDDM_2_7_CAPS of the adapter behind the GDI display `name`, and the adapter's LUID:
    the adapter opened by the name, queried, closed. `kmt` holds the three gdi32 calls (the tests
    pass a fake). Each call only reads; RecordError naming the call and its NTSTATUS, so a failed
    query refuses the run (D38)."""

    def failed(call: str, status: int) -> RecordError:
        return RecordError(
            f"{call} returned NTSTATUS 0x{status & 0xFFFFFFFF:08x}, so HAGS as applied is unread "
            "(plans/m2.md D38); fix: rerun, and read record.wddm27_caps if it repeats"
        )

    opened = OpenAdapterFromGdiDisplayName()
    opened.DeviceName = name
    status = kmt.D3DKMTOpenAdapterFromGdiDisplayName(ctypes.byref(opened))
    if status:
        raise failed(f"D3DKMTOpenAdapterFromGdiDisplayName({name})", status)
    caps = ctypes.c_uint32()
    try:
        query = QueryAdapterInfo(
            opened.hAdapter,
            WDDM_2_7_CAPS,
            ctypes.cast(ctypes.pointer(caps), ctypes.c_void_p),
            ctypes.sizeof(caps),
        )
        status = kmt.D3DKMTQueryAdapterInfo(ctypes.byref(query))
        if status:
            raise failed("D3DKMTQueryAdapterInfo(WDDM_2_7_CAPS)", status)
    finally:
        kmt.D3DKMTCloseAdapter(ctypes.byref(CloseAdapter(opened.hAdapter)))
    luid = (opened.AdapterLuid.HighPart << 32) | opened.AdapterLuid.LowPart
    return caps.value, f"0x{luid:x}"


class Machine:
    """The machine's facts for the system identity; the tests replace it."""

    def displays(self) -> list[dict]:
        """Each display device's name, adapter name and state flags (EnumDisplayDevicesW)."""
        from ctypes import wintypes

        class DisplayDevice(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        found = []
        index = 0
        while True:
            device = DisplayDevice()
            device.cb = ctypes.sizeof(device)
            if not user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
                return found
            found.append(
                {
                    "name": device.DeviceName,
                    "adapter": device.DeviceString,
                    "flags": device.StateFlags,
                }
            )
            index += 1

    def display_mode(self, name: str) -> dict:
        """A display's current mode, read DPI-aware (EnumDisplaySettingsW on a per-monitor-aware
        thread, the thread's awareness restored after)."""
        from ctypes import wintypes

        class DevMode(ctypes.Structure):
            _fields_ = [
                ("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPositionX", wintypes.LONG),
                ("dmPositionY", wintypes.LONG),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(PER_MONITOR_AWARE_V2))
        try:
            mode = DevMode()
            mode.dmSize = ctypes.sizeof(mode)
            if not user32.EnumDisplaySettingsW(name, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
                raise RecordError(f"EnumDisplaySettings({name}) failed; fix: check the display")
        finally:
            if previous:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
        return {
            "width": mode.dmPelsWidth,
            "height": mode.dmPelsHeight,
            "hz": mode.dmDisplayFrequency,
            "dpiAware": bool(previous),
        }

    def registry(self, key: str, value: str) -> Any:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            return winreg.QueryValueEx(handle, value)[0]

    def driver(self, adapter: str) -> str | None:
        """The display driver's version for the adapter's name (the display class key)."""
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DISPLAY_CLASS) as handle:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(handle, index)
                except OSError:
                    return None
                index += 1
                try:
                    with winreg.OpenKey(handle, sub) as entry:
                        if winreg.QueryValueEx(entry, "DriverDesc")[0] == adapter:
                            return winreg.QueryValueEx(entry, "DriverVersion")[0]
                except OSError:
                    continue

    def windows_build(self) -> int:
        return sys.getwindowsversion().build  # type: ignore[attr-defined]

    def hags(self, name: str) -> tuple[int, str]:
        """wddm27_caps through gdi32's D3DKMT calls."""
        gdi32 = ctypes.WinDLL("gdi32")  # type: ignore[attr-defined]
        for call in (
            "D3DKMTOpenAdapterFromGdiDisplayName",
            "D3DKMTQueryAdapterInfo",
            "D3DKMTCloseAdapter",
        ):
            getattr(gdi32, call).argtypes = [ctypes.c_void_p]
            getattr(gdi32, call).restype = ctypes.c_long  # NTSTATUS
        return wddm27_caps(name, gdi32)


def system_facts(machine: Machine, options: dict[str, str], display: dict) -> tuple[dict, dict]:
    """(identity, recorded) of the system: GPU, HAGS as applied (the primary display's adapter's
    WDDM 2.7 caps), resolution, window mode and Windows build, then the facts recorded but never
    matched (the driver, the update revision, the display's rate, the caps and the adapter's
    LUID, HwSchMode as requested: None when unset, "unread: ..." when the read failed). The
    resolution is the primary display's mode, which exclusive fullscreen keeps (no
    fullscreenResolution is written; D22); RecordError, naming the fix, when it or the window
    mode is not the suite's display, or HAGS is unread."""
    displays = machine.displays()
    primary = [d for d in displays if d["flags"] & PRIMARY]
    if len(primary) != 1:
        raise RecordError(f"{len(primary)} primary displays among {len(displays)}; fix: set one")
    mode = window_mode(options)
    if mode != display["window"]:
        raise RecordError(
            f"the written options give {mode}, suite.json display.window says {display['window']}; "
            "fix: the display's optionsTxt"
        )
    screen = machine.display_mode(primary[0]["name"])
    if screen.get("dpiAware") is not True:
        raise RecordError(
            "the display mode was read without DPI awareness (SetThreadDpiAwarenessContext "
            "failed), so it may be a scaled size (D22); fix: rerun, and read record.Machine."
            "display_mode if it repeats"
        )
    resolution = f"{screen['width']}x{screen['height']}"
    if resolution != display["resolution"]:
        raise RecordError(
            f"the primary display runs {resolution}, suite.json display.resolution is "
            f"{display['resolution']}; fix: set the display yourself (the harness never changes "
            "system settings)"
        )
    caps, luid = machine.hags(primary[0]["name"])
    requested: Any
    try:
        requested = machine.registry(GRAPHICS_DRIVERS, "HwSchMode")
    except FileNotFoundError:  # never set: the driver's default applies, which the caps give
        requested = None
    except OSError as error:  # recorded only: unread, never passed off as unset
        requested = f"unread: {error}"
    driver = machine.driver(primary[0]["adapter"])
    if driver is None:
        raise RecordError(
            f"no driver key under HKLM\\{DISPLAY_CLASS} has DriverDesc {primary[0]['adapter']!r}, "
            "and the record notes the driver version (AGENTS.md); fix: find the adapter's key "
            "there and correct record.Machine.driver's match"
        )
    found = {
        "gpu": primary[0]["adapter"],
        "hags": bool(caps & HWSCH_ENABLED),
        "resolution": resolution,
        "windowMode": mode,
        "windowsBuild": machine.windows_build(),
    }
    recorded = {
        "driver": driver,
        "windowsRevision": machine.registry(CURRENT_VERSION, "UBR"),
        "display": {
            "name": primary[0]["name"],
            "hz": screen["hz"],
            "displays": sum(1 for d in displays if d["flags"] & ATTACHED),
        },
        "hags": {
            "caps": caps,
            "supported": bool(caps & HWSCH_SUPPORTED),
            "enabledByDefault": bool(caps & HWSCH_ENABLED_BY_DEFAULT),
            "adapterLuid": luid,
        },
        "hwSchMode": requested,
    }
    return found, recorded


# The record.


def check_acceptance(items: Any) -> None:
    """Each entry item, pass, evidence: pass a boolean, or null while its verdict waits, the
    evidence's `pending` saying on what (run-record.md#record)."""
    if not isinstance(items, list) or not items:
        raise RecordError("an acceptance record holds no item; fix: record each item run")
    for entry in items:
        if not isinstance(entry, dict) or tuple(entry) != ACCEPTANCE_KEYS:
            raise RecordError(f"acceptance entry {entry!r}; fix: give item, pass, evidence")
        evidence = entry["evidence"] if isinstance(entry["evidence"], dict) else {}
        waits = entry["pass"] is None and isinstance(evidence.get("pending"), str)
        if entry["item"] not in ITEMS or not (isinstance(entry["pass"], bool) or waits):
            raise RecordError(
                f"acceptance entry {entry['item']!r}: no item, or a pass neither boolean nor null "
                "with its pending reason"
            )


def write_record(root: Path, record: dict, say: Callable[[str], None] | None = None) -> Path:
    """results/records/<name>.json, once: the identity checked (check_identity; a session that
    failed before its identity was read records none, and never with status ok), an acceptance
    record's items checked, the status one of STATUSES; JSON, LF, never overwritten."""
    name = record.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise RecordError(f"record name {name!r}; fix: the spec's name")
    if record.get("status") not in STATUSES:
        raise RecordError(f"status {record.get('status')!r}; fix: one of {', '.join(STATUSES)}")
    if record.get("identity") is not None or record["status"] == "ok":
        check_identity(record.get("identity"))
    if record.get("kind") == "acceptance":
        check_acceptance(record.get("acceptance"))
    path = root / RECORDS / f"{name}.json"
    if path.exists():
        raise RecordError(f"{RECORDS}/{path.name} exists; fix: records are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    # Written whole beside it, then renamed: a run killed mid-write leaves no short record, and
    # the rename refuses a record that appeared meanwhile.
    part = path.with_name(f".{path.name}.part")
    part.write_bytes(text.encode("utf-8"))
    try:
        part.rename(path)
    except FileExistsError:
        part.unlink()
        raise RecordError(
            f"{RECORDS}/{path.name} exists; fix: records are never overwritten"
        ) from None
    if say is not None:
        say(f"record: {RECORDS}/{path.name}, {len(text.encode('utf-8')):,} bytes")
    return path


def read_record(root: Path, name: str) -> dict:
    """results/records/<name>.json as an object; RecordError naming the fix."""
    path = root / RECORDS / f"{name}.json"
    if not NAME.fullmatch(name) or not path.is_file():
        raise RecordError(f"no record {RECORDS}/{name}.json; fix: a run's name (`ls {RECORDS}`)")
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise RecordError(f"{RECORDS}/{name}.json is not JSON ({error}); fix: restore it") from None
    if not isinstance(found, dict):
        raise RecordError(f"{RECORDS}/{name}.json is no object; fix: restore it from git")
    return found


def record_names(root: Path) -> list[str]:
    """Every record's name under results/records/, sorted."""
    folder = root / RECORDS
    return sorted(p.stem for p in folder.glob("*.json")) if folder.is_dir() else []


def judged_twins(root: Path, cid: str) -> list[bool]:
    """The twin monitor's history (measurement.md#calibration): for every record judged by the
    calibration `cid` whose twin was judged, oldest first by its start, whether its twin lay at or
    beyond the geo-mean threshold; a record that cannot be read is `verify records`' to report."""
    found = []
    for name in record_names(root):
        try:
            one = read_record(root, name)
        except RecordError:
            continue
        judged = one.get("verdicts") or {}
        twin = judged.get("twin") or {}
        if judged.get("calibration") == cid and twin.get("inside") is not None:
            found.append((str(one.get("startedAt")), twin["inside"] is False))
    return [beyond for _, beyond in sorted(found)]


# Calibrations (measurement.md#calibration): config/calibrations/<mode>-<identity sha256>.json,
# written by `calibrate`, matched key by key on the identity; the baseline pack recorded, not
# matched (user, 2026-10-06).
CALIBRATIONS = "config/calibrations"
CALIBRATION_ID = re.compile(r"(?:quick|full)-[0-9a-f]{64}")
CALIBRATION_KEYS = (
    "schema",
    "id",
    "mode",
    "createdAt",
    "identityHash",
    "identity",
    "resourcePacks",
    "views",
    "rounds",
    "twinsPerSession",
    "falseRate",
    "floorPct",
    "baseline",
    "sessions",
    "nulls",
    "thresholds",
)


def identity_hash(found: dict) -> str:
    """An identity's sha256 over its canonical JSON: a calibration's id carries it."""
    return sha256_of(found)


def load_calibration(root: Path, cid: Any) -> dict:
    """config/calibrations/<cid>.json checked: an id `calibrate` writes, its fields, its id and
    identity hash agreeing with its identity. RecordError naming the fix, `calibrate` when the
    calibration does not exist."""
    if not isinstance(cid, str) or not CALIBRATION_ID.fullmatch(cid):
        raise RecordError(
            f"calibration {cid!r} is no calibration id (<mode>-<the identity's sha256>); fix: the "
            "id `optilux calibrate` printed, or null"
        )
    mode = cid.split("-", 1)[0]
    path = root / CALIBRATIONS / f"{cid}.json"
    shown_path = f"{CALIBRATIONS}/{path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise RecordError(
            f"no calibration {cid[:24]}... in {CALIBRATIONS}/; fix: `optilux calibrate --mode "
            f"{mode}` for this identity"
        ) from None
    except ValueError as error:
        raise RecordError(f"{shown_path} is not JSON ({error}); fix: restore it") from None
    missing = [key for key in CALIBRATION_KEYS if not isinstance(data, dict) or key not in data]
    if missing:
        raise RecordError(
            f"{shown_path} lacks {', '.join(missing)}; fix: restore it from git, or `optilux "
            f"calibrate --mode {mode}` again"
        )
    digest = identity_hash(data["identity"])
    held = (data["id"], data["mode"], data["identityHash"], cid)
    if held != (cid, mode, digest, f"{mode}-{digest}"):
        raise RecordError(
            f"{shown_path}: its id, mode or identity hash disagrees with its content; fix: "
            "restore it from git (a calibration is never edited)"
        )
    return data


def first_difference(a: Any, b: Any, path: str) -> str:
    """The first path at which two differing JSON values differ (a key, then an index)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in [*a, *(k for k in b if k not in a)]:
            inner = f"{path}.{key}" if re.fullmatch(r"[A-Za-z_]\w*", key) else f'{path}["{key}"]'
            if key not in a or key not in b:
                return f"{inner} (in one only)"
            if a[key] != b[key]:
                return first_difference(a[key], b[key], inner)
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            if x != y:
                return first_difference(x, y, f"{path}[{i}]")
    return path


def identity_differences(found: Any, other: Any) -> list[str]:
    """The identity keys on which two identities differ, in IDENTITY_KEYS order, each as the
    first path inside it that differs (`harness.modules["optilux/stats.py"]`); a key one of them
    lacks is named so; `identity` alone when either was never recorded."""
    if not isinstance(found, dict) or not isinstance(other, dict):
        return ["identity (none recorded)"]
    keys = [*IDENTITY_KEYS, *(k for k in [*found, *other] if k not in IDENTITY_KEYS)]
    differ = []
    for key in dict.fromkeys(keys):
        if key not in found or key not in other:
            differ.append(f"{key} (in one only)")
        elif found[key] != other[key]:
            differ.append(first_difference(found[key], other[key], key))
    return differ
