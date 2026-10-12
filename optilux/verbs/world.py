"""`optilux world snapshot|restore <id> [--world <name>] [--json]` (docs/plans/m2.md M2.P04,
docs/measurement.md#session).

`snapshot` copies the game's saves/<name> (default: the id) to snapshots/<id>/ and writes its
manifest and facts (tree hash, files, the bench player's uuid, F8); `restore` makes saves/<name>
equal to snapshots/<id>/ in place (D44). Exit 0 when the action held.
"""

import argparse
import json
import sys

from optilux import REPO_ROOT, platform, record, world
from optilux.session import RunHost
from optilux.verbs import Verb
from optilux.verbs.install import Say

PREFIX = "optilux world"
ACTIONS = ("snapshot", "restore")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=ACTIONS,
        help="snapshot: copy and hash the live world; restore: the live world back to its snapshot",
    )
    parser.add_argument("id", help="the world's id: its views file and its snapshot")
    parser.add_argument("--world", metavar="NAME", help="the saves/ folder (default: the id)")


def run(args: argparse.Namespace) -> int:
    prefix = f"{PREFIX} {args.action}"
    say: Say = (lambda text: None) if args.json else lambda text: print(text, flush=True)
    save = args.world or args.id
    host = RunHost()
    try:
        if args.action == "snapshot":
            found = world.snapshot(REPO_ROOT, args.id, save, host, say)
        else:
            found = world.restore(REPO_ROOT, args.id, save, host, say)
    except (world.WorldError, record.RecordError, platform.PlatformError, OSError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{prefix}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, **found}, default=str))
    else:
        print(f"{prefix}: ok; {found['treeSha256']} ({found['files']} files)")
    return 0


VERB = Verb(
    name="world",
    help="snapshot a bench world (copy, manifest, tree hash) or restore it in place",
    run=run,
    configure=configure,
    structured=True,
)
