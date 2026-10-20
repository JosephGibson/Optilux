"""The similarity check's core (docs/shader.md#policy, docs/plans/m3.md D55), pure: no file, git
or config is read here; `verify similarity` and the pre-commit hook hand it the texts.

GLSL is reduced to normalized tokens: comments, whitespace and preprocessor directives dropped,
a `#define`'s replacement kept (its name and parameters dropped) unless it is a value (is_value),
every identifier reduced to
ID, every number to NUM and true and false to BOOL; keywords and punctuators stay as written. So
neither layout, comments nor renamed identifiers hide a copy.

Each file's k-grams are hashed (Karp-Rabin) and winnowed: every window of w consecutive hashes
keeps its rightmost minimum (Schleimer, Wilkerson and Aiken, SIGMOD 2003, sections 1 and 3:
plans/m3.md P10). A match of t = w + k - 1 tokens or more shares at least one fingerprint, and
none shorter than k shares any. Winnowing guarantees one shared fingerprint, not the span: each
shared fingerprint is checked token by token and extended over both sequences to its whole
match, so a match is measured in tokens, never in fingerprints.
"""

import re
import zlib
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

# The GLSL sources: Iris's stage files (.vsh, .gsh, .fsh, .csh, .tcs, .tes), .glsl includes,
# and glslang's stage endings (.vert, .tesc, .tese, .geom, .frag, .comp), which the control pack
# uses for its includes (Atomosphere.glsl.frag). Any other file (properties, lang, images) is no
# GLSL and is left out on both sides.
IRIS_STAGES = (".vsh", ".gsh", ".fsh", ".csh", ".tcs", ".tes")
GLSLANG_STAGES = (".vert", ".tesc", ".tese", ".geom", ".frag", ".comp")
SUFFIXES = frozenset((*IRIS_STAGES, ".glsl", *GLSLANG_STAGES))

IDENTIFIER = "ID"
NUMBER = "NUM"
BOOLEAN = "BOOL"
# GLSL 4.60's keywords (section 3.6) bar the types matched by TYPE_WORD: a keyword keeps its text,
# as renaming one changes the code; true and false are boolean literals (BOOLEAN).
KEYWORDS = frozenset(
    """
    const uniform buffer shared attribute varying coherent volatile restrict readonly writeonly
    atomic_uint layout centroid flat smooth noperspective patch sample invariant precise break
    continue do for while switch case default if else subroutine in out inout int void bool
    float double discard return uint lowp mediump highp precision struct
    """.split()  # noqa: SIM905 the spec's keyword table, kept as its words
)
TYPE_WORD = re.compile(
    r"[iubd]?vec[234]|d?mat[234](?:x[234])?"
    r"|[iu]?(?:sampler|image)(?:1D|2D|3D|Cube|2DRect|Buffer|2DMS)(?:Array)?(?:Shadow)?"
)
BOOLEANS = frozenset(("true", "false"))
# One scan over the spliced text: comments, newlines, blanks, words, numbers (C's
# preprocessing number, so 1.0e-5, 0x1Fu and 2.0lf are one token each), multi-character
# punctuators before single ones, and any other character as itself.
SCAN = re.compile(
    r"(?P<block>/\*.*?(?:\*/|\Z))"
    r"|(?P<line>//[^\n]*)"
    r"|(?P<newline>\n)"
    r"|(?P<blank>[ \t\f\v]+)"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<number>\.?[0-9](?:[eEpP][+-]|[0-9A-Za-z_.])*)"
    r"|(?P<punct><<=|>>=|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||\^\^|[-+*/%&|^]=|##|\.\.\."
    r"|[-+*/%<>=!~&|^?:;,.()\[\]{}#])"
    r"|(?P<other>.)",
    re.DOTALL,
)
# Karp-Rabin over 32-bit token codes: the Mersenne prime 2^61 - 1 as the modulus and a fixed
# base, so a hash is the same in every process (Python's str hash is salted per process).
MODULUS = (1 << 61) - 1
BASE = 1_000_003


@dataclass(frozen=True)
class Source:
    """One file's normalized tokens and the physical line each starts on."""

    name: str
    tokens: tuple[str, ...]
    lines: tuple[int, ...]


