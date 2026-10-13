"""`optilux calibrate --mode quick|full [--json]` (docs/measurement.md#calibration, docs/plans/m2.md
M2.P07 and M2.P09): the current identity's calibration.

- Its sessions: statistics.calibration.minSessionsPerMode calibration runs of the baseline (D35:
  the reference pack with the played profile; the runner adds twinsPerSession twins), named
  cal-<mode>-<the identity hash's first 12>-<n>. A session counts when its record is ok, of this
  identity, kind and mode, and each twin is judged on every view of the mode (stats.nulls_of).
- The count comes first, announced: the sessions whole, those to run and their launches; then each
  session runs through `run`'s runner, each launch announced as `run` announces it. calibrate stops
  at the first session that does not end whole; a rerun resumes, keeping the whole sessions and
  passing over a taken name (a record that does not count, or an orphan the runner finishes).
- Then config/calibrations/<mode>-<identity sha256>.json: the identity and its hash, the mode's
  views and rounds, the false rate and floor, the baseline (recorded, never matched), the
  sessions, every null candidate's per-view ratios and the thresholds they give. An existing
  calibration of the identity ends calibrate at once.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from optilux import REPO_ROOT, launch, platform, record, stats, world
from optilux.session import RunHost, now
from optilux.verbs import Verb
from optilux.verbs import run as run_verb
from optilux.verbs.install import Say, shown

PREFIX = "optilux calibrate"
# plans/m2.md D35: the baseline is Unbound r5.9.3 with the played profile.
BASELINE_PROFILE = "played"
# The bench world (measurement.md#baseline-suite): its views file, snapshot and live world.
WORLD = "bench_263"
# A session's name: its identity's hash cut to 12 hex digits keeps it within record.NAME's 40.
HASH_SHOWN = 12


def session_name(mode: str, digest: str, n: int) -> str:
    return f"cal-{mode}-{digest[:HASH_SHOWN]}-{n}"


def session_spec(name: str, mode: str, pack: str) -> dict:
    """One calibration session's run spec."""
    return {
        "name": name,
        "kind": "calibration",
        "mode": mode,
        "views": WORLD,
        "world": WORLD,
        "variants": [{"id": "baseline", "pack": pack, "profile": BASELINE_PROFILE}],
        "tier": "bench",
        "resourcePacks": record.PACK_SET,
        "calibration": None,
        "notes": "calibrate: a null session, the baseline against its twins (measurement.md)",
    }


@dataclass(frozen=True)
class Plan:
    """The calibration to make: the identity, its id, the mode's views and rounds, the sessions
    it needs and the launches a session takes."""

    mode: str
    identity: dict
    digest: str
    cid: str
    views: list[str]
    rounds: int
    twins: int
    need: int
    launches: int
    ready: run_verb.Prepared


def plan(root: Path, mode: str, machine: record.Machine) -> Plan:
    """The current identity, built as `run` builds it for a calibration session (nothing
    launched), and what the calibration of the mode needs."""
    pack = launch.reference_pack(platform.load(root)).file
    probe = session_spec(f"cal-{mode}-probe", mode, pack)
    ready = run_verb.prepare(root, probe, machine, fresh=False)
    digest = record.identity_hash(ready.identity)
    calibration = ready.suite["statistics"]["calibration"]
    return Plan(
        mode=mode,
        identity=ready.identity,
        digest=digest,
        cid=f"{mode}-{digest}",
        views=list(ready.spec.view_ids),
        rounds=ready.spec.rounds,
        twins=calibration["twinsPerSession"],
        need=calibration["minSessionsPerMode"],
        launches=1,
        ready=ready,
    )


def session_state(root: Path, p: Plan, name: str) -> dict:
    """A session name's state: `new` (nothing under it), `taken` (a record that does not count,
    or a run whose record is not written: an orphan `run` finishes), or `whole` with its null
    candidates."""
    if not (root / record.RECORDS / f"{name}.json").is_file():
        return {"state": "taken" if (root / record.RAW / name).exists() else "new"}
    found = record.read_record(root, name)
    problems = []
    if found.get("status") != "ok":
        problems.append(f"status {found.get('status')}: {found.get('reason')}")
    differ = record.identity_differences(found.get("identity"), p.identity)
    if differ:
        problems.append(f"another identity ({', '.join(differ)})")
    if (found.get("kind"), found.get("mode")) != ("calibration", p.mode):
        problems.append(f"a {found.get('kind')} run of mode {found.get('mode')}")
    if not problems:
        nulls = stats.nulls_of(found.get("captures") or [], p.views, p.rounds, name)
        problems += nulls["problems"]
        if not problems:
            return {"state": "whole", "nulls": nulls["nulls"]}
    return {"state": "taken", "why": "; ".join(problems)}


