"""`optilux test`: pytest on tests/ with the repo root as rootdir."""

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


def run(args: argparse.Namespace) -> int:
    """Run pytest in a fresh interpreter of this venv; pass 0 and 1 through, map the rest to 1."""
    command = [sys.executable, "-m", "pytest", str(REPO_ROOT / "tests"), f"--rootdir={REPO_ROOT}"]
    code = subprocess.run(command, cwd=REPO_ROOT).returncode
    if code in (0, 1):
        return code
    reason = PYTEST_EXITS.get(code, "unknown exit code: read pytest's output above")
    print(f"optilux test: pytest exited {code}, {reason}", file=sys.stderr)
    return 1


VERB = Verb(name="test", help="run the test suite (pytest on tests/)", run=run)
