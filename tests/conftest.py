"""Shared test helpers: git without leaked GIT_* variables, throwaway repos that prove they are
not this checkout before anything is written (docs/workflow.md#testing), and the skip of
Windows-only tests on other systems (docs/plans/m1.md D19)."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from optilux import REPO_ROOT


def pytest_configure(config: pytest.Config) -> None:
    """Every pytest process ignores CTRL_BREAK: test_presentmon sends a real one to a child's
    group, and should the group be gone the console hands it to every process on it, the
    parallel run's other workers included (presentmon.Host.ctrl_break)."""
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the tests marked `windows` off Windows: CI ran Linux until 0.01.03, and the suite
    stays runnable there."""
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="Windows only (docs/plans/m1.md D19)")
    for item in items:
        if "windows" in item.keywords:
            item.add_marker(skip)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # Inside a hook, GIT_INDEX_FILE and GIT_DIR would point at this repo; strip every GIT_*.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    command = ["git", *args]
    return subprocess.run(  # noqa: S603 git and its arguments, no shell
        command, cwd=repo, env=env, capture_output=True, text=True, check=check
    )


def fresh_repo(path: Path, branch: str) -> Path:
    """An empty repo on `branch` at path, outside this checkout; no hooks run in it."""
    root = path.resolve()
    assert not root.is_relative_to(REPO_ROOT)
    root.mkdir()
    git(root, "init", "-q", "-b", branch)
    top = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    assert top == root and top != REPO_ROOT  # proven not this repo before anything is written
    for key, value in (
        ("user.name", "Fixture"),
        ("user.email", "fixture@example.invalid"),
        ("core.autocrlf", "false"),
        ("core.hooksPath", (root.parent / "no-hooks").as_posix()),  # absent dir: no hooks
    ):
        git(root, "config", "--local", key, value)
    return root


def commit_file(root: Path, name: str, content: bytes, message: str) -> str:
    """Write, add and commit one file; the new HEAD sha."""
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(content)
    git(root, "add", name)
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def cloned(tmp_path: Path) -> Path:
    """A repo on main holding the bootstrap commit, pushed to a bare origin beside it."""
    git(tmp_path, "init", "-q", "--bare", "-b", "main", "origin.git")
    root = fresh_repo(tmp_path / "repo", "main")
    commit_file(root, "README.md", b"# Fixture\n", "0.00.00: Repo bootstrap.")
    git(root, "remote", "add", "origin", (tmp_path / "origin.git").as_posix())
    git(root, "push", "-q", "-u", "origin", "main")
    return root
