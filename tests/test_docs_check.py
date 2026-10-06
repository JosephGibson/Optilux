"""optilux.docs_check: one fixture tree per violation, the slug rule, and the repo's own docs."""

import json
from pathlib import Path

import pytest

from optilux import REPO_ROOT, cli, docs_check
from optilux.verbs import verify

# A tree that passes every rule; each test breaks one thing in it.
CLEAN = {
    "AGENTS.md": "# Fixture\nStatus: clean; see docs/a.md#first-section. Latest stop: docs/a.md.\n",
    "docs/a.md": "# A\nStatus: headings to cite.\n\n## First section\n\n## 2. Second (marks)\n",
    "docs/b.md": "# B\nStatus: cites.\n\nSee a.md#first-section and a.md#2-second-marks.\n",
}


def tree(root: Path, changes: dict[str, str | bytes]) -> Path:
    """CLEAN with `changes` laid over it, written as bytes so no newline is translated."""
    for name, content in {**CLEAN, **changes}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    return root


def rules(root: Path) -> list[tuple[str, str]]:
    return [(v.file, v.rule) for v in docs_check.check_tree(root).violations]


def sized(size: int) -> bytes:
    head = b"# Big\nStatus: padded.\n"
    return head + b"x" * (size - len(head) - 1) + b"\n"


def test_clean_tree_passes(tmp_path: Path) -> None:
    assert rules(tree(tmp_path, {})) == []


@pytest.mark.parametrize(
    ("name", "cap"),
    [
        ("AGENTS.md", 6_144),
        ("docs/big.md", 24_576),
        ("docs/prompts/m9.md", 40_960),
        ("docs/roadmap.md", 40_960),
        ("docs/plans/m9.md", 40_960),
    ],
)
def test_too_large(tmp_path: Path, name: str, cap: int) -> None:
    assert rules(tree(tmp_path, {name: sized(cap)})) == []
    assert rules(tree(tmp_path, {name: sized(cap + 1)})) == [(name, "size")]


def test_sources_are_exempt_but_citable(tmp_path: Path) -> None:
    source = b"\xef\xbb\xbf" + sized(50_000).replace(b"\n", b"\r\n")
    cite = "# C\nStatus: cites a source.\n\nSee sources/pb.md#big.\n"
    assert rules(tree(tmp_path, {"docs/sources/pb.md": source, "docs/c.md": cite})) == []


def test_dangling_cite(tmp_path: Path) -> None:
    cite = "# C\nStatus: cites.\n\nSee a.md#first-sectoin and nope.md#first-section.\n"
    violations = docs_check.check_tree(tree(tmp_path, {"docs/c.md": cite})).violations
    assert [(v.file, v.rule, v.line) for v in violations] == [("docs/c.md", "cite", 4)] * 2
    assert violations[0].fix == "cite a.md#first-section"


def test_cite_resolution_order(tmp_path: Path) -> None:
    # The citing file's directory, then docs/, then the root; a URL's .md#anchor is no cite.
    plan = (
        "# Plan\nStatus: resolves.\n\n"
        "p.md#plan, a.md#first-section, AGENTS.md#fixture, https://example.com/x.md#y.\n"
    )
    assert rules(tree(tmp_path, {"docs/plans/p.md": plan})) == []


def test_fenced_blocks_hold_no_cites_and_no_headings(tmp_path: Path) -> None:
    fenced = "# C\nStatus: fences.\n\n```text\nnope.md#skipped\n## Fenced\n```\nSee c.md#fenced.\n"
    violations = docs_check.check_tree(tree(tmp_path, {"docs/c.md": fenced})).violations
    assert [(v.file, v.rule, v.line) for v in violations] == [("docs/c.md", "cite", 8)]


