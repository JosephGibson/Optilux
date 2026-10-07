"""`optilux pack release` and `pack release --check` with a fake gh and git in throwaway repos: a
bare origin stands in for GitHub's git side, FakeGh for its releases. The version is VERSION at the
checked commit. The check passes on a pushed branch whose VERSION is newer than origin/main's and
untagged, and refuses each broken rule; on GitHub's pull_request merge commit it reads the PR head
through --ref HEAD^2, as ci.yml does; the release runs the same rules on main's tip and is created
only when absent, never for a version tagged elsewhere."""

import json
import subprocess
from pathlib import Path

import pytest
from conftest import commit_file, git

from optilux import cli
from optilux.verbs import pack

SUBJECT = "feat: release path"
CHANGELOG = (
    "# Changelog\n\nUser-facing changes.\n\n"
    "## 0.2.0 Game control\nGame control.\n- One.\n- Two.\n\n"
    "## 0.00 Foundation\nFoundation, before VERSION.\n"
)
ENTRY = "Game control.\n- One.\n- Two.\n"
TREE = {
    "shader/shaders/shaders.properties": b"# fixture pack\n",
    "LICENSE": b"MIT\n",
    "CHANGELOG.md": CHANGELOG.encode(),
    "VERSION": b"0.2.0\n",
    ".gitignore": b"build/\n",  # as in the real repo: the zip never dirties the tree
}
URL = "https://github.com/owner/Optilux/releases/tag/{tag}"
BUMP = "set VERSION to 0.3.0 for a milestone or 0.2.1 for a patch (workflow.md#release)"


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
    """`cloned` (main: M0's legacy bootstrap subject, no VERSION) with the fixture pack,
    CHANGELOG and VERSION 0.2.0 committed on m1, pushed."""
    root = cloned
    git(root, "switch", "-q", "-c", "m1")
    for name, content in TREE.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", SUBJECT)
    git(root, "push", "-q", "-u", "origin", "m1")
    monkeypatch.setattr(pack, "REPO_ROOT", root)
    return root


@pytest.fixture
def on_main(pushed: Path) -> Path:
    """After the user's merge: main fast-forwarded to m1's tip, pushed, checked out."""
    git(pushed, "switch", "-q", "main")
    git(pushed, "merge", "-q", "--ff-only", "m1")
    git(pushed, "push", "-q", "origin", "main")
    return pushed


@pytest.fixture
def merged(pushed: Path) -> Path:
    """GitHub's pull_request checkout: a merge of m1 into main, detached, not on origin."""
    git(pushed, "switch", "-q", "--detach", "main")
    git(pushed, "merge", "-q", "--no-ff", "m1", "-m", "Merge 1234567 into 89abcde")
    return pushed


def fake(monkeypatch: pytest.MonkeyPatch, *releases: str, failure: str | None = None) -> FakeGh:
    gh = FakeGh(releases, failure)
    monkeypatch.setattr(pack, "run_gh", gh)
    return gh


def problems(found: list[tuple[str, str]]) -> list[str]:
    return [text for outcome, text in found if outcome == pack.PROBLEM]


