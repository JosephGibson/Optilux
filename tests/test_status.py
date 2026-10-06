"""optilux.prompts on a fixture file and on docs/prompts/m0.md; `optilux status` in a throwaway
repo with a bare origin, and on this repo with the remote faked."""

import json
from pathlib import Path

import pytest
from conftest import commit_file, git

from optilux import REPO_ROOT, cli, prompts, repo
from optilux.verbs import status

FIXTURE = """# M7 prompts
Status: fixture.

## Rules
- One fenced block per phase.

## 0.07.00 First
```text
Run 0.07.00.
Second line: `code` and ## not a heading.
```

## 0.07.01 Second
```text
Run 0.07.01.
```

## Resume
```text
Resume M7.
```
"""


def test_parse_fixture() -> None:
    prompt_set = prompts.parse(FIXTURE, 7, "m7.md")
    assert [p.version for p in prompt_set.phases] == ["0.07.00", "0.07.01"]
    assert [p.title for p in prompt_set.phases] == ["First", "Second"]
    first, second = prompt_set.phases
    assert first.text == "Run 0.07.00.\nSecond line: `code` and ## not a heading.\n"
    assert (second.text, second.line) == ("Run 0.07.01.\n", 13)
    assert prompt_set.resume == "Resume M7.\n"
    assert prompt_set.phase("0.07.01") is second and prompt_set.phase("0.07.09") is None


def without_resume() -> str:
    return FIXTURE[: FIXTURE.index("## Resume")]


def resume_first() -> str:
    body = FIXTURE[: FIXTURE.index("## 0.07.01")]
    return (
        body
        + FIXTURE[FIXTURE.index("## Resume") :]
        + FIXTURE[len(body) : FIXTURE.index("## Resume")]
    )


@pytest.mark.parametrize(
    ("text", "detail", "fix"),
    [
        (without_resume(), "no `## Resume` section", "add `## Resume` with one fenced block"),
        (resume_first(), "`## 0.07.01 Second` follows `## Resume`", "move `## Resume` to the end"),
        (
            FIXTURE.replace("Run 0.07.00.", "x\n```\n```text\ny"),
            "holds 2 fenced blocks",
            "keep exactly one",
        ),
        (
            FIXTURE.replace("```text\nRun 0.07.01.\n```\n", ""),
            "holds 0 fenced blocks",
            "keep exactly one",
        ),
        (FIXTURE.replace("Run 0.07.01.", " "), "`## 0.07.01 Second` has an empty block", "write"),
        (FIXTURE.replace("## Resume", "## Notes\n\n## Resume"), "neither a phase nor", "head it"),
        (
            FIXTURE.replace("0.07.01 Second", "0.08.01 Second"),
            "`## 0.08.01` is not a phase of milestone 7",
            "number it 0.07.01 or move it to docs/prompts/m8.md",
        ),
        (
            FIXTURE.replace("0.07.01 Second", "0.07.00 Second"),
            "`## 0.07.00` after `## 0.07.00`",
            "order the phases ascending, each version once",
        ),
        (
            FIXTURE.replace("0.07.01 Second", "0.06.99 Second"),
            "`## 0.06.99` is not a phase of milestone 7",
            "number it 0.07.99 or move it to docs/prompts/m6.md",
        ),
        (
            FIXTURE.replace("## 0.07.01 Second", "## 0.07.01"),
            "`## 0.07.01` has no title",
            "write `## 0.07.01 <title>`",
        ),
        (FIXTURE.replace("Resume M7.\n```\n", "Resume M7.\n"), "never closed", "close it with ```"),
        (
            FIXTURE[: FIXTURE.index("## 0.07.00")],
            "no phase heading",
            "add one `## 0.07.PP <title>`",
        ),
    ],
)
def test_parse_faults_name_the_fix(text: str, detail: str, fix: str) -> None:
    with pytest.raises(prompts.PromptError) as caught:
        prompts.parse(text, 7, "m7.md")
    message = str(caught.value)
    assert message.startswith("m7.md") and detail in message and f"fix: {fix}" in message


def test_parse_repo_prompts() -> None:
    prompt_set = prompts.load(REPO_ROOT, 0)
    assert [p.version for p in prompt_set.phases] == [f"0.00.0{n}" for n in range(7)]
    assert all(p.title and p.text.endswith("\n") for p in prompt_set.phases)
    assert prompt_set.phases[4].text.startswith("Run M0 phase 0.00.04 on branch m0")
    assert prompt_set.resume.startswith("Resume M0 in C:\\Projects\\Optilux.")


def test_load_names_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(prompts.PromptError, match=r"docs/prompts/m3\.md: no such file; fix: "):
        prompts.load(tmp_path, 3)


@pytest.mark.parametrize(
    ("newest", "milestone", "expected"),
    [
        (None, 0, "0.00.00"),
        ("0.00.03", 0, "0.00.04"),
        ("0.00.06", 1, "0.01.00"),
        ("0.01.09", 1, "0.01.10"),
    ],
)
def test_next_phase(newest: str | None, milestone: int, expected: str) -> None:
    assert prompts.next_phase(newest, milestone) == expected