def test_missing_toc(tmp_path: Path) -> None:
    head = "# Long\nStatus: long.\n"
    toc = "\n## Contents\nBody\n"
    body = "\n## Body\n" + "line\n" * 100
    assert rules(tree(tmp_path, {"docs/long.md": head + toc + body})) == []
    assert rules(tree(tmp_path, {"docs/long.md": head + "line\n" * 98})) == []  # 100 lines
    missing = [("docs/long.md", "toc")]
    assert rules(tree(tmp_path, {"docs/long.md": head + body})) == missing
    assert rules(tree(tmp_path, {"docs/long.md": head + "Preamble.\n" + toc + body})) == missing
    assert rules(tree(tmp_path, {"docs/long.md": "# Long\n" + toc + body})) == missing


def test_crlf(tmp_path: Path) -> None:
    crlf = CLEAN["docs/a.md"].replace("\n", "\r\n")
    assert rules(tree(tmp_path, {"docs/a.md": crlf})) == [("docs/a.md", "lf")]


def test_bom(tmp_path: Path) -> None:
    bom = b"\xef\xbb\xbf" + CLEAN["docs/a.md"].encode()
    assert rules(tree(tmp_path, {"docs/a.md": bom})) == [("docs/a.md", "bom")]


def test_not_utf8(tmp_path: Path) -> None:
    latin1 = (CLEAN["docs/a.md"] + "Café.\n").encode("latin-1")
    assert rules(tree(tmp_path, {"docs/a.md": latin1})) == [("docs/a.md", "utf8")]


def test_three_sentence_status(tmp_path: Path) -> None:
    three = "# Fixture\nStatus: 0.00.02 done. Next: 0.00.03. Latest stop: docs/handoff.md.\n"
    assert rules(tree(tmp_path, {"AGENTS.md": three})) == [("AGENTS.md", "status-sentences")]


def test_non_ascii_status(tmp_path: Path) -> None:
    arrow = "# Fixture\nStatus: 0.00.01 → 0.00.02.\n"
    assert rules(tree(tmp_path, {"AGENTS.md": arrow})) == [("AGENTS.md", "status-ascii")]


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("mc-26.3 verified", "mc-263-verified"),
        ("8. Open decisions", "8-open-decisions"),
        ("7. Decisions taken (user, 2026-10-05)", "7-decisions-taken-user-2026-10-05"),
        ("0.00.02 `optilux verify docs` and the test", "00002-optilux-verify-docs-and-the-test"),
    ],
)
def test_slug(heading: str, anchor: str) -> None:
    assert docs_check.slug(heading) == anchor


def test_repo_docs_pass() -> None:
    violations = docs_check.check_tree(REPO_ROOT).violations
    assert violations == [], "\n".join(f"{v.file}: {v.rule}: {v.detail}" for v in violations)


def test_verify_docs_json_on_the_repo(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["verify", "docs", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["violations"] == []
    agents = next(entry for entry in report["files"] if entry["file"] == "AGENTS.md")
    assert agents["cap"] == 6_144 and agents["margin"] == 6_144 - agents["size"]


def test_verify_docs_exits_1_and_names_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    crlf = CLEAN["docs/a.md"].replace("\n", "\r\n")
    monkeypatch.setattr(verify, "REPO_ROOT", tree(tmp_path, {"docs/a.md": crlf}))
    assert cli.main(["verify", "docs"]) == 1
    out = capsys.readouterr().out
    assert "docs/a.md: lf: " in out and "fix: convert every CRLF to LF" in out


def test_claude_docs_are_checked_without_a_cap(tmp_path: Path) -> None:
    skill = "---\nname: x\ndescription: fixture\n---\nSee a.md#first-section.\n"
    report = docs_check.check_tree(tree(tmp_path, {".claude/skills/x/SKILL.md": skill}))
    assert report.violations == []
    entry = next(e for e in report.files if e.file == ".claude/skills/x/SKILL.md")
    assert (entry.cap, entry.margin) == (None, None)
    assert rules(tree(tmp_path, {".claude/agents/r.md": sized(100_000)})) == []
    crlf = skill.replace("\n", "\r\n")
    assert rules(tree(tmp_path, {".claude/agents/r.md": crlf})) == [(".claude/agents/r.md", "lf")]
    dangling = skill.replace("a.md#first-section", "a.md#nope")
    assert rules(tree(tmp_path, {".claude/agents/r.md": dangling})) == [
        (".claude/agents/r.md", "cite")
    ]