def write_calibration(root: Path, p: Plan, sessions: list[tuple[str, list[dict]]]) -> Path:
    """config/calibrations/<id>.json from the whole sessions' null candidates."""
    rules = p.ready.suite["statistics"]
    nulls = [null for _, found in sessions for null in found]
    found = stats.thresholds(nulls, p.views, rules["falseRate"], rules["thresholdFloorPct"])
    base = p.ready.spec.variants[0]
    data = {
        "schema": record.SCHEMA,
        "id": p.cid,
        "mode": p.mode,
        "createdAt": now(),
        "identityHash": p.digest,
        "identity": p.identity,
        "resourcePacks": record.PACK_SET,
        "views": p.views,
        "rounds": p.rounds,
        "twinsPerSession": p.twins,
        "falseRate": rules["falseRate"],
        "floorPct": rules["thresholdFloorPct"],
        "baseline": {
            "pack": p.ready.pack.file,
            "sha512": p.ready.pack.sha512,
            "profile": base["profile"],
            "options": base["options"],
        },
        "sessions": [name for name, _ in sessions],
        "nulls": nulls,
        "thresholds": stats.rounded(found),
    }
    path = root / record.CALIBRATIONS / f"{p.cid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    part = path.with_name(f".{path.name}.part")
    part.write_bytes(text.encode("utf-8"))
    part.replace(path)
    record.load_calibration(root, p.cid)  # read back as `run` and `compare` will read it
    return path


def calibrate(
    root: Path, mode: str, host: RunHost, machine: record.Machine, say: Say, announce: Say
) -> dict:
    """The identity's calibration of `mode`: its missing sessions run, each announced, then its
    file written. The outcome: the id, the sessions, whether it stopped and why."""
    p = plan(root, mode, machine)
    path = root / record.CALIBRATIONS / f"{p.cid}.json"
    outcome: dict = {"calibration": p.cid, "identityHash": p.digest, "mode": mode, "ran": []}
    if path.is_file():
        say(f"{PREFIX}: {shown(path, root)} exists for this identity; nothing to run")
        return {**outcome, "path": shown(path, root), "stopped": None}
    whole: list[tuple[str, list[dict]]] = []
    passed: list[str] = []
    n = 1
    while True:  # the names taken so far: whole sessions kept, others passed over
        name = session_name(mode, p.digest, n)
        state = session_state(root, p, name)
        if state["state"] == "new":
            break
        if state["state"] == "whole":
            whole.append((name, state["nulls"]))
        else:
            passed.append(f"{name} ({state.get('why') or 'no record yet'})")
        n += 1
    todo = max(0, p.need - len(whole))
    announce(
        f"{PREFIX}: {mode} mode, identity {p.digest[:HASH_SHOWN]}: {p.need} sessions of "
        f"{p.twins} twins; {len(whole)} whole, {todo} to run, {todo * p.launches} launch(es) of "
        "the game in all, each announced; hands off the mouse and keyboard until the end"
    )
    for skipped in passed:
        say(f"{PREFIX}: passed over {skipped}")
    pack = p.ready.pack.file
    while len(whole) < p.need:
        name = session_name(mode, p.digest, n)
        n += 1
        if session_state(root, p, name)["state"] != "new":
            continue
        say(f"{PREFIX}: session {len(whole) + 1} of {p.need}: {name}")
        found, _ = run_verb.run_session(
            root, session_spec(name, mode, pack), host, machine, say, announce
        )
        outcome["ran"].append(name)
        state = session_state(root, p, name)
        if state["state"] != "whole":
            why = state.get("why") or found.get("reason") or found.get("status")
            return {**outcome, "stopped": f"{name} does not count: {why}", "whole": len(whole)}
        whole.append((name, state["nulls"]))
    written = write_calibration(root, p, whole[: p.need])
    return {**outcome, "path": shown(written, root), "stopped": None, "whole": len(whole)}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", required=True, choices=record.MODES, help="quick or full")


def run(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)

    def announce(text: str) -> None:  # every launch is announced, --json or not
        print(text, file=sys.stderr if args.json else sys.stdout, flush=True)

    try:
        outcome = calibrate(root, args.mode, RunHost(), record.Machine(), say, announce)
    except (
        record.RecordError,
        platform.PlatformError,
        launch.LaunchError,
        world.WorldError,
        OSError,
    ) as error:
        problem = str(error)
        if args.json:
            print(json.dumps({"ok": False, "problem": problem}))
        else:
            print(f"{PREFIX}: {problem}", file=sys.stderr)
        return 1
    ok = outcome["stopped"] is None
    if args.json:
        print(json.dumps({"ok": ok, **outcome}))
    elif ok:
        print(f"{PREFIX}: {outcome['calibration']} in {outcome['path']}")
    else:
        print(f"{PREFIX}: stopped: {outcome['stopped']}; rerun to resume", file=sys.stderr)
    return 0 if ok else 1


VERB = Verb(
    name="calibrate",
    help="run the current identity's missing null sessions and write its calibration",
    run=run,
    configure=configure,
    structured=True,
)
