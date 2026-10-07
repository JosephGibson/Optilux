"""Stored prompts, which `optilux status` prints verbatim.

- docs/prompts/m<N>.md, a milestone's prompt set (docs/workflow.md#running-a-milestone): one
  `## <phase> <title>` heading per phase, each followed by exactly one fenced block holding the
  prompt; `## Resume` last, with one fenced block.
- docs/prompts/standing.md, the Plan and Release prompts every milestone uses, each with its own
  `- Estimate: <h> h` line; placeholders such as {M} are filled in for the milestone at hand.
- A phase prompt's size comes from its phase's `- Estimate: <h> h` in docs/plans/m<N>.md.

A phase is `M<N>.P<PP>` from M2 on (roadmap.md D33); M0's and M1's sets and plans keep `0.MM.PP`,
which reads as the same milestone and number.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from optilux import docs_check
from optilux.docs_check import FENCE

# A section heading, at column 0 as the Rules write them; the title is the rest of the line.
SECTION = re.compile(r"^## (\S.*?)\s*$")
# A phase ID, M2.P01, or as M0 and M1 wrote it, 0.01.02 (the milestone, then the number).
PHASE_ID = re.compile(r"M(\d{1,2})\.P(\d{2})|0\.(\d{2})\.(\d{2})")
# A phase heading's text: the phase, then the title.
PHASE = re.compile(r"(\S+)(?:\s+(.*))?")
RESUME = "Resume"
STANDING = "docs/prompts/standing.md"
PLAN, RELEASE = "Plan", "Release"
# The estimate line of a plan phase and of a standing prompt: agent hours, the first number on the
# line, written `1.5 h` as docs/templates/plan.md has it; a bare number passes too.
ESTIMATE = re.compile(r"^- Estimate: (\d+(?:\.\d+)?)(?: ?h)?\b")
# What a plan phase's estimate line may add after the hours (plans/m1.md section 5):
# `; machine: 1 launch.` and ` Attended: the user's look review.`, each up to its full stop.
MACHINE = re.compile(r"machine: (.+?)\.?(?:\s+Attended:|$)")
ATTENDED = re.compile(r"Attended: (.+?)\.?$")
# A plan phase's heading: `### <phase> <title>`.
PLAN_PHASE = re.compile(r"^### (\S+)(?:\s|$)")
# Size buckets of an estimate in agent hours (user, 2026-10-06). M is a typical phase: ALC's took
# about 1 h (docs/workflow.md#git) and M0's were estimated at 1-1.5 h; XL is past two typical
# phases, a candidate for a split. The last bucket is open-ended.
SIZES = ((0.5, "S"), (1.5, "M"), (3.0, "L"))
LARGEST = "XL"


class PromptError(ValueError):
    """A prompt file that breaks the format; the message names the file, the line and the fix."""


def phase_key(text: str | None) -> tuple[int, int] | None:
    """(milestone, number) of a phase ID in either form: M2.P01 -> (2, 1), 0.01.13 -> (1, 13);
    None for any other text."""
    match = PHASE_ID.fullmatch(text or "")
    if match is None:
        return None
    if match.group(1) is not None:
        return int(match.group(1)), int(match.group(2))
    return int(match.group(3)), int(match.group(4))


def phase_id(milestone: int, number: int) -> str:
    """The ID of a new phase: M2.P01."""
    return f"M{milestone}.P{number:02d}"


@dataclass(frozen=True)
class Prompt:
    phase: str  # the ID as its heading writes it
    title: str
    text: str  # the fenced block's lines, verbatim, with a trailing newline
    line: int  # of the heading

    @property
    def key(self) -> tuple[int, int]:
        return phase_key(self.phase) or (-1, -1)  # parse admits only phase IDs


@dataclass(frozen=True)
class PromptSet:
    file: str
    milestone: int
    phases: tuple[Prompt, ...]
    resume: str

    def phase(self, phase: str) -> Prompt | None:
        """The prompt of a phase, its ID in either form."""
        key = phase_key(phase)
        return next((prompt for prompt in self.phases if prompt.key == key), None)


@dataclass
class Section:
    line: int
    heading: str
    blocks: list[tuple[int, str]]
    lines: list[str] = field(default_factory=list)  # outside the fenced blocks


@dataclass(frozen=True)
class PlanPhase:
    """What a plan says of one phase beside its commit: the estimate in agent hours, the machine
    time it needs (launches, downloads) and what needs the user, each as the plan words it."""

    estimate: float
    machine: str | None
    attended: str | None


@dataclass(frozen=True)
class Standing:
    """A standing prompt (Plan or Release) with its estimate in agent hours."""

    name: str
    estimate: float | None
    text: str  # verbatim, placeholders unfilled


def prompt_name(milestone: int) -> str:
    return f"docs/prompts/m{milestone}.md"


def prompt_file(root: Path, milestone: int) -> Path:
    return root / prompt_name(milestone)


def error(file: str, line: int | None, detail: str, fix: str) -> PromptError:
    where = file if line is None else f"{file}:{line}"
    return PromptError(f"{where}: {detail}; fix: {fix}")


def sections(text: str, file: str) -> list[Section]:
    """The `## ` sections of a file with their fenced blocks; headings inside a fence are text."""
    found = [Section(0, "", [])]
    fence = ""
    opened = 0
    block: list[str] = []
    for number, line in enumerate(text.split("\n"), 1):
        match = FENCE.match(line)
        if fence:
            marker = match.group(1) if match else ""
            closes = marker and marker[0] == fence[0] and len(marker) >= len(fence)
            if closes and line.strip() == marker:
                found[-1].blocks.append((opened, "\n".join(block) + "\n"))
                fence = ""
            else:
                block.append(line)
        elif match:
            fence, opened, block = match.group(1), number, []
        elif heading := SECTION.match(line):
            found.append(Section(number, heading.group(1), []))
        else:
            found[-1].lines.append(line)
    if fence:
        raise error(file, opened, "the fenced block is never closed", f"close it with {fence}")
    return found


def one_block(section: Section, file: str, what: str) -> str:
    """The text of a section's single fenced block; PromptError when there is not exactly one."""
    count = len(section.blocks)
    name = f"`## {section.heading}`"
    if count != 1:
        detail = f"{name} holds {count} fenced blocks"
        raise error(file, section.line, detail, f"keep exactly one fenced block holding {what}")
    line, text = section.blocks[0]
    if not text.strip():
        raise error(file, line, f"{name} has an empty block", f"write {what} in it")
    return text


