"""optilux.prompts on a fixture file and on docs/prompts/m0.md and m1.md; `optilux status` in a
throwaway repo with a bare origin, and on this repo with the remote faked. Phases are M<N>.P<PP>,
or 0.MM.PP in M0's and M1's sets; the last phase done is docs/handoff.md's `Last phase:` line, or
without one the newest `0.MM.PP.N: ` subject; Release or the switch follows from VERSION against
origin/main's (roadmap.md D33)."""

import json
import re
from pathlib import Path

import pytest
from conftest import commit_file, git

from optilux import REPO_ROOT, cli, prompts, repo
from optilux.verbs import milestone, pack, status

FIXTURE = """# M7 prompts
Status: fixture.

## Rules
- One fenced block per phase.

## M7.P01 First
```text
Run M7.P01.
Second line: `code` and ## not a heading.
```

## M7.P02 Second
```text
Run M7.P02.
```

## Resume
```text
Resume M7.
```
"""


def test_parse_fixture() -> None:
    prompt_set = prompts.parse(FIXTURE, 7, "m7.md")
    assert [p.phase for p in prompt_set.phases] == ["M7.P01", "M7.P02"]
    assert [p.key for p in prompt_set.phases] == [(7, 1), (7, 2)]
    assert [p.title for p in prompt_set.phases] == ["First", "Second"]
    first, second = prompt_set.phases
    assert first.text == "Run M7.P01.\nSecond line: `code` and ## not a heading.\n"
    assert (second.text, second.line) == ("Run M7.P02.\n", 13)
    assert prompt_set.resume == "Resume M7.\n"
    assert prompt_set.phase("M7.P02") is second and prompt_set.phase("M7.P09") is None
    assert prompt_set.phase("0.07.02") is second  # the legacy form names the same phase


def test_parse_reads_the_legacy_form() -> None:
    legacy = FIXTURE.replace("## M7.P01", "## 0.07.01").replace("## M7.P02", "## 0.07.02")
    prompt_set = prompts.parse(legacy, 7, "m7.md")
    assert [(p.phase, p.key) for p in prompt_set.phases] == [
        ("0.07.01", (7, 1)),
        ("0.07.02", (7, 2)),
    ]
    assert prompt_set.phase("M7.P01") is prompt_set.phases[0]


@pytest.mark.parametrize(
    ("text", "milestone", "key"),
    [
        ("M2.P01", 2, 1),
        ("M10.P00", 10, 0),
        ("0.01.13", 1, 13),
        ("0.01.13.0", None, None),  # a legacy version, not a phase
        ("M2.P1", None, None),
        ("m2.P01", None, None),
        ("Resume", None, None),
        (None, None, None),
    ],
)
def test_phase_key(text: str | None, milestone: int | None, key: int | None) -> None:
    assert prompts.phase_key(text) == (None if milestone is None else (milestone, key))


def without_resume() -> str:
    return FIXTURE[: FIXTURE.index("## Resume")]


def resume_first() -> str:
    body = FIXTURE[: FIXTURE.index("## M7.P02")]
    return (
        body
        + FIXTURE[FIXTURE.index("## Resume") :]
        + FIXTURE[len(body) : FIXTURE.index("## Resume")]
    )


