"""`optilux test`: pytest on tests/ with the repo root as rootdir, in parallel unless --serial."""

import argparse
import subprocess
import sys

from optilux import REPO_ROOT
from optilux.verbs import Verb

# pytest's exit codes other than 0 (passed) and 1 (failed), with the fix for each.
PYTEST_EXITS = {
    2: "interrupted: rerun `optilux test`",
    3: "internal error: read the traceback above",
    4: "usage error: check [tool.pytest.ini_options] in pyproject.toml",
    5: "no tests collected: add a test_*.py under tests/",
}
# pytest-xdist, one worker per logical CPU: 361 tests ran in 12.6 s against 39.8 s serially on
# 2026-10-07 (0.01.12, docs/handoff.md); --serial keeps one process, for a test that
# passes only alone and for the coverage report (docs/workflow.md#testing).
PARALLEL = ["-n", "auto"]


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--serial", action="store_true", help="one process, no pytest-xdist")


def command(serial: bool) -> list[str]:
    """pytest in this venv's interpreter on tests/, the repo root as rootdir."""
    tests = [sys.executable, "-m", "pytest", str(REPO_ROOT / "tests"), f"--rootdir={REPO_ROOT}"]
    return tests if serial else [*tests, *PARALLEL]


def run(args: argparse.Namespace) -> int:
    """Run pytest in a fresh interpreter of this venv; pass 0 and 1 through, map the rest to 1."""
    code = subprocess.run(command(args.serial), cwd=REPO_ROOT).returncode  # noqa: S603 argv list
    if code in (0, 1):
        return code
    reason = PYTEST_EXITS.get(code, "unknown exit code: read pytest's output above")
    print(f"optilux test: pytest exited {code}, {reason}", file=sys.stderr)
    return 1


VERB = Verb(
    name="test",
    help="run the test suite (pytest on tests/, in parallel)",
    run=run,
    configure=configure,
)
