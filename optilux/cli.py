"""The `optilux` command line: argparse with one subcommand per registered verb."""

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from optilux.verbs import Verb, install, launch, milestone, pack, status, test, verify

# The verb registry: every verb module's VERB, in `optilux --help` order.
VERBS: tuple[Verb, ...] = (
    test.VERB,
    verify.VERB,
    status.VERB,
    milestone.VERB,
    pack.VERB,
    install.VERB,
    launch.VERB,
)


class Parser(argparse.ArgumentParser):
    """ArgumentParser that exits 1, not 2, on a usage error, and names the fix."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: {message}; run `{self.prog} --help` for usage\n")


def build_parser(verbs: Sequence[Verb] = VERBS) -> argparse.ArgumentParser:
    parser = Parser(prog="optilux", description="Optilux benchmark harness.")
    subparsers = parser.add_subparsers(dest="verb", metavar="<verb>", title="verbs")
    for verb in verbs:
        sub = subparsers.add_parser(verb.name, help=verb.help, description=verb.help)
        if verb.structured:
            sub.add_argument("--json", action="store_true", help="print JSON instead of text")
        if verb.configure is not None:
            verb.configure(sub)
        sub.set_defaults(run=verb.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verb is None:
        parser.print_usage(sys.stderr)
        print("optilux: no verb given; run `optilux --help` to list the verbs", file=sys.stderr)
        return 1
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