@pytest.mark.parametrize(
    ("text", "detail", "fix"),
    [
        (without_resume(), "no `## Resume` section", "add `## Resume` with one fenced block"),
        (resume_first(), "`## M7.P02 Second` follows `## Resume`", "move `## Resume` to the end"),
        (
            FIXTURE.replace("Run M7.P01.", "x\n```\n```text\ny"),
            "holds 2 fenced blocks",
            "keep exactly one",
        ),
        (
            FIXTURE.replace("```text\nRun M7.P02.\n```\n", ""),
            "holds 0 fenced blocks",
            "keep exactly one",
        ),
        (FIXTURE.replace("Run M7.P02.", " "), "`## M7.P02 Second` has an empty block", "write"),
        (FIXTURE.replace("## Resume", "## Notes\n\n## Resume"), "neither a phase nor", "head it"),
        (
            FIXTURE.replace("M7.P02 Second", "M8.P02 Second"),
            "`## M8.P02` is not a phase of milestone 7",
            "number it M7.P02 or move it to docs/prompts/m8.md",
        ),
        (
            FIXTURE.replace("M7.P02 Second", "M7.P01 Second"),
            "`## M7.P01` after `## M7.P01`",
            "order the phases ascending, each phase once",
        ),
        (
            FIXTURE.replace("M7.P02 Second", "0.07.01 Second"),
            "`## 0.07.01` after `## M7.P01`",
            "order the phases ascending, each phase once",
        ),
        (
            FIXTURE.replace("M7.P02 Second", "M6.P99 Second"),
            "`## M6.P99` is not a phase of milestone 7",
            "number it M7.P99 or move it to docs/prompts/m6.md",
        ),
        (
            FIXTURE.replace("## M7.P02 Second", "## M7.P02"),
            "`## M7.P02` has no title",
            "write `## M7.P02 <title>`",
        ),
        (FIXTURE.replace("Resume M7.\n```\n", "Resume M7.\n"), "never closed", "close it with ```"),
        (
            FIXTURE[: FIXTURE.index("## M7.P01")],
            "no phase heading",
            "add one `## M7.P<PP> <title>`",
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
    assert [p.phase for p in prompt_set.phases] == [f"0.00.0{n}" for n in range(7)]
    assert all(p.title and p.text.endswith("\n") for p in prompt_set.phases)
    assert prompt_set.phases[4].text.startswith("Run M0 phase 0.00.04 on branch m0")
    assert prompt_set.resume.startswith("Resume M0 in C:\\Projects\\Optilux.")
    m1 = prompts.load(REPO_ROOT, 1)
    assert (m1.phases[0].key, m1.phases[-1].key) == ((1, 2), (1, 13))


def test_repo_prompts_number_their_steps_in_sequence() -> None:
    # A step glued to the line before it (`...quit.2. next`) leaves a gap in the numbering and
    # hides itself from the briefing's STOP and /critique reading; 0.01.05 and 0.01.08 once had it.
    texts = {name: p.text for name, p in prompts.load_standing(REPO_ROOT).items()}
    for number in (0, 1):
        texts.update({p.phase: p.text for p in prompts.load(REPO_ROOT, number).phases})
    for name, text in texts.items():
        numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\. ", text, re.M)]
        assert numbers == list(range(1, len(numbers) + 1)), name


def test_m1_prompts_follow_the_audited_form() -> None:
    # The form of docs/prompts/m1.md Rules: the why and a Done-when up front, a Report that backs
    # its claims; 0.01.02 predates it and ran as written. The Plan prompt asks the same of M2+
    # through docs/prompts/standing.md#phase-prompts.
    phases = prompts.load(REPO_ROOT, 1).phases
    texts = {p.phase: p.text for p in phases if p.key > (1, 2)}
    texts["Plan"] = prompts.load_standing(REPO_ROOT)[prompts.PLAN].text
    assert len(texts) == 12  # 0.01.03 to 0.01.13 (0.01.11 to 0.01.13: the amendments) and Plan
    for name, text in texts.items():
        first = text.split("\n", 1)[0]
        assert "Take `date` first" in first and " Why: " in first, name
        assert " Done when: " in first and "Read AGENTS.md" not in first, name
    for phase, text in texts.items():
        if phase != "Plan":
            assert "back each claim with output from this session" in text, phase
    reviewed = {p for p, text in texts.items() if "Review: call the reviewer agent" in text}
    assert reviewed == {"0.01.03", "0.01.04", "0.01.05", "0.01.06", "0.01.07"}


def test_load_names_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(prompts.PromptError, match=r"docs/prompts/m3\.md: no such file; fix: "):
        prompts.load(tmp_path, 3)


@pytest.mark.parametrize(
    ("last", "milestone", "expected"),
    [
        (None, 0, "M0.P00"),
        ("0.00.03", 0, "M0.P04"),
        ("0.00.06", 1, "M1.P00"),  # the last phase is another milestone's: its plan comes first
        ("0.01.13", 1, "M1.P14"),
        ("0.01.13", 2, "M2.P00"),
        ("M2.P00", 2, "M2.P01"),
        ("M2.P09", 2, "M2.P10"),
        ("junk", 2, "M2.P00"),
    ],
)
def test_next_phase(last: str | None, milestone: int, expected: str) -> None:
    assert prompts.next_phase(last, milestone) == expected


PLAN = """# M7 plan
Status: fixture.

## 5. Phases
### M7.P01 First
- Estimate: 0.3 h.

### M7.P02 Second
- Estimate: 2 agent; 30 min machine.

## 6. Decisions
- Estimate: 9 h.
"""


@pytest.mark.parametrize(
    ("hours", "size"),
    [(0.3, "S"), (0.5, "S"), (0.6, "M"), (1.5, "M"), (2, "L"), (3, "L"), (3.5, "XL"), (8, "XL")],
)
def test_size(hours: float, size: str) -> None:
    assert prompts.size(hours) == size


def test_phase_estimate(tmp_path: Path) -> None:
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "m7.md").write_text(PLAN, encoding="utf-8")
    assert prompts.phase_estimate(tmp_path, 7, "M7.P01") == 0.3
    assert prompts.phase_estimate(tmp_path, 7, "0.07.01") == 0.3  # the same phase
    assert prompts.phase_estimate(tmp_path, 7, "M7.P02") == 2  # stops at the next heading
    assert prompts.phase_estimate(tmp_path, 7, "M7.P03") is None
    assert prompts.phase_estimate(tmp_path, 8, "M8.P00") is None  # no plan
    assert prompts.phase_estimate(REPO_ROOT, 0, "0.00.00") == 0.3
    assert prompts.phase_estimate(REPO_ROOT, 0, "0.00.06") == 1.5  # "1.5 h, plus the user's merge"


def test_plan_phases_read_the_machine_and_attended_notes(tmp_path: Path) -> None:
    plan = (
        "# M7 game control\n\n### M7.P00 A\n- Estimate: 2 h; machine: the downloads (took 30 s).\n"
        "\n### M7.P01 B\n- Estimate: 1.5 h; machine: 1 launch. Attended: the user's look review"
        " (a named stop).\n\n### 0.07.02 C\n- Estimate: 1 h.\n\n### M7.P03 D\nNo estimate.\n"
        "\n```text\n### M7.P04 E\n- Estimate: 9 h.\n```\n"
    )
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "m7.md").write_text(plan, encoding="utf-8")
    phases = prompts.plan_phases(tmp_path, 7)
    assert phases == {
        (7, 0): prompts.PlanPhase(2, "the downloads (took 30 s)", None),
        (7, 1): prompts.PlanPhase(1.5, "1 launch", "the user's look review (a named stop)"),
        (7, 2): prompts.PlanPhase(1, None, None),
    }
    assert prompts.plan_title(tmp_path, 7) == "M7 game control"
    assert prompts.plan_title(tmp_path, 8) is None and prompts.plan_phases(tmp_path, 8) == {}
    real = prompts.plan_phases(REPO_ROOT, 1)
    assert real[(1, 2)].machine and "downloads" in real[(1, 2)].machine
    assert real[(1, 10)].attended and "look review" in real[(1, 10)].attended


@pytest.mark.parametrize(
    ("kind", "size", "model"),
    [
        ("planning", "S", "Fable 5.1 xHigh"),
        ("planning", None, "Fable 5.1 xHigh"),
        ("release", "S", "Sonnet 5.5 xHigh"),
        ("implementation", "S", "Sonnet 5.5 xHigh"),
        ("implementation", "M", "Opus 5.5 high"),
        ("implementation", "L", "Opus 5.5 xHigh"),
        ("implementation", "XL", "Opus 5.5 Max"),
    ],
)
def test_model_for(kind: str, size: str | None, model: str) -> None:
    suggestion = status.model_for(kind, size)
    assert suggestion is not None and suggestion[0] == model and suggestion[1]


def test_model_for_never_guesses_a_size() -> None:
    assert status.model_for("implementation", None) is None
    assert status.model_for(None, None) is None
    assert set(status.SIZE_MODELS) == {size for _, size in prompts.SIZES} | {prompts.LARGEST}


@pytest.mark.parametrize(
    ("prompt", "critique", "stops"),
    [
        (None, None, []),
        ("Run M7.P02.\n1. Do it.\n2. Commit.\n", None, []),
        (
            "3. Offer me /critique of the plan; fold in.\n4. STOP for my approval.\n",
            3,
            ["step 4: STOP for my approval"],
        ),
        ("2. The critique offer, no slash.\n", None, []),
        (
            "5. The launch: x.y is open: if absent, STOP and ask me to name a world (D23). Go.\n",
            None,
            ["step 5: if absent, STOP and ask me to name a world (D23)"],
        ),
        (
            "1. A. STOP and ask me to run /mcp.\n2. Then STOP for my look review; record it.\n",
            None,
            ["step 1: STOP and ask me to run /mcp", "step 2: STOP for my look review"],
        ),
        ("Stop conditions: section 7. We stop when told.\n1. stop is not STOPPED.\n", None, []),
    ],
)
def test_prompt_steps(prompt: str | None, critique: int | None, stops: list[str]) -> None:
    assert status.prompt_steps(prompt) == (critique, stops)


def test_cut() -> None:
    assert status.cut("short", 10) == "short"
    assert status.cut("one two three four", 12) == "one two..."
    assert status.cut("one, two, three, four", 12) == "one..."  # a cut word is dropped, not shown


def test_cut_drops_parentheticals_before_it_cuts() -> None:
    # The point of a handoff question sits outside its cites: "(workflow.md#skills)" goes first,
    # so "are still pending" is not the part that is lost.
    long = "The evals for optilux-next and optilux-release (workflow.md#skills) are still pending"
    assert (
        status.cut(long, 70) == "The evals for optilux-next and optilux-release are still pending"
    )
    assert status.cut("P34 (D23) is open", 30) == "P34 (D23) is open"  # it fits: untouched
    assert status.cut("a (b (c)) d e f g h", 10) == "a d e..."  # nested ones, then the cut


def test_last_text_without_a_phase() -> None:
    facts = {"last_phase": None, "last_commit": "feat: x"}
    assert status.last_text(facts) == 'no phase done yet; newest "feat: x"'


def test_standing_prompts_of_this_repo() -> None:
    standing = prompts.load_standing(REPO_ROOT)
    plan, release = standing[prompts.PLAN], standing[prompts.RELEASE]
    assert (plan.estimate, release.estimate) == (1, 0.3)
    filled = prompts.fill(plan.text, 2, "M2.P00", "0.3.0")
    assert filled.startswith("Plan milestone M2 as phase M2.P00 on branch m2 in C:\\Projects\\")
    assert "docs/plans/m1.md as the worked example" in filled
    assert "Number the phases M2.P01 on" in filled and "headed `## M2.P<PP> <title>`" in filled
    assert "in the form of docs/prompts/standing.md#phase-prompts" in filled
    assert "Set VERSION to 0.3.0 and add `## 0.3.0 <Name>` to CHANGELOG.md" in filled
    assert "`Last phase: M2.P00`" in filled and "VERSION reads 0.3.0" in filled
    assert "{" not in filled
    assert release.text == "/optilux-release\n"


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("# S\n\n## Release\n- Estimate: 0.3 h.\n```text\nr\n```\n", "no `## Plan` section"),
        ("# S\n\n## Plan\n```text\np\n```\n\n## Release\n- Estimate: 1 h.\n```text\nr\n```\n", ""),
    ],
)
def test_standing_faults_name_the_fix(tmp_path: Path, text: str, detail: str) -> None:
    (tmp_path / "docs" / "prompts").mkdir(parents=True)
    with pytest.raises(prompts.PromptError, match=r"standing.md: no such file; fix: restore"):
        prompts.load_standing(tmp_path)
    (tmp_path / prompts.STANDING).write_text(text, encoding="utf-8")
    with pytest.raises(prompts.PromptError) as caught:
        prompts.load_standing(tmp_path)
    expected = detail or "`## Plan` has no `- Estimate: <h> h` line; fix: add one above"
    assert expected in str(caught.value)