def milestone_repo(cloned: Path) -> Path:
    """`cloned` on a pushed m7 with one phase committed, Status lines and the fixture prompts."""
    git(cloned, "switch", "-q", "-c", "m7", "--no-track", "origin/main")
    (cloned / "docs" / "prompts").mkdir(parents=True)
    (cloned / "docs" / "prompts" / "m7.md").write_bytes(FIXTURE.encode())
    (cloned / "docs" / "roadmap.md").write_bytes(b"# Roadmap\nStatus: roadmap M7.\n")
    git(cloned, "add", "docs")
    commit_file(cloned, "AGENTS.md", b"# Fixture\nStatus: agents M7.\n", "0.07.00: First.")
    git(cloned, "push", "-q", "-u", "origin", "m7")
    return cloned


def test_status_in_a_throwaway_repo(cloned: Path) -> None:
    root = milestone_repo(cloned)
    facts = status.collect(root)
    assert (facts["branch"], facts["pushed"], facts["clean"]) == ("m7", True, True)
    assert (facts["version_local"], facts["version_main"]) == ("0.07.00", "0.00.00")
    assert (facts["next_phase"], facts["next_title"]) == ("0.07.01", "Second")
    assert (facts["prompt_file"], facts["prompt"]) == ("docs/prompts/m7.md", "Run 0.07.01.\n")
    assert facts["status_lines"] == {
        "AGENTS.md": "Status: agents M7.",
        "docs/roadmap.md": "Status: roadmap M7.",
    }
    assert facts["hooks_set"] is False
    assert facts["problems"] == [
        "hooks path not set; fix: `git config --local core.hooksPath .githooks`"
    ]
    git(root, "config", "--local", "core.hooksPath", ".githooks")
    assert status.collect(root)["problems"] == [] and status.collect(root)["hooks_set"]


def test_status_text_prints_the_prompt_verbatim(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = milestone_repo(cloned)
    monkeypatch.setattr(status, "REPO_ROOT", root)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        "branch:     m7, pushed\nversion:    0.07.00 local, 0.00.00 on origin/main\n"
    )
    assert "next phase: 0.07.01 Second (docs/prompts/m7.md)\n" in out
    assert "AGENTS.md: Status: agents M7.\n" in out and "tree:       clean\n" in out
    assert out.endswith("\nnext prompt, 0.07.01 Second, verbatim:\nRun 0.07.01.\n")


def test_status_exits_0_with_problems(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = milestone_repo(cloned)
    (root / "extra.txt").write_bytes(b"dirty\n")
    commit_file(root, "second.txt", b"x\n", "0.07.01: Second.")  # not pushed; no 0.07.02 prompt
    facts = status.collect(root)
    assert (facts["pushed"], facts["clean"], facts["prompt"]) == (False, False, None)
    assert facts["changes"] == ["?? extra.txt"] and facts["next_phase"] == "0.07.02"
    assert "HEAD is not on origin/m7; fix: `git push -u origin m7`" in facts["problems"]
    assert any(
        p.startswith("no stored prompt for 0.07.02; fix: add `## 0.07.02 <title>`")
        and p.endswith("`optilux milestone start 8`")
        for p in facts["problems"]
    )
    (root / "docs" / "prompts" / "m7.md").write_bytes(without_resume().encode())
    monkeypatch.setattr(status, "REPO_ROOT", root)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "tree:       2 changes: M docs/prompts/m7.md; ?? extra.txt\n" in out
    assert "problem:    docs/prompts/m7.md: no `## Resume` section; fix: " in out
    assert "next prompt" not in out


def test_status_before_the_first_phase(cloned: Path) -> None:
    git(cloned, "switch", "-q", "-c", "m7", "--no-track", "origin/main")
    facts = status.collect(cloned)
    assert (facts["version_local"], facts["next_phase"]) == ("0.00.00", "0.07.00")
    assert facts["pushed"] is False and facts["prompt"] is None
    assert any("docs/prompts/m7.md: no such file; fix: " in p for p in facts["problems"])


def test_status_outside_a_repo(tmp_path: Path) -> None:
    facts = status.collect(tmp_path)
    assert facts["problems"] == [
        f"{tmp_path} is not a git repository; fix: run inside the Optilux checkout"
    ]


def test_status_json_on_this_repo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The remote is faked: no network in a test, and the answer must not depend on GitHub.
    head = repo.head(REPO_ROOT)
    monkeypatch.setattr(repo, "remote_sha", lambda root, branch, remote=repo.ORIGIN: head)
    assert cli.main(["status", "--json"]) == 0
    facts = json.loads(capsys.readouterr().out)
    assert facts["branch"] == repo.current_branch(REPO_ROOT) and facts["head"] == head
    assert facts["version_local"] == facts["version_main"] == repo.newest_version(REPO_ROOT)
    assert facts["next_phase"] == prompts.next_phase(facts["version_local"], facts["milestone"])
    prompt = prompts.load(REPO_ROOT, facts["milestone"]).phase(facts["next_phase"])
    assert facts["prompt"] == (prompt.text if prompt else None)
    assert facts["status_lines"]["AGENTS.md"].startswith("Status: ")
    assert facts["status_lines"]["docs/roadmap.md"].startswith("Status: ")
