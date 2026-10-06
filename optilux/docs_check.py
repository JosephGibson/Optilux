"""The doc rules (docs/workflow.md#docs-rules) as one pure check over a tree.

`check_tree` reads the root's .md files and docs/**/*.md and returns every violation with its fix;
it writes nothing. `optilux verify docs` prints it; tests/test_docs_check.py runs it over the repo.
"""

import posixpath
import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

# Byte caps (docs/workflow.md#docs-rules). They force cuts of duplicated text, never a split by
# concern; raised from 4,096 and 16,384 by the user on 2026-10-06.
AGENTS_CAP = 6_144
DOCS_CAP = 24_576
# docs/roadmap.md and docs/plans/*.md: the critic refuses a plan over 50,000 characters.
PLAN_CAP = 40_960

# A file over this many lines needs `## Contents` directly after its Status line.
TOC_MAX_LINES = 100
CONTENTS = "## Contents"

STATUS = "Status:"
# Status lines point to the handoff; the detail lives there, not in the line.
STATUS_MAX_SENTENCES = 2

# docs/sources/ holds external documents verbatim: cite targets, never checked.
SOURCES = "docs/sources/"

UTF8_BOM = b"\xef\xbb\xbf"

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
# A URL's own `x.md#y` is the remote site's business, not a cite. The lookbehind starts a match
# only at a word's start: without it a 40 KB word took 3 s (a scheme retried at every position).
URL = re.compile(r"(?<![\w+.-])[A-Za-z][\w+.-]*://\S+")
# A cite: a path ending in .md, `#`, an anchor. The anchor class is wider than a slug, so a cite
# with capitals or underscores is caught as dangling instead of slipping past the pattern.
CITE = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.md)#([\w-]+)")
# A sentence ends at . ! or ?, optionally closed by quotes or brackets, before whitespace or the
# end; a period inside a name (docs/handoff.md, 0.00.02) does not end one.
SENTENCE_END = re.compile(r"[.!?][\"')\]]*(?=\s|$)")


def slug(heading: str) -> str:
    """The anchor of a heading, GitHub's rule: lowercase; drop every character that is not a
    letter, digit, space or hyphen; spaces to hyphens.

    "mc-26.3 verified" -> platform.md#mc-263-verified;
    "8. Open decisions" -> design.md#8-open-decisions.
    """
    kept = "".join(ch for ch in heading.strip().lower() if ch.isalnum() or ch in " -")
    return kept.replace(" ", "-")


@dataclass(frozen=True)
class Violation:
    file: str
    rule: str
    detail: str
    fix: str
    line: int | None = None

    def text(self) -> str:
        where = self.file if self.line is None else f"{self.file}:{self.line}"
        return f"{where}: {self.rule}: {self.detail}\n  fix: {self.fix}"


@dataclass(frozen=True)
class FileSize:
    file: str
    size: int
    cap: int | None

    @property
    def margin(self) -> int | None:
        return None if self.cap is None else self.cap - self.size


@dataclass(frozen=True)
class Report:
    files: list[FileSize]
    violations: list[Violation]


def cap_for(file: str) -> int | None:
    """The byte cap of a checked file (posix path from the root); None for the root's other .md
    (README.md and CHANGELOG.md are human-facing, CLAUDE.md one line)."""
    if file == "AGENTS.md":
        return AGENTS_CAP
    if file == "docs/roadmap.md" or posixpath.dirname(file) == "docs/plans":
        return PLAN_CAP
    if file.startswith("docs/"):
        return DOCS_CAP
    return None


def doc_files(root: Path) -> list[str]:
    """The root's .md files and every .md under docs/, sources included, as sorted posix paths.

    Not a walk of the whole tree: runtime/ is never read; .venv/ and reference/ hold others' docs.
    """
    paths = [*root.glob("*.md"), *(root / "docs").rglob("*.md")]
    return sorted(p.relative_to(root).as_posix() for p in paths if p.is_file())


def unfenced(lines: list[str]) -> list[tuple[int, str]]:
    """(1-based line number, line) for every line outside fenced code blocks, fences dropped."""
    kept: list[tuple[int, str]] = []
    fence = ""
    for number, line in enumerate(lines, 1):
        match = FENCE.match(line)
        if not fence:
            if match:
                fence = match.group(1)
            else:
                kept.append((number, line))
        elif match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
            if line.strip() == match.group(1):
                fence = ""
    return kept


def split_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def headings(text: str) -> set[str]:
    """The slugs of every heading outside fenced code blocks."""
    slugs = set()
    for _, line in unfenced(split_lines(text)):
        match = HEADING.match(line)
        if match and match.group(1):
            slugs.add(slug(match.group(1)))
    return slugs


def sentence_count(text: str) -> int:
    return sum(1 for part in SENTENCE_END.split(text) if any(ch.isalnum() for ch in part))


