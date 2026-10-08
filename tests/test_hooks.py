"""optilux.hooks: message and command fixtures, the entry points on JSON stdin, the git hooks end to
end in a throwaway repo, and the Claude Code settings that wire them."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import fresh_repo

from optilux import REPO_ROOT, hooks


@pytest.mark.parametrize(
    "message",
    [
        "feat: git and Claude Code hooks\n",
        "fix(status): read the handoff's last phase",
        "feat(pack)!: read the version from VERSION",
        "perf: x",
        "refactor(launch-gate): split the gate",
        "revert: drop the second reload",
        "# Please enter the commit message.\ndocs: doc check\n# Lines with '#' are ignored.\n",
        "build(deps): bump uv to 0.12.24",  # a dependency's version, though shaped like 0.MM.PP
        "docs: " + "x" * 66,  # 72 characters exactly
    ],
)
def test_commit_msg_accepts(message: str) -> None:
    assert hooks.commit_msg(message, "0.2.0") == []


FORMAT = "not `type(scope)!: summary`"
NAMES = "a subject never names a milestone, phase, version or date"


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("bad", FORMAT),
        ("0.01.13.0: x", FORMAT),  # the form before D33, refused from then on
        ("feature: x", FORMAT),
        ("Fix: capitalised type", FORMAT),
        ("fix(Status): capitalised scope", FORMAT),
        ("fix(): empty scope", FORMAT),
        ("fix:no space", FORMAT),
        ("fix: ", FORMAT),
        ("fix!(status): bang first", FORMAT),
        ("docs: " + "x" * 67, "73 characters"),
        ("docs: plan M2 and its prompts", "names 'M2'"),
        ("feat: finish M2.P03", "names 'M2'"),
        ("chore: release v0.2.0", "names 'v0.2.0'"),
        ("chore: release 0.2.0", "names '0.2.0'"),  # the version in VERSION
        ("docs: the stop of 2026-10-07", "names '2026-10-07'"),
        ("fix: hooks\n\nA body.", "more than one line"),
        ("fix: hooks\n\nPhase: M2.P03", "more than one line"),
        ("fix: hooks\n\nCo-Authored-By: Claude <noreply@anthropic.com>", "attribution"),
        ("feat: generated hooks", "attribution token 'generated'"),
        ("feat: hooks written by Claude Code", "attribution token 'by Claude'"),
        ("feat: Claude's hooks", "attribution token 'Claude'"),
        ("docs: hooks, see anthropic.com", "attribution token 'anthropic'"),
    ],
)
def test_commit_msg_refuses(message: str, reason: str) -> None:
    assert any(reason in problem for problem in hooks.commit_msg(message, "0.2.0"))


def test_commit_msg_without_a_version_file() -> None:
    # Before VERSION existed, and in a repo without one, only the general rules apply.
    assert hooks.commit_msg("chore: release 0.2.0") == []
    assert hooks.commit_msg("chore: release 0.2.0", "0.2.1") == []  # another version passes


HEREDOC = "git commit -m \"$(cat <<'EOF'\n0.00.03: X.\n\nGenerated with Claude Code\nEOF\n)\""


@pytest.mark.parametrize(
    ("command", "branch"),
    [
        ("git push --force origin m0", "m0"),
        ("git push -f", "m0"),
        ("git push -uf origin m0", "m0"),
        ("git push --force-with-lease origin m0", "m0"),
        ("git push --force-with-lease=m0:abc123 origin m0", "m0"),
        ("git push origin +m0:m0", "m0"),
        ("git push --mirror origin", "m0"),
        ("git push --all origin", "m0"),
        ("git commit --no-verify -m '0.00.03: X.'", "m0"),
        ("git commit -nm '0.00.03: X.'", "m0"),
        ("git -c core.hooksPath=/dev/null commit -m '0.00.03: X.'", "m0"),
        ("git push origin main", "m0"),
        ("git push origin HEAD:main", "m0"),
        ("git push origin m0:refs/heads/main", "m0"),
        ("git push origin --delete main", "m0"),
        ("git push", "main"),
        ("git push origin", "main"),
        ("git push -u origin HEAD", "main"),
        ("git commit -m '0.00.03: X.' -m 'Co-Authored-By: Claude <noreply@anthropic.com>'", "m0"),
        ("git commit -m '0.00.03: X.' --trailer 'Co-authored-by: someone'", "m0"),
        (HEREDOC, "m0"),
        ("cd /c/Projects/Optilux && git push --force origin m0", "m0"),
        ("git status; git push -f origin m0", "m0"),
        ("git status\ngit push --force origin m0", "m0"),
        ("bash -c 'git push --force origin m0'", "m0"),
        ("pwsh -NoProfile -Command git push --force origin m0", "m0"),
        ("git -C . push --force origin m0", "m0"),
        ("GIT_TRACE=1 git push --force origin m0 2>&1 | Out-String", "m0"),
        ("C:/Program\\ Files/Git/cmd/git.exe push -f origin m0", "m0"),
    ],
)
def test_git_guard_refuses(command: str, branch: str) -> None:
    assert hooks.git_guard(command, lambda: branch) is not None


@pytest.mark.parametrize(
    ("command", "branch"),
    [
        ("git push -u origin m0", "m0"),
        ("git push -u origin m1", "main"),
        ("git push", "m0"),
        ("git push origin HEAD", "m0"),
        ("git push origin m0 --dry-run", "m0"),
        ("git push -o ci.skip origin m0", "m0"),
        ('GH=gh; "$GH" release view v0.00.06', "m0"),
        ("$GH pr view 1", "main"),
        ("git commit -m '0.00.03: Git and Claude Code hooks.'", "m0"),
        ("git status && git log --oneline -5", "main"),
        ('echo "git push --force"', "main"),
        ("git log --grep=--no-verify", "m0"),
        ("uv run optilux test", "main"),
    ],
)
def test_git_guard_passes(command: str, branch: str) -> None:
    assert hooks.git_guard(command, lambda: branch) is None


def run_hook(name: str, event: dict) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "optilux.hooks", name]
    return subprocess.run(  # noqa: S603 this interpreter and a hook name
        command, input=json.dumps(event), capture_output=True, text=True
    )


def bash_event(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def test_git_guard_entry_point_blocks_with_exit_2() -> None:
    result = run_hook("git_guard", bash_event("git push --force origin m0", REPO_ROOT))
    assert result.returncode == 2
    assert result.stderr.startswith("optilux git guard: `git push --force`")


def test_git_guard_entry_point_passes_with_exit_0() -> None:
    result = run_hook("git_guard", bash_event("git push -u origin m0", REPO_ROOT))
    assert (result.returncode, result.stderr) == (0, "")


def test_git_guard_is_inert_outside_the_repo(tmp_path: Path) -> None:
    assert run_hook("git_guard", bash_event("git push --force", tmp_path)).returncode == 0
    # A command that names the repo is judged wherever the session stands.
    drive, rest = REPO_ROOT.as_posix().split(":", 1) if REPO_ROOT.drive else ("", "")
    for path in filter(None, (REPO_ROOT.as_posix(), drive and f"/{drive.lower()}{rest}")):
        event = bash_event(f"cd {path} && git push --force", tmp_path)
        assert run_hook("git_guard", event).returncode == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Git Bash paths exist on Windows only")
def test_git_bash_paths_are_inside_the_repo() -> None:
    drive, rest = REPO_ROOT.as_posix().split(":", 1)
    assert hooks.inside(f"/{drive.lower()}{rest}/docs", REPO_ROOT)
    assert not hooks.inside(f"/{drive.lower()}/", REPO_ROOT)


def test_post_edit_reports_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"\xef\xbb\xbf# Fixture\n")
    (tmp_path / "bad.py").write_bytes(b"import os\n")
    monkeypatch.setattr(hooks, "REPO_ROOT", tmp_path)
    for name, finding in (("AGENTS.md", "AGENTS.md: bom: "), ("bad.py", "F401")):
        event = {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / name)}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        assert hooks.main(["post_edit"]) == 0
        output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert output["hookEventName"] == "PostToolUse" and finding in output["additionalContext"]


def test_post_edit_is_inert_outside_the_repo(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_bytes(b"import os\n")
    event = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "bad.py")}}
    result = run_hook("post_edit", event)
    assert (result.returncode, result.stdout) == (0, "")


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # No GIT_* variable leaks in: inside a hook, GIT_INDEX_FILE would point at this repo's index.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    command = ["git", *args]
    return subprocess.run(  # noqa: S603 git and its arguments, no shell
        command, cwd=repo, env=env, capture_output=True, text=True, check=check
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repo whose hooks are this checkout's .githooks (docs/workflow.md#testing)."""
    root = (tmp_path / "repo").resolve()
    assert not root.is_relative_to(REPO_ROOT)
    root.mkdir()
    git(root, "init", "-q", "-b", "m0")
    top = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    assert top == root and top != REPO_ROOT  # proven not this repo before anything is written
    for key, value in (
        ("user.name", "Fixture"),
        ("user.email", "fixture@example.invalid"),
        ("core.autocrlf", "false"),
        ("core.hooksPath", (REPO_ROOT / ".githooks").as_posix()),
    ):
        git(root, "config", "--local", key, value)
    return root


