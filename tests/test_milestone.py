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
    advanced = commit_file(cloned, "docs/x.md", b"# X\n", "0.00.01: Advance.")
    git(cloned, "push", "-q", "origin", "main")
    git(cloned, "reset", "-q", "--hard", "HEAD~1")
    assert milestone.start(cloned, 1) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        f"optilux milestone start: on m1 at {advanced[:7]} (origin/main), no upstream\n"
    )
    assert "next: write docs/plans/m1.md and docs/prompts/m1.md (phase 0.01.00)\n" in out
    assert out.endswith(
        "then: `optilux status`; the first commit pushes with `git push -u origin m1`\n"
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


def test_names_the_stored_prompt_when_it_exists(
    cloned: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prompt = (
        b"# M1\n\n## 0.01.00 First\n```text\nRun 0.01.00.\n```\n\n## Resume\n```text\nR.\n```\n"
    )
    commit_file(cloned, "docs/prompts/m1.md", prompt, "0.00.01: Prompts.")
    git(cloned, "push", "-q", "origin", "main")
    assert milestone.start(cloned, 1) == 0
    assert "next: paste the `## 0.01.00` prompt of docs/prompts/m1.md\n" in capsys.readouterr().out


def test_cli_rejects_a_bad_number(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["milestone", "start", "x1"]) == 1
    assert "milestone 'x1' is not a number; fix: give the MM of 0.MM.PP" in capsys.readouterr().err
    assert cli.main(["milestone", "start", "123"]) == 1


def test_milestone_needs_a_target(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["milestone"])
    assert caught.value.code == 1 and "optilux milestone --help" in capsys.readouterr().err


def test_verbs_are_registered() -> None:
    names = [verb.name for verb in cli.VERBS]
    assert "status" in names and "milestone" in names
    assert cli.build_parser().parse_args(["status", "--json"]).json is True