def check_encoding(file: str, raw: bytes) -> list[Violation]:
    found = []
    if raw.startswith(UTF8_BOM):
        found.append(
            Violation(file, "bom", "starts with a UTF-8 BOM", "remove the 3 BOM bytes at the start")
        )
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as error:
        detail = f"not UTF-8: byte {error.start} does not decode"
        found.append(Violation(file, "utf8", detail, "re-save the file as UTF-8 without BOM"))
    if crs := raw.count(b"\r"):
        detail = f"{crs} CR bytes; line endings must be LF"
        found.append(Violation(file, "lf", detail, "convert every CRLF to LF"))
    return found


def check_layout(file: str, lines: list[str]) -> list[Violation]:
    """The Status line (ASCII, at most two sentences) and the TOC directly after it."""
    found = []
    body = unfenced(lines)
    index = next((i for i, (_, line) in enumerate(body) if line.startswith(STATUS)), None)
    if index is not None:
        number, line = body[index]
        status = line[len(STATUS) :]
        odd = sorted({ch for ch in status if not ch.isascii()})
        if odd:
            detail = f"Status line has non-ASCII characters: {' '.join(odd)}"
            fix = "replace them with ASCII (-> for an arrow, - for a dash)"
            found.append(Violation(file, "status-ascii", detail, fix, number))
        count = sentence_count(status)
        if count > STATUS_MAX_SENTENCES:
            detail = f"Status line has {count} sentences, at most {STATUS_MAX_SENTENCES}"
            fix = "cut it to two sentences; the detail goes to docs/handoff.md"
            found.append(Violation(file, "status-sentences", detail, fix, number))
    if len(lines) <= TOC_MAX_LINES:
        return found
    if index is None:
        detail = f"{len(lines)} lines and no Status line to put {CONTENTS} after"
        fix = f"add a Status line under the title and {CONTENTS} directly after it"
        found.append(Violation(file, "toc", detail, fix))
        return found
    following = next(((n, line) for n, line in body[index + 1 :] if line.strip()), None)
    if following is None or following[1].rstrip() != CONTENTS:
        detail = f"{len(lines)} lines and no {CONTENTS} directly after the Status line"
        fix = f"add {CONTENTS} (one line naming the sections) directly after the Status line"
        found.append(Violation(file, "toc", detail, fix, body[index][0]))
    return found


def resolve(citing: str, path: str, slugs: dict[str, set[str]]) -> str | None:
    """The doc a cite's path names: relative to the citing file's directory, then docs/, then the
    root."""
    for base in (posixpath.dirname(citing), "docs", ""):
        candidate = posixpath.normpath(posixpath.join(base, path))
        if candidate in slugs:
            return candidate
    return None


def check_cites(file: str, lines: list[str], slugs: dict[str, set[str]]) -> list[Violation]:
    found = []
    for number, line in unfenced(lines):
        for match in CITE.finditer(URL.sub(" ", line)):
            path, anchor = match.groups()
            cite = match.group(0)
            target = resolve(file, path, slugs)
            if target is None:
                where = posixpath.dirname(file) or "the root"
                detail = f"{cite}: no {path} under {where}, docs/ or the root"
                fix = "point the cite at an existing doc"
                found.append(Violation(file, "cite", detail, fix, number))
            elif anchor not in slugs[target]:
                detail = f"{cite}: {target} has no heading with that slug"
                close = get_close_matches(anchor, sorted(slugs[target]), n=1)
                fix = f"cite {path}#{close[0]}" if close else f"cite a heading of {target}"
                found.append(Violation(file, "cite", detail, fix, number))
    return found


def check_tree(root: Path) -> Report:
    """Every checked doc's size against its cap, and every violation of the doc rules under root."""
    files = doc_files(root)
    raws = {file: (root / file).read_bytes() for file in files}
    texts = {
        file: raw.removeprefix(UTF8_BOM).decode("utf-8", errors="replace").replace("\r\n", "\n")
        for file, raw in raws.items()
    }
    slugs = {file: headings(text) for file, text in texts.items()}
    checked = [file for file in files if not file.startswith(SOURCES)]
    sizes = [FileSize(file, len(raws[file]), cap_for(file)) for file in checked]
    violations = []
    for entry in sizes:
        file = entry.file
        if entry.margin is not None and entry.margin < 0:
            detail = f"{entry.size:,} bytes, {-entry.margin:,} over the {entry.cap:,} cap"
            fix = "cut duplicated text; never split a doc by concern (docs/workflow.md#docs-rules)"
            violations.append(Violation(file, "size", detail, fix))
        violations += check_encoding(file, raws[file])
        lines = split_lines(texts[file])
        violations += check_layout(file, lines)
        violations += check_cites(file, lines, slugs)
    return Report(sizes, violations)
