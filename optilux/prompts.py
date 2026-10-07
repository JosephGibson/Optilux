"""Stored prompts, which `optilux status` prints verbatim.

- docs/prompts/m<MM>.md, a milestone's prompt set, in the format of docs/prompts/m0.md Rules: one
  `## 0.MM.PP <title>` heading per phase, each followed by exactly one fenced block holding the
  prompt; `## Resume` last, with one fenced block.
- docs/prompts/standing.md, the Plan and Release prompts every milestone uses, each with its own
  `- Estimate: <h> h` line; placeholders such as {M} are filled in for the milestone at hand.
- A phase prompt's size comes from its phase's `- Estimate: <h> h` in docs/plans/m<MM>.md.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from optilux import docs_check
from optilux.docs_check import FENCE

# A section heading, at column 0 as the Rules write them; the title is the rest of the line.
SECTION = re.compile(r"^## (\S.*?)\s*$")
# A phase heading's text: the version, then the title.
PHASE = re.compile(r"(0\.(\d{2})\.(\d{2}))(?:\s+(.*))?")
RESUME = "Resume"
VERSION = re.compile(r"0\.(\d{2})\.(\d{2})")
STANDING = "docs/prompts/standing.md"
PLAN, RELEASE = "Plan", "Release"
# The estimate line of a plan phase and of a standing prompt: agent hours, the first number on the
# line, written `2 agent` as docs/templates/plan.md has it or `1.5 h` as plans/m0.md does.
ESTIMATE = re.compile(r"^- Estimate: (\d+(?:\.\d+)?)(?: ?h)?\b")
# What a plan phase's estimate line may add after the hours (plans/m1.md section 5):
# `; machine: 1 launch.` and ` Attended: the user's look review.`, each up to its full stop.
MACHINE = re.compile(r"machine: (.+?)\.?(?:\s+Attended:|$)")
ATTENDED = re.compile(r"Attended: (.+?)\.?$")
# A plan phase's heading: `### 0.MM.PP <title>`.
PLAN_PHASE = re.compile(r"^### (0\.\d{2}\.\d{2})(?:\s|$)")
# Size buckets of an estimate in agent hours (user, 2026-10-06). M is a typical phase: ALC's took
# about 1 h (docs/workflow.md#git) and M0's were estimated at 1-1.5 h; XL is past two typical
# phases, a candidate for a split. The last bucket is open-ended.
SIZES = ((0.5, "S"), (1.5, "M"), (3.0, "L"))
LARGEST = "XL"


class PromptError(ValueError):
    """A prompt file that breaks the format; the message names the file, the line and the fix."""


@dataclass(frozen=True)
class Prompt:
    version: str
    title: str
    text: str  # the fenced block's lines, verbatim, with a trailing newline
    line: int  # of the heading


@dataclass(frozen=True)
class PromptSet:
    file: str
    milestone: int
    phases: tuple[Prompt, ...]
    resume: str

    def phase(self, version: str) -> Prompt | None:
        return next((prompt for prompt in self.phases if prompt.version == version), None)


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
    section: Section, match: re.Match[str], milestone: int, previous: str | None, file: str
) -> Prompt:
    version, major, minor, title = match.groups()
    name = f"`## {version}`"
    if not title:
        raise error(file, section.line, f"{name} has no title", f"write {name[:-1]} <title>`")
    if int(major) != milestone:
        detail = f"{name} is not a phase of milestone {milestone}"
        fix = f"number it 0.{milestone:02d}.{minor} or move it to {prompt_name(int(major))}"
        raise error(file, section.line, detail, fix)
    if previous is not None and version <= previous:
        detail = f"{name} after `## {previous}`"
        raise error(file, section.line, detail, "order the phases ascending, each version once")
    return Prompt(version, title, one_block(section, file, f"the {version} prompt"), section.line)


def parse(text: str, milestone: int, file: str = "docs/prompts/m<MM>.md") -> PromptSet:
    """The phases and the Resume prompt of a prompt file; PromptError names the first fault."""
    phases: list[Prompt] = []
    resume: str | None = None
    form = f"`## 0.{milestone:02d}.PP <title>`"
    for section in sections(text, file)[1:]:
        if resume is not None:
            detail = f"`## {section.heading}` follows `## {RESUME}`"
            raise error(file, section.line, detail, f"move `## {RESUME}` to the end")
        if section.heading == RESUME:
            resume = one_block(section, file, "the Resume prompt")
        elif match := PHASE.fullmatch(section.heading):
            previous = phases[-1].version if phases else None
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


def next_phase(newest: str | None, milestone: int) -> str:
    """The phase after the newest version prefix, inside the milestone: the newest plus one, or
    the milestone's first phase when nothing of it is committed yet."""
    match = VERSION.fullmatch(newest or "")
    if match and int(match.group(1)) == milestone:
        return f"0.{milestone:02d}.{int(match.group(2)) + 1:02d}"
    return f"0.{milestone:02d}.00"


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


def plan_phases(root: Path, milestone: int) -> dict[str, PlanPhase]:
    """The phases of a plan that carry a `- Estimate:` line: the first one under each
    `### <version> ...`, up to the next heading. Empty without a plan."""
    found: dict[str, PlanPhase] = {}
    version: str | None = None
    for line in unfenced_lines(root / plan_name(milestone)):
        if line.startswith("#"):
            heading = PLAN_PHASE.match(line)
            version = heading.group(1) if heading else None
        elif version is not None and version not in found:
            estimate = ESTIMATE.match(line)
            if estimate:
                rest = line[estimate.end() :]
                machine, attended = MACHINE.search(rest), ATTENDED.search(rest)
                found[version] = PlanPhase(
                    float(estimate.group(1)),
                    machine.group(1) if machine else None,
                    attended.group(1) if attended else None,
                )
    return found


def phase_estimate(root: Path, milestone: int, version: str) -> float | None:
    """The estimate of a phase in its plan; None when the plan, the phase or the line is
    missing."""
    phase = plan_phases(root, milestone).get(version)
    return phase.estimate if phase else None


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


def fill(text: str, milestone: int, version: str) -> str:
    """A standing prompt for a milestone: {M} its number, {MM} its two digits, {PREV} the
    previous milestone's number, {VERSION} the phase the prompt commits."""
    for key, value in (
        ("{MM}", f"{milestone:02d}"),
        ("{M}", str(milestone)),
        ("{PREV}", str(milestone - 1)),
        ("{VERSION}", version),
    ):
        text = text.replace(key, value)
    return text
