"""`optilux launch <world> [--tier bench] [--no-token] [--set key=value] [--quit-after S] [--json]`
(docs/platform.md#install-and-launch).

Starts the platform's game in a world through optilux.launch: the gate, the hashes, game/mods/,
the pre-launch files, the started command line's check and the join. Without --quit-after the
game keeps running when the verb exits; with it the verb stays that long in the world, quits by
WM_CLOSE (until the mod's `quit`, 0.01.05) and reads the option files back. Exit 0 when every
check passed, with --quit-after also an exit code 0 and the files read back as written.
"""

import argparse
import json
import math
import sys

from optilux import REPO_ROOT, launch, platform
from optilux.verbs import Verb

PREFIX = "optilux launch"
DEFAULT_TIER = "bench"


def parse_sets(items: list[str]) -> dict[str, str]:
    """--set key=value items as a dict; a malformed or repeated key is refused."""
    found: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise launch.LaunchError(f"--set {item!r} is not key=value; fix: --set <key>=<value>")
        if key in found:
            raise launch.LaunchError(f"--set {key} is given twice; fix: give it once")
        found[key] = value
    return found


def held(quit_facts: dict, back: dict) -> list[str]:
    """The report's lines after the quit."""
    options = back["options"]
    excepted = ", ".join(
        f"{k} {d['written']} -> {d['read']}" for k, d in options["excepted"].items()
    )
    moved = "; ".join(f"{k}: {d['written']} -> {d['read']}" for k, d in options["moved"].items())
    iris = back["iris"]
    sodium = back["sodium"]
    kept = options["keys"] - len(options["moved"]) - len(options["excepted"])
    return [
        f"quit: WM_CLOSE to {quit_facts['windows']} window, exit code {quit_facts['exitCode']} in "
        f"{quit_facts['seconds']:.1f} s",
        f"read back: options.txt {kept} of {options['keys']} keys as written"
        + (f"; moved: {moved}" if moved else "")
        + f"; F3 excepted: {excepted or 'none moved'}",
        f"read back: iris.properties {iris['keys'] - len(iris['moved'])} of {iris['keys']} keys as "
        f"written; sodium-options.json flags "
        + ("held" if not sodium["flagsMoved"] else f"moved {sodium['flagsMoved']}")
        + (", text unchanged" if sodium["sameText"] else ", text rewritten by Sodium"),
    ]


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("world", help="the world folder under runtime/<platform>/game/saves/")
    parser.add_argument(
        "--tier", default=DEFAULT_TIER, help=f"the mod tier to launch (default {DEFAULT_TIER})"
    )
    parser.add_argument(
        "--no-token", action="store_true", help="start without -Doptilux.token (A1: the mod inert)"
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override one options.txt key the suite writes, for this launch; recorded",
    )
    parser.add_argument(
        "--quit-after",
        type=float,
        metavar="SECONDS",
        help="stay this long in the world, then quit by WM_CLOSE and read the files back",
    )


def run(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    say = (lambda text: None) if args.json else lambda text: print(text, flush=True)
    host = launch.Host()
    try:
        if args.quit_after is not None and not (
            math.isfinite(args.quit_after) and args.quit_after >= 0
        ):
            raise launch.LaunchError(
                f"--quit-after {args.quit_after:g} is not a finite count of seconds, 0 or more; "
                "fix: give one"
            )
        overrides = parse_sets(args.set)
        launched = launch.launch(
            root, args.world, args.tier, not args.no_token, overrides, say, host
        )
        result = launched.facts
        ok = True
        if args.quit_after is None:
            say(f"running: pid {launched.pid}; close its window to quit")
        else:
            try:
                launch.hold(launched.process, host, args.quit_after)
                say(f"held {args.quit_after:g} s in the world")
                result["quit"] = launch.quit_game(launched.process, host)
            except BaseException as error:
                how = launch.end(launched.process, host)
                if isinstance(error, launch.LaunchError):
                    raise launch.LaunchError(f"{error}; the game was ended ({how})") from None
                raise
            try:
                result["readBack"] = launch.read_back(launched.game, launched.prelaunch)
            except (OSError, ValueError) as error:
                raise launch.LaunchError(f"the files cannot be read back: {error}") from None
            result["timings"]["holdSeconds"] = args.quit_after
            result["timings"]["quitSeconds"] = round(result["quit"]["seconds"], 2)
            for line in held(result["quit"], result["readBack"]):
                say(line)
            ok = result["quit"]["exitCode"] == 0 and result["readBack"]["ok"]
    except (launch.LaunchError, platform.PlatformError) as error:
        if args.json:
            print(json.dumps({"ok": False, "problem": str(error)}))
        else:
            print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": ok, **result, "problem": None}))
        return 0 if ok else 1
    verdict = (
        f"pid {result['pid']}, joined in {result['join']['seconds']:.1f} s, log {result['log']}"
    )
    if ok:
        print(f"{PREFIX}: ok; {verdict}")
        return 0
    reason = (
        f"exit code {result['quit']['exitCode']}"
        if result["quit"]["exitCode"] != 0
        else "the files did not read back as written"
    )
    print(f"{PREFIX}: failed: {reason}; {verdict}", file=sys.stderr)
    return 1


VERB = Verb(
    name="launch",
    help="start the game hash-checked in a world and check the started command line",
    run=run,
    configure=configure,
    structured=True,
)
