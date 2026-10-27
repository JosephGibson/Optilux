"""`optilux run <spec.json> [--check] [--json]` (docs/run-record.md#run-spec, docs/plans/m1.md
0.01.08 and 0.01.09, docs/plans/m2.md M2.P01 and M2.P05).

One runner for every kind (simp2): orphans finished first (a run whose journal outlived it, D41),
the spec checked (optilux/record.py, every refusal naming its fix), the display against the suite
and the identity built before anything launches (`--check` prints it and stops there, the live
world left to the run), the live world restored to its snapshot (D44), for a measured run the
displays held on throughout and the machine to itself (D42), then the announced launch, held
against the identity, the mod opened, the kind's body, the quit; whatever breaks, the game ends
one way (end_game, simp20) and the facts gathered so far go into the record. The journal
raw/<name>/partial.json follows the run.

- An acceptance run without a mode: the session start of docs/mod-protocol.md#choreography (A10
  is its selftest), then at the first view A4 (a copy of the reference zip with one program
  broken, selected for one reload that must answer iris-compile-error; the pack restored,
  reloaded, ready, one frame), A7 (SendInput's key and mouse motion with input.block off open a
  screen and turn the camera; blocked, they change nothing; unblocked again, the motion turns it),
  A9 (120 frames captured inside one PresentMon run, their stamps matched to its rows by order);
  per view A2 (a capture with F2 pressed inside it through SendInput; the new screenshot must
  equal one captured frame byte for byte; a miss is kept and retaken once) and A3 (`/tp` through
  `command` against camera.place with tpSemantics, both read back); F4's reload table; then
  `input.block off` and `quit`. A1's launch starts without the token and never connects: the pipe
  list holds no optilux- pipe, latest.log no applied mixin and no active line, the JVM's thread
  dump no optilux- thread; WM_CLOSE ends it.
- A measured run (measurement, calibration, or acceptance of A8 and A11 on a mode's schedule):
  optilux/measure.py's session; a measurement run's Optilux variants' zips built and passed by
  `check L0` before anything is written, as a visual run's (plans/m4.md D80); before the launch
  those zips written, the twins copied from the baseline's zip and the passthrough pack written,
  all deleted with the variants' files after the quit; every window
  cut from the run's one PresentMon CSV. A run that
  names its calibration is refused unless the calibration's identity equals its own key by key,
  and its record holds the verdicts (optilux/stats.py: each candidate's, the twin's check and the
  twin monitor over the calibration's judged twins) or A8's and A11's judged entries.
- A visual run (plans/m3.md D63): its Optilux variants' zips built and passed by `check L0`
  before anything is written, then written into shaderpacks/; the session start, one lap over the
  mode's views (mode coverage: the views file's coverage views, D64) and at each view per variant
  a reload and a pair of frames (measure.visual_body),
  every frame hashed; the displays held on but never refused off; never split.
- A session over capture.reloadCap (plans/m2.md D43, run-record.md#split-sessions) runs as one
  launch per group of its views, each a part <session>-p<n> recorded on its own with the session's
  spec and its `split`, each with the warm-up pass while suite.json keeps it (D47); `run` resumes
  it at its first part without an ok record (a re-run's name takes the next letter), ends it
  invalid when a part's identity differs from the first ok part's, and once its last part is ok
  writes the session record: the parts, their one identity, the verdicts and A8's and A11's
  entries.

The record goes to results/records/<name>.json, the request log and the raw artifacts to
results/raw/<name>/. Exit 0 when the status is ok.
"""

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from optilux import (
    REPO_ROOT,
    launch,
    measure,
    modclient,
    packzip,
    platform,
    presentmon,
    record,
    repo,
    stats,
    world,
)
from optilux.acceptance import (
    MOD_THREAD,
    a1,
    a2,
    a3,
    a4,
    a7,
    a9,
    broken_copies,
    helper_lines,
    reload_table,
    remove_broken,
    session_plan,
    thread_names,
)
from optilux.session import (
    CLOSED,
    PARTIAL,
    PIPES,
    PLACE_TIMEOUT,
    READY_TIMEOUT,
    REQUESTS,
    STABLE_FRAMES,
    Journal,
    RunError,
    RunHost,
    Session,
    SessionEnded,
    check_presentmon,
    load_spec,
    now,
    record_status,
    replace,
    session_start,
    settle_view,
    trim,
    view_pose,
)
from optilux.verbs import Verb
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, Say, shown

PREFIX = "optilux run"
# A measured record's steps and events go to raw/ (a full-mode session takes thousands of steps).
STEPS = "steps.json"
EVENTS = "events.json"
CAPTURES = "captures.json"
# `check L0` on an Optilux variant's zip (plans/m3.md M3.P04; its file under shaderpacks/:
# measure.zip_name): a child process reading the zip on its stdin, so
# the check's modules stay out of the measured closure (run-record.md#identity: harness).
L0_COMMAND = ("-m", "optilux.cli", "check", "L0", "-", "--json")
L0_TIMEOUT = 600
# `check L1` on a dump run's own record before it is written (plans/m3.md M3.P08): its closures
# become the record's `offline` field, the child kept out of the measured closure as L0's is.
L1_COMMAND = ("-m", "optilux.cli", "check", "L1", "-", "--json")
# A5's verdict over its waits' frames (plans/m3.md D68): `compare -` on the record so far, the
# frames decoded by optilux/visual.py in the child, out of the measured closure.
A5_COMMAND = ("-m", "optilux.cli", "compare", "-", "--json")
A5_TIMEOUT = 600
# A visual run aligns its captures on the Optilux pack's cycle (plans/m3.md D63), which pipeline
# spec v0 states (D57); Iris's frame counter wraps at 720720, which a cycle must divide.
PIPELINE = "config/pipeline.json"
FRAME_WRAP = 720720


@dataclass(frozen=True)
class Prepared:
    """A checked spec and its session's identity, built before anything launches or is written:
    the snapshot as (tree hash, file count, manifest), the system facts recorded beside the
    identity, the pinned PresentMon."""

    spec: record.Spec
    plat: platform.Platform
    suite: dict
    pack: platform.Pinned
    views: dict
    base: Path
    java_home: Path
    snapshot: tuple[str, int, str]
    presentmon: Path
    identity: dict
    recorded: dict
    optilux: dict | None = None  # an Optilux variant's zip, built in memory (optilux_zip)
    # A visual, dump or measurement run's Optilux zips, each built once (variant_zips).
    zips: tuple[dict, ...] = ()
    cycle: int = 1  # a visual run's align (pipeline_cycle)


def optilux_zip(root: Path, build: dict) -> dict:
    """An Optilux variant's zip (plans/m3.md D63), built in memory before anything is written, so
    `--check` refuses one that cannot build: `pack build`'s bytes from the working tree, or `pack
    build --ref`'s from the commit the spec's ref named when it was checked (never the ref again:
    it may have moved since). Its file name under shaderpacks/, bytes, entries and sha512."""
    commit = build["commit"]
    try:
        if commit is None:
            sources = packzip.tree_sources(root)
        else:
            sources = packzip.commit_sources(root, commit, build["variant"])
    except packzip.PackError as error:
        raise record.RecordError(f"{build['variant']}: {error}") from None
    data = packzip.zip_bytes(sources)
    name, digest = measure.zip_name(build), hashlib.sha512(data).hexdigest()
    return {"file": name, "data": data, "entries": len(sources), "sha512": digest}


def variant_zips(root: Path, spec: record.Spec) -> tuple[dict, ...]:
    """Each Optilux zip a visual, dump or measurement run's variants load (plans/m3.md D63,
    plans/m4.md D80), built once however many variants share it, each refused unless it passes
    `check L0` (check_l0), in the variants' order; each with its build."""
    found: dict[str, dict] = {}
    for variant in spec.variants:
        build = variant["build"]
        if build is None or measure.zip_name(build) in found:
            continue
        zipped = optilux_zip(root, build)
        zipped["l0"] = check_l0(root, zipped, build["variant"])
        found[zipped["file"]] = {**zipped, "build": build}
    return tuple(found.values())


def zip_pins(ready: Prepared) -> dict[str, str]:
    """The sha512 of each zip a variant may load, by its file under shaderpacks/: the reference
    pack's pin and each Optilux zip's as built (measure.variant_sha512)."""
    return {ready.pack.file: ready.pack.sha512, **{z["file"]: z["sha512"] for z in ready.zips}}


def zip_build(ready: Prepared, variant: measure.Variant) -> dict:
    """An Optilux variant's own build as its spec named it (two refs may name one commit, so one
    zip; a twin's, its baseline's) and its zip's `check L0` summary; nothing for another pack."""
    zipped = next((z for z in ready.zips if z["file"] == variant.source), None)
    if zipped is None:
        return {}
    named = ready.spec.variants[0]["id"] if variant.role == "twin" else variant.id
    build = next(v["build"] for v in ready.spec.variants if v["id"] == named)
    return {"build": build, "l0": zipped["l0"]}


