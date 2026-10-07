"""Git facts for the verbs: every call runs git in a given root, captures its output and never
prompts for credentials. Nothing here writes; the verbs that write (milestone) call git themselves.
"""

import os
import re
import subprocess
from pathlib import Path

ORIGIN = "origin"
# main moves only by the user's rebase merge of a PR (docs/workflow.md#git).
MAIN = "main"
# The release version, MAJOR.MINOR.PATCH, in the root file VERSION (docs/workflow.md#release).
VERSION_FILE = "VERSION"
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
# M0's and M1's subjects began with their phase, `0.MM.PP: ` or `0.MM.PP.N: ` (roadmap.md D32);
# no commit carries it from D33 on, and refs from before VERSION existed are read through it.
LEGACY = re.compile(r"(0\.(\d{2})\.(\d{2})(?:\.(?:0|[1-9]\d*))?): ")
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
    # git writes commit messages in UTF-8 (i18n.logOutputEncoding); Windows' locale code page
    # would misread or refuse a non-ASCII subject that the Linux CI reads fine.
    return subprocess.run(  # noqa: S603 argv list, no shell
        command,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
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


def file_at(root: Path, ref: str, path: str) -> str | None:
    """A file's text at a commit present locally; None when the commit or the file is absent."""
    result = git(root, "show", f"{ref}:{path}")
    return result.stdout if result.returncode == 0 else None


def version_at(root: Path, ref: str) -> str | None:
    """The text of VERSION at ref, stripped; None when ref has no VERSION (before 0.2.0)."""
    text = file_at(root, ref, VERSION_FILE)
    return text.strip() if text is not None else None


def released_at(root: Path, ref: str) -> str | None:
    """The version a ref carries: its VERSION, or for a ref from before VERSION existed the
    newest `0.MM.PP.N: ` subject prefix on it (v0.00.06 for M0); None when neither is there."""
    return version_at(root, ref) or newest_version(root, ref)


def version_key(text: str | None) -> tuple[int, int, int] | None:
    """A version as numbers for ordering: 0.2.0 -> (0, 2, 0). A legacy prefix maps its milestone
    to the minor, 0.00.06 -> (0, 0, 6), so v0.00.06 sorts below 0.2.0 (D33). None otherwise."""
    if match := VERSION.fullmatch(text or ""):
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if match := LEGACY.fullmatch(f"{text}: "):
        return (0, int(match.group(2)), int(match.group(3)))
    return None


def next_minor(text: str | None) -> str:
    """The version a milestone after `text` ships as: its minor plus one (0.2.0 -> 0.3.0)."""
    major, minor, _ = version_key(text) or (0, 0, 0)
    return f"{major}.{minor + 1}.0"


def version_of(subject: str) -> str | None:
    """The legacy version prefix of a commit subject (`0.01.12.1: ...` -> `0.01.12.1`,
    `0.00.03: ...` -> `0.00.03`), or None."""
    match = LEGACY.match(subject)
    return match.group(1) if match else None


def phase_of(version: str) -> str:
    """The phase of a version, its patch number dropped (`0.01.12.1` -> `0.01.12`)."""
    return ".".join(version.split(".")[:3])


def newest_subject(root: Path, ref: str = "HEAD") -> str | None:
    """The subject of the newest commit on ref that carries a version prefix."""
    log = read(root, "log", "--format=%s", ref)
    if log is None:
        return None
    return next((line for line in log.splitlines() if version_of(line)), None)


def newest_version_run(root: Path, ref: str = "HEAD") -> list[str]:
    """The subjects, newest first, of the commits on ref whose version is of the newest version's
    phase: a phase with side commits (tooling, a prompt fix) or patches has several. Commits
    without a version are skipped; the run ends at the first commit of another phase."""
    log = read(root, "log", "--format=%s", ref)
    run: list[str] = []
    phase = None
    for line in (log or "").splitlines():
        version = version_of(line)
        if version is None:
            continue
        if phase is None:
            phase = phase_of(version)
        elif phase_of(version) != phase:
            break
        run.append(line)
    return run


def newest_version(root: Path, ref: str = "HEAD") -> str | None:
    """The version prefix of the newest commit on ref whose subject carries one."""
    subject = newest_subject(root, ref)
    return version_of(subject) if subject else None


def changes(root: Path) -> list[str]:
    """`git status --porcelain` lines: empty when the tree is clean; GitError when git status
    fails (outside a repository, a safe.directory refusal), which is no clean tree."""
    result = git(root, "status", "--porcelain")
    if result.returncode != 0:
        raise GitError(f"git status failed: {failure(result)}")
    return result.stdout.strip().splitlines()


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


def remote_refs(root: Path, kind: str, *patterns: str, remote: str = ORIGIN) -> dict[str, str]:
    """{ref: sha} of `git ls-remote <kind> <remote> <patterns>` (kind --heads or --tags), read
    live. Raises GitError when the remote cannot be read, TimeoutExpired past the limit."""
    result = git(root, "ls-remote", kind, remote, *patterns, timeout=REMOTE_TIMEOUT)
    if result.returncode:
        raise GitError(f"`git ls-remote {remote}` failed: {failure(result)}")
    pairs = (line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
    return {ref: sha for sha, ref in pairs}


def remote_tag(root: Path, tag: str, remote: str = ORIGIN) -> str | None:
    """The commit a tag on the remote points at, None when the tag is absent. An annotated tag
    is listed as the tag object and, under `^{}`, the commit it peels to; the commit wins."""
    ref = f"refs/tags/{tag}"
    refs = remote_refs(root, "--tags", ref, f"{ref}^{{}}", remote=remote)
    return refs.get(f"{ref}^{{}}") or refs.get(ref)


def remote_branches_at(root: Path, sha: str, remote: str = ORIGIN) -> list[str]:
    """The branches on the remote whose tip is sha, read live with `git ls-remote --heads`."""
    refs = remote_refs(root, "--heads", remote=remote)
    return sorted(ref.removeprefix("refs/heads/") for ref, tip in refs.items() if tip == sha)


def resolve(root: Path, ref: str) -> str | None:
    """The commit sha a ref names (HEAD, HEAD^2, a branch, a sha), None when it names none."""
    return read(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")


def message(root: Path, sha: str) -> str | None:
    """The full message of a commit present locally, None when the object was never fetched."""
    return read(root, "log", "-1", "--format=%B", sha, "--")


def subject(root: Path, sha: str) -> str | None:
    """The subject of a commit present locally, None when the object was never fetched."""
    return read(root, "log", "-1", "--format=%s", sha, "--")