def with_standing(root: Path) -> None:
    """The real standing prompts, so the fixture repos test them too."""
    (root / "docs" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / prompts.STANDING).write_bytes((REPO_ROOT / prompts.STANDING).read_bytes())


def handoff(last: str | None, questions: str = "") -> bytes:
    """A handoff whose `Last phase:` line names `last` (none without it)."""
    line = f"Last phase: {last}\n" if last else ""
    return f"# Handoff\nStatus: fixture.\n\n## Outcome\n{line}- Done.\n{questions}".encode()


def milestone_repo(cloned: Path) -> Path:
    """`cloned` (main: the legacy bootstrap subject, no VERSION) on a pushed m7 with its plan
    phase and first phase done: VERSION 0.8.0, the fixture prompts and plan, the standing
    prompts and a handoff naming M7.P01."""
    git(cloned, "switch", "-q", "-c", "m7", "--no-track", "origin/main")
    with_standing(cloned)
    (cloned / "docs" / "prompts" / "m7.md").write_bytes(FIXTURE.encode())
    (cloned / "docs" / "plans").mkdir(parents=True)
    (cloned / "docs" / "plans" / "m7.md").write_bytes(PLAN.encode())
    (cloned / "docs" / "handoff.md").write_bytes(handoff("M7.P01"))
    (cloned / "VERSION").write_bytes(b"0.8.0\n")
    git(cloned, "add", "-A")
    git(cloned, "commit", "-q", "-m", "feat: first")
    git(cloned, "push", "-q", "-u", "origin", "m7")
    return cloned