def parse_phase(
    section: Section, match: re.Match[str], milestone: int, previous: Prompt | None, file: str
) -> Prompt:
    phase, title = match.groups()
    key = phase_key(phase) or (-1, -1)  # the caller matched a phase ID
    name = f"`## {phase}`"
    if not title:
        raise error(file, section.line, f"{name} has no title", f"write {name[:-1]} <title>`")
    if key[0] != milestone:
        detail = f"{name} is not a phase of milestone {milestone}"
        fix = f"number it {phase_id(milestone, key[1])} or move it to {prompt_name(key[0])}"
        raise error(file, section.line, detail, fix)
    if previous is not None and key <= previous.key:
        detail = f"{name} after `## {previous.phase}`"
        raise error(file, section.line, detail, "order the phases ascending, each phase once")
    return Prompt(phase, title, one_block(section, file, f"the {phase} prompt"), section.line)


def parse(text: str, milestone: int, file: str = "docs/prompts/m<N>.md") -> PromptSet:
    """The phases and the Resume prompt of a prompt file; PromptError names the first fault."""
    phases: list[Prompt] = []
    resume: str | None = None
    form = f"`## M{milestone}.P<PP> <title>`"
    for section in sections(text, file)[1:]:
        match = PHASE.fullmatch(section.heading)
        if resume is not None:
            detail = f"`## {section.heading}` follows `## {RESUME}`"
            raise error(file, section.line, detail, f"move `## {RESUME}` to the end")
        if section.heading == RESUME:
            resume = one_block(section, file, "the Resume prompt")
        elif match and phase_key(match.group(1)):
            previous = phases[-1] if phases else None
            phases.append(parse_phase(section, match, milestone, previous, file))
        elif phases:
            detail = f"`## {section.heading}` is neither a phase nor `## {RESUME}`"
            fix = f"head it {form} or move it before the first phase"
            raise error(file, section.line, detail, fix)
    if not phases:
        fix = f"add one {form} heading per phase, each with one fenced block"
        raise error(file, None, "no phase heading", fix)
    if resume is None:
        fix = f"add `## {RESUME}` with one fenced block as the last section"
        raise error(file, None, f"no `## {RESUME}` section", fix)
    return PromptSet(file, milestone, tuple(phases), resume)


