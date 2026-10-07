"""`optilux milestone start` in a throwaway repo with a bare origin: refuses a dirty tree and an
existing local or remote branch, cuts from the fetched origin/main with --no-track."""

from pathlib import Path

import pytest
from conftest import commit_file, fresh_repo, git

from optilux import cli
from optilux.verbs import milestone


def branch(root: Path) -> str:
    return git(root, "branch", "--show-current").stdout.strip()


def test_refuses_a_dirty_tree(cloned: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cloned / "extra.txt").write_bytes(b"dirty\n")
    assert milestone.start(cloned, 1) == 1
    err = capsys.readouterr().err
    assert err.startswith("optilux milestone start: the tree is not clean (1 changes: ?? extra.txt")
    assert err.endswith("); fix: commit first\n")
    assert branch(cloned) == "main"


def test_refuses_an_existing_local_branch(cloned: Path, capsys: pytest.CaptureFixture[str]) -> None:
    git(cloned, "branch", "m1")
    assert milestone.start(cloned, 1) == 1
    assert "branch m1 exists locally; fix: `git switch m1`" in capsys.readouterr().err
    assert branch(cloned) == "main"


def test_refuses_an_existing_remote_branch(
    cloned: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(cloned, "push", "-q", "origin", "main:refs/heads/m2")
    assert milestone.start(cloned, 2) == 1
    err = capsys.readouterr().err
    assert "origin has m2 already" in err and "--no-track origin/m2" in err
    assert branch(cloned) == "main"


def test_refuses_without_an_origin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = fresh_repo(tmp_path / "lonely", "main")
    assert milestone.start(root, 1) == 1
    assert "no `origin` remote; fix: `git remote add origin <url>`" in capsys.readouterr().err


def test_cuts_the_fetched_origin_main_with_no_track(
    cloned: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # origin/main moves on after the clone, so a cut from the stale local main would be wrong.
    advanced = commit_file(cloned, "docs/x.md", b"# X\n", "docs: advance")
    git(cloned, "push", "-q", "origin", "main")
    git(cloned, "reset", "-q", "--hard", "HEAD~1")
    assert milestone.start(cloned, 1) == 0
    out = capsys.readouterr().out
    # main carries the legacy bootstrap subject 0.00.00 and no VERSION: the next minor is 0.1.0.
    assert out == (
        f"optilux milestone start: on m1 at {advanced[:7]} (origin/main), no upstream\n"
        "next: `uv run optilux status` prints the next prompt\n"
        "then: the first commit sets VERSION 0.1.0; push it with `git push -u origin m1`\n"
    )
    assert branch(cloned) == "m1"
    assert git(cloned, "rev-parse", "m1").stdout.strip() == advanced
    assert git(cloned, "config", "--get", "branch.m1.remote", check=False).returncode != 0
    assert git(cloned, "rev-parse", "--abbrev-ref", "m1@{upstream}", check=False).returncode != 0
    assert milestone.start(cloned, 1) == 1  # exists locally now
    git(cloned, "push", "-q", "-u", "origin", "m1")
    git(cloned, "switch", "-q", "main")
    git(cloned, "branch", "-q", "-D", "m1")
    assert milestone.start(cloned, 1) == 1 and "origin has m1 already" in capsys.readouterr().err


def test_names_the_version_the_first_commit_sets(
    cloned: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # After a release at 0.2.0 (or its patch 0.2.1), the next milestone ships as 0.3.0.
    commit_file(cloned, "VERSION", b"0.2.1\n", "fix: a patch release")
    git(cloned, "push", "-q", "origin", "main")
    assert milestone.start(cloned, 2) == 0
    assert "then: the first commit sets VERSION 0.3.0; push it" in capsys.readouterr().out


def test_cli_rejects_a_bad_number(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["milestone", "start", "x1"]) == 1
    assert "milestone 'x1' is not a number; fix: give its number" in capsys.readouterr().err
    assert cli.main(["milestone", "start", "123"]) == 1


def test_milestone_needs_a_target(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["milestone"])
    assert caught.value.code == 1 and "optilux milestone --help" in capsys.readouterr().err


def test_verbs_are_registered() -> None:
    names = [verb.name for verb in cli.VERBS]
    assert "status" in names and "milestone" in names
    assert cli.build_parser().parse_args(["status", "--json"]).json is True


def test_a_git_status_that_fails_is_no_clean_tree(tmp_path: Path) -> None:
    """Outside a repository git status exits 128: that is an error, not an empty change list."""
    from optilux import repo

    with pytest.raises(repo.GitError, match="git status"):
        repo.changes(tmp_path)


def test_a_remote_that_does_not_answer_is_refused(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ls-remote past its limit, or a fetch past its own, refuses with the fix: no traceback."""
    import subprocess

    from optilux import repo

    def slow(*args: object, **kwargs: object) -> str:
        raise subprocess.TimeoutExpired("git ls-remote", 30)

    monkeypatch.setattr(repo, "remote_sha", slow)
    assert milestone.start(cloned, 1) == 1
    assert "did not answer" in capsys.readouterr().err
    monkeypatch.setattr(repo, "remote_sha", lambda root, branch: None)
    real = repo.git

    def no_fetch(root: Path, *args: str, timeout: float | None = None):
        if args[:1] == ("fetch",):
            raise subprocess.TimeoutExpired("git fetch", timeout or 0)
        return real(root, *args, timeout=timeout)

    monkeypatch.setattr(repo, "git", no_fetch)
    assert milestone.start(cloned, 1) == 1
    assert "did not answer" in capsys.readouterr().err