def commit(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    return git(repo, "commit", "--allow-empty", "-m", message, check=False)


def test_commit_msg_hook_end_to_end(repo: Path) -> None:
    for message, reason in (
        ("bad", "commit-msg: refused: not `type(scope)!: summary`"),
        ("0.01.13.0: x", "commit-msg: refused: not `type(scope)!: summary`"),
        ("docs: " + "x" * 67, "commit-msg: refused: 73 characters: cut it to 72"),
        ("fix: x\n\nCo-Authored-By: Claude", "commit-msg: refused: more than one line"),
        ("fix: x\n\nCo-Authored-By: Claude", "attribution token 'Co-Authored-By'"),
    ):
        refused = commit(repo, message)
        assert refused.returncode != 0 and reason in refused.stderr, message
    # The hook reads VERSION from the root of the repository it runs in.
    (repo / "VERSION").write_bytes(b"0.2.0\n")
    refused = commit(repo, "chore: release 0.2.0")
    assert refused.returncode != 0 and "names '0.2.0'" in refused.stderr
    assert commit(repo, "test: good").returncode == 0
    assert git(repo, "log", "--format=%s").stdout.splitlines() == ["test: good"]


def test_pre_commit_hook_end_to_end(repo: Path) -> None:
    for name, bad, good, finding in (
        ("lint.py", b"import os\n", b'print("ok")\n', "pre-commit: ruff check:"),
        ("README.md", b"\xef\xbb\xbf# Readme\n", b"# Readme\n", "README.md: bom: "),
    ):
        (repo / name).write_bytes(bad)
        git(repo, "add", name)
        refused = commit(repo, f"test: add {name}")
        assert refused.returncode != 0 and finding in refused.stderr
        (repo / name).write_bytes(good)
        git(repo, "add", name)
        accepted = commit(repo, f"test: add {name}")
        assert accepted.returncode == 0, accepted.stderr


def test_claude_settings_wire_the_hooks() -> None:
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_bytes())
    pre, post = settings["hooks"]["PreToolUse"][0], settings["hooks"]["PostToolUse"][0]
    assert pre["matcher"] == "Bash|PowerShell"
    assert pre["hooks"][0]["command"].endswith("-m optilux.hooks git_guard")
    assert post["matcher"] == "Edit|Write"
    assert post["hooks"][0]["command"].endswith("-m optilux.hooks post_edit")
    allow = settings["permissions"]["allow"]
    for command in ("uv *", "git commit *", "git push *", "git switch *", "gh run watch *"):
        assert f"Bash({command})" in allow and f"PowerShell({command})" in allow


