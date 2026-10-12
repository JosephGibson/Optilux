"""`optilux run <spec.json> [--check] [--json]` (docs/run-record.md#run-spec, docs/plans/m1.md
0.01.08 and 0.01.09, docs/plans/m2.md M2.P01).

An acceptance run: the spec checked (optilux/record.py, every refusal naming its fix), the display
against the suite and the identity built before anything launches (`--check` prints it and
stops there, the live world left to the run), the live world restored to its snapshot (D44),
then the announced launches; the session's launch facts are held against the identity. The
session launch runs the session start of docs/mod-protocol.md#choreography (A10 is its
selftest). At the first view: A4 (a copy of the reference zip with one program broken, selected
for one reload that must answer iris-compile-error; the pack restored, reloaded, ready, one
frame), A7 (SendInput's key and mouse motion with input.block off open a screen and turn the
camera; blocked, they change nothing; unblocked again, the motion turns it), A9 (120 frames
captured inside one PresentMon run, their stamps matched to its rows by order). Then per view A2
(a capture with F2 pressed inside it through SendInput; the new screenshot must equal one
captured frame byte for byte; a miss is kept and retaken once) and A3 (`/tp` through `command`
against camera.place with tpSemantics, both read back), F4's reload table (`reloads` in the
spec: heap after GC and private bytes every 10 reloads), then `input.block off` and `quit`. A1's
launch starts without the token and never connects: the pipe list holds no optilux- pipe,
latest.log no applied mixin and no active line, the JVM's thread dump no optilux- thread;
WM_CLOSE ends it. The record goes to results/records/<name>.json, the request log and the raw
artifacts to results/raw/<name>/. Exit 0 when every item passed.
"""

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, launch, modclient, platform, presentmon, record, repo, world
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
    PIPES,
    PLACE_TIMEOUT,
    READY_TIMEOUT,
    REQUESTS,
    STABLE_FRAMES,
    RunError,
    RunHost,
    Session,
    check_presentmon,
    load_spec,
    now,
    record_status,
    session_start,
    settle_view,
    trim,
    view_pose,
)
from optilux.verbs import Verb
from optilux.verbs.install import JAVA_DIR, JAVA_PROFILE, RUNTIME, Say, shown

PREFIX = "optilux run"


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