def test_status_in_a_throwaway_repo(cloned: Path) -> None:
    root = milestone_repo(cloned)
    facts = status.collect(root)
    assert (facts["branch"], facts["pushed"], facts["clean"]) == ("m7", True, True)
    assert (facts["version_local"], facts["version_main"]) == ("0.8.0", "0.00.00")
    assert (facts["next_kind"], facts["next_phase"], facts["next_title"]) == (
        "implementation",
        "M7.P02",
        "Second",
    )
    assert (facts["next_source"], facts["prompt"]) == ("docs/prompts/m7.md", "Run M7.P02.\n")
    assert (facts["next_estimate"], facts["next_size"]) == (2, "L")
    assert facts["next_estimate_source"] == "docs/plans/m7.md" and facts["switch"] is None
    assert facts["milestone_name"] == "M7 plan"
    assert (facts["next_model"], facts["next_critique_step"], facts["next_stops"]) == (
        "Opus 5.5 xHigh",
        None,
        [],
    )
    assert (facts["next_machine"], facts["next_attended"]) == (None, None)
    progress = facts["progress"]
    assert (progress["first"], progress["last"]) == ("M7.P01", "M7.P02")
    assert (progress["done"], progress["total"]) == (1, 2)
    assert progress["hours_done"] == 0.3 and progress["hours_total"] == pytest.approx(2.3)
    assert facts["upcoming"] == [] and facts["open_questions"] == []
    assert (facts["last_phase"], facts["last_phase_source"]) == ("M7.P01", "docs/handoff.md")
    assert (facts["last_title"], facts["last_commit"]) == ("First", "feat: first")
    assert facts["hooks_set"] is False
    assert facts["problems"] == [
        "hooks path not set; fix: `git config --local core.hooksPath .githooks`"
    ]
    git(root, "config", "--local", "core.hooksPath", ".githooks")
    assert status.collect(root)["problems"] == [] and status.collect(root)["hooks_set"]
    # A VERSION no newer than origin/main's is named with the version to set.
    (root / "VERSION").write_bytes(b"0.0.0\n")
    assert (
        "VERSION 0.0.0 is not newer than origin/main's 0.00.00; "
        "fix: set it to 0.1.0 (docs/workflow.md#release)"
    ) in status.collect(root)["problems"]


