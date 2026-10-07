"""`optilux run <spec.json> [--json]` (docs/run-record.md#run-spec, docs/plans/m1.md 0.01.08 and
0.01.09).

An acceptance run: the spec checked (optilux/record.py, every refusal naming its fix), the live
world hash-checked against its snapshot and the display against the suite, then the announced
launches. The session launch runs the session start of docs/mod-protocol.md#choreography (A10
is its selftest). At the first view: A4 (a copy of the reference zip with one program broken,
selected for one reload that must answer iris-compile-error; the pack restored, reloaded, ready,
one frame), A7 (SendInput's key and mouse motion with input.block off open a screen and turn the
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
from pathlib import Path
from typing import Any

from optilux import REPO_ROOT, launch, modclient, platform, presentmon, record, repo
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


def perform(
    root: Path, spec_path: Path, host: RunHost, machine: record.Machine, say: Say, announce: Say
) -> dict:
    """The run: checks, the session launch, A1's launch, the record. Returns the record."""
    plat = platform.load(root)
    suite = json.loads((root / platform.SUITE).read_text(encoding="utf-8"))
    java_profile = json.loads((root / JAVA_PROFILE).read_text(encoding="utf-8"))
    base = root / RUNTIME / plat.id
    saves = base / launch.GAME / launch.SAVES
    pack = launch.reference_pack(plat)
    spec = record.check_spec(root, load_spec(spec_path), plat, suite, saves, pack.file)
    views, views_path = record.load_views(root, spec.views)
    snapshot = root / record.SNAPSHOTS / spec.views
    snap_hash, snap_files, manifest = record.tree(snapshot)
    live_hash, live_files = record.tree_hash(saves / spec.world)
    if live_hash != snap_hash:
        raise record.RecordError(
            f"saves/{spec.world} hashes {live_hash[:12]}... ({live_files} files), its snapshot "
            f"{record.SNAPSHOTS}/{spec.views}/ {snap_hash[:12]}... ({snap_files}); fix: retake the "
            "snapshot from the world, or restore it (M2's `world restore`)"
        )
    say(
        f"world: saves/{spec.world} equals {record.SNAPSHOTS}/{spec.views}/: {snap_hash} "
        f"({snap_files} files)"
    )
    options = launch.written_options(suite["display"], {})
    system, system_recorded = record.system_facts(machine, options, suite["display"])
    say(
        f"system: {system['gpu']}, {system['resolution']} {system['windowMode']}, HAGS "
        f"{'on' if system['hags'] else 'off'}, Windows build {system['windowsBuild']}"
    )
    java_home = root / JAVA_DIR / java_profile["runtime"]["build"]
    jcmd = java_home / "bin" / "jcmd.exe"
    pm_exe = check_presentmon(root) if "A9" in spec.items else None
    leftover = broken_copies(base / launch.GAME)
    if leftover:
        raise record.RecordError(
            f"shaderpacks/ holds {', '.join(p.name for p in leftover)} from an earlier A4; fix: "
            "delete it (A4 writes its copy fresh)"
        )
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
    session_facts: dict[str, Any] = {}
    problems: list[str] = []
    ident = None
    table = None
    variants: list[dict] = []
    recorded: dict[str, Any] = {
        "platformFile": record.file_sha256(plat.path),
        **system_recorded,
        "harness": {"commit": head, "dirty": dirty},
    }
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
            client, mod = launch.open_mod(launched, root, host, say, raw / REQUESTS)
        except BaseException as error:
            how = launch.end(launched.process, host)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise RunError(f"{error}; the game was ended ({how})") from None
        session_facts["mod"] = mod
        s = Session(root, raw, launched, client, host, say)
        try:
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
            start = session_start(s, pack.file, suite["capture"]["gpuWarmupS"])
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
        recorded["optionsTxt"] = launched.facts["optionsFile"]  # as the game read it
        mods_log = helper_lines(launched.log.read_text(encoding="utf-8", errors="replace"))
        session_facts["helperLog"] = {
            "applied": len(mods_log["applied"]),
            "active": len(mods_log["active"]),
            "hookFailures": len(mods_log["hookFailures"]),
            "irisOutsideReload": len(mods_log["irisOutsideReload"]),
        }
        packs = [p for p in launched.facts["hashes"]["packs"] if p["kind"] == "resourcePack"]
        settings = dict(launched.facts["settings"])
        ident = record.identity(
            plat=plat,
            tier=spec.tier,
            spec_path=platform.spec_path(root, plat.id),
            mods=launched.facts["mods"]["sha512"],
            world={
                "snapshot": f"{record.SNAPSHOTS}/{spec.views}",
                "treeSha256": snap_hash,
                "files": snap_files,
                "live": spec.world,
            },
            views_path=views_path,
            packs=[{"file": p["file"], "sha512": p["sha512"]} for p in packs],
            settings=settings,
            suite=suite,
            java=record.java_identity(java_home, java_profile, mod["hello"]["versions"]["java"]),
            system=system,
        )
        if "A1" in spec.items:
            control = {
                "sessionPipeListed": session_facts["pipeListed"],
                "sessionMixinsApplied": session_facts["helperLog"]["applied"],
                "sessionThreads": session_facts["threads"],
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


def run(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)

    def announce(text: str) -> None:  # every launch is announced, --json or not
        print(text, file=sys.stderr if args.json else sys.stdout, flush=True)

    try:
        found = perform(root, Path(args.spec), RunHost(), record.Machine(), say, announce)
    except OSError as error:  # a file the run reads or writes before its session (a lock)
        problem = f"{error}; fix: quit whatever holds or removed that file, then rerun"
        if args.json:
            print(json.dumps({"ok": False, "problem": problem}))
        else:
            print(f"{PREFIX}: {problem}", file=sys.stderr)
        return 1
    except (record.RecordError, platform.PlatformError, launch.LaunchError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
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
