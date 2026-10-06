"""CLI verbs: one module per verb, each exporting VERB; optilux.cli registers them."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Verb:
    """One `optilux` verb. `run` returns 0 or 1; `structured` adds `--json` to its parser."""

    name: str
    help: str
    run: Callable[[argparse.Namespace], int]
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    structured: bool = False