def prepare(root: Path, spec_path: Path, machine: record.Machine) -> Prepared:
    """Everything `run` checks before the live world, and the identity (run-record.md#identity)
    built from what the session will use, nothing launched or written (`--check` stops here): the
    spec, the views and the snapshot's tree hash, the display and HAGS, PresentMon's pin, no copy
    left by an earlier A4, then the launch spec, the views file and the JDK's release file
    hashed, the jars launch places, the pinned resource packs, the options file as the launch
    would write it, the measured modules. A failed launch records this identity (id7, id9)."""
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    java_profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    base = root / RUNTIME / plat.id
    game = base / launch.GAME
    pack = launch.reference_pack(plat)
    saves = game / launch.SAVES
    spec = record.check_spec(root, load_spec(spec_path), plat, suite, saves, pack.file)
    views, views_path = record.load_views(root, spec.views)
    snapshot = record.tree(root / record.SNAPSHOTS / spec.views)
    options = launch.written_options(suite["display"], {})
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
    pre = launch.prelaunch(suite["display"], spec.tier, pack.file, {})
    _, options_file = launch.planned_options(game, pre)
    java_home = root / JAVA_DIR / java_profile["runtime"]["build"]
    packs = [p for p in plat.tier_files(spec.tier) if p.kind == "resourcePack"]
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
        packs=[{"file": p.file, "sha512": p.sha512} for p in packs],
        settings=record.settings_identity(launch.settings_facts(pre, True), options_file),
        suite=suite,
        java=record.java_identity(java_home, java_profile),
        system=system,
        harness=record.harness_identity(root, pm_exe),
    )
    record.check_identity(found)
    recorded = {"platformFile": record.file_sha256(plat.path), **system_recorded}
    return Prepared(
        spec, plat, suite, pack, views, base, java_home, snapshot, pm_exe, found, recorded
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


def perform(
    root: Path, spec_path: Path, host: RunHost, machine: record.Machine, say: Say, announce: Say
) -> dict:
    """The run: prepare's checks and identity, the live world restored to its snapshot, the session
    launch held against the identity, A1's launch, the record. Returns the record."""
    ready = prepare(root, spec_path, machine)
    spec, suite, pack, views = ready.spec, ready.suite, ready.pack, ready.views
    snap_hash, snap_files, manifest = ready.snapshot
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
    jcmd = ready.java_home / "bin" / "jcmd.exe"
    pm_exe = ready.presentmon if "A9" in spec.items else None
    raw = root / record.RAW / spec.name
    raw.mkdir(parents=True)
    (raw / "world-manifest.txt").write_text(manifest, encoding="utf-8", newline="\n")
    started = now()
    head = repo.head(root)
    try:
        dirty: bool | str = bool(repo.changes(root))
    except repo.GitError as error:
        dirty = f"unread: {error}"
    items: dict[str, dict] = {}
    restored["copied"], restored["deleted"] = len(restored["copied"]), len(restored["deleted"])
    session_facts: dict[str, Any] = {"restore": restored}
    problems: list[str] = []
    ident: dict | None = ready.identity  # a failed launch records it (id9)
    table = None
    variants: list[dict] = []
    recorded: dict[str, Any] = {**ready.recorded, "harness": {"commit": head, "dirty": dirty}}
    status = "ok"
    try:
        announce(
            f"launch (announced): the session, tier {spec.tier}, world {spec.world}, "
            f"unmodified {pack.file}: {session_plan(spec, views)}; hands off the mouse and "
            "keyboard until the quit"
        )
        launched = launch.launch(root, spec.world, spec.tier, True, {}, say, host)
        session_facts["launch"] = trim(launched.facts)
        recorded["amd"] = launched.facts["gate"]["amd"]
        recorded["java"] = launched.facts["gate"]["java"]  # JVMs beside the game
        try:
            differ = record.launch_differences(ready.identity, launched.facts)
            differ += reread(root, ready)
            if differ:  # the identity is not this session's: none is recorded
                ident = None
                raise RunError(
                    f"the launch's {', '.join(differ)} differ from the identity built before it; "
                    "fix: rerun with nothing changing config/ or runtime/ beside the run"
                )
            client, mod = launch.open_mod(launched, root, host, say, raw / REQUESTS)
        except BaseException as error:
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise RunError(f"{error}; the game was ended ({how})") from None
        session_facts["mod"] = mod
        s = Session(root, raw, launched, client, host, say)
        try:
            running, java = mod["hello"]["versions"]["java"], ready.identity["java"]
            if running != java["version"]:
                ident = None
                raise RunError(
                    f"the game runs Java {running}, {java['runtime']}'s release file says "
                    f"{java['version']}; fix: run `optilux install`"
                )
            if "A1" in spec.items:
                # A1's positive controls: the detectors A1 relies on, seeing the mod active here.
                expected = modclient.pipe_name(launched.mod_token()).removeprefix(PIPES)
                try:
                    session_facts["pipeListed"] = expected in host.pipes()
                except OSError as error:
                    session_facts["pipeListed"] = f"unread: {error}"
                try:
                    dump = host.thread_dump(jcmd, launched.pid)
                    (raw / "session-threads.txt").write_text(dump, encoding="utf-8", newline="\n")
                    session_facts["threads"] = [
                        name for name in thread_names(dump) if name.startswith(MOD_THREAD)
                    ]
                except (OSError, RunError, subprocess.SubprocessError) as error:
                    session_facts["threads"] = f"unread: {error}"
            start = session_start(
                s,
                pack.file,
                suite["capture"]["gpuWarmupS"],
                system["resolution"],
                suite["display"]["resolution"],
            )
            items["A10"] = {
                "pass": start["selftest"]["pass"] is True,
                "selftest": start["selftest"],
                "after": {"worldWait": start["joined"]},
            }
            variants.append(
                {
                    "pack": pack.file,
                    "sha512": pack.sha512,
                    "profile": None,
                    "options": {
                        "count": len(start["options"]["values"]),
                        "values": start["options"]["values"],
                    },
                }
            )
            session_facts["reload"] = start["reload"]
            previous = start["joined"]["pose"]["dimension"]
            weather = None
            a2_views, a3_views, settled = [], [], []
            session_facts["views"] = settled
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
            if spec.reloads:
                table = reload_table(s, jcmd, pack.file, spec.reloads)
            home = view_pose(views["views"][0])
            s.step("camera.place home", lambda: client.camera_place(home, PLACE_TIMEOUT))
            s.step("input.block off", lambda: client.input_block(False))
            s.label = "quit"
            session_facts["quit"] = launch.quit_mod(client, launched.process, host)
            say(
                f"quit: exit code {session_facts['quit']['exitCode']} in "
                f"{session_facts['quit']['seconds']:.1f} s"
            )
        except BaseException as error:
            client.close()
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise RunError(f"the session: {error}; the game was ended ({how})") from None
        finally:
            s.drain()
            session_facts["steps"] = s.steps
            session_facts["events"] = s.events
            session_facts["stray"] = list(client.stray)
            if "A4" in spec.items:  # the game has exited here: its pack copy can go
                session_facts["a4Cleanup"] = remove_broken(launched.game)
            # Every session's request log, a failed one's too (m1-acceptance-1 and -2 had none).
            try:
                session_facts["logCheck"] = launch.check_log(raw / REQUESTS, launched.mod_token())
            except (launch.LaunchError, OSError) as error:
                session_facts["logCheck"] = {"tokenAbsent": False, "problem": str(error)}
        session_facts["readBack"] = launch.read_back(launched.game, launched.prelaunch)
        shutil.copyfile(launched.log, raw / "session-latest.log")
        # As the game read it; its unwritten keys are the identity's settings (D37).
        recorded["optionsTxt"] = {"sha256": launched.facts["optionsFile"]["sha256"]}
        mods_log = helper_lines(launched.log.read_text(encoding="utf-8", errors="replace"))
        session_facts["helperLog"] = {
            "applied": len(mods_log["applied"]),
            "active": len(mods_log["active"]),
            "hookFailures": len(mods_log["hookFailures"]),
            "irisOutsideReload": len(mods_log["irisOutsideReload"]),
        }
        if "A1" in spec.items:
            control = {
                "sessionPipeListed": session_facts["pipeListed"],
                "sessionMixinsApplied": session_facts["helperLog"]["applied"],
                "sessionThreads": session_facts["threads"],
            }
            # A1's launch is a session too: the world back to its snapshot first (D44).
            again = world.restore(root, spec.views, spec.world, host, say)
            session_facts["restoreA1"] = {
                **again,
                "copied": len(again["copied"]),
                "deleted": len(again["deleted"]),
            }
            items["A1"] = a1(root, raw, spec.world, spec.tier, host, say, announce, jcmd, control)
    except KeyboardInterrupt:
        status = "aborted"
        problems.append("stopped by the user")
    except (RunError, launch.LaunchError, modclient.ModError, record.RecordError) as error:
        problems.append(str(error))
    except Exception as error:  # noqa: BLE001 a session ran: its record is written whatever broke
        problems.append(f"{type(error).__name__}: {error}")
    status, acceptance = record_status(
        status, problems, session_facts, items, spec.items, spec.reloads, table
    )
    found = {
        "schema": record.SCHEMA,
        "name": spec.name,
        "kind": spec.kind,
        "spec": spec.data,
        "status": status,
        "reason": "; ".join(problems) or None,
        "startedAt": started,
        "endedAt": now(),
        "identity": ident,
        "recorded": recorded,
        "variants": variants,
        "acceptance": acceptance,
    }
    if spec.reloads:
        found["reloadTable"] = table
    return {**found, "session": session_facts, "raw": shown(raw, root)}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("spec", help="the run spec, a JSON file (docs/run-record.md#run-spec)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the spec and print the identity; nothing launches",
    )


def check(ready: Prepared, as_json: bool) -> int:
    """`--check`: the identity `run` would record, key by key; nothing launched or written."""
    if as_json:
        found = {"ok": True, "name": ready.spec.name, "launched": False}
        print(json.dumps({**found, "identity": ready.identity}))
        return 0
    print(
        f"{PREFIX} --check: {ready.spec.name} ({ready.spec.kind} on {ready.spec.views}) holds; "
        "nothing launched, the live world left to the run; the identity:"
    )
    for key, value in ready.identity.items():
        print(f"{key}: {json.dumps(value)}")  # ASCII: a piped stdout may be cp1252
    return 0


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
        found = perform(root, Path(args.spec), RunHost(), record.Machine(), say, announce)
    except OSError as error:  # a file the run reads or writes before its session (a lock)
        return refuse(f"{error}; fix: quit whatever holds or removed that file, then rerun")
    except (
        record.RecordError,
        platform.PlatformError,
        launch.LaunchError,
        world.WorldError,
    ) as error:
        return refuse(str(error))
    try:
        path = record.write_record(root, found, say)
    except record.RecordError as error:
        dump = root / found["raw"] / "record-unwritten.json"
        dump.write_text(json.dumps(found, indent=1, default=str) + "\n", encoding="utf-8")
        message = f"{error}; the record's content is in {shown(dump, root)}"
        print(f"{PREFIX}: {message}", file=sys.stderr)
        return 1
    passed = {entry["item"]: entry["pass"] for entry in found["acceptance"]}
    if args.json:
        print(
            json.dumps(
                {
                    "ok": found["status"] == "ok",
                    "record": shown(path, root),
                    "status": found["status"],
                    "reason": found["reason"],
                    "items": passed,
                }
            )
        )
    else:
        items = ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in passed.items())
        line = f"{PREFIX}: {found['status']}; {shown(path, root)}: {items}"
        if found["reason"]:
            line += f"; {found['reason']}"
        print(line, file=sys.stdout if found["status"] == "ok" else sys.stderr)
    return 0 if found["status"] == "ok" else 1


VERB = Verb(
    name="run",
    help="run an acceptance spec: the session, the items, the record",
    run=run,
    configure=configure,
    structured=True,
)