def test_changelog_entry(tmp_path: Path, pushed: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    assert pack.changelog_entry(tmp_path, "0.2.0") == pack.Entry(
        "## 0.2.0 Game control", "Game control", ENTRY
    )
    # The legacy heading `## 0.00 Foundation` is history: no version reads it.
    with pytest.raises(pack.PackError, match=r"has no `## 0.3.0 <Name>` section; fix: add `## 0.3"):
        pack.changelog_entry(tmp_path, "0.3.0")
    with pytest.raises(pack.PackError, match=r"has no `## 0.2.1 <Name>` section"):
        pack.changelog_entry(tmp_path, "0.2.1")  # a patch has its own entry
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.2.0 Game control\n\n## 0.00 X\nx\n")
    with pytest.raises(pack.PackError, match=r"`## 0.2.0 Game control` section is empty; fix: add"):
        pack.changelog_entry(tmp_path, "0.2.0")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.2.0\nGame control.\n")
    with pytest.raises(
        pack.PackError,
        match="`## 0.2.0` names no release; fix: head it `## 0.2.0 <Name>` "
        r"\(title `Optilux <version>: <Name>`\)",
    ):
        pack.changelog_entry(tmp_path, "0.2.0")
    (tmp_path / "CHANGELOG.md").unlink()
    with pytest.raises(pack.PackError, match=r"no CHANGELOG.md under"):
        pack.changelog_entry(tmp_path, "0.2.0")
    # At a ref, the committed file counts, not the working tree's.
    (pushed / "CHANGELOG.md").write_bytes(b"# Changelog\n")
    assert pack.changelog_entry(pushed, "0.2.0", "HEAD").text == ENTRY


def test_check_passes_on_a_pushed_branch(
    pushed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    assert cli.main(["pack", "release", "--check"]) == 0
    sha = head(pushed)[:7]
    assert capsys.readouterr().out == (
        f"ok:      subject of HEAD ({sha}): {SUBJECT}\n"
        "ok:      VERSION at HEAD: 0.2.0\n"
        "ok:      VERSION 0.2.0 is newer than origin/main's 0.00.00\n"
        "ok:      CHANGELOG.md `## 0.2.0 Game control`: 3 lines; "
        "title `Optilux 0.2.0: Game control`\n"
        "ok:      no tag v0.2.0 on origin\n"
        "ok:      no GitHub release v0.2.0\n"
        "ok:      tree clean\n"
        f"ok:      HEAD ({sha}) is the tip of origin/m1\n"
        "optilux pack release --check: 8 ok, 0 skipped, 0 problems\n"
    )
    assert gh.calls == [view("v0.2.0")]


def test_check_without_remote_never_calls_gh(
    pushed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch, "v0.2.0")  # a draft release that would refuse, were it looked up
    assert cli.main(["pack", "release", "--check", "--no-remote"]) == 0
    out = capsys.readouterr().out
    assert "skipped: no GitHub release lookup for v0.2.0 (--no-remote)\n" in out
    assert out.endswith("optilux pack release --check: 7 ok, 1 skipped, 0 problems\n")
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
    assert found[0].startswith("subject of HEAD 'Merge 1234567 into 89abcde': not `type(scope)")
    assert "is no branch tip on origin; fix: push it (`git push origin <branch>`)" in found[1]
    assert pack.version_from_git(merged, "HEAD^2") == "0.2.0"


def test_ci_refuses_a_version_released_already_before_the_merge(
    merged: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A PR whose VERSION has a tag on origin already: ci.yml's check fails without gh's login,
    # so the merge never reaches release.yml with it.
    fake(monkeypatch)
    push_tag(merged, "v0.2.0", "main")
    assert cli.main(["pack", "release", "--check", "--no-remote", "--ref", "HEAD^2"]) == 1
    tagged = head(merged, "main")[:7]
    assert (
        f"problem: 0.2.0 is released already: tag v0.2.0 on origin is at {tagged}; fix: {BUMP}\n"
    ) in capsys.readouterr().out


def test_build_takes_the_version_from_ref(
    merged: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["pack", "build", "--ref", "HEAD^2"]) == 0
    wrote = "wrote build/optilux-0.2.0.zip (3 entries, version 0.2.0)"
    assert wrote in capsys.readouterr().out
    assert cli.main(["pack", "build", "--ref", "main"]) == 1  # main predates VERSION
    assert "main has no VERSION; fix: add it" in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        cli.main(["pack", "build", "--ref", "HEAD^2", "--version", "0.2.0"])
    assert caught.value.code == 1 and "not allowed with argument" in capsys.readouterr().err


def test_check_refuses_a_version_tagged_elsewhere_or_a_draft(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch, "v0.2.0")
    assert problems(pack.check(pushed, "HEAD", remote=True)) == [
        "release v0.2.0 exists but origin has no tag v0.2.0 (a draft?); "
        "fix: publish or delete the draft on GitHub, then rerun"
    ]
    push_tag(pushed, "v0.2.0", "main")
    tagged = head(pushed, "main")[:7]
    released = f"0.2.0 is released already: tag v0.2.0 on origin is at {tagged}; fix: {BUMP}"
    assert problems(pack.check(pushed, "HEAD", remote=True)) == [released]
    fake(monkeypatch)  # the tag alone, without a release, refuses alike
    assert problems(pack.check(pushed, "HEAD", remote=True)) == [released]


def test_check_refuses_a_version_not_newer_than_mains(
    on_main: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The next milestone's branch before its first commit sets VERSION: main is at 0.2.0 too.
    fake(monkeypatch)
    git(on_main, "switch", "-q", "-c", "m2")
    commit_file(on_main, "note.txt", b"x\n", "docs: plan the next milestone")
    git(on_main, "push", "-q", "-u", "origin", "m2")
    assert problems(pack.check(on_main, "HEAD", remote=True)) == [
        f"VERSION 0.2.0 is not newer than origin/main's 0.2.0; fix: {BUMP}"
    ]
    changelog = CHANGELOG.replace("## 0.2.0", "## 0.3.0 Perf loop\nPerf.\n\n## 0.2.0")
    (on_main / "CHANGELOG.md").write_bytes(changelog.encode())
    git(on_main, "add", "CHANGELOG.md")
    commit_file(on_main, "VERSION", b"0.3.0\n", "chore: set the next minor version")
    git(on_main, "push", "-q", "origin", "m2")
    assert problems(pack.check(on_main, "HEAD", remote=True)) == []
    found = dict((text, outcome) for outcome, text in pack.check(on_main, "HEAD", remote=True))
    assert found["VERSION 0.3.0 is newer than origin/main's 0.2.0"] == pack.OK


def test_check_refuses_a_bad_subject_a_missing_entry_and_an_unpushed_ref(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch)
    commit_file(pushed, "note.txt", b"x\n", "WIP")
    git(pushed, "push", "-q", "origin", "m1")
    found = problems(pack.check(pushed, "HEAD", remote=True))
    assert len(found) == 1
    assert found[0].startswith("subject of HEAD 'WIP': not `type(scope)!: summary`: start with")
    assert problems(pack.check(pushed, "HEAD~1", remote=True)) == [
        f"HEAD~1 ({head(pushed, 'HEAD~1')[:7]}) is no branch tip on origin; "
        "fix: push it (`git push origin m1`), or check a branch tip instead"
    ]
    commit_file(pushed, "VERSION", b"0.3.0\n", "chore: set the next minor version")
    found = problems(pack.check(pushed, "HEAD", remote=True))
    assert len(found) == 2
    assert found[0].startswith("CHANGELOG.md has no `## 0.3.0 <Name>` section; fix: add `## 0.3")
    assert found[1].startswith(f"HEAD ({head(pushed)[:7]}) is no branch tip on origin")
    commit_file(pushed, "VERSION", b"0.3\n", "fix: short version")
    found = problems(pack.check(pushed, "HEAD", remote=True))
    assert found[0].startswith("VERSION at HEAD: version '0.3' is not of the form MAJOR.MINOR.")


def test_check_refuses_a_dirty_tree_and_an_unreadable_remote(
    pushed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch, failure="HTTP 401: Bad credentials (https://api.github.com/graphql)")
    (pushed / "LICENSE").write_bytes(b"changed\n")
    git(pushed, "remote", "set-url", "origin", (pushed.parent / "gone.git").as_posix())
    found = problems(pack.check(pushed, "HEAD", remote=True))
    assert len(found) == 3  # origin's three reads fail alike and are reported once
    assert found[0].startswith("`git ls-remote origin` failed: ")
    assert found[0].endswith("; fix: check the network and `git remote -v`")
    assert found[1] == (
        "`gh release view v0.2.0` failed: HTTP 401: Bad credentials "
        "(https://api.github.com/graphql); "
        "fix: `gh auth status` here; on a runner, GH_TOKEN from the workflow token"
    )
    assert found[2] == (
        "the tree is not clean (1 changes: M LICENSE); "
        "fix: commit, or discard what the change does not need"
    )
    assert problems(pack.check(pushed, "nope", remote=True))[0].startswith("'nope' names no commit")


def test_release_creates_the_release_when_absent(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    sha = head(on_main)
    assert cli.main(["pack", "release"]) == 0
    assert (on_main / "build/optilux-0.2.0.zip").is_file()
    create = gh.calls[1]
    notes = create[create.index("--notes-file") + 1]
    assert gh.calls == [
        view("v0.2.0"),
        [
            *["release", "create", "v0.2.0", "build/optilux-0.2.0.zip"],
            *["--title", "Optilux 0.2.0: Game control", "--notes-file", notes, "--target", sha],
        ],
    ]
    assert gh.notes == ENTRY
    assert not Path(notes).exists()  # the temporary notes file is gone
    out = capsys.readouterr().out
    assert out.startswith("optilux pack release: wrote build/optilux-0.2.0.zip (3 entries")
    assert out.endswith(
        "optilux pack release: created release v0.2.0 'Optilux 0.2.0: Game control' "
        f"at {sha[:7]} with optilux-0.2.0.zip: "
        f"{URL.format(tag='v0.2.0')}\n"
    )
    assert pack.check(on_main, "HEAD", remote=False)[-2] == (pack.OK, "tree clean")


def test_release_at_head_exists_already(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A rerun of release.yml after it released: the check passes and nothing is created.
    gh = fake(monkeypatch, "v0.2.0")
    push_tag(on_main, "v0.2.0")
    assert cli.main(["pack", "release", "--check"]) == 0
    assert cli.main(["pack", "release"]) == 0
    assert gh.calls == [view("v0.2.0"), view("v0.2.0")]
    assert not (on_main / "build").exists()
    assert capsys.readouterr().out.endswith(
        f"exists at HEAD {head(on_main)[:7]}: {URL.format(tag='v0.2.0')}; nothing to do\n"
    )


@pytest.mark.parametrize("released", [False, True])
def test_release_refuses_a_version_released_elsewhere(
    on_main: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    released: bool,
) -> None:
    # A merge to main that kept a released VERSION: release.yml fails and names the fix.
    gh = fake(monkeypatch, *(["v0.2.0"] if released else []))
    push_tag(on_main, "v0.2.0", "HEAD~1")
    assert cli.main(["pack", "release"]) == 1
    assert gh.calls == [view("v0.2.0")]  # nothing created
    tagged = head(on_main, "HEAD~1")[:7]
    assert capsys.readouterr().err == (
        f"optilux pack release: 0.2.0 is released already: tag v0.2.0 on origin is at {tagged}; "
        f"fix: {BUMP}\n"
    )
    assert not (on_main / "build").exists()


def test_release_refuses_a_release_without_its_tag(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch, "v0.2.0")
    assert cli.main(["pack", "release"]) == 1
    assert gh.calls == [view("v0.2.0")]
    assert "exists but origin has no tag v0.2.0 (a draft?)" in capsys.readouterr().err


def test_release_refuses_a_dirty_tree_and_reports_gh_failures(
    on_main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    (on_main / "LICENSE").write_bytes(b"changed\n")
    assert cli.main(["pack", "release"]) == 1
    assert gh.calls == [view("v0.2.0")]  # looked up, nothing created
    assert "the tree is not clean (1 changes: M LICENSE)" in capsys.readouterr().err
    git(on_main, "checkout", "--", "LICENSE")
    gh = fake(monkeypatch, failure="HTTP 403: Resource not accessible by integration")
    assert cli.main(["pack", "release"]) == 1
    assert capsys.readouterr().err == (
        "optilux pack release: `gh release view v0.2.0` failed: HTTP 403: Resource not "
        "accessible by integration; "
        "fix: `gh auth status` here; on a runner, GH_TOKEN from the workflow token\n"
    )


def test_release_refuses_off_mains_tip(
    pushed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = fake(monkeypatch)
    assert cli.main(["pack", "release"]) == 1  # on m1: the merge would leave this commit behind
    assert gh.calls == [] and not (pushed / "build").exists()
    main = head(pushed, "main")[:7]
    assert capsys.readouterr().err == (
        f"optilux pack release: HEAD {head(pushed)[:7]} is not the tip of origin/main ({main}); "
        "fix: release.yml releases after the user's merge; before it, run "
        "`optilux pack release --check`\n"
    )
    # A merge or squash commit on main fails the subject rule; Rebase and merge keeps the PR's.
    commit_file(pushed, "note.txt", b"x\n", "Merge pull request #1 from owner/m1")
    git(pushed, "push", "-q", "origin", "m1:main")
    git(pushed, "switch", "-q", "--detach", "m1")
    assert cli.main(["pack", "release"]) == 1
    assert (
        "optilux pack release: subject of HEAD 'Merge pull request #1 from owner/m1': not "
        "`type(scope)!: summary`"
    ) in capsys.readouterr().err


def test_check_options_need_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pack", "release", "--no-remote"]) == 1
    assert capsys.readouterr().err == (
        "optilux pack release: --no-remote and --ref belong to --check; "
        "fix: add --check, or drop them\n"
    )
    assert cli.main(["pack", "release", "--ref", "HEAD^2"]) == 1
