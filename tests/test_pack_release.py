"""`optilux pack release` and `pack release --check` with a fake gh and git in throwaway repos: a
bare origin stands in for GitHub's git side, FakeGh for its releases. The check passes on a
pushed phase and refuses each broken rule; on GitHub's pull_request merge commit it reads the PR
head through --ref HEAD^2; the release is created only when absent, never over a tag elsewhere."""

import json
import subprocess
from pathlib import Path

import pytest
from conftest import commit_file, git

from optilux import cli
from optilux.verbs import pack

PHASE = "0.00.06.0: CI, release workflow, optilux-release."
CHANGELOG = (
    "# Changelog\n\nUser-facing changes.\n\n"
    "## 0.00 Foundation\nFoundation.\n- One.\n- Two.\n\n"
    "## 0.01 Game control\nNext.\n"
)
ENTRY = "Foundation.\n- One.\n- Two.\n"
TREE = {
    "shader/shaders/shaders.properties": b"# fixture pack\n",
    "LICENSE": b"MIT\n",
    "CHANGELOG.md": CHANGELOG.encode(),
    ".gitignore": b"build/\n",  # as in the real repo: the zip never dirties the tree
}
URL = "https://github.com/owner/Optilux/releases/tag/{tag}"


class FakeGh:
    """gh as pack.run_gh calls it: releases by tag, every call recorded, the notes file read when
    `release create` runs (it is deleted afterwards). `failure` makes every call fail with it."""

    def __init__(self, releases: tuple[str, ...] = (), failure: str | None = None) -> None:
        self.releases = {tag: URL.format(tag=tag) for tag in releases}
        self.failure = failure
        self.calls: list[list[str]] = []
        self.notes: str | None = None

    def __call__(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        done = subprocess.CompletedProcess
        if self.failure:
            return done(["gh", *args], 1, "", f"{self.failure}\n")
        tag = args[2]
        if args[:2] == ("release", "view"):
            if tag in self.releases:
                shown = json.dumps({"tagName": tag, "url": self.releases[tag]})
                return done(["gh", *args], 0, shown, "")
            return done(["gh", *args], 1, "", "release not found\n")
        assert args[:2] == ("release", "create"), args
        assert (root / args[3]).is_file()  # the asset exists when gh uploads it
        self.notes = Path(args[args.index("--notes-file") + 1]).read_text(encoding="utf-8")
        self.releases[tag] = URL.format(tag=tag)
        return done(["gh", *args], 0, f"{self.releases[tag]}\n", "")


def view(tag: str) -> list[str]:
    return ["release", "view", tag, "--json", "tagName,url"]


def head(root: Path, ref: str = "HEAD") -> str:
    return git(root, "rev-parse", ref).stdout.strip()


def push_tag(root: Path, tag: str, ref: str = "HEAD") -> None:
    git(root, "tag", tag, ref)
    git(root, "push", "-q", "origin", tag)


@pytest.fixture
def pushed(cloned: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`cloned` with the fixture pack and CHANGELOG committed as 0.00.06.0 on m0, pushed."""
    root = cloned
    git(root, "switch", "-q", "-c", "m0")
    for name, content in TREE.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", PHASE)
    git(root, "push", "-q", "-u", "origin", "m0")
    monkeypatch.setattr(pack, "REPO_ROOT", root)
    return root


@pytest.fixture
def on_main(pushed: Path) -> Path:
    """After the user's merge: main fast-forwarded to the 0.00.06.0 commit, pushed, checked out."""
    git(pushed, "switch", "-q", "main")
    git(pushed, "merge", "-q", "--ff-only", "m0")
    git(pushed, "push", "-q", "origin", "main")
    return pushed


@pytest.fixture
def merged(pushed: Path) -> Path:
    """GitHub's pull_request checkout: a merge of m0 into main, detached, not on origin."""
    git(pushed, "switch", "-q", "--detach", "main")
    git(pushed, "merge", "-q", "--no-ff", "m0", "-m", "Merge 1234567 into 89abcde")
    return pushed


def fake(monkeypatch: pytest.MonkeyPatch, *releases: str, failure: str | None = None) -> FakeGh:
    gh = FakeGh(releases, failure)
    monkeypatch.setattr(pack, "run_gh", gh)
    return gh


def problems(found: list[tuple[str, str]]) -> list[str]:
    return [text for outcome, text in found if outcome == pack.PROBLEM]


def test_changelog_entry(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    assert pack.changelog_entry(tmp_path, "0.00.06") == pack.Entry(
        "## 0.00 Foundation", "Foundation", ENTRY
    )
    last = pack.changelog_entry(tmp_path, "0.01.03.2")  # the last section ends at EOF
    assert (last.name, last.text) == ("Game control", "Next.\n")
    with pytest.raises(pack.PackError, match=r"has no `## 0.02 <Name>` section; fix: add `## 0.02"):
        pack.changelog_entry(tmp_path, "0.02.01.0")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.00 Foundation\n\n## 0.01 X\nx\n")
    with pytest.raises(pack.PackError, match=r"`## 0.00 Foundation` section is empty; fix: add"):
        pack.changelog_entry(tmp_path, "0.00.06")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.00\nFoundation.\n")
    with pytest.raises(
        pack.PackError,
        match="`## 0.00` names no milestone; fix: head it `## 0.00 <Name>` "
        r"\(title `Optilux <version>: <Name>`\)",
    ):
        pack.changelog_entry(tmp_path, "0.00.06")
    (tmp_path / "CHANGELOG.md").unlink()
    with pytest.raises(pack.PackError, match=r"no CHANGELOG.md under"):
        pack.changelog_entry(tmp_path, "0.00.06")


def test_check_passes_on_a_pushed_phase(
    pushed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    assert cli.main(["pack", "release", "--check"]) == 0
    sha = head(pushed)[:7]
    assert capsys.readouterr().out == (
        f"ok:      subject of HEAD ({sha}): {PHASE}\n"
        "ok:      CHANGELOG.md `## 0.00 Foundation`: 3 lines\n"
        "ok:      no release and no tag v0.00.06.0 on GitHub\n"
        "ok:      tree clean\n"
        f"ok:      HEAD ({sha}) is the tip of origin/m0\n"
        "optilux pack release --check: 5 ok, 0 skipped, 0 problems\n"
    )
    assert gh.calls == [view("v0.00.06.0")]


def test_check_without_remote_never_calls_gh(
    pushed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch, "v0.00.06.0")  # a release that would refuse, were it looked up
    assert cli.main(["pack", "release", "--check", "--no-remote"]) == 0
    out = capsys.readouterr().out
    assert "skipped: no release and no tag v0.00.06.0 on GitHub (--no-remote)\n" in out
    assert out.endswith("optilux pack release --check: 4 ok, 1 skipped, 0 problems\n")
    assert gh.calls == []


def test_check_reads_the_pr_head_of_a_merge_commit(
    merged: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gh = fake(monkeypatch)
    # ci.yml's command line on a pull_request event.
    assert cli.main(["pack", "release", "--check", "--no-remote", "--ref", "HEAD^2"]) == 0
    assert gh.calls == []
    found = problems(pack.check(merged, "HEAD", remote=False))
    assert len(found) == 2
    assert found[0].startswith("subject of HEAD 'Merge 1234567 into 89abcde': not `0.MM.PP.N: ")
    assert "is no branch tip on origin; fix: push it (`git push origin <branch>`)" in found[1]
    assert pack.version_from_git(merged, "HEAD^2") == "0.00.06.0"
    with pytest.raises(pack.PackError, match="the subject of HEAD 'Merge 1234567 into 89abcde'"):
        pack.version_from_git(merged)


def test_build_takes_the_version_from_ref(
    merged: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["pack", "build", "--ref", "HEAD^2"]) == 0
    wrote = "wrote build/optilux-0.00.06.0.zip (3 entries, version 0.00.06.0)"
    assert wrote in capsys.readouterr().out
    assert cli.main(["pack", "build"]) == 1
    assert "fix: give --version, or --ref a commit that carries one" in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        cli.main(["pack", "build", "--ref", "HEAD^2", "--version", "0.00.06"])
    assert caught.value.code == 1 and "not allowed with argument" in capsys.readouterr().err


def test_check_refuses_an_existing_release_or_tag(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch, "v0.00.06.0")
    url = URL.format(tag="v0.00.06.0")
    assert problems(pack.check(pushed, "HEAD", remote=True)) == [
        f"release v0.00.06.0 exists already ({url}); "
        "fix: commit the next phase, whose version has none"
    ]
    fake(monkeypatch)
    push_tag(pushed, "v0.00.06.0", "main")
    tagged = head(pushed, "main")[:7]
    assert problems(pack.check(pushed, "HEAD", remote=True)) == [
        f"tag v0.00.06.0 exists on origin ({tagged}) without a release; "
        "fix: commit the next phase, whose version has none"
    ]


def test_check_refuses_a_bad_subject_a_missing_entry_and_an_unpushed_ref(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch)
    commit_file(pushed, "note.txt", b"x\n", "WIP")
    git(pushed, "push", "-q", "origin", "m0")
    assert problems(pack.check(pushed, "HEAD", remote=True)) == [
        "subject of HEAD 'WIP': not `0.MM.PP.N: <summary>`: start with the phase and its patch "
        "number, e.g. `0.01.13.0: ...`"
    ]
    assert problems(pack.check(pushed, "HEAD~1", remote=True)) == [
        f"HEAD~1 ({head(pushed, 'HEAD~1')[:7]}) is no branch tip on origin; "
        "fix: push it (`git push origin m0`), or check a branch tip instead"
    ]
    changelog = b"# Changelog\n\n## 0.00 Foundation\nFoundation.\n"
    commit_file(pushed, "CHANGELOG.md", changelog, "0.01.01.0: Next.")
    found = problems(pack.check(pushed, "HEAD", remote=True))
    assert len(found) == 2
    assert found[0].startswith("CHANGELOG.md has no `## 0.01 <Name>` section; fix: add `## 0.01")
    assert found[1].startswith(f"HEAD ({head(pushed)[:7]}) is no branch tip on origin")


def test_check_refuses_a_dirty_tree_and_an_unreadable_remote(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch, failure="HTTP 401: Bad credentials (https://api.github.com/graphql)")
    (pushed / "LICENSE").write_bytes(b"changed\n")
    git(pushed, "remote", "set-url", "origin", (pushed.parent / "gone.git").as_posix())
    found = problems(pack.check(pushed, "HEAD", remote=True))
    assert found[0] == (
        "`gh release view v0.00.06.0` failed: HTTP 401: Bad credentials "
        "(https://api.github.com/graphql); "
        "fix: `gh auth status` here; on a runner, GH_TOKEN from the workflow token"
    )
    assert found[1] == (
        "the tree is not clean (1 changes: M LICENSE); "
        "fix: commit the phase, or discard what it does not need"
    )
    assert found[2].startswith("`git ls-remote origin` failed: ")
    assert found[2].endswith("; fix: check the network and `git remote -v`")
    assert problems(pack.check(pushed, "nope", remote=True))[0].startswith("'nope' names no commit")


def test_release_creates_the_release_when_absent(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    sha = head(on_main)
    assert cli.main(["pack", "release"]) == 0
    assert (on_main / "build/optilux-0.00.06.0.zip").is_file()
    create = gh.calls[1]
    notes = create[create.index("--notes-file") + 1]
    assert gh.calls == [
        view("v0.00.06.0"),
        [
            *["release", "create", "v0.00.06.0", "build/optilux-0.00.06.0.zip"],
            *["--title", "Optilux 0.00.06.0: Foundation", "--notes-file", notes, "--target", sha],
        ],
    ]
    assert gh.notes == ENTRY
    assert not Path(notes).exists()  # the temporary notes file is gone
    out = capsys.readouterr().out
    assert out.startswith("optilux pack release: wrote build/optilux-0.00.06.0.zip (3 entries")
    assert out.endswith(
        "optilux pack release: created release v0.00.06.0 'Optilux 0.00.06.0: Foundation' "
        f"at {sha[:7]} with optilux-0.00.06.0.zip: "
        f"{URL.format(tag='v0.00.06.0')}\n"
    )
    assert pack.check(on_main, "HEAD", remote=False)[-2] == (pack.OK, "tree clean")


def test_release_at_head_exists_already(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch, "v0.00.06.0")
    push_tag(on_main, "v0.00.06.0")
    assert cli.main(["pack", "release"]) == 0
    assert gh.calls == [view("v0.00.06.0")]
    assert capsys.readouterr().out.endswith(
        f"exists at HEAD {head(on_main)[:7]}: {URL.format(tag='v0.00.06.0')}; nothing to do\n"
    )


@pytest.mark.parametrize("released", [False, True])
def test_release_refuses_a_tag_elsewhere(
    on_main: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    released: bool,
) -> None:
    gh = fake(monkeypatch, *(["v0.00.06.0"] if released else []))
    push_tag(on_main, "v0.00.06.0", "HEAD~1")
    assert cli.main(["pack", "release"]) == 1
    assert gh.calls == [view("v0.00.06.0")]  # nothing created
    tagged, sha = head(on_main, "HEAD~1")[:7], head(on_main)[:7]
    assert capsys.readouterr().err == (
        f"optilux pack release: tag v0.00.06.0 on origin is at {tagged}, not HEAD {sha}; "
        "fix: never move a tag: commit the next phase, whose version gets its own release\n"
    )


def test_release_refuses_a_release_without_its_tag(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch, "v0.00.06.0")
    assert cli.main(["pack", "release"]) == 1
    assert gh.calls == [view("v0.00.06.0")]
    assert "exists but origin has no tag v0.00.06.0 (a draft?)" in capsys.readouterr().err


def test_release_refuses_a_dirty_tree_and_reports_gh_failures(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    (on_main / "LICENSE").write_bytes(b"changed\n")
    assert cli.main(["pack", "release"]) == 1
    assert gh.calls == []
    assert "the tree is not clean (1 changes: M LICENSE)" in capsys.readouterr().err
    git(on_main, "checkout", "--", "LICENSE")
    gh = fake(monkeypatch, failure="HTTP 403: Resource not accessible by integration")
    assert cli.main(["pack", "release"]) == 1
    assert capsys.readouterr().err == (
        "optilux pack release: `gh release view v0.00.06.0` failed: HTTP 403: Resource not "
        "accessible by integration; "
        "fix: `gh auth status` here; on a runner, GH_TOKEN from the workflow token\n"
    )


def test_release_refuses_off_mains_tip(
    pushed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    assert cli.main(["pack", "release"]) == 1  # on m0: the merge would leave this commit behind
    assert gh.calls == [] and not (pushed / "build").exists()
    main = head(pushed, "main")[:7]
    assert capsys.readouterr().err == (
        f"optilux pack release: HEAD {head(pushed)[:7]} is not the tip of origin/main ({main}); "
        "fix: release.yml releases after the user's merge; before it, run "
        "`optilux pack release --check`\n"
    )
    commit_file(pushed, "note.txt", b"x\n", "Merge pull request #1 from owner/m0")
    git(pushed, "push", "-q", "origin", "m0:main")
    git(pushed, "switch", "-q", "--detach", "m0")
    assert cli.main(["pack", "release"]) == 1
    assert capsys.readouterr().err.endswith(
        "carries no 0.MM.PP.N prefix; fix: release from main's tip after a Rebase and merge, "
        "which keeps the phase subject\n"
    )


def test_check_options_need_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pack", "release", "--no-remote"]) == 1
    assert capsys.readouterr().err == (
        "optilux pack release: --no-remote and --ref belong to --check; "
        "fix: add --check, or drop them\n"
    )
    assert cli.main(["pack", "release", "--ref", "HEAD^2"]) == 1
