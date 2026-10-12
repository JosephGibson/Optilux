"""`optilux world snapshot|restore|prep <id> [--world <name>] [--json]` (docs/plans/m2.md
M2.P04, docs/measurement.md#session).

`snapshot` copies the game's saves/<name> (default: the id) to snapshots/<id>/ and writes its
manifest and facts (tree hash, files, the bench player's uuid, F8); `restore` makes saves/<name>
equal to snapshots/<id>/ in place (D44); `prep` prepares the views file <id>'s world and retakes
its snapshot (optilux/world.py: the world prep set, Chunky, the kill, the view functions, the
reference frames under results/raw/prep-<id>-<time>/). Exit 0 when the action held.
"""

import argparse
import json
import sys

from optilux import REPO_ROOT, launch, modclient, platform, record, world
from optilux.session import RunError, RunHost
from optilux.verbs import Verb
from optilux.verbs.install import InstallError, Say

PREFIX = "optilux world"
ACTIONS = ("snapshot", "restore", "prep")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=ACTIONS,
        help="snapshot: copy and hash the live world; restore: the live world back to its "
        "snapshot; prep: prepare the world and retake its snapshot",
    )
    parser.add_argument("id", help="the world's id: its views file and its snapshot")
    parser.add_argument(
        "--world",
        metavar="NAME",
        help="the saves/ folder (default: the id); prep always uses the id",
    )


def run(args: argparse.Namespace) -> int:
    prefix = f"{PREFIX} {args.action}"
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)

    def announce(text: str) -> None:  # every launch is announced, --json or not
        print(text, file=sys.stderr if args.json else sys.stdout, flush=True)

    save = args.world or args.id
    host = RunHost()
    try:
        if args.action == "snapshot":
            found = world.snapshot(REPO_ROOT, args.id, save, host, say)
        elif args.action == "restore":
            found = world.restore(REPO_ROOT, args.id, save, host, say)
        else:
            if args.world not in (None, args.id):
                raise world.WorldError("prep prepares the id's own world; fix: drop --world")
            found = world.prep(REPO_ROOT, args.id, host, say, announce)
    except (
        world.WorldError,
        record.RecordError,
        platform.PlatformError,
        launch.LaunchError,
        modclient.ModError,
        RunError,
        InstallError,
        OSError,
    ) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{prefix}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, **found}, default=str))
    elif args.action == "prep":
        snap = found["snapshot"]
        print(
            f"{prefix}: ok; {len(found['views'])} views prepared, snapshot {snap['treeSha256']} "
            f"({snap['files']} files); facts in {record.RAW}/{found['name']}/prep.json"
        )
    else:
        print(f"{prefix}: ok; {found['treeSha256']} ({found['files']} files)")
    return 0


VERB = Verb(
    name="world",
    help="snapshot, restore or prepare a bench world (copy, tree hash, restore in place, prep)",
    run=run,
    configure=configure,
    structured=True,
)
