"""Git facts for the verbs: every call runs git in a given root, captures its output and never
prompts for credentials. Nothing here writes; the verbs that write (milestone) call git themselves.
"""

import os
import re
import subprocess
from pathlib import Path

ORIGIN = "origin"
# main moves only by the user's rebase merge of a milestone PR (docs/workflow.md#git).
MAIN = "main"
# docs/workflow.md#git: every commit's subject starts with its phase, `0.MM.PP: `.
VERSION = re.compile(r"(0\.(\d{2})\.(\d{2})): ")
# Milestone branches are m0, m1, ... (docs/workflow.md#git), the number unpadded.
BRANCH = re.compile(r"m(\d{1,2})")
# A remote call that needs credentials fails at once instead of hanging on a prompt.
NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0"}
# `optilux status` is injected into a skill: a dead network must fail it in bounded time, and a
# GitHub round trip on this machine takes under 2 s.
REMOTE_TIMEOUT = 60


class GitError(RuntimeError):
    """A git call that failed; the message carries git's own reason."""


def git(root: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Run git in root; the caller judges the exit code. Raises TimeoutExpired past `timeout`."""
    env = {**os.environ, **NO_PROMPT}
    command = ["git", *args]
    return subprocess.run(
        command, cwd=root, env=env, capture_output=True, text=True, timeout=timeout
    )


def read(root: Path, *args: str) -> str | None:
    """Stripped stdout of a git call, None when it exits non-zero."""
    result = git(root, *args)
    return result.stdout.strip() if result.returncode == 0 else None


def failure(result: subprocess.CompletedProcess[str]) -> str:
    """git's reason for a failed call, one line."""
    text = (result.stderr.strip() or result.stdout.strip()).splitlines()
    return text[0] if text else f"git exited {result.returncode}"


def is_repo(root: Path) -> bool:
    return read(root, "rev-parse", "--is-inside-work-tree") == "true"


def current_branch(root: Path) -> str | None:
    """The checked-out branch, None when HEAD is detached."""
    return read(root, "symbolic-ref", "--short", "-q", "HEAD")


def milestone_of(branch: str | None) -> int | None:
    """The milestone number of a branch name (m0 -> 0); None for any other name."""
    match = BRANCH.fullmatch(branch or "")
    return int(match.group(1)) if match else None


def branch_name(milestone: int) -> str:
    return f"m{milestone}"


def head(root: Path) -> str | None:
    return read(root, "rev-parse", "--verify", "-q", "HEAD")


def version_of(subject: str) -> str | None:
    """The version prefix of a commit subject (`0.00.03: ...` -> `0.00.03`), or None."""
    match = VERSION.match(subject)
    return match.group(1) if match else None


def newest_version(root: Path, ref: str = "HEAD") -> str | None:
    """The version prefix of the newest commit on ref whose subject carries one."""
    log = read(root, "log", "--format=%s", ref)
    if log is None:
        return None
    return next(filter(None, map(version_of, log.splitlines())), None)


def changes(root: Path) -> list[str]:
    """`git status --porcelain` lines: empty when the tree is clean."""
    return (read(root, "status", "--porcelain") or "").splitlines()


def hooks_path(root: Path) -> str | None:
    return read(root, "config", "--local", "--get", "core.hooksPath")


def has_remote(root: Path, remote: str = ORIGIN) -> bool:
    return read(root, "remote", "get-url", remote) is not None


def local_branch_exists(root: Path, branch: str) -> bool:
    return read(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}") is not None


def remote_sha(root: Path, branch: str, remote: str = ORIGIN) -> str | None:
    """The sha of a branch on the remote, read live with `git ls-remote`; None when the branch
    is absent. Raises GitError when the remote cannot be read, TimeoutExpired past the limit."""
    args = ("ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}")
    result = git(root, *args, timeout=REMOTE_TIMEOUT)
    if result.returncode == 0:
        return result.stdout.split()[0]
    if result.returncode == 2:  # --exit-code: the remote answered and has no such ref
        return None
    raise GitError(f"`git ls-remote {remote}` failed: {failure(result)}")


def subject(root: Path, sha: str) -> str | None:
    """The subject of a commit present locally, None when the object was never fetched."""
    return read(root, "log", "-1", "--format=%s", sha, "--")