@dataclass(frozen=True)
class Match:
    """A maximal run of equal tokens: `length` tokens from `candidate_start` in the candidate
    and from `reference_start` in the reference, with the lines they span in each file."""

    candidate: str
    reference: str
    candidate_start: int
    reference_start: int
    length: int
    candidate_lines: tuple[int, int]
    reference_lines: tuple[int, int]

    def text(self) -> str:
        first, last = self.candidate_lines
        start, end = self.reference_lines
        return (
            f"{self.candidate}:{first}-{last} matches {self.reference}:{start}-{end} "
            f"({self.length} tokens)"
        )


def is_source(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in SUFFIXES


def splice(text: str) -> tuple[str, list[int]]:
    """The text with CRLF and CR read as LF and every backslash-newline removed (GLSL joins those
    lines before comments or directives are read), and the offsets in it where each physical
    line after the first starts."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts, starts, length = [], [], 0
    for index, piece in enumerate(text.split("\\\n")):
        if index:
            starts.append(length)  # a removed continuation still ends a physical line
        starts.extend(length + match.start() + 1 for match in re.finditer("\n", piece))
        parts.append(piece)
        length += len(piece)
    return "".join(parts), sorted(starts)


def kind(word: str) -> str:
    if word in BOOLEANS:
        return BOOLEAN
    if word in KEYWORDS or TYPE_WORD.fullmatch(word):
        return word
    return IDENTIFIER


def replacement(directive: list[tuple[str, str, int, int]]) -> list[tuple[str, int]]:
    """A `#define`'s replacement tokens, (normalized token, offset); none for any other
    directive. `directive` holds its raw tokens after the `#`: (token, kind, start, end)."""
    if len(directive) < 2 or directive[0][0] != "define" or directive[1][1] != "word":
        return []
    body = directive[2:]
    name_end = directive[1][3]
    if body and body[0][0] == "(" and body[0][2] == name_end:  # a function-like macro's params
        close = next((i for i, item in enumerate(body) if item[0] == ")"), len(body) - 1)
        body = body[close + 1 :]
    found = [(normalized(piece, group), start) for piece, group, start, _ in body]
    if is_value([piece for piece, _ in found]):
        return []
    return found


def is_value(replacement: list[str]) -> bool:
    """A replacement that is a value, not code: one token (an option's number or flag, an alias)
    or a signed number. Kept, values line up into runs of NUM that say nothing of their source:
    Unbound r5.9.3's lib/common.glsl holds 111 in a row, which any fresh pack's options list of
    72 values would match."""
    return len(replacement) == 1 or (
        replacement[:1] in (["-"], ["+"]) and replacement[1:] == [NUMBER]
    )


def normalized(piece: str, group: str) -> str:
    if group == "word":
        return kind(piece)
    return NUMBER if group == "number" else piece


def tokenize(name: str, text: str) -> Source:
    """A GLSL file's normalized tokens with their physical lines (module docstring)."""
    spliced, starts = splice(text)
    found: list[tuple[str, int]] = []
    directive: list[tuple[str, str, int, int]] | None = None
    line_start = True  # only blanks and comments since the last newline
    for match in SCAN.finditer(spliced):
        group = match.lastgroup or "other"
        if group in ("block", "line", "blank"):
            continue
        if group == "newline":
            if directive is not None:
                found += replacement(directive)
                directive = None
            line_start = True
            continue
        piece, start = match.group(), match.start()
        if directive is not None:
            directive.append((piece, group, start, match.end()))
        elif line_start and piece == "#":
            directive = []
        else:
            found.append((normalized(piece, group), start))
        line_start = False
    if directive is not None:
        found += replacement(directive)
    lines = [line_of(starts, offset) for _, offset in found]
    return Source(name, tuple(token for token, _ in found), tuple(lines))


def line_of(starts: list[int], offset: int) -> int:
    """The physical line (from 1) of an offset in the spliced text."""
    low, high = 0, len(starts)
    while low < high:  # bisect_right: the line starts at or before offset
        middle = (low + high) // 2
        if starts[middle] <= offset:
            low = middle + 1
        else:
            high = middle
    return low + 1


def kgram_hashes(tokens: tuple[str, ...], k: int) -> list[int]:
    """Each k-gram's Karp-Rabin hash, by its first token's index."""
    if len(tokens) < k:
        return []
    codes = [zlib.crc32(token.encode("utf-8")) for token in tokens]
    top = pow(BASE, k - 1, MODULUS)
    value = 0
    for code in codes[:k]:
        value = (value * BASE + code) % MODULUS
    hashes = [value]
    for index in range(k, len(codes)):
        value = ((value - codes[index - k] * top) * BASE + codes[index]) % MODULUS
        hashes.append(value)
    return hashes


def winnow(hashes: list[int], w: int) -> list[int]:
    """The positions winnowing selects: each window of w consecutive hashes keeps its rightmost
    minimum, each position once. Fewer than w hashes make no window, so none is selected: such a
    file holds fewer than t tokens, too few for a match of t."""
    selected: list[int] = []
    window: deque[int] = deque()  # positions whose hashes strictly increase from the front
    for index, value in enumerate(hashes):
        while window and hashes[window[-1]] >= value:
            window.pop()  # an equal hash to the left is dropped: the rightmost one wins
        window.append(index)
        if window[0] <= index - w:
            window.popleft()
        if index >= w - 1 and (not selected or selected[-1] != window[0]):
            selected.append(window[0])
    return selected


def fingerprints(source: Source, k: int, w: int) -> dict[int, list[int]]:
    """The winnowed fingerprints of one file: hash -> the token positions that carry it."""
    hashes = kgram_hashes(source.tokens, k)
    found: dict[int, list[int]] = {}
    for position in winnow(hashes, w):
        found.setdefault(hashes[position], []).append(position)
    return found


def matches(
    candidates: Iterable[Source], references: Iterable[Source], k: int, w: int
) -> list[Match]:
    """Every maximal match reached from a fingerprint a candidate shares with a reference: the
    k-gram checked token by token (a hash collision is skipped), then extended left and right
    over both token sequences. Fingerprints on one run give one match, as a pair inside a match
    already found on its diagonal is skipped."""
    if k < 1 or w < 1:
        raise ValueError(f"k {k} and w {w} must be 1 or more")
    refs = list(references)
    index: dict[int, list[tuple[int, int]]] = {}
    for number, ref in enumerate(refs):
        for value, positions in fingerprints(ref, k, w).items():
            index.setdefault(value, []).extend((number, position) for position in positions)
    found: list[Match] = []
    for cand in candidates:
        a = cand.tokens
        seen: dict[tuple[int, int], list[tuple[int, int]]] = {}  # (ref, diagonal) -> spans
        for value, positions in fingerprints(cand, k, w).items():
            for number, j in index.get(value, ()):
                b = refs[number].tokens
                for i in positions:
                    spans = seen.setdefault((number, i - j), [])
                    if any(first <= i and i + k <= end for first, end in spans):
                        continue
                    if a[i : i + k] != b[j : j + k]:
                        continue  # equal hashes, different tokens
                    first, start = i, j
                    while first and start and a[first - 1] == b[start - 1]:
                        first, start = first - 1, start - 1
                    end, stop = i + k, j + k
                    while end < len(a) and stop < len(b) and a[end] == b[stop]:
                        end, stop = end + 1, stop + 1
                    spans.append((first, end))
                    found.append(match(cand, refs[number], first, start, end - first))
    return sorted(found, key=lambda m: (-m.length, m.candidate, m.candidate_start, m.reference))


def match(cand: Source, ref: Source, first: int, start: int, length: int) -> Match:
    last, stop = first + length - 1, start + length - 1
    return Match(
        candidate=cand.name,
        reference=ref.name,
        candidate_start=first,
        reference_start=start,
        length=length,
        candidate_lines=(cand.lines[first], cand.lines[last]),
        reference_lines=(ref.lines[start], ref.lines[stop]),
    )


def sources(texts: Mapping[str, str]) -> list[Source]:
    """The GLSL files of a name -> text mapping, tokenized, in name order."""
    return [tokenize(name, texts[name]) for name in sorted(texts) if is_source(name)]