def load(root: Path, milestone: int) -> PromptSet:
    """The prompt set of a milestone in the repo; PromptError when the file is missing or wrong."""
    path = prompt_file(root, milestone)
    name = prompt_name(milestone)
    if not path.is_file():
        fix = "write the milestone's prompt set there, one prompt per phase and Resume last"
        raise error(name, None, "no such file", fix)
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    return parse(text, milestone, name)


def next_phase(last: str | None, milestone: int) -> str:
    """The phase after the last one done, inside the milestone: its number plus one, or the
    milestone's first phase, P00 (its plan), when the last one done belongs to another."""
    key = phase_key(last)
    if key and key[0] == milestone:
        return phase_id(milestone, key[1] + 1)
    return phase_id(milestone, 0)


def size(hours: float) -> str:
    """S, M, L or XL for an estimate in agent hours (SIZES)."""
    return next((name for limit, name in SIZES if hours <= limit), LARGEST)


def estimate_in(lines: list[str]) -> float | None:
    """The hours of the first `- Estimate: <h> h` line, None without one."""
    found = (ESTIMATE.match(line) for line in lines)
    return next((float(match.group(1)) for match in found if match), None)


def plan_name(milestone: int) -> str:
    return f"docs/plans/m{milestone}.md"


def unfenced_lines(path: Path) -> list[str]:
    """The lines of a text file outside fenced code, LF-normalized; empty when it is no file."""
    if not path.is_file():
        return []
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    return [line for _, line in docs_check.unfenced(docs_check.split_lines(text))]


def plan_title(root: Path, milestone: int) -> str | None:
    """The milestone's name: the plan's title without its `# `, None without a plan."""
    lines = unfenced_lines(root / plan_name(milestone))
    return next((line[2:].strip() for line in lines if line.startswith("# ")), None)


def plan_phases(root: Path, milestone: int) -> dict[tuple[int, int], PlanPhase]:
    """The phases of a plan that carry a `- Estimate:` line, by phase_key: the first one under
    each `### <phase> ...`, up to the next heading. Empty without a plan."""
    found: dict[tuple[int, int], PlanPhase] = {}
    key: tuple[int, int] | None = None
    for line in unfenced_lines(root / plan_name(milestone)):
        if line.startswith("#"):
            heading = PLAN_PHASE.match(line)
            key = phase_key(heading.group(1)) if heading else None
        elif key is not None and key not in found:
            estimate = ESTIMATE.match(line)
            if estimate:
                rest = line[estimate.end() :]
                machine, attended = MACHINE.search(rest), ATTENDED.search(rest)
                found[key] = PlanPhase(
                    float(estimate.group(1)),
                    machine.group(1) if machine else None,
                    attended.group(1) if attended else None,
                )
    return found


def phase_estimate(root: Path, milestone: int, phase: str) -> float | None:
    """The estimate of a phase in its plan; None when the plan, the phase or the line is
    missing."""
    key = phase_key(phase)
    found = plan_phases(root, milestone).get(key) if key else None
    return found.estimate if found else None


def load_standing(root: Path) -> dict[str, Standing]:
    """The Plan and Release prompts of docs/prompts/standing.md, each with its estimate;
    PromptError when the file is missing or a section breaks the format."""
    path = root / STANDING
    if not path.is_file():
        raise error(STANDING, None, "no such file", "restore the standing prompts from git")
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    found = {section.heading: section for section in sections(text, STANDING)[1:]}
    standing = {}
    for name in (PLAN, RELEASE):
        section = found.get(name)
        if section is None:
            raise error(STANDING, None, f"no `## {name}` section", f"add `## {name}`")
        estimate = estimate_in(section.lines)
        if estimate is None:
            detail = f"`## {name}` has no `- Estimate: <h> h` line"
            raise error(STANDING, section.line, detail, "add one above its fenced block")
        standing[name] = Standing(
            name, estimate, one_block(section, STANDING, f"the {name} prompt")
        )
    return standing


def fill(text: str, milestone: int, phase: str, version: str) -> str:
    """A standing prompt for a milestone: {M} its number, {PREV} the previous milestone's
    number, {PHASE} the phase the prompt completes, {VERSION} the release version it sets."""
    for key, value in (
        ("{M}", str(milestone)),
        ("{PREV}", str(milestone - 1)),
        ("{PHASE}", phase),
        ("{VERSION}", version),
    ):
        text = text.replace(key, value)
    return text
