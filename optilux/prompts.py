"""Stored prompt sets, docs/prompts/m<MM>.md, in the format of docs/prompts/m0.md Rules: one
`## 0.MM.PP <title>` heading per phase, each followed by exactly one fenced block holding the
prompt; `## Resume` last, with one fenced block. `optilux status` prints the next prompt verbatim.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from optilux.docs_check import FENCE

# A section heading, at column 0 as the Rules write them; the title is the rest of the line.
SECTION = re.compile(r"^## (\S.*?)\s*$")
# A phase heading's text: the version, then the title.
PHASE = re.compile(r"(0\.(\d{2})\.(\d{2}))(?:\s+(.*))?")
RESUME = "Resume"
VERSION = re.compile(r"0\.(\d{2})\.(\d{2})")


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


def parse_phase(section: Section, milestone: int, previous: str | None, file: str) -> Prompt:
    version, major, minor, title = PHASE.fullmatch(section.heading).groups()
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
        elif PHASE.fullmatch(section.heading):
            previous = phases[-1].version if phases else None
            phases.append(parse_phase(section, milestone, previous, file))
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