def pipeline_cycle(root: Path) -> int:
    """The Optilux pack's cycle in frames, config/pipeline.json's (plans/m3.md D57): a visual
    run's captures align on it (D63). RecordError naming the fix."""
    try:
        cycle = json.loads((root / PIPELINE).read_text(encoding="utf-8"))["cycle"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise record.RecordError(f"{PIPELINE} gives no cycle ({error}); fix: restore it") from None
    if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle < 1 or FRAME_WRAP % cycle:
        raise record.RecordError(
            f"{PIPELINE}'s cycle {cycle!r} does not divide {FRAME_WRAP}, where Iris's frame "
            "counter wraps; fix: the pack's cycle in frames"
        )
    return cycle


def check_l0(root: Path, zipped: dict, variant: str) -> dict:
    """`check L0` on an Optilux variant's zip (plans/m3.md M3.P04): run in a child process, the
    bytes built on its stdin, so no check module enters the harness hash; its verdict held to the
    zip's sha512, a verdict on other bytes refused; RecordError naming the first problems when the
    zip fails it. Its summary, recorded with the variant."""
    try:
        done = subprocess.run(  # noqa: S603 this interpreter and the CLI, no shell
            [sys.executable, *L0_COMMAND],
            cwd=root,
            input=zipped["data"],
            capture_output=True,
            timeout=L0_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise record.RecordError(
            f"{variant}: `check L0` did not run ({error}); fix: `uv run optilux check L0`"
        ) from None
    try:
        found = json.loads(done.stdout.decode("utf-8"))
    except ValueError:
        found = None
    if not isinstance(found, dict):
        why = done.stderr.decode("utf-8", "replace").strip().splitlines() or ["no output"]
        raise record.RecordError(
            f"{variant}: `check L0` printed no verdict (exit {done.returncode}: {why[-1]}); fix: "
            "`uv run optilux check L0` shows why"
        )
    if "error" in found:
        raise record.RecordError(f"{variant}: `check L0` cannot check its zip: {found['error']}")
    if found.get("sha512") != zipped["sha512"]:
        raise record.RecordError(
            f"{variant}: `check L0` judged other bytes (sha512 {str(found.get('sha512'))[:12]}..., "
            f"built {zipped['sha512'][:12]}...); fix: rerun"
        )
    if found.get("ok") is not True:
        problems = found.get("problems") or ["no problem named"]
        more = f" and {len(problems) - 3} more" if len(problems) > 3 else ""
        raise record.RecordError(
            f"{variant}: its zip (sha512 {zipped['sha512'][:12]}...) fails `check L0`: "
            f"{'; '.join(problems[:3])}{more}; fix: the pack, until `optilux check L0` passes"
        )
    matrix = found["matrix"]
    return {
        "ok": True,
        "sha512": found["sha512"],
        "glslang": found["glslang"],
        "pipeline": found["pipeline"],
        "builds": matrix["builds"],
        "variants": matrix["variants"],
        "profiles": [p["profile"] for p in found["profiles"]],
    }


def prepare(
    root: Path,
    spec_in: Path | dict,
    machine: record.Machine,
    fresh: bool = True,
    match: bool = True,
) -> Prepared:
    """Everything `run` checks before the live world, and the identity (run-record.md#identity)
    built from what the session will use, nothing launched or written (`--check` stops here): the
    spec (a file, or its data from `calibrate`), the views and the snapshot's tree hash, the
    display and HAGS, PresentMon's pin, no copy left by an earlier A4, then the launch spec, the
    views file and the JDK's release file hashed, the jars launch places, the resource-pack set's
    packs (the static-textures pack by the store's copy), the options file as the launch would
    write it, the measured modules; a calibration the
    spec names matched key by key on that identity. A failed launch records this identity (id7,
    id9). `fresh` False: the spec's name may be taken (record.check_spec); `match` False: the
    calibration's identity is left unmatched (a split session's own check comes first)."""
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    java_profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    base = root / RUNTIME / plat.id
    game = base / launch.GAME
    pack = launch.reference_pack(plat)
    spec = checked(root, spec_in, fresh)
    views, views_path = record.load_views(root, spec.views)
    # It calls the view functions (A5 reaches its views as a measured pass does).
    walks = spec.mode is not None or spec.kind == record.DUMP or spec.a5 is not None
    stale = measure.stale_functions(root, views) if walks else []
    if stale:
        raise record.RecordError(
            f"{record.SNAPSHOTS}/{spec.views}/'s view functions differ from {record.VIEWS}/"
            f"{spec.views}.json for {', '.join(stale)}; fix: `optilux world prep {spec.views}`"
        )
    snapshot = record.tree(root / record.SNAPSHOTS / spec.views)
    packs = launch.set_packs(base, plat, spec.tier, suite, record.PACK_SET)
    files = [p["file"] for p in packs]
    options = launch.written_options(suite["display"], {}, files)
    system, system_recorded = record.system_facts(machine, options, suite["display"])
    pm_exe = check_presentmon(root)
    leftover = broken_copies(game)
    if leftover:
        raise record.RecordError(
            f"shaderpacks/ holds {', '.join(p.name for p in leftover)} from an earlier A4; fix: "
            "delete it (A4 writes its copy fresh)"
        )
    if platform.load_spec(root, plat.id) is None:
        raise record.RecordError(f"no launch spec for {plat.id}; fix: run `optilux install`")
    pre = launch.prelaunch(suite["display"], spec.tier, pack.file, {}, files)
    _, options_file = launch.planned_options(game, pre)
    java_home = root / JAVA_DIR / java_profile["runtime"]["build"]
    found = record.identity(
        plat=plat,
        tier=spec.tier,
        spec_path=platform.spec_path(root, plat.id),
        mods=list(launch.wanted_mods(base, plat, spec.tier).values()),
        world={
            "snapshot": f"{record.SNAPSHOTS}/{spec.views}",
            "treeSha256": snapshot[0],
            "files": snapshot[1],
        },
        views_path=views_path,
        packs=[{"file": p["file"], "sha512": p["sha512"]} for p in packs],
        settings=record.settings_identity(launch.settings_facts(pre, True), options_file),
        suite=suite,
        java=record.java_identity(java_home, java_profile),
        system=system,
        harness=record.harness_identity(root, pm_exe),
    )
    record.check_identity(found)
    if spec.cal is not None and match:  # measurement.md#calibration: matched key by key
        differ = record.identity_differences(found, spec.cal["identity"])
        if differ:
            raise record.RecordError(
                f"calibration {spec.cal['id'][:24]}... was measured under another identity: "
                f"{', '.join(differ)} differ; fix: `optilux calibrate --mode {spec.mode}` for "
                "this identity, then name its id"
            )
    recorded = {"platformFile": record.file_sha256(plat.path), **system_recorded}
    optilux = None
    if spec.optilux is not None:  # built, then refused unless it passes L0
        optilux = optilux_zip(root, spec.optilux)
        optilux["l0"] = check_l0(root, optilux, spec.optilux["variant"])
    zips: tuple[dict, ...] = ()
    cycle = 1
    if spec.kind == record.VISUAL:
        zips, cycle = variant_zips(root, spec), pipeline_cycle(root)
    elif spec.kind == record.DUMP or spec.mode is not None:  # a measured run's too (D80)
        zips = variant_zips(root, spec)
    elif spec.a5 is not None:  # aligned on the pack's cycle, as a visual run's captures
        cycle = pipeline_cycle(root)
        if spec.a5["first"] is not None and optilux is not None:
            a5_same(root, spec.a5["first"], found, optilux["sha512"])
    return Prepared(
        spec,
        plat,
        suite,
        pack,
        views,
        base,
        java_home,
        snapshot,
        pm_exe,
        found,
        recorded,
        optilux,
        zips,
        cycle,
    )


def a5_same(root: Path, first: str, identity: dict, sha512: str) -> None:
    """A5's second launch against its first (plans/m3.md D68): the identity equal key by key and
    the same zip, so one verdict judges the waits of both; RecordError naming what differs."""
    found = record.read_record(root, first)
    differ = record.identity_differences(identity, found.get("identity"))
    if differ:
        raise record.RecordError(
            f"{first} ran under another identity: {', '.join(differ)} differ; fix: both of A5's "
            "launches under one identity (run-record.md#comparison)"
        )
    theirs = [v.get("sha512") for v in found.get("variants") or [] if isinstance(v, dict)]
    if theirs != [sha512]:
        raise record.RecordError(
            f"{first} loaded another zip (sha512 {str(theirs)[:20]}...), this launch builds "
            f"{sha512[:12]}...; fix: A5's second launch on the first's pack"
        )


def checked(root: Path, spec_in: Path | dict, fresh: bool = True) -> record.Spec:
    """The spec (a file, or its data) checked against the platform and the suite alone
    (record.check_spec): its kind, variants, calibration and, over the cap, its groups."""
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    saves = root / RUNTIME / plat.id / launch.GAME / launch.SAVES
    data = load_spec(spec_in) if isinstance(spec_in, Path) else spec_in
    pack = launch.reference_pack(plat).file
    return record.check_spec(root, data, plat, suite, saves, pack, fresh)


@dataclass(frozen=True)
class Part:
    """One launch of a split session (run-record.md#split-sessions): the session, the part's
    number of all the parts, its run name (a re-run's with its letter), its group of views."""

    session: str
    n: int
    parts: int
    name: str
    views: tuple[str, ...]


def part_spec(ready: Prepared, part: Part) -> record.Spec:
    """The session's checked spec as one part runs it: the part's name, views and reloads, its
    `split`; the warm-up pass the session's (suite.json capture.warmupPass, D47)."""
    spec = ready.spec
    ci = record.candidates(spec.kind, spec.variants, ready.suite)
    split = {
        "session": part.session,
        "part": part.n,
        "parts": part.parts,
        "views": list(part.views),
    }
    return dataclasses.replace(
        spec,
        name=part.name,
        view_ids=part.views,
        planned=record.planned_reloads(len(part.views), ci, spec.rounds, spec.warmup),
        groups=(),
        split=split,
    )


def reread(root: Path, ready: Prepared) -> list[str]:
    """The identity keys built from config files alone (platform, launch spec, views, suite,
    Java), read again once launch has read them: a key that moved since prepare is one the
    session may not have run with."""
    spec = ready.spec
    java_profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    kept = ("mods", "world", "settings", "system", "harness")
    again = record.identity(
        plat=platform.load(root),
        tier=spec.tier,
        spec_path=platform.spec_path(root, ready.plat.id),
        views_path=root / record.VIEWS / f"{spec.views}.json",
        packs=ready.identity["resourcePacks"]["packs"],
        suite=json.loads((root / platform.SUITE).read_text(encoding="utf-8")),
        java=record.java_identity(ready.java_home, java_profile),
        **{key: ready.identity[key] for key in kept},
    )
    return [key for key in record.IDENTITY_KEYS if again[key] != ready.identity[key]]


class Runner:
    """One run's session and the facts its record needs, for every kind (simp2)."""

    def __init__(
        self,
        root: Path,
        ready: Prepared,
        host: RunHost,
        say: Say,
        announce: Say,
        restored: dict,
        marks: dict,
    ) -> None:
        self.root = root
        self.ready = ready
        self.spec = ready.spec
        self.host = host
        self.say = say
        self.announce = announce
        self.marks = marks
        self.raw = root / record.RAW / self.spec.name
        self.raw.mkdir(parents=True)
        (self.raw / "world-manifest.txt").write_text(
            ready.snapshot[2], encoding="utf-8", newline="\n"
        )
        self.started = now()
        head = repo.head(root)
        try:
            dirty: bool | str = bool(repo.changes(root))
        except repo.GitError as error:
            dirty = f"unread: {error}"
        restored["copied"], restored["deleted"] = len(restored["copied"]), len(restored["deleted"])
        self.facts: dict[str, Any] = {"restore": restored}
        self.problems: list[str] = []
        self.status = "ok"
        self.ident: dict | None = ready.identity  # a failed launch records it (id9)
        self.recorded: dict[str, Any] = {
            **ready.recorded,
            "harness": {"commit": head, "dirty": dirty},
        }
        self.items: dict[str, dict] = {}
        self.table: dict | None = None
        self.variants: list[dict] = []
        self.s: Session | None = None
        self.launched: launch.Launched | None = None
        self.m: measure.Measured | None = None
        if self.spec.kind in (record.VISUAL, record.DUMP):
            self.found = visual_variants(ready)
        else:
            self.found = measure.variants(self.spec, ready.suite) if self.spec.mode else []
        self.created: list[Path] = []  # the files under shaderpacks/ this run wrote
        # An acceptance session's pack: the reference pack, or its Optilux variant's zip once
        # written (write_optilux), which iris.properties names from the start-of-run reload on.
        self.pack_file, self.pack_sha512 = ready.pack.file, ready.pack.sha512
        self.iris_pack: str | None = None
        self.journal = Journal(
            self.raw,
            {
                "schema": record.SCHEMA,
                "name": self.spec.name,
                "spec": self.spec.data,
                "startedAt": self.started,
                "identity": ready.identity,
                "recorded": self.recorded,
                "runner": host.process_facts(os.getpid()),
                **({"split": self.spec.split} if self.spec.split else {}),
            },
        )

    def mark(self, phase: str) -> None:
        self.marks[phase] = time.monotonic()

    def own(self, path: Path) -> None:
        """A file the run is about to write under shaderpacks/ (a twin, a settings file):
        journaled before it exists (D41), deleted once the game has exited."""
        if path not in self.created:
            self.created.append(path)
            self.journal.set("files", [shown(p, self.root) for p in self.created])

    def end_game(self, client: modclient.Client | None) -> str:
        """The one way a game that failed a check or a step is ended (simp20): the client closed,
        then WM_CLOSE, then a kill (launch.end); how it ended."""
        if client is not None:
            client.close()
        if self.launched is None:
            return "no game was started"
        return launch.end(self.launched.process, self.host)

    def session(self, plan: str, body: Callable[[Session], None]) -> None:
        """The announced launch, held against the identity, the mod opened, `body`, the quit;
        the game ended on any error, which is raised again as RunError (SessionEnded kept), and
        the session's facts kept whatever happened."""
        spec, ready, host, say = self.spec, self.ready, self.host, self.say
        self.mark("launch")
        self.announce(
            f"launch (announced): the session, tier {spec.tier}, world {spec.world}, {plan}; "
            "hands off the mouse and keyboard until the quit"
        )
        launched = launch.launch(self.root, spec.world, spec.tier, True, {}, say, host)
        self.launched = launched
        self.facts["launch"] = trim(launched.facts)
        self.recorded["amd"] = launched.facts["gate"]["amd"]
        self.recorded["java"] = launched.facts["gate"]["java"]  # JVMs beside the game
        try:  # F10: the startup call is recorded, never blocked
            self.recorded["connectionsAtJoin"] = host.connections(launched.pid)
        except (OSError, ValueError) as error:
            self.recorded["connectionsAtJoin"] = f"unread: {error}"
        except Exception as error:  # noqa: BLE001 psutil's errors: a record, never a stop
            self.recorded["connectionsAtJoin"] = f"unread: {type(error).__name__}: {error}"
        self.mark("mod")
        try:
            self.journal.set("game", host.process_facts(launched.pid) or {"pid": launched.pid})
            differ = record.launch_differences(ready.identity, launched.facts)
            differ += reread(self.root, ready)
            if differ:  # the identity is not this session's: none is recorded
                self.ident = None
                self.journal.set("identity", None)
                raise RunError(
                    f"the launch's {', '.join(differ)} differ from the identity built before it; "
                    "fix: rerun with nothing changing config/ or runtime/ beside the run"
                )
            client, mod = launch.open_mod(launched, self.root, host, say, self.raw / REQUESTS)
        except BaseException as error:
            how = self.end_game(None)
            self.after_game()
            self.evidence(launched)
            if not isinstance(error, Exception):  # a stop or an exit: raised as it is
                raise
            raise RunError(f"{error}; the game was ended ({how})") from None
        self.facts["mod"] = mod
        s = Session(self.root, self.raw, launched, client, host, say)
        self.s = s
        try:
            running, java = mod["hello"]["versions"]["java"], ready.identity["java"]
            if running != java["version"]:
                self.ident = None
                self.journal.set("identity", None)
                raise RunError(
                    f"the game runs Java {running}, {java['runtime']}'s release file says "
                    f"{java['version']}; fix: run `optilux install`"
                )
            body(s)
            s.label = "quit"
            self.mark("quit")
            self.facts["quit"] = launch.quit_mod(client, launched.process, host)
            say(
                f"quit: exit code {self.facts['quit']['exitCode']} in "
                f"{self.facts['quit']['seconds']:.1f} s"
            )
        except BaseException as error:
            how = self.end_game(client)
            if not isinstance(error, Exception):  # a stop or an exit: raised as it is
                raise
            kind = SessionEnded if isinstance(error, SessionEnded) else RunError
            raise kind(f"the session: {error}; the game was ended ({how})") from None
        finally:
            s.drain()
            self.facts["steps"] = s.steps
            self.facts["events"] = s.events
            self.facts["stray"] = list(client.stray)
            self.after_game()
            # Every session's request log, a failed one's too (m1-acceptance-1 and -2 had none).
            try:
                self.facts["logCheck"] = launch.check_log(self.raw / REQUESTS, launched.mod_token())
            except (launch.LaunchError, OSError) as error:
                self.facts["logCheck"] = {"tokenAbsent": False, "problem": str(error)}
            self.evidence(launched)

    def evidence(self, launched: launch.Launched) -> None:
        """What a session leaves after the game's exit, a broken one's too, each read on its own
        (never raised over the session's error): the option files read back (iris.properties as
        the last capture wrote it, naming its variant's pack), latest.log copied to raw/ and its
        helper lines counted (a hook failure there makes the record invalid)."""
        pre = launched.prelaunch
        last, debug = self.iris_pack, False
        if self.m is not None and self.m.last_written is not None:
            last, debug = self.m.last_written.pack, self.m.last_debug
        if last is not None:
            display = self.ready.suite["display"]
            iris = launch.iris_properties(display, self.spec.tier, last, debug)
            pre = dataclasses.replace(pre, iris=iris)
        try:
            self.facts["readBack"] = launch.read_back(launched.game, pre)
        except (OSError, ValueError) as error:
            self.facts["readBack"] = {"ok": False, "problem": str(error)}
        # As the game read it; its unwritten keys are the identity's settings (D37).
        self.recorded["optionsTxt"] = {"sha256": launched.facts["optionsFile"]["sha256"]}
        try:
            shutil.copyfile(launched.log, self.raw / "session-latest.log")
            text = launched.log.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            self.facts["helperLog"] = {"problem": str(error)}
            return
        mods_log = helper_lines(text)
        self.facts["helperLog"] = {
            "applied": len(mods_log["applied"]),
            "active": len(mods_log["active"]),
            "hookFailures": len(mods_log["hookFailures"]),
            "irisOutsideReload": len(mods_log["irisOutsideReload"]),
        }

    def after_game(self) -> None:
        """What the game held and its exit frees: A4's copy; a measured run's twins and settings
        files, those it wrote and no other (launch refuses a saved settings file)."""
        if "A4" in self.spec.items and self.launched is not None:
            self.facts["a4Cleanup"] = remove_broken(self.launched.game)
        if self.created:
            self.facts["filesCleanup"] = measure.remove_files(self.created)


# The acceptance body (M1's items).


def acceptance_body(run: Runner, s: Session) -> None:
    spec, ready, suite, views = run.spec, run.ready, run.ready.suite, run.ready.views
    client, launched, host, raw = s.client, s.launched, run.host, run.raw
    system = ready.identity["system"]
    jcmd = ready.java_home / "bin" / "jcmd.exe"
    items, facts = run.items, run.facts
    if "A1" in spec.items:
        # A1's positive controls: the detectors A1 relies on, seeing the mod active here.
        expected = modclient.pipe_name(launched.mod_token()).removeprefix(PIPES)
        try:
            facts["pipeListed"] = expected in host.pipes()
        except OSError as error:
            facts["pipeListed"] = f"unread: {error}"
        try:
            dump = host.thread_dump(jcmd, launched.pid)
            (raw / "session-threads.txt").write_text(dump, encoding="utf-8", newline="\n")
            facts["threads"] = [name for name in thread_names(dump) if name.startswith(MOD_THREAD)]
        except (OSError, RunError, subprocess.SubprocessError) as error:
            facts["threads"] = f"unread: {error}"
    start: dict = {}
    try:
        session_start(
            s,
            run.pack_file,
            suite["capture"]["gpuWarmupS"],
            system["resolution"],
            suite["display"]["resolution"],
            start,
            before_reload=(lambda: optilux_files(run, s)) if spec.optilux else None,
        )
    finally:
        if "selftest" in start:  # A10 holds at every start; a failed one ends the session (c5)
            items["A10"] = {
                "pass": start["selftest"]["pass"] is True,
                "selftest": start["selftest"],
                "after": {"worldWait": start["joined"]},
            }
    run.variants.append(
        {
            "pack": run.pack_file,
            "sha512": run.pack_sha512,
            **({"build": spec.optilux} if spec.optilux else {}),
            "profile": None,
            "options": {
                "count": len(start["options"]["values"]),
                "values": start["options"]["values"],
            },
        }
    )
    facts["reload"] = start["reload"]
    previous = start["joined"]["pose"]["dimension"]
    weather = None
    a2_views: list[dict] = []
    a3_views: list[dict] = []
    settled: list[dict] = []
    facts["views"] = settled
    pm_exe = ready.presentmon if "A9" in spec.items else None
    # Each item's evidence lands in the record as it is taken, so a later failure keeps it.
    first = views["views"][0]
    singles = [item for item in ("A4", "A7", "A9") if item in spec.items]
    if singles or spec.reloads:
        done = settle_view(s, first, weather, suite, previous)
        settled.append({"view": first["id"], **done})
        previous, weather = first["dim"], first["weather"]
        if "A4" in spec.items:
            items["A4"] = {"pass": False, "view": first["id"]}
            a4(s, items["A4"])
        if "A7" in spec.items:
            items["A7"] = {"pass": False, "view": first["id"]}
            a7(s, first, items["A7"])
        if pm_exe is not None:  # A9 asked: PresentMon's pin checked before the launch
            s.step(
                f"{first['id']}: A9 ready",
                lambda: client.ready(STABLE_FRAMES, done["settleSeconds"], READY_TIMEOUT),
                lambda a: f"{a['seconds']:.2f} s, limitedBy {a['limitedBy']}",
            )
            items["A9"] = {"pass": False, "view": first["id"]}
            a9(s, pm_exe, f"{presentmon.SESSION_PREFIX}{spec.name}", items["A9"])
    if "A2" in spec.items:
        items["A2"] = {"pass": False, "complete": False, "views": a2_views}
    if "A3" in spec.items:
        items["A3"] = {"pass": False, "complete": False, "views": a3_views}
    for view in views["views"] if "A2" in spec.items or "A3" in spec.items else []:
        done = settle_view(s, view, weather, suite, previous)
        settled.append({"view": view["id"], **done})
        previous, weather = view["dim"], view["weather"]
        if "A2" in spec.items:
            a2_views.append(a2(s, view, system["resolution"], done["settleSeconds"]))
        if "A3" in spec.items:
            a3_views.append(a3(s, view))
    for item, done_views in (("A2", a2_views), ("A3", a3_views)):
        if item in spec.items:
            items[item]["pass"] = all(v["pass"] for v in done_views)
            items[item]["complete"] = True
    if spec.a5 is not None:
        a5_session(run, s, previous)
    if spec.reloads:
        run.table = reload_table(s, jcmd, run.pack_file, spec.reloads)
    home = view_pose(views["views"][0])
    s.step("camera.place home", lambda: client.camera_place(home, PLACE_TIMEOUT))
    s.step("input.block off", lambda: client.input_block(False))


def a5_session(run: Runner, s: Session, previous: str) -> None:
    """A5's waits in this launch (measure.a5_body, plans/m3.md D68) over the views file's perf
    views, from the dimension the session stands in, the weather not yet ramped; its evidence in
    the record as each wait is taken. Judged after the session (judge_a5)."""
    ready, plan = run.ready, run.spec.a5
    if plan is None:
        return
    evidence: dict[str, Any] = {
        "pass": False,
        "complete": False,
        "first": plan["first"],
        "from": plan["from"],
        "count": plan["count"],
        "of": plan["of"],
        "waits": [],
    }
    run.items[record.A5] = evidence
    run.m = measure.Measured(
        s=s,
        spec=run.spec,
        suite=ready.suite,
        views=list(ready.views["views"]),
        found=[],
        journal=run.journal,
        pm_exe=ready.presentmon,
        jcmd=ready.java_home / "bin" / "jcmd.exe",
        display_mode=ready.identity["system"]["resolution"],
        own=run.own,
        luid=ready.recorded["hags"]["adapterLuid"],
        marks=run.marks,
        previous=previous,
        cycle=ready.cycle,
    )
    measure.a5_body(run.m, run.pack_file, plan["waits"], evidence)
    evidence["complete"] = True


def a5_hold(run: Runner) -> None:
    """A5's entry waits (pass null) until the record's status is known: judge_a5 decides it."""
    entry = run.items.get(record.A5)
    if entry is not None:
        entry["pass"] = None
        entry["pending"] = "judged once the session's status is known"


def judge_a5(run: Runner, acceptance: list[dict], status: str) -> str:
    """A5's verdict once the record's status is known (plans/m3.md D68), as a measured run's items
    are judged after its status: only an ok session whose last wait ends the sequence is judged,
    the waits of this launch and of the first it names (`remeasures`) by their frames' decoded
    pixels in a child process, `compare -` reading the record so far on its stdin (optilux/visual.py
    stays out of the run's imports: run-record.md#identity, harness). Any other session leaves the
    entry waiting with why, never passed; a launch the next continues waits on it. The status
    after the verdict: failed on a miss or when no verdict came."""
    entry = next((e for e in acceptance if e["item"] == record.A5), None)
    plan = run.spec.a5
    if entry is None or plan is None or entry["pass"] is not None:  # not run: failed as such
        return status
    evidence = entry["evidence"]
    if status != "ok" or not evidence.get("complete"):
        evidence["pending"] = f"the session ended {status}, so its waits are not judged"
        return status
    last = plan["from"] + plan["count"] - 1
    if last < plan["of"]:
        evidence["pending"] = (
            f"judged in the next launch's record, which names this one (`remeasures`): waits "
            f"{plan['from']}-{last} of {plan['of']} here (plans/m3.md D68)"
        )
        return status
    held = {
        "schema": record.SCHEMA,
        "name": run.spec.name,
        "kind": run.spec.kind,
        "spec": run.spec.data,
        "status": status,
        "identity": run.ident,
        "variants": run.variants,
        "acceptance": [entry],
    }
    why, judged = None, {}
    try:
        done = subprocess.run(  # noqa: S603 this interpreter and the CLI, no shell
            [sys.executable, *A5_COMMAND],
            cwd=run.root,
            input=json.dumps(held, default=str).encode("utf-8"),
            capture_output=True,
            timeout=A5_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        why = f"`compare -` did not run ({error})"
    else:
        try:
            result = json.loads(done.stdout.decode("utf-8"))
        except ValueError:
            result = None
        judged = (result.get("a5") or {}) if isinstance(result, dict) else {}
        if not isinstance(result, dict) or result.get("ok") is not True or "pass" not in judged:
            lines = done.stderr.decode("utf-8", "replace").strip().splitlines() or ["no output"]
            problem = result.get("problem") if isinstance(result, dict) else None
            why = problem or f"`compare -` exited {done.returncode}: {lines[-1]}"
    if why is not None:
        evidence["pending"] = f"unjudged: {why}"
        run.problems.append(f"A5 unjudged: {why}")
        return "failed"
    evidence.pop("pending", None)
    entry["pass"] = judged["pass"]
    evidence["why"] = judged["why"]
    evidence["judged"] = judged["judged"]
    if judged["pass"] is not True:
        run.problems.append("items failed: A5")
        return "failed"
    return status


def write_zip(run: Runner, zipped: dict, build: dict) -> dict:
    """An Optilux variant's zip under shaderpacks/ before the launch (plans/m3.md D63), the bytes
    prepare built (optilux_zip): journaled before it exists, its part file too (D41), written
    through that part name and its sha512 checked against the bytes built. A file of its name
    already there, or its settings file, is refused: the run deletes only what it wrote."""
    name = zipped["file"]
    packs = run.ready.base / launch.GAME / launch.SHADER_PACKS
    target = packs / name
    part = target.with_name(target.name + ".part")
    for path in (target, part, packs / measure.SETTINGS.format(pack=name)):
        if path.exists():
            raise RunError(f"{path.name} exists in shaderpacks/; fix: delete it, then rerun")
    run.own(target)
    run.own(part)
    part.write_bytes(zipped["data"])
    part.replace(target)
    digest = platform.sha512(target)
    if digest != zipped["sha512"]:
        raise RunError(f"{name} hashes {digest[:12]}..., built {zipped['sha512'][:12]}...")
    run.say(
        f"{build['variant']}: wrote shaderpacks/{name} ({zipped['entries']} entries, sha512 "
        f"{digest[:12]}..., check L0 passed)"
    )
    return {
        "file": name,
        "sha512": digest,
        "entries": zipped["entries"],
        **build,
        "l0": zipped["l0"],
    }


def write_optilux(run: Runner) -> dict:
    """An acceptance run's Optilux variant written (write_zip), the pack its session loads."""
    build, zipped = run.spec.optilux, run.ready.optilux
    if build is None or zipped is None:
        raise RunError("the spec names no Optilux variant")
    found = write_zip(run, zipped, build)
    run.pack_file, run.pack_sha512 = found["file"], found["sha512"]
    return found


def optilux_files(run: Runner, s: Session) -> None:
    """Before the start-of-run reload: iris.properties naming the Optilux variant's zip and its
    settings file written empty, so the reload loads it at its defaults (measure.variant_files;
    Iris re-reads both at a reload, spike R4); the settings file journaled first, as the zip."""
    name = run.pack_file
    variant = measure.Variant(measure.OPTILUX_ZIP, "baseline", name, name, None, {}, False)
    display = run.ready.suite["display"]
    for path, data in measure.variant_files(
        s.launched.game, display, run.spec.tier, variant
    ).items():
        if path.parent.name == launch.SHADER_PACKS:
            run.own(path)
        path.write_bytes(data)
    run.iris_pack = name


def acceptance_after(run: Runner) -> None:
    """A1's launch after the session, the world restored first (D44)."""
    spec, facts, root, host = run.spec, run.facts, run.root, run.host
    if "A1" not in spec.items:
        return
    control = {
        "sessionPipeListed": facts["pipeListed"],
        "sessionMixinsApplied": facts["helperLog"].get("applied", 0),
        "sessionThreads": facts["threads"],
    }
    again = world.restore(root, spec.views, spec.world, host, run.say)
    facts["restoreA1"] = {**again, "copied": len(again["copied"]), "deleted": len(again["deleted"])}
    jcmd = run.ready.java_home / "bin" / "jcmd.exe"
    run.items["A1"] = a1(
        root, run.raw, spec.world, spec.tier, host, run.say, run.announce, jcmd, control
    )


# The measured body (optilux/measure.py).


def measured_plan(run: Runner) -> str:
    spec = run.spec
    ids = ", ".join(v.id for v in run.found)
    split = spec.split
    return (
        (f"part {split['part']} of {split['parts']} of {split['session']}: " if split else "")
        + f"a {spec.mode}-mode {spec.kind} run of {ids}"
        + (" alone in every slot" if spec.alone else "")
        + f" on {len(spec.view_ids)} views, {spec.rounds} round(s), {spec.planned} reloads"
        + (", no windows" if not spec.windows else "")
        + ("" if spec.warmup else ", no warm-up pass")
        + ", PresentMon recording throughout"
        + (", the heap read every 10 reloads and the GPU memory after each" if spec.heap else "")
    )


def measured_before(run: Runner) -> None:
    """Before the launch, the run's files journaled first (D41): each Optilux zip written
    (write_zip, plans/m4.md D80), then the twins' zips copied from the baseline's zip on disk and
    held to its sha512, the passthrough pack written."""
    ready = run.ready
    game = ready.base / launch.GAME
    pins = zip_pins(ready)
    run.journal.set(
        "variants",
        [
            {
                "id": v.id,
                "role": v.role,
                "pack": v.pack,
                "sha512": measure.variant_sha512(v, pins),
                **zip_build(ready, v),
                "profile": v.profile,
                "options": v.options,
                "timers": v.timers,
            }
            for v in run.found
        ],
    )
    run.journal.set("validity", ready.suite["validity"])  # an orphan's flags use its own suite
    if ready.zips:
        run.facts["zips"] = [write_zip(run, zipped, zipped["build"]) for zipped in ready.zips]
    base = run.found[0]
    source = game / launch.SHADER_PACKS / base.pack
    digest = measure.variant_sha512(base, pins)
    run.facts["twins"] = measure.make_twins(game, run.found, source, digest, run.own)
    passthrough = measure.make_passthrough(game, run.found, run.own)
    if passthrough is not None:
        run.facts["passthrough"] = passthrough


def measured_body(run: Runner, s: Session) -> None:
    ready, spec = run.ready, run.spec
    by_id = {v["id"]: v for v in ready.views["views"]}
    run.m = measure.Measured(
        s=s,
        spec=spec,
        suite=ready.suite,
        views=[by_id[vid] for vid in spec.view_ids],
        found=run.found,
        journal=run.journal,
        pm_exe=ready.presentmon,
        jcmd=ready.java_home / "bin" / "jcmd.exe",
        display_mode=ready.identity["system"]["resolution"],
        own=run.own,
        luid=ready.recorded["hags"]["adapterLuid"],
        marks=run.marks,
    )
    measure.body(run.m)


def measured_fields(run: Runner) -> dict:
    """A measured record's own fields (run-record.md#fields): mode and calibration, the variants
    with their effective options, every capture with its summaries and flags, the heap table;
    the steps, events and full captures to raw/."""
    spec, m = run.spec, run.m
    pid = run.launched.pid if run.launched is not None else -1
    captures: list[dict] = []
    if m is not None:
        captures, problems = measure.summarize(m, pid)
        run.problems += problems
    per_view = len(measure.schedule(run.found, spec.rounds, spec.alone))
    planned = len(spec.view_ids) * ((1 if spec.warmup else 0) + per_view)
    run.problems += measure.measured_problems(
        captures, planned, run.status == "ok" and not run.problems
    )
    ready = run.ready
    found: dict[str, Any] = {
        "mode": spec.mode,
        "calibration": spec.calibration,
        "variants": (
            measure.variant_records(m, zip_pins(ready), lambda v: zip_build(ready, v)) if m else []
        ),
        "captures": [{k: v for k, v in c.items() if k != "problems"} for c in captures],
    }
    if spec.heap:
        found["heapTable"] = measure.heap_table(m.heap if m else [], run.host.physical_memory())
    full = {"captures": captures, "entries": m.entries if m else []}
    (run.raw / CAPTURES).write_text(json.dumps(full, indent=1, default=str) + "\n", "utf-8")
    return found


def judge_session(run: Runner, found: dict, status: str) -> None:
    """An ok session's judgment (run-record.md#record): a judged measurement run's verdicts, or
    A8's and A11's entries; an item of a session that did not end ok, or of a part, waits. A
    verdict's error or a failed item is a problem of the run's."""
    spec = run.spec
    captures, expected = found.get("captures") or [], found.get("variants") or None
    if spec.kind == "acceptance":
        if status == "ok":
            found["acceptance"] = item_entries(spec, captures, expected)
        else:
            why = f"the session ended {status}"
            found["acceptance"] = [
                {"item": i, "pass": None, "evidence": {"pending": why}} for i in spec.items
            ]
        failed = [e["item"] for e in found["acceptance"] if e["pass"] is False]
        if failed:  # an item waiting (pass null) has not failed, and never passes
            run.problems.append(f"items failed: {', '.join(failed)}")
    elif status == "ok" and spec.split is None and spec.cal is not None:
        try:
            found["verdicts"] = verdicts(run.root, captures, spec.cal, spec.cal["mode"], expected)
        except stats.StatsError as error:
            run.problems.append(f"the verdicts: {error}")


def verdicts(
    root: Path, captures: list[dict], cal: dict, mode: str, expected: list[dict] | None
) -> dict:
    """A judged run's verdicts (stats.judge, the record's variants `expected`) and the twin
    monitor over the twins judged under its calibration before it, then its own, by the
    calibration's window (measurement.md#calibration)."""
    found = stats.judge(captures, cal, mode, expected)
    history = record.judged_twins(root, cal["id"])
    if found["twin"]["inside"] is not None:
        history.append(not found["twin"]["inside"])
    window = cal["twinMonitor"]
    found["twinMonitor"] = stats.twin_monitor(history, window["window"], window["maxExceed"])
    return found


def timed_variant(spec: record.Spec) -> str | None:
    """A8's candidate: the first equal to the baseline but with timers on (record's check)."""
    base = spec.variants[0]
    same = (base["profile"], base["options"])
    return next(
        (
            v["id"]
            for v in spec.variants[1:]
            if v["timers"] and (v["profile"], v["options"]) == same
        ),
        None,
    )


def item_entries(
    spec: record.Spec, captures: list[dict], expected: list[dict] | None = None
) -> list[dict]:
    """A8's and A11's entries judged by the spec's calibration (stats.judge_items, the record's
    variants `expected`); a part's wait on its session record, and a session whose captures
    cannot be judged leaves them waiting, never passed."""
    if spec.split is not None or spec.cal is None:
        why = (
            f"judged in session {spec.split['session']}'s record"
            if spec.split
            else "no calibration"
        )
        return [{"item": i, "pass": None, "evidence": {"pending": why}} for i in spec.items]
    try:
        timed = timed_variant(spec)
        return stats.judge_items(captures, spec.cal, spec.items, timed, spec.first, expected)
    except stats.StatsError as error:
        why = f"unjudged: {error}"
        return [{"item": i, "pass": None, "evidence": {"pending": why}} for i in spec.items]


def measured_status(run: Runner) -> str:
    """A measured record's status (run-record.md#record): aborted kept; invalid when the session
    ended at focus.lost or screen.opened (D42), on a hook error or a hook failure or an Iris
    failure outside a reload in latest.log; failed on any other problem."""
    facts, status = run.facts, run.status
    events = facts.get("events", [])
    # The quit's own screens (the game's saving screens) come after the last capture.
    ending = [e for e in events if e.get("step") != "quit" and measure.ends(e)]
    hooks = [e for e in events if e["event"] == "hook.error"]
    logged = facts.get("helperLog", {})
    if ending:
        run.problems.append(f"{ending[0]['event']} at frame {ending[0]['frameIndex']} (D42)")
    if hooks:
        run.problems.append("hook.error in the session")
    if logged.get("hookFailures"):
        run.problems.append(f"the mod logged {logged['hookFailures']} hook failure(s)")
    if logged.get("irisOutsideReload"):
        run.problems.append("Iris failed to load a pack outside shaders.reload")
    if status == "ok" and (
        ending or hooks or logged.get("hookFailures") or logged.get("irisOutsideReload")
    ):
        status = "invalid"
    check = facts.get("logCheck")
    if check is not None and check.get("tokenAbsent") is not True:
        run.problems.append(f"the request log holds the token: {check.get('problem', '')}")
    elif check is None and "mod" in facts:
        run.problems.append("the request log was not checked for the token")
    stray = [x for x in facts.get("stray", []) if x.get("ok") is False]
    if stray:
        run.problems.append(f"the mod sent {len(stray)} answer(s) to no request of ours")
    quit_facts = facts.get("quit")
    if quit_facts is not None and quit_facts["exitCode"] != 0:
        run.problems.append(f"the session's quit exited {quit_facts['exitCode']}")
    if quit_facts is not None and quit_facts.get("pipeEnded") is False:
        run.problems.append(launch.UNREAD_END)
    if "readBack" in facts and not facts["readBack"]["ok"]:
        run.problems.append("the option files did not read back as written")
    if facts.get("filesCleanup", {}).get("kept"):
        run.problems.append(f"the run's files were not deleted: {facts['filesCleanup']['kept']}")
    if run.problems and status == "ok":
        status = "failed"
    return status


def measured_session_facts(run: Runner) -> None:
    """A measured session's facts for its record: the steps and events moved to raw/, counted."""
    facts, raw = run.facts, run.raw
    steps, events = facts.pop("steps", []), facts.pop("events", [])
    (raw / STEPS).write_text(json.dumps(steps, indent=1, default=str) + "\n", "utf-8")
    (raw / EVENTS).write_text(json.dumps(events, indent=1, default=str) + "\n", "utf-8")
    facts["steps"] = {"count": len(steps), "file": shown(raw / STEPS, run.root)}
    facts["events"] = {
        "counts": dict(Counter(e["event"] for e in events)),
        "file": shown(raw / EVENTS, run.root),
    }
    if run.m is not None:
        facts.update(run.m.facts)
    if isinstance(facts.get("start"), dict):  # its options are the baseline's, in variants
        facts["start"] = {k: v for k, v in facts["start"].items() if k != "options"}


# The visual body (plans/m3.md D63; optilux/measure.py's visual_body).


def visual_variants(ready: Prepared) -> list[measure.Variant]:
    """A visual run's variants as its session loads them: the first the baseline, which the others
    are tiered against (optilux/visual.py), each by the file Iris loads from shaderpacks/ (an
    Optilux variant's zip, or the reference pack) with its profile's options and the spec's."""
    found = []
    for n, variant in enumerate(ready.spec.variants):
        build = variant["build"]
        pack = ready.pack.file if build is None else measure.zip_name(build)
        role = "baseline" if n == 0 else "candidate"
        options = dict(variant["options"])
        found.append(
            measure.Variant(variant["id"], role, pack, pack, variant["profile"], options, False)
        )
    return found


def visual_plan(run: Runner) -> str:
    spec = run.spec
    ids = ", ".join(f"{v.id} ({v.pack})" for v in run.found)
    return (
        f"a {spec.mode}-mode visual run of {ids} on {len(spec.view_ids)} views, {spec.planned} "
        f"reloads, at each view and variant a pair of frames {measure.PAIR_MS / 1000:g} s apart"
    )


def visual_before(run: Runner) -> None:
    """The variants journaled, then each Optilux zip written into shaderpacks/ (write_zip) before
    the launch, the run's files journaled first (D41)."""
    ready = run.ready
    run.journal.set(
        "variants",
        [
            {
                "id": v.id,
                "role": v.role,
                "pack": v.pack,
                "sha512": measure.variant_sha512(v, zip_pins(ready)),
                **zip_build(ready, v),
                "profile": v.profile,
                "options": v.options,
                "timers": False,
            }
            for v in run.found
        ],
    )
    run.facts["zips"] = [write_zip(run, zipped, zipped["build"]) for zipped in ready.zips]


def visual_session(run: Runner, s: Session) -> None:
    run.m = view_session(run, s)
    measure.visual_body(run.m)


def dump_session(run: Runner, s: Session) -> None:
    run.m = view_session(run, s)
    measure.dump_body(run.m)


def view_session(run: Runner, s: Session) -> measure.Measured:
    """A visual or dump session's state over the spec's views (a coverage run's too, D64)."""
    ready, spec = run.ready, run.spec
    by_id = {v["id"]: v for v in record.every_view(ready.views)}
    return measure.Measured(
        s=s,
        spec=spec,
        suite=ready.suite,
        views=[by_id[vid] for vid in spec.view_ids],
        found=run.found,
        journal=run.journal,
        pm_exe=ready.presentmon,
        jcmd=ready.java_home / "bin" / "jcmd.exe",
        display_mode=ready.identity["system"]["resolution"],
        own=run.own,
        luid=ready.recorded["hags"]["adapterLuid"],
        marks=run.marks,
        cycle=ready.cycle,
    )


def visual_fields(run: Runner) -> dict:
    """A visual record's own fields (run-record.md#record): the mode; the variants, each zip's
    sha512 (an Optilux variant's build and `check L0` summary beside it) and its effective options
    in full; every pair (the events that flagged one stay in raw/captures.json); a pair planned
    but not taken, or one missing a frame, a problem of the run's."""
    spec, m = run.spec, run.m
    entries = m.entries if m is not None else []
    planned = len(spec.view_ids) * len(run.found)
    run.problems += measure.visual_problems(
        entries, planned, run.status == "ok" and not run.problems
    )
    (run.raw / CAPTURES).write_text(json.dumps({"captures": entries}, indent=1) + "\n", "utf-8")
    captures = [{k: v for k, v in e.items() if k != "problems"} for e in entries]
    return {"mode": spec.mode, "variants": loaded_variants(run), "captures": captures}


def loaded_variants(run: Runner) -> list[dict]:
    """A visual or dump record's variants: each zip's sha512 (an Optilux variant's build and `check
    L0` summary beside it) and its effective options in full."""
    m, ready = run.m, run.ready
    variants = []
    for v in run.found:
        mine = m.effective.get(v.id) if m is not None else None
        variants.append(
            {
                "id": v.id,
                "role": v.role,
                "pack": v.pack,
                "sha512": measure.variant_sha512(v, zip_pins(ready)),
                **zip_build(ready, v),
                "profile": v.profile,
                "options": v.options,
                "effective": None
                if mine is None
                else {
                    "sha256": mine["sha256"],
                    "count": len(mine["values"]),
                    "values": mine["values"],
                },
            }
        )
    return variants


# The dump body (plans/m3.md D60; optilux/measure.py's dump_body).

# Each Optilux zip a dump run loads, kept beside its dumps: L1 reads the variants' sources there.
PACKS = "packs"


def dump_plan(run: Runner) -> str:
    spec = run.spec
    ids = ", ".join(f"{v.id} ({v.pack})" for v in run.found)
    return (
        f"a dump run of {ids} at {', '.join(spec.view_ids)}, one view per dimension, "
        f"{spec.planned} reloads, each variant's with Iris's debug flag on and its print copied"
    )


def dump_before(run: Runner) -> None:
    """As visual_before, then each Optilux zip's bytes kept under raw/<run>/packs/, L1's sources."""
    visual_before(run)
    packs = run.raw / PACKS
    packs.mkdir()
    for zipped in run.ready.zips:
        (packs / zipped["file"]).write_bytes(zipped["data"])


def dump_fields(run: Runner) -> dict:
    """A dump record's own fields (run-record.md#record): the variants as a visual record's; each
    dump with its files' count, bytes and manifest; `dumps`, every manifest's files by name with the
    sha256 dump equality compares (an ID map's own sha256 in its dump's `dated`), once however many
    dumps share it; a dump planned but not taken, or one without its print, a run's problem."""
    spec, m = run.spec, run.m
    entries = m.entries if m is not None else []
    planned = len(spec.view_ids) * len(run.found)
    run.problems += measure.dump_problems(entries, planned, run.status == "ok" and not run.problems)
    (run.raw / CAPTURES).write_text(json.dumps({"captures": entries}, indent=1) + "\n", "utf-8")
    dumps = {e["dump"]["manifest"]: e["files"] for e in entries}
    captures = [{k: v for k, v in e.items() if k not in ("problems", "files")} for e in entries]
    found = {"variants": loaded_variants(run), "captures": captures, "dumps": dumps}
    found["packs"] = {z["file"]: f"{PACKS}/{z['file']}" for z in run.ready.zips}
    return found


def check_l1(root: Path, found: dict) -> dict:
    """A dump record's `offline` field (offline.md#rules: each closure with its method and
    evidence): `check L1` on the record as it stands, in a child process reading it on stdin;
    RecordError naming why there is none."""
    try:
        done = subprocess.run(  # noqa: S603 this interpreter and the CLI, no shell
            [sys.executable, *L1_COMMAND],
            cwd=root,
            input=json.dumps(found).encode("utf-8"),
            capture_output=True,
            timeout=L0_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise record.RecordError(f"`check L1` did not run ({error})") from None
    try:
        result = json.loads(done.stdout.decode("utf-8"))
    except ValueError:
        result = None
    if not isinstance(result, dict) or "offline" not in result:
        why = (result or {}).get("error") if isinstance(result, dict) else None
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines() or ["no output"]
        raise record.RecordError(f"`check L1` judged nothing: {why or lines[-1]}")
    return result["offline"]


# The run.


def perform(
    root: Path,
    spec_in: Path | dict,
    host: RunHost,
    machine: record.Machine,
    say: Say,
    announce: Say,
    part: Part | None = None,
    displays: dict | None = None,
) -> dict:
    """The run, or one part of a split session's: orphans finished (D41), prepare's checks and
    identity, the live world restored to its snapshot, D42's check for a measured run (its
    displays held on by its caller: their facts), the session, the record. Returns the record."""
    marks: dict[str, float] = {"prepare": time.monotonic()}
    orphans = measure.finish_orphans(root, host, say)
    ready = prepare(root, spec_in, machine)
    if part is not None:
        ready = dataclasses.replace(ready, spec=part_spec(ready, part))
    elif ready.spec.groups:
        raise record.RecordError(
            f"{ready.spec.name} splits into {len(ready.spec.groups)} launches; fix: run it "
            "through `optilux run`, which runs its parts"
        )
    spec = ready.spec
    snap_hash, snap_files, _ = ready.snapshot
    marks["restore"] = time.monotonic()
    # The live world restored to its snapshot before every session (D44, F15).
    restored = world.restore(root, spec.views, spec.world, host, say)
    if restored["treeSha256"] != snap_hash:
        raise record.RecordError(
            f"{record.SNAPSHOTS}/{spec.views}/ hashes {restored['treeSha256'][:12]}... now, "
            f"{snap_hash[:12]}... ({snap_files} files) when the identity was built; fix: rerun "
            "with nothing writing snapshots/ beside the run"
        )
    system = ready.identity["system"]
    say(
        f"system: {system['gpu']}, {system['resolution']} {system['windowMode']}, HAGS "
        f"{'on' if system['hags'] else 'off'}, Windows build {system['windowsBuild']}"
    )
    machine_facts = None
    if spec.mode is not None and spec.kind != record.VISUAL:  # D42: a measured run's
        marks["machine"] = time.monotonic()
        machine_facts = measure.machine_to_itself(host, ready.recorded["hags"]["adapterLuid"], say)
        say(
            f"machine (D42): {machine_facts['idleSeconds']:.0f} s without input, no other process "
            f"above {measure.GPU_MAX_PCT:g} % of the 3D engine"
        )
    run = Runner(root, ready, host, say, announce, restored, marks)
    if orphans:
        run.facts["orphansFinished"] = [o["name"] for o in orphans]
    if machine_facts is not None:
        run.facts["machine"] = machine_facts
    if displays is not None:
        run.facts["displays"] = displays
    try:
        if spec.kind == record.VISUAL:
            visual_before(run)
            run.session(visual_plan(run), lambda s: visual_session(run, s))
        elif spec.kind == record.DUMP:
            dump_before(run)
            run.session(dump_plan(run), lambda s: dump_session(run, s))
        elif spec.mode is None:
            pack = f"unmodified {ready.pack.file}"
            if spec.optilux is not None:
                run.facts["optilux"] = write_optilux(run)
                pack = f"{spec.optilux['variant']} as {run.pack_file}"
            run.session(
                f"{pack}: {session_plan(spec, ready.views)}", lambda s: acceptance_body(run, s)
            )
            acceptance_after(run)
        else:
            measured_before(run)
            run.session(measured_plan(run), lambda s: measured_body(run, s))
    except KeyboardInterrupt:
        run.status = "aborted"
        run.problems.append("stopped by the user")
    except SessionEnded as error:
        run.status = "invalid"
        run.problems.append(str(error))
    except (RunError, launch.LaunchError, modclient.ModError, record.RecordError) as error:
        run.problems.append(str(error))
    except Exception as error:  # noqa: BLE001 a session ran: its record is written whatever broke
        run.problems.append(f"{type(error).__name__}: {error}")
    finally:
        if run.launched is None and run.created:  # no game ever held them
            run.facts["filesCleanup"] = measure.remove_files(run.created)
    marks["after"] = time.monotonic()
    found = {
        "schema": record.SCHEMA,
        "name": spec.name,
        "kind": spec.kind,
        "spec": spec.data,
        "notes": spec.notes,
        "status": run.status,
        "reason": None,
        "startedAt": run.started,
        "endedAt": None,
        "identity": run.ident,
        "recorded": run.recorded,
    }
    if spec.kind == record.VISUAL:
        found.update(mode=spec.mode, variants=[], captures=[])
        try:
            found.update(visual_fields(run))
        except Exception as error:  # noqa: BLE001 the record is written whatever its pairs met
            run.problems.append(f"the pairs' record: {type(error).__name__}: {error}")
        status = measured_status(run)
        try:
            measured_session_facts(run)
        except Exception as error:  # noqa: BLE001 as above
            run.problems.append(f"the session's raw files: {type(error).__name__}: {error}")
            status = "failed" if status == "ok" else status
        run.facts["timeSplit"] = measure.time_split(marks, time.monotonic())
    elif spec.kind == record.DUMP:
        found.update(variants=[], captures=[], dumps={})
        try:
            found.update(dump_fields(run))
        except Exception as error:  # noqa: BLE001 the record is written whatever its dumps met
            run.problems.append(f"the dumps' record: {type(error).__name__}: {error}")
        status = measured_status(run)
        if status == "ok":  # closures only over a whole set of dumps of an ok session
            try:
                held = {**found, "status": status, "raw": shown(run.raw, root)}
                found["offline"] = check_l1(root, held)
            except record.RecordError as error:
                run.problems.append(str(error))
                status = "failed"
        try:
            measured_session_facts(run)
        except Exception as error:  # noqa: BLE001 as above
            run.problems.append(f"the session's raw files: {type(error).__name__}: {error}")
            status = "failed" if status == "ok" else status
        run.facts["timeSplit"] = measure.time_split(marks, time.monotonic())
    elif spec.mode is None:
        a5_hold(run)
        status, acceptance = record_status(
            run.status, run.problems, run.facts, run.items, spec.items, spec.reloads, run.table
        )
        status = judge_a5(run, acceptance, status)
        found.update(variants=run.variants, acceptance=acceptance)
        if spec.reloads:
            found["reloadTable"] = run.table
    else:
        found.update(mode=spec.mode, calibration=spec.calibration, variants=[], captures=[])
        if spec.split is not None:  # a part, whatever its analysis meets
            found["split"] = spec.split
        try:
            found.update(measured_fields(run))
        except Exception as error:  # noqa: BLE001 the record is written whatever the cut met
            run.problems.append(f"the captures' analysis: {type(error).__name__}: {error}")
        status = measured_status(run)
        judge_session(run, found, status)
        if run.problems and status == "ok":
            status = "failed"
        try:
            measured_session_facts(run)
        except Exception as error:  # noqa: BLE001 as above
            run.problems.append(f"the session's raw files: {type(error).__name__}: {error}")
            status = "failed" if status == "ok" else status
        run.facts["timeSplit"] = measure.time_split(marks, time.monotonic())
    found.update(status=status, reason="; ".join(run.problems) or None, endedAt=now())
    return {**found, "session": run.facts, "raw": shown(run.raw, root)}


def close_journal(raw: Path) -> None:
    """The run's journal renamed journal.json once its record (or the record's content) is
    written: the run ended, so the next run finds no orphan in it (D41)."""
    partial = raw / PARTIAL
    if partial.exists():
        replace(partial, raw / CLOSED)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("spec", help="the run spec, a JSON file (docs/run-record.md#run-spec)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the spec and print the identity; nothing launches",
    )


def check(ready: Prepared, as_json: bool) -> int:
    """`--check`: the identity `run` would record, key by key, the calibration that matched it,
    a split session's launches and an Optilux variant's zip as built (a visual, dump or measured
    run's, each with its sha512); nothing launched or written."""
    cid = ready.spec.calibration
    groups = [list(g) for g in ready.spec.groups]
    zipped = None
    if ready.optilux is not None:
        zipped = {k: v for k, v in ready.optilux.items() if k != "data"}
        zipped["build"] = ready.spec.optilux
    zips = [{k: v for k, v in z.items() if k != "data"} for z in ready.zips]
    measured = ready.spec.mode is not None and ready.spec.kind != record.VISUAL
    if as_json:
        found = {"ok": True, "name": ready.spec.name, "launched": False, "calibration": cid}
        found["optilux"] = zipped
        if ready.spec.kind == record.VISUAL:
            found.update(zips=zips, cycle=ready.cycle, planned=ready.spec.planned)
        if ready.spec.kind == record.DUMP:
            found.update(zips=zips, views=list(ready.spec.view_ids), planned=ready.spec.planned)
        if measured:
            found.update(zips=zips, planned=ready.spec.planned)
        print(json.dumps({**found, "groups": groups, "identity": ready.identity}))
        return 0
    judged = f"; calibration {cid[:24]}... matches it key by key" if cid else ""
    print(
        f"{PREFIX} --check: {ready.spec.name} ({ready.spec.kind} on {ready.spec.views}) holds"
        f"{judged}; nothing launched, the live world left to the run; the identity:"
    )
    if groups:
        launches = "; ".join(", ".join(g) for g in groups)
        print(f"split: {len(groups)} launches of views (D43): {launches}")
    if zipped is not None:
        print(f"optilux: {json.dumps(zipped)}")
    if ready.spec.kind == record.VISUAL:
        print(
            f"visual: {ready.spec.planned} reloads on {', '.join(ready.spec.view_ids)}, aligned on "
            f"cycle {ready.cycle}; zips: {json.dumps(zips)}"
        )
    if ready.spec.kind == record.DUMP:
        print(
            f"dump: {ready.spec.planned} reloads, one view per dimension: "
            f"{', '.join(ready.spec.view_ids)}; zips: {json.dumps(zips)}"
        )
    if measured:
        print(
            f"measured: {ready.spec.planned} reloads on {', '.join(ready.spec.view_ids)}; zips: "
            f"{json.dumps(zips)}"
        )
    a5 = ready.spec.a5
    if a5 is not None:
        last = a5["from"] + a5["count"] - 1
        print(
            f"A5: waits {a5['from']}-{last} of {a5['of']}"
            + (f", continuing {a5['first']}" if a5["first"] else "")
            + f"; {ready.spec.planned} reloads, aligned on cycle {ready.cycle}"
        )
    for key, value in ready.identity.items():
        print(f"{key}: {json.dumps(value)}")  # ASCII: a piped stdout may be cp1252
    return 0


def summary_line(found: dict) -> str:
    """The run's outcome in one line: a measured run's captures and verdicts, a visual run's pairs,
    an acceptance run's items."""
    parts = []
    if found.get("kind") == record.DUMP:
        captures = found.get("captures") or []
        valid = sum(1 for c in captures if c.get("valid"))
        manifests = {c["dump"]["manifest"] for c in captures if "dump" in c}
        return f"{valid} of {len(captures)} dumps whole, {len(manifests)} distinct"
    if "captures" in found:
        captures = found["captures"]
        valid = sum(1 for c in captures if c.get("valid"))
        parts.append(f"{valid} of {len(captures)} captures valid")
        if found.get("kind") == record.VISUAL:
            moving = [f"{c['view']}/{c['variant']}" for c in captures if "moving" in c["flags"]]
            parts.append(f"pairs moving: {', '.join(moving) or 'none'}")
    judged = found.get("verdicts")
    if judged:
        parts += [f"{c['variant']} {c['verdict']}" for c in judged["candidates"]]
        twin = {True: "inside", False: "beyond", None: "unmeasured"}[judged["twin"]["inside"]]
        parts.append(f"twin {twin}")
    shown_pass = {True: "pass", False: "FAIL", None: "waits"}
    parts += [f"{e['item']} {shown_pass[e['pass']]}" for e in found.get("acceptance") or []]
    return ", ".join(parts)


def write_launch(root: Path, found: dict, say: Say) -> Path:
    """A launch's record written and its journal closed (the record's content dumped beside the
    journal when the write is refused: RecordError naming the dump)."""
    raw = root / found["raw"]
    try:
        path = record.write_record(root, found, say)
    except record.RecordError as error:
        dump = raw / "record-unwritten.json"
        dump.write_text(json.dumps(found, indent=1, default=str) + "\n", encoding="utf-8")
        close_journal(raw)  # ended, its content kept: no orphan for the next run to finish
        raise record.RecordError(
            f"{error}; the record's content is in {shown(dump, root)}"
        ) from None
    close_journal(raw)
    return path


def run_session(
    root: Path,
    spec_in: Path | dict,
    host: RunHost,
    machine: record.Machine,
    say: Say,
    announce: Say,
    displays: dict | None = None,
) -> tuple[dict, Path]:
    """One session through the runner (`run`'s and `calibrate`'s): one launch and its record, or a
    split session's parts from the first without an ok record, then its session record. The
    last record written and its path: a part that did not end ok stops the session there. A
    measured session holds the displays on throughout (measure.displays_on), unless its caller
    holds them already (`displays`, calibrate's over its sessions); a visual one too, never
    refused with them off."""
    data = load_spec(spec_in) if isinstance(spec_in, Path) else spec_in
    spec = checked(root, data)

    def launches(held: dict | None) -> tuple[dict, Path]:
        if not spec.groups:
            found = perform(root, data, host, machine, say, announce, displays=held)
            return found, write_launch(root, found, say)
        return run_split(root, data, spec, host, machine, say, announce, held)

    viewed = spec.kind in (record.VISUAL, record.DUMP)
    if (spec.mode is None and not viewed) or displays is not None:
        return launches(displays)
    # A visual run reads its frames back and a dump run its files, and neither needs a presented
    # row: the displays are held on through both but never refused off (m3-capture-1's selftest
    # captured 3840x2160 with them off).
    with measure.displays_on(host, say, not viewed) as held:
        return launches(held)


def part_record(root: Path, session: str, n: int) -> tuple[dict | None, str]:
    """Part n of a session: its ok record if one exists, and the next free run name (a name
    whose record or raw folder exists is taken: an orphan's folder the next run finishes)."""
    for retry in range(len(record.RETRIES) + 1):
        name = record.part_name(session, n, retry)
        if (root / record.RECORDS / f"{name}.json").is_file():
            found = record.read_record(root, name)
            split = found.get("split") or {}
            if (split.get("session"), split.get("part"), found.get("status")) == (session, n, "ok"):
                return found, name
            continue
        if not (root / record.RAW / name).exists():
            return None, name
    raise record.RecordError(
        f"part {n} of {session} ran {len(record.RETRIES) + 1} times; fix: start a new session"
    )


def run_split(
    root: Path,
    data: dict,
    spec: record.Spec,
    host: RunHost,
    machine: record.Machine,
    say: Say,
    announce: Say,
    displays: dict | None = None,
) -> tuple[dict, Path]:
    """A split session (run-record.md#split-sessions): each part without an ok record launched,
    recorded, stopped at the first that does not end ok; the session ended invalid when a part's
    identity differs from the first ok part's; the session record once every part is ok."""
    done: list[dict] = []
    for n, views in enumerate(spec.groups, start=1):
        found, name = part_record(root, spec.name, n)
        if found is not None:
            if record.canonical(found["spec"]) != record.canonical(data):
                raise record.RecordError(
                    f"{name} ran another spec under the name {spec.name}; fix: rerun with its "
                    "spec, or start a new session under a new name"
                )
            done.append(found)
            say(f"{PREFIX}: {spec.name}: part {n} of {len(spec.groups)} is {name}, ok")
            continue
        if done:
            ready = prepare(root, data, machine, match=False)
            differ = record.identity_differences(ready.identity, done[0]["identity"])
            moved = None if differ else zips_moved(ready, done[0])
            if differ or moved:
                why = (
                    f"part {n}'s identity differs from {done[0]['name']}'s: {', '.join(differ)}"
                    if differ
                    else f"part {n}'s {moved}"
                ) + (
                    " (a split session's parts share one identity and their variants' zips; "
                    "never resumed: start a new one)"
                )
                return write_session(root, data, spec, done, "invalid", why, say)
        say(f"{PREFIX}: {spec.name}: part {n} of {len(spec.groups)} as {name}: {', '.join(views)}")
        part = Part(spec.name, n, len(spec.groups), name, views)
        found = perform(root, data, host, machine, say, announce, part, displays)
        path = write_launch(root, found, say)
        if found["status"] != "ok":
            return found, path
        done.append(found)
    return write_session(root, data, spec, done, "ok", None, say)


def zips_moved(ready: Prepared, first: dict) -> str | None:
    """Why a split session's next part, as prepared, would load other bytes than its first ok part
    did: a variant whose file or sha512 differs (an Optilux variant's working tree or ref moved
    between the launches, plans/m4.md D80); None when each loads the same zip."""
    pins = zip_pins(ready)
    held = {v.get("id"): (v.get("pack"), v.get("sha512")) for v in first.get("variants") or []}
    for v in measure.variants(ready.spec, ready.suite):
        digest = measure.variant_sha512(v, pins)
        if held.get(v.id) != (v.pack, digest):
            pack, sha512 = held.get(v.id, (None, None))
            return (
                f"{v.id} would load {v.pack} (sha512 {digest[:12]}...), {first['name']} loaded "
                f"{pack} (sha512 {str(sha512)[:12]}...)"
            )
    return None


# A variant as its parts must agree on it: its file and pin, the options written (a profile's
# read afresh each launch, never identity) and read back, the timers.
VARIANT_KEYS = ("id", "role", "pack", "sha512", "profile", "options", "timers")


def variants_held(found: dict) -> list[dict]:
    """A record's variants as one split session's parts must share them."""
    return [
        {
            **{k: v.get(k) for k in VARIANT_KEYS},
            "effective": (v.get("effective") or {}).get("sha256"),
        }
        for v in found.get("variants") or []
    ]


def session_mismatch(parts: list[dict], groups: tuple[tuple[str, ...], ...]) -> str | None:
    """Why ok parts do not make one session: an identity or variants other than the first part's
    (a profile edited between launches leaves the spec and the identity as they were), or a part
    whose `split` is not the session's group of that number."""
    if len(parts) != len(groups):
        return f"{len(parts)} parts for {len(groups)} groups"
    for n, (part, views) in enumerate(zip(parts, groups, strict=True), start=1):
        differ = record.identity_differences(part.get("identity"), parts[0].get("identity"))
        if differ:
            return (
                f"{part['name']}'s identity differs from {parts[0]['name']}'s: {', '.join(differ)}"
            )
        if variants_held(part) != variants_held(parts[0]):
            return f"{part['name']}'s variants differ from {parts[0]['name']}'s"
        split = part.get("split") or {}
        if (split.get("part"), split.get("views")) != (n, list(views)):
            held = f"{split.get('views')} as part {split.get('part')}"
            return f"{part['name']} measured {held}, not group {n}"
    return None


def write_session(
    root: Path,
    data: dict,
    spec: record.Spec,
    parts: list[dict],
    status: str,
    reason: str | None,
    say: Say,
) -> tuple[dict, Path]:
    """A split session's record (run-record.md#split-sessions): its parts' names, their one
    identity and the first part's variants; when it ends ok, the verdicts over the mode's views
    with the calibration's id (each view bracketed in its own part), or A8's and A11's entries;
    no captures (the parts keep them)."""
    found: dict[str, Any] = {
        "schema": record.SCHEMA,
        "name": spec.name,
        "kind": spec.kind,
        "spec": data,
        "notes": spec.notes,
        "status": status,
        "reason": reason,
        "startedAt": parts[0]["startedAt"] if parts else now(),
        "endedAt": now(),
        "identity": parts[0]["identity"] if parts else None,
        "mode": spec.mode,
        "calibration": spec.calibration,
        "parts": [p["name"] for p in parts],
        "groups": [list(g) for g in spec.groups],
        "variants": parts[0].get("variants", []) if parts else [],
    }
    if status == "ok":
        mismatch = session_mismatch(parts, spec.groups)
        if mismatch:
            found.update(
                status="invalid",
                reason=f"{mismatch} (a split session's parts share one identity and its groups; "
                "never resumed: start a new one)",
            )
            status = "invalid"
    if status == "ok":
        captures = record.session_captures(root, found)
        expected = found["variants"] or None
        problems = []
        if spec.cal is not None and spec.kind == "measurement":
            try:
                found["verdicts"] = verdicts(root, captures, spec.cal, spec.cal["mode"], expected)
            except stats.StatsError as error:
                problems.append(f"the verdicts: {error}")
        if spec.kind == "acceptance":
            found["acceptance"] = item_entries(spec, captures, expected)
            failed = [e["item"] for e in found["acceptance"] if e["pass"] is False]
            if failed:
                problems.append(f"items failed: {', '.join(failed)}")
        if problems:
            found.update(status="failed", reason="; ".join(problems))
    elif spec.kind == "acceptance":  # never judged: each item waits on a new session
        why = f"session {spec.name} ended {status}: {reason}"
        found["acceptance"] = [
            {"item": i, "pass": None, "evidence": {"pending": why}} for i in spec.items
        ]
    return found, record.write_record(root, found, say)


def run(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)

    def announce(text: str) -> None:  # every launch is announced, --json or not
        print(text, file=sys.stderr if args.json else sys.stdout, flush=True)

    def refuse(problem: str) -> int:
        if args.json:
            print(json.dumps({"ok": False, "problem": problem}))
        else:
            print(f"{PREFIX}: {problem}", file=sys.stderr)
        return 1

    try:
        if args.check:
            return check(prepare(root, Path(args.spec), record.Machine()), args.json)
        found, path = run_session(root, Path(args.spec), RunHost(), record.Machine(), say, announce)
    except OSError as error:  # a file the run reads or writes before its session (a lock)
        return refuse(f"{error}; fix: quit whatever holds or removed that file, then rerun")
    except (
        record.RecordError,
        platform.PlatformError,
        launch.LaunchError,
        world.WorldError,
    ) as error:
        return refuse(str(error))
    if args.json:
        print(
            json.dumps(
                {
                    "ok": found["status"] == "ok",
                    "record": shown(path, root),
                    "status": found["status"],
                    "reason": found["reason"],
                    "outcome": summary_line(found),
                }
            )
        )
    else:
        line = f"{PREFIX}: {found['status']}; {shown(path, root)}: {summary_line(found)}"
        if found["reason"]:
            line += f"; {found['reason']}"
        if found.get("split") and found["status"] != "ok":
            line += f"; rerun to resume {found['split']['session']} at this part"
        print(line, file=sys.stdout if found["status"] == "ok" else sys.stderr)
    return 0 if found["status"] == "ok" else 1


VERB = Verb(
    name="run",
    help="run a spec: an acceptance, measured, visual or dump session and its record",
    run=run,
    configure=configure,
    structured=True,
)