def row(label: str, text: str) -> str:
    """A briefing row as `optilux status` prints it."""
    return f"{label:<{status.LABEL}}{text}"


def test_status_text_prints_the_briefing_and_the_prompt_verbatim(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = milestone_repo(cloned)
    monkeypatch.setattr(status, "REPO_ROOT", root)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    model, why = status.SIZE_MODELS["L"]
    rule, light = "=" * status.RULE, "-" * status.RULE
    assert out.split("\n\n")[0].splitlines() == [
        "OPTILUX M7 plan | branch m7, pushed | 0.8.0 local, 0.00.00 on origin/main",
        rule,
        row("NEXT", "M7.P02 Second (docs/prompts/m7.md)"),
        row("KIND", status.KINDS["implementation"]),
        row("COMPLEXITY", "L (2 h agent estimate, docs/plans/m7.md)"),
        row("MODEL", f"{model} ({why})"),
        row("CRITIQUE", "no"),
        row("NEEDS YOU", "nothing: it runs unattended"),
        row("MACHINE", "none stated in the plan"),
        light,
        row(
            "PROGRESS",
            "[##########..........] 1 of 2 phases (M7.P01 to M7.P02), 0.3 of 2.3 h agent",
        ),
        row("LAST", 'M7.P01 First done (handoff, 0 commits since); newest "feat: first"'),
        row("OPEN", "none in docs/handoff.md"),
        light,
        row("TREE", "clean"),
        row("CHECKS", "hooks not set"),
        row("PROBLEM", "hooks path not set; fix: `git config --local core.hooksPath .githooks`"),
    ]
    assert "switch to" not in out
    assert out.endswith("\n\nnext prompt, M7.P02 Second, verbatim:\nRun M7.P02.\n")
    assert out.split("\n\n")[0].isascii()


def test_status_counts_phases_by_the_handoff_not_the_commits(cloned: Path) -> None:
    # A phase may take several commits: those after the last phase done are the next phase's
    # work in progress, and only the handoff's `Last phase:` line moves the milestone on.
    root = milestone_repo(cloned)
    commit_file(root, "side.txt", b"x\n", "fix(prompts): tooling for the next phase")
    commit_file(root, "more.txt", b"x\n", "test: more")
    facts = status.collect(root)
    assert (facts["last_phase"], facts["next_phase"]) == ("M7.P01", "M7.P02")
    assert facts["last_phase_after"] == 2  # a forgotten line shows as commits piling up
    last = row("LAST", 'M7.P01 First done (handoff, 2 commits since); newest "test: more"')
    assert last in status.briefing(facts)
    commit_file(root, "docs/handoff.md", handoff("M7.P02"), "docs: hand off the second phase")
    facts = status.collect(root)
    assert (facts["last_phase"], facts["last_title"], facts["progress"]["done"]) == (
        "M7.P02",
        "Second",
        2,
    )
    assert facts["next_kind"] == "release"


def test_status_reads_m0_and_m1_phases_from_their_subjects(cloned: Path) -> None:
    # Mixed history, as on m1: a prompt set and plan in 0.MM.PP form, phases done in
    # `0.MM.PP.N: ` subjects and no `Last phase:` line yet, conventional commits on top.
    git(cloned, "switch", "-q", "-c", "m7", "--no-track", "origin/main")
    with_standing(cloned)
    legacy = FIXTURE.replace("M7.P01", "0.07.01").replace("M7.P02", "0.07.02")
    (cloned / "docs" / "prompts" / "m7.md").write_bytes(legacy.encode())
    (cloned / "docs" / "plans").mkdir(parents=True)
    (cloned / "docs" / "plans" / "m7.md").write_bytes(PLAN.replace("M7.P0", "0.07.0").encode())
    git(cloned, "add", "-A")
    commit_file(cloned, "first.txt", b"x\n", "0.07.01: First.")
    commit_file(cloned, "patch.txt", b"x\n", "0.07.01.1: Patch the first.")
    commit_file(cloned, "VERSION", b"0.8.0\n", "feat(release)!: version from VERSION")
    git(cloned, "push", "-q", "-u", "origin", "m7")
    facts = status.collect(cloned)
    assert (facts["last_phase"], facts["last_phase_source"]) == ("0.07.01", "git log")
    assert (facts["next_phase"], facts["prompt"]) == ("0.07.02", "Run 0.07.02.\n")
    assert facts["progress"]["done"] == 1 and facts["version_local"] == "0.8.0"
    commit_file(cloned, "second.txt", b"x\n", "0.07.02.0: Second.")
    facts = status.collect(cloned)
    assert (facts["last_phase"], facts["next_kind"]) == ("0.07.02", "release")
    # The handoff's line, once written, wins over the subjects.
    commit_file(cloned, "docs/handoff.md", handoff("0.07.01"), "docs: hand off")
    assert status.collect(cloned)["last_phase"] == "0.07.01"


def test_status_names_a_missing_estimate_and_a_gap(cloned: Path) -> None:
    root = milestone_repo(cloned)
    (root / "docs" / "plans" / "m7.md").unlink()
    facts = status.collect(root)
    assert (facts["next_kind"], facts["next_size"], facts["prompt"]) == (
        "implementation",
        None,
        "Run M7.P02.\n",
    )
    assert (
        "no estimate for M7.P02 in docs/plans/m7.md; "
        "fix: add `- Estimate: <h> h.` to `### M7.P02` in docs/plans/m7.md"
    ) in facts["problems"]
    briefing = status.briefing(facts)
    assert row("COMPLEXITY", "unknown (no estimate for this prompt)") in briefing
    assert row("MODEL", "unknown (no size to choose by)") in briefing
    assert (
        row("PROGRESS", "[##########..........] 1 of 2 phases (M7.P01 to M7.P02), hours unknown")
        in briefing
    )
    gap = FIXTURE.replace("M7.P02 Second", "M7.P03 Third")
    (root / "docs" / "prompts" / "m7.md").write_bytes(gap.encode())
    facts = status.collect(root)
    assert (facts["next_kind"], facts["prompt"]) == (None, None)
    assert (
        "no stored prompt for M7.P02; fix: add `## M7.P02 <title>` to docs/prompts/m7.md "
        "(its phases end at M7.P03)"
    ) in facts["problems"]
    assert row("NEXT", "no next prompt: see PROBLEM below") in status.briefing(facts)


def test_status_names_a_handoff_line_that_names_no_phase(cloned: Path) -> None:
    root = milestone_repo(cloned)
    (root / "docs" / "handoff.md").write_bytes(handoff("0.07.01.0"))  # a version, not a phase
    facts = status.collect(root)
    assert (
        "docs/handoff.md: `Last phase: 0.07.01.0` names no phase; "
        "fix: write `Last phase: M<N>.P<PP>`, the phase the stop completed"
    ) in facts["problems"]


def test_status_plans_while_the_set_starts_at_the_phase_after_the_next(cloned: Path) -> None:
    # The plan phase in progress: no phase of M7 done yet, the set it wrote starts at M7.P01 and
    # is not committed; the cycle yields the Plan prompt for M7.P00, setting the next minor.
    root = milestone_repo(cloned)
    (root / "docs" / "handoff.md").unlink()
    facts = status.collect(root)
    assert (facts["next_kind"], facts["next_phase"], facts["next_title"]) == (
        "planning",
        "M7.P00",
        "Plan M7",
    )
    assert facts["prompt"].startswith("Plan milestone M7 as phase M7.P00 on branch m7 in ")
    assert "Set VERSION to 0.1.0 and add `## 0.1.0 <Name>`" in facts["prompt"]
    assert (facts["next_estimate"], facts["next_size"]) == (1, "M")
    assert not any("no stored prompt" in problem for problem in facts["problems"])
    # A set starting later is a gap, not the plan phase.
    gap = FIXTURE.replace("M7.P02 Second", "M7.P03 Second").replace("M7.P01 First", "M7.P02 F")
    (root / "docs" / "prompts" / "m7.md").write_bytes(gap.encode())
    facts = status.collect(root)
    assert (facts["next_kind"], facts["prompt"]) == (None, None)
    assert any("no stored prompt for M7.P00; fix:" in problem for problem in facts["problems"])


def test_status_gives_the_release_once_every_phase_is_done(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = milestone_repo(cloned)
    (root / "extra.txt").write_bytes(b"dirty\n")
    commit_file(root, "docs/handoff.md", handoff("M7.P02"), "docs: hand off")  # not pushed
    facts = status.collect(root)
    assert (facts["pushed"], facts["clean"]) == (False, False)
    assert facts["changes"] == ["?? extra.txt"] and facts["switch"] is None
    assert (facts["next_kind"], facts["next_phase"], facts["next_title"]) == (
        "release",
        None,
        "Release M7",
    )
    assert (facts["prompt"], facts["next_size"]) == ("/optilux-release\n", "S")
    assert "HEAD is not on origin/m7; fix: `git push -u origin m7`" in facts["problems"]
    monkeypatch.setattr(status, "REPO_ROOT", root)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    model, why = status.SIZE_MODELS["S"]
    assert row("NEXT", "Release M7 (docs/prompts/standing.md)") in lines
    assert row("KIND", status.KINDS["release"]) in lines
    assert row("COMPLEXITY", "S (0.3 h agent estimate, docs/prompts/standing.md)") in lines
    assert row("MODEL", f"{model} ({why})") in lines
    assert any(
        line.startswith(row("PROGRESS", "[####################] 2 of 2 phases")) for line in lines
    )
    assert not any(line.startswith("MACHINE") for line in lines)
    assert out.endswith("\n\nnext prompt, Release M7, verbatim:\n/optilux-release\n")
    (root / "docs" / "prompts" / "m7.md").write_bytes(without_resume().encode())
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert row("TREE", "2 changes: M docs/prompts/m7.md; ?? extra.txt") in out.splitlines()
    assert row("PROBLEM", "docs/prompts/m7.md: no `## Resume` section; fix: ") in out
    assert row("NEXT", "no next prompt: see PROBLEM below") in out.splitlines()
    assert "\nnext prompt, " not in out


def test_status_after_the_merge_switches_and_plans_the_next_milestone(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = milestone_repo(cloned)
    commit_file(root, "docs/handoff.md", handoff("M7.P02"), "docs: hand off")
    git(root, "push", "-q", "origin", "m7", "m7:main")  # the user's merge, as a fast-forward
    facts = status.collect(root)
    assert (facts["version_local"], facts["version_main"]) == ("0.8.0", "0.8.0")
    assert (facts["next_kind"], facts["next_phase"], facts["next_title"]) == (
        "planning",
        "M8.P00",
        "Plan M8",
    )
    assert facts["prompt"].startswith("Plan milestone M8 as phase M8.P00 on branch m8 in ")
    assert "Set VERSION to 0.9.0 and add `## 0.9.0 <Name>`" in facts["prompt"]
    switch = ["uv run optilux milestone start 8", "git branch -D m7", "git push origin --delete m7"]
    assert facts["switch"] == switch
    monkeypatch.setattr(status, "REPO_ROOT", root)
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert row("KIND", status.KINDS["planning"]) in lines
    assert row("COMPLEXITY", "M (1 h agent estimate, docs/prompts/standing.md)") in lines
    assert row("SWITCH", "first run the switch block to m8 below") in lines
    block = "\nswitch to m8 first, paste:\n" + "\n".join(switch) + "\n"
    assert block + "\nnext prompt, M8.P00 Plan M8, verbatim:\nPlan milestone M8" in out
    git(root, "switch", "-q", "main")
    git(root, "merge", "-q", "--ff-only", "m7")
    git(root, "push", "-q", "origin", "--delete", "m7")
    facts = status.collect(root)  # on main: the milestone of the last phase done
    assert (facts["branch"], facts["pushed"], facts["next_title"]) == ("main", None, "Plan M8")
    assert facts["switch"] == ["uv run optilux milestone start 8", "git branch -D m7"]


def test_the_switch_block_starts_the_next_milestone(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # What M1's merge hands to M2, run end to end on M7 and M8: the switch block as status prints
    # it, then the plan commit that sets the next minor, which status and the release check take.
    root = milestone_repo(cloned)
    (root / "CHANGELOG.md").write_bytes(b"# Changelog\n\n## 0.8.0 Seven\nSeven.\n")
    git(root, "add", "CHANGELOG.md")
    commit_file(root, "docs/handoff.md", handoff("M7.P02"), "docs: hand off")
    git(root, "push", "-q", "origin", "m7", "m7:main")
    switch = status.collect(root)["switch"]
    assert switch == [
        "uv run optilux milestone start 8",
        "git branch -D m7",
        "git push origin --delete m7",
    ]
    assert milestone.start(root, 8) == 0
    out = capsys.readouterr().out
    assert out.endswith(
        "next: `uv run optilux status` prints the next prompt\n"
        "then: the first commit sets VERSION 0.9.0; push it with `git push -u origin m8`\n"
    )
    git(root, "branch", "-q", "-D", "m7")
    git(root, "push", "-q", "origin", "--delete", "m7")
    facts = status.collect(root)
    assert (facts["branch"], facts["switch"], facts["next_phase"]) == ("m8", None, "M8.P00")
    assert (facts["version_local"], facts["version_main"]) == ("0.8.0", "0.8.0")
    assert not any("VERSION" in problem for problem in facts["problems"])
    # The plan commit: VERSION, its CHANGELOG entry, the prompt set, the plan and the handoff.
    (root / "VERSION").write_bytes(b"0.9.0\n")
    changelog = b"# Changelog\n\n## 0.9.0 Eight\nEight.\n\n## 0.8.0 Seven\nSeven.\n"
    (root / "CHANGELOG.md").write_bytes(changelog)
    (root / "docs" / "prompts" / "m8.md").write_bytes(FIXTURE.replace("M7", "M8").encode())
    (root / "docs" / "plans" / "m8.md").write_bytes(PLAN.replace("M7", "M8").encode())
    (root / "docs" / "handoff.md").write_bytes(handoff("M8.P00"))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "docs: plan the milestone and its prompts")
    git(root, "push", "-q", "-u", "origin", "m8")
    facts = status.collect(root)
    assert (facts["next_kind"], facts["next_phase"], facts["version_local"]) == (
        "implementation",
        "M8.P01",
        "0.9.0",
    )
    monkeypatch.setattr(pack, "run_gh", lambda *args: pytest.fail("no gh without --check"))
    found = pack.check(root, "HEAD", remote=False)
    assert [text for outcome, text in found if outcome == pack.PROBLEM] == []
    assert (pack.OK, "VERSION 0.9.0 is newer than origin/main's 0.8.0") in found


HANDOFF = """
## Open questions
- P1: whether the world exists; the user was unsure.
- Second question, with no semicolon.
- Third.
- Fourth.
- Fifth; with a tail.

## Time
- Not a question.
"""


def test_status_lists_the_handoffs_open_questions(
    cloned: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = milestone_repo(cloned)
    (root / "docs" / "handoff.md").write_bytes(handoff("M7.P01", HANDOFF))
    facts = status.collect(root)
    assert facts["open_questions"][:2] == [
        "P1: whether the world exists; the user was unsure.",
        "Second question, with no semicolon.",
    ]
    assert len(facts["open_questions"]) == 5
    monkeypatch.setattr(status, "REPO_ROOT", root)
    assert cli.main(["status"]) == 0
    lines = capsys.readouterr().out.splitlines()
    shown = [
        row("OPEN", "P1: whether the world exists"),
        row("", "Second question, with no semicolon."),
        row("", "Third."),
        row("", "Fourth."),
        row("", "(+1 more in docs/handoff.md)"),
    ]
    start = lines.index(shown[0])
    assert lines[start : start + 5] == shown


def test_status_plans_a_milestone_without_a_prompt_set(cloned: Path) -> None:
    git(cloned, "switch", "-q", "-c", "m7", "--no-track", "origin/main")
    with_standing(cloned)
    facts = status.collect(cloned)
    assert (facts["version_local"], facts["next_phase"]) == ("0.00.00", "M7.P00")
    assert (facts["next_kind"], facts["next_title"], facts["next_size"]) == (
        "planning",
        "Plan M7",
        "M",
    )
    assert facts["prompt"].startswith("Plan milestone M7 as phase M7.P00 on branch m7 in ")
    assert "docs/plans/m6.md as the worked example" in facts["prompt"]
    assert facts["pushed"] is False and facts["switch"] is None
    # A planning step: Fable whatever the size, the critique offered at step 3, the approval
    # a stop at step 4, no plan yet to show progress through.
    assert (facts["next_model"], facts["next_critique_step"]) == (status.PLANNING_MODEL[0], 3)
    assert facts["next_stops"] == ["step 4: STOP for my approval of the plan"]
    assert (facts["progress"], facts["upcoming"], facts["milestone_name"]) == (None, [], None)
    lines = status.briefing(facts)
    assert row("KIND", status.KINDS["planning"]) in lines
    assert row("MODEL", "Fable 5.1 xHigh (" + status.PLANNING_MODEL[1] + ")") in lines
    assert row("CRITIQUE", "offered at step 3 (/critique; you decide)") in lines
    assert row("NEEDS YOU", "step 4: STOP for my approval of the plan") in lines
    assert row("PROGRESS", "no plan or prompt set yet") in lines
    assert lines[0].startswith("OPTILUX M7 | branch m7, not pushed | ")
    assert not any(line.startswith("MACHINE") for line in lines)
    (cloned / prompts.STANDING).unlink()
    facts = status.collect(cloned)
    assert facts["prompt"] is None
    assert any("docs/prompts/standing.md: no such file; fix: " in p for p in facts["problems"])


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
    assert facts["version_main"] == repo.released_at(REPO_ROOT, "HEAD")
    assert facts["version_local"] == (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert prompts.phase_key(facts["last_phase"]) is not None
    # Whatever the state of this checkout, the cycle always yields a next prompt with a size.
    assert facts["prompt"] and facts["next_kind"] in ("planning", "implementation", "release")
    assert facts["next_size"] in ("S", "M", "L", "XL") and facts["next_model"]
    # The briefing is one block of ASCII: the skill prints it in a code block, and the Windows
    # console would raise on anything else.
    briefing = "\n".join(status.briefing(facts))
    assert briefing.isascii() and "\n\n" not in briefing
