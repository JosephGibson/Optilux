"""optilux.hooks: message and command fixtures, the entry points on JSON stdin, the git hooks end to
end in a throwaway repo, and the Claude Code settings that wire them."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from optilux import REPO_ROOT, hooks


@pytest.mark.parametrize(
    "message",
    [
        "0.00.03: Git and Claude Code hooks.\n",
        "0.00.01: Python project and optilux test.",
        "0.12.34: x",
        "# Please enter the commit message.\n0.00.02: Doc check.\n# Lines with '#' are ignored.\n",
        "0.00.05: Regenerated lockfile.",
        "0.00.05: " + "x" * 63,  # 72 characters exactly
    ],
)
def test_commit_msg_accepts(message: str) -> None:
    assert hooks.commit_msg(message) == []


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("bad", "not `0.MM.PP: <summary>`"),
        ("0.0.3: Short version.", "not `0.MM.PP: <summary>`"),
        ("0.00.03:No space.", "not `0.MM.PP: <summary>`"),
        ("0.00.03: ", "not `0.MM.PP: <summary>`"),
        ("0.00.05: " + "x" * 64, "73 characters"),
        ("0.00.03: Hooks.\n\nA body.", "more than one line"),
        ("0.00.03: Hooks.\n\nCo-Authored-By: Claude <noreply@anthropic.com>", "attribution"),
        ("0.00.03: Generated hooks.", "attribution token 'Generated'"),
        ("0.00.03: Hooks written by Claude Code.", "attribution token 'by Claude'"),
        ("0.00.03: Claude's hooks.", "attribution token 'Claude'"),
        ("0.00.03: Hooks, see anthropic.com.", "attribution token 'anthropic'"),
    ],
)
def test_commit_msg_refuses(message: str, reason: str) -> None:
    assert any(reason in problem for problem in hooks.commit_msg(message))


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
    refused = commit(repo, "bad")
    assert refused.returncode != 0 and "commit-msg: refused: not `0.MM.PP" in refused.stderr
    assert commit(repo, "0.00.01: Good.").returncode == 0
    assert git(repo, "log", "--format=%s").stdout.splitlines() == ["0.00.01: Good."]


def test_pre_commit_hook_end_to_end(repo: Path) -> None:
    for name, bad, good, finding in (
        ("lint.py", b"import os\n", b'print("ok")\n', "pre-commit: ruff check:"),
        ("README.md", b"\xef\xbb\xbf# Readme\n", b"# Readme\n", "README.md: bom: "),
    ):
        (repo / name).write_bytes(bad)
        git(repo, "add", name)
        refused = commit(repo, f"0.00.01: Add {name}.")
        assert refused.returncode != 0 and finding in refused.stderr
        (repo / name).write_bytes(good)
        git(repo, "add", name)
        accepted = commit(repo, f"0.00.01: Add {name}.")
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