@pytest.mark.parametrize(
    "command",
    [
        'git commit --no-verif -m "0.01.12: x"',
        "git push --no-veri origin m1",
        "git push --forc origin m1",
        "git push --force-w origin m1",
        "git push --mirr origin",
        "git push --al origin",
        "cmd /c git push --force origin m1",
        'cmd.exe /C git commit --no-verify -m "0.01.12: x"',
    ],
)
def test_git_guard_refuses_abbreviations_and_cmd(command: str) -> None:
    """git takes any unambiguous prefix of a long option, and cmd /c runs git too."""
    assert hooks.git_guard(command, lambda: "m1") is not None


def test_git_guard_reads_commits_untracked_mode_as_no_skip() -> None:
    """-uno is --untracked-files=no: its n is the mode's value, not -n."""
    assert hooks.git_guard('git commit -uno -m "0.01.12: x"', lambda: "m1") is None
    assert hooks.git_guard("git push --follow-tags origin m1", lambda: "m1") is None


def test_git_guard_blocks_when_it_cannot_read_the_event() -> None:
    """A guard that cannot read its input fails closed: an unread command could be a force push."""
    command = [sys.executable, "-m", "optilux.hooks", "git_guard"]
    found = subprocess.run(  # noqa: S603 this interpreter and a hook name
        command, input="{not json", capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert found.returncode == 2 and "cannot read" in found.stderr


def stage(root: Path, name: str, content: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(content.encode())
    git(root, "add", name)


def handoff(phase: str | None) -> str:
    line = f"Last phase: {phase}\n" if phase else ""
    return f"# Handoff\nStatus: fixture.\n\n## Outcome\n{line}- Done.\n"


def test_the_handoff_line_advances_one_phase_of_the_branch(tmp_path: Path) -> None:
    root = fresh_repo(tmp_path / "repo", "m1")
    stage(root, "docs/handoff.md", handoff(None))
    git(root, "commit", "-q", "-m", "docs: start")
    stage(root, "docs/handoff.md", handoff("0.01.13"))  # M1's own form, from no line at all
    assert hooks.handoff_findings(root) == []
    git(root, "commit", "-q", "-m", "docs: hand off")
    git(root, "switch", "-q", "-c", "m2")
    where = "docs/handoff.md's `Last phase:`"
    for phase, finding in (
        ("M2.P01", f"{where} M2.P01 does not follow 0.01.13; fix: write M2.P00"),
        ("M3.P00", f"{where} M3.P00 is no phase of m2; fix: name a phase of M2"),
        ("M2.P1", f"{where} M2.P1 names no phase; fix: write M<N>.P<PP>"),
        (None, f"{where} line is gone; fix: keep it"),
    ):
        stage(root, "docs/handoff.md", handoff(phase))
        found = hooks.handoff_findings(root)
        assert len(found) == 1 and found[0].startswith(finding), (phase, found)
    stage(root, "docs/handoff.md", handoff("M2.P00"))
    assert hooks.handoff_findings(root) == []
    git(root, "commit", "-q", "-m", "docs: plan")
    stage(root, "docs/handoff.md", handoff("M2.P02"))  # P01 skipped
    assert hooks.handoff_findings(root)[0].endswith("does not follow M2.P00; fix: write M2.P01")
    stage(root, "docs/handoff.md", handoff("M2.P00") + "More.\n")  # the line unchanged
    assert hooks.handoff_findings(root) == []


def test_version_is_newer_than_origin_mains_with_its_entry(cloned: Path) -> None:
    # cloned: main holds the legacy bootstrap subject 0.00.00 and no VERSION, pushed.
    git(cloned, "switch", "-q", "-c", "m2")
    assert hooks.version_findings(cloned) == [
        "no VERSION staged; fix: add it with the release version"
    ]
    stage(cloned, "VERSION", "0.0.0\n")
    found = hooks.version_findings(cloned)
    assert found[0].startswith("VERSION 0.0.0 is not newer than origin/main's 0.00.00; fix: set")
    stage(cloned, "VERSION", "0.3.0\n")
    assert hooks.version_findings(cloned)[0].startswith("no CHANGELOG.md under")
    stage(cloned, "CHANGELOG.md", "# Changelog\n\n## 0.2.0 Old\nOld.\n")
    assert "has no `## 0.3.0 <Name>` section" in hooks.version_findings(cloned)[0]
    stage(cloned, "CHANGELOG.md", "# Changelog\n\n## 0.3.0 Perf loop\nPerf.\n")
    assert hooks.version_findings(cloned) == []
    (cloned / "VERSION").write_bytes(b"0.0.1\n")  # unstaged: the index is what commits
    assert hooks.version_findings(cloned) == []
    git(cloned, "commit", "-q", "-m", "docs: plan")
    git(cloned, "push", "-q", "origin", "m2:main")  # merged: main carries 0.3.0 now
    git(cloned, "fetch", "-q", "origin")
    git(cloned, "checkout", "-q", "--", "VERSION")
    assert hooks.version_findings(cloned) == [
        "VERSION 0.3.0 is not newer than origin/main's 0.3.0; fix: set VERSION to 0.4.0 for a "
        "milestone or 0.3.1 for a patch (workflow.md#release)"
    ]


def test_version_check_waits_for_an_origin(tmp_path: Path) -> None:
    root = fresh_repo(tmp_path / "lonely", "m2")
    assert hooks.version_findings(root) == []  # nothing to compare with


def test_pre_commit_refuses_a_first_commit_without_its_version(repo: Path, tmp_path: Path) -> None:
    # End to end through .githooks: origin/main at 0.2.0, a new branch's commit is refused until
    # VERSION moves past it with its CHANGELOG entry.
    git(tmp_path, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(repo, "remote", "add", "origin", (tmp_path / "origin.git").as_posix())
    stage(repo, "VERSION", "0.2.0\n")
    stage(repo, "CHANGELOG.md", "# Changelog\n\n## 0.2.0 Game control\nGame control.\n")
    assert commit(repo, "docs: release").returncode == 0
    git(repo, "push", "-q", "origin", "m0:main")
    git(repo, "fetch", "-q", "origin")
    stage(repo, "notes.md", "# Notes\nStatus: fixture.\n")
    refused = commit(repo, "docs: plan the next milestone")
    assert refused.returncode != 0
    assert "pre-commit: VERSION 0.2.0 is not newer than origin/main's 0.2.0" in refused.stderr
    stage(repo, "VERSION", "0.3.0\n")
    stage(repo, "CHANGELOG.md", "# Changelog\n\n## 0.3.0 Perf loop\nPerf.\n\n## 0.2.0 G\nG.\n")
    accepted = commit(repo, "docs: plan the next milestone")
    assert accepted.returncode == 0, accepted.stderr
