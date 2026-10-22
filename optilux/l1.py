"""L1, Iris-faithful (docs/offline.md#levels, plans/m3.md D69): a dump record's prints (`run`'s
dump kind, D60) judged against its baseline's, the first variant.

- Dump equality and took-effect: per candidate and dimension, its print against the baseline's
  there, stage by stage (a file's name without Iris's NNN_ counter: ShaderPrinter numbers the
  programs per pipeline). Equal in a dimension, the candidate is skipped there; equal in every
  dimension, it did not take effect: both closures (offline.md#decision-powers). Prints are
  compared only with prints of the same record, so only with debug prints (D60, P13).
- The premise check: the source files the candidate changes (its zip against the baseline's, both
  kept under raw/<run>/packs/ or the reference pack's pinned zip), the functions each changes, and
  whether one is defined in a dumped stage of the candidate and reachable from its main. It closes
  only when every change lies in a function's text: not compiled (no dumped stage defines one) or
  not executed (defined, never reached: Iris keeps uncalled functions under its debug flag, P13).
  A change elsewhere, a name a #define also takes, or a file it cannot parse leave it undecided.
- The impact matrix: changed files -> the program files including them -> config/pipeline.json's
  passes in each dimension -> their views; a changed option -> the passes it names.
- The audit (docs/shader.md#pipeline-spec): per dump, the passes enabled there (their dimension,
  no `program.<name>.enabled = false` in its preprocessed.properties), each buffer a pass samples
  written by an enabled pass before it, each buffer written read after it (or the screen), and
  each custom uniform a pass reads defined wherever the pass runs. Iris's own uniforms wait for a
  list read from its jar.

Pure but for reading the record's raw folder and the store's zip; the run reaches it through
`check L1 -` in a child process, so its rules stay out of the harness hash (run-record.md#identity).
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from optilux import offline, record

PATCHED = "patched_shaders"
PREPROCESSED = "preprocessed.properties"
# A stage file of a print: Iris's counter, the program's name, its stage ending (PatchShaderType).
COUNTED = re.compile(r"(?P<n>\d{3})_(?P<rest>.+)")
STAGE_FILE = re.compile(r"(?P<program>.+)\.(?P<ending>vsh|tcs|tes|gsh|fsh|csh)")
DUMP_EQUALITY = "L1 dump equality"
PREMISE = "L1 premise check"
# Each closing method with the verdicts it may record (offline.md#decision-powers).
METHODS = {DUMP_EQUALITY: ("no effect", "skip"), PREMISE: ("not compiled", "not executed")}
# GLSL as the premise check reads it: comments dropped, directive lines apart, then tokens.
TOKEN = re.compile(r"[A-Za-z_]\w*|\d[\w.]*|\S")
IDENT = re.compile(r"[A-Za-z_]\w*")
DEFINED = re.compile(r"^\s*#\s*define\s+(?P<name>\w+)", re.M)
# A line ending in a backslash continues on the next (a #define's body).
CONTINUED = re.compile(r"\\[ \t]*\r?\n")
# Names no function takes: GLSL's statement and declaration keywords (a call's name never is one).
KEYWORDS = frozenset(
    (
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "default",
        "return",
        "break",
        "continue",
        "discard",
        "layout",
        "struct",
        "uniform",
        "in",
        "out",
        "inout",
        "const",
    )
)
# The files a print shows (printed): GLSL by its ending, and the properties files Iris prints.
GLSL_ENDINGS = (".glsl", *(f".{e}" for e in offline.STAGES))
PRINTED_PROPERTIES = (
    "shaders.properties",
    "block.properties",
    "item.properties",
    "entity.properties",
)
# The audit: buffers a pass samples or writes (Iris's colortex aliases), and Iris's stage order.
BUFFER = re.compile(r"colortex\d+|gcolor|gdepth|gnormal|composite|gaux[1-4]|shadowcolor[01]?")
SCREEN = "screen"
STAGE_ORDER = (
    "shadow",
    "shadowcomp",
    "begin",
    "prepare",
    "gbuffers",
    "deferred",
    "composite",
    "final",
)
DISABLED = re.compile(r"^\s*program\.(?P<name>[\w/-]+)\.enabled\s*[=:]\s*false\s*$", re.M)
CUSTOM_UNIFORM = re.compile(r"^\s*uniform\.\w+\.(?P<name>\w+)\s*[=:]", re.M)


class L1Error(RuntimeError):
    """A record L1 cannot judge; the message names the fix."""


# Dump equality.


def stage_key(name: str) -> str:
    """A print's file by what it is: its name from game/ without Iris's NNN_ counter."""
    folder, _, base = name.rpartition("/")
    counted = COUNTED.fullmatch(base)
    base = counted["rest"] if counted else base
    return f"{folder}/{base}" if folder else base


def keyed(files: Mapping[str, str]) -> dict[str, str]:
    """A print's files by stage_key; L1Error when two files share one (two programs of a name)."""
    found: dict[str, str] = {}
    for name, digest in files.items():
        key = stage_key(name)
        if key in found:
            raise L1Error(f"two files of the print are {key}; fix: tell them apart in l1.stage_key")
        found[key] = digest
    return found


def compare_prints(base: Mapping[str, str], cand: Mapping[str, str]) -> dict:
    """A candidate's print against the baseline's: equal (their manifests: record.dump_manifest),
    the stages each has and the other lacks, those that differ, and whether only Iris's counter
    moved (the same stages, numbered otherwise)."""
    bk, ck = keyed(base), keyed(cand)
    changed = sorted(k for k in bk.keys() & ck.keys() if bk[k] != ck[k])
    equal = record.dump_manifest(dict(base)) == record.dump_manifest(dict(cand))
    found = {
        "equal": equal,
        "changed": changed,
        "baselineOnly": sorted(bk.keys() - ck.keys()),
        "candidateOnly": sorted(ck.keys() - bk.keys()),
    }
    found["renumbered"] = not equal and not (
        changed or found["baselineOnly"] or found["candidateOnly"]
    )
    return found


def prints(found: dict) -> dict[tuple[str, str], dict]:
    """Each dump of an ok-shaped record by (variant, dimension): its capture and its files."""
    dumps = found.get("dumps") or {}
    taken: dict[tuple[str, str], dict] = {}
    for capture in found.get("captures") or []:
        files = dumps.get(capture["dump"]["manifest"])
        if files is None:
            raise L1Error(f"dump {capture['index']}'s manifest is not in `dumps`; fix: its record")
        key = (capture["variant"], capture["dimension"])
        if key in taken:
            raise L1Error(f"{key[0]} was dumped twice in {key[1]}; fix: its record")
        taken[key] = {"capture": capture, "files": files}
    return taken


def equality(found: dict) -> tuple[str, list[dict]]:
    """The baseline and each candidate's dump equality per dimension the baseline was dumped in:
    the comparison, the skips and, equal everywhere, the closure."""
    variants = [v["id"] for v in found.get("variants") or []]
    if not variants:
        raise L1Error("the record holds no variant; fix: a dump run that dumped one")
    base, *candidates = variants  # one variant: a print for L2, no candidate to judge
    taken = prints(found)
    dims = [d for d in record.DIMENSIONS if (base, d) in taken]
    if not dims:
        raise L1Error(f"the baseline {base} has no dump; fix: a dump run that ended with one")
    judged = []
    for vid in candidates:
        rows = {}
        for dim in dims:
            if (vid, dim) not in taken:
                rows[dim] = None
                continue
            rows[dim] = compare_prints(taken[(base, dim)]["files"], taken[(vid, dim)]["files"])
        equal = [d for d in dims if rows[d] is not None and rows[d]["equal"]]
        whole = all(rows[d] is not None for d in dims)
        evidence = {
            d: {
                "baseline": taken[(base, d)]["capture"]["dump"]["manifest"],
                "candidate": taken[(vid, d)]["capture"]["dump"]["manifest"],
            }
            for d in equal
        }
        closures = []
        if equal and whole and len(equal) == len(dims):
            closures.append(
                {
                    "method": DUMP_EQUALITY,
                    "power": "close",
                    "verdict": "no effect",
                    "dimensions": equal,
                    "evidence": evidence,
                }
            )
        elif equal:
            closures.append(
                {
                    "method": DUMP_EQUALITY,
                    "power": "close",
                    "verdict": "skip",
                    "dimensions": equal,
                    "evidence": evidence,
                }
            )
        judged.append(
            {
                "variant": vid,
                "tookEffect": any(rows[d] is not None and not rows[d]["equal"] for d in dims),
                "undumped": [d for d in dims if rows[d] is None],
                "dimensions": rows,
                "closures": closures,
            }
        )
    return base, judged


# GLSL as the premise check reads it.


@dataclass
class Unit:
    """A GLSL text's functions: each name with its definitions' tokens (signature and body, its
    directive lines in place) and the names its bodies call; the tokens outside every definition,
    in order; whether its braces balance (else nothing in it is judged)."""

    functions: dict[str, list[str]] = field(default_factory=dict)
    calls: dict[str, set[str]] = field(default_factory=dict)
    outside: list[str] = field(default_factory=list)
    balanced: bool = True


def tokens_of(source: str) -> list[str]:
    """A GLSL text's tokens: comments dropped, a line ending in a backslash joined to the next
    (a #define's body stays in its directive), each directive line one token in its place (its
    words single-spaced), every other line's tokens."""
    text = CONTINUED.sub(" ", offline.COMMENT.sub(" ", source))
    tokens: list[str] = []
    for line in offline.lines_of(text):
        if line.lstrip().startswith("#"):
            tokens.append(" ".join(line.split()))
        else:
            tokens += TOKEN.findall(line)
    return tokens


def glsl_unit(source: str) -> Unit:
    """The functions of a GLSL text (tokens_of): at depth 0 each `{` right after a `)` whose `(`
    follows a name that is no keyword is a definition, from the token before that name to its
    `}`. Directive tokens open and close nothing."""
    tokens = tokens_of(source)
    unit = Unit()
    depth, start, i, last = 0, 0, 0, 0
    while i < len(tokens):
        word = tokens[i]
        if word == "{" and depth == 0 and i and tokens[i - 1] == ")":
            opened = matching_paren(tokens, i - 1)
            name = tokens[opened - 1] if opened else ""
            if IDENT.fullmatch(name) and name not in KEYWORDS:
                end = matching_brace(tokens, i)
                if end is None:
                    unit.balanced = False
                    return unit
                head = max(start, (opened or 0) - 2)
                unit.outside += tokens[last:head]
                unit.functions.setdefault(name, []).append(" ".join(tokens[head : end + 1]))
                body = [t for t in tokens[i + 1 : end] if not t.startswith("#")]
                unit.calls.setdefault(name, set()).update(
                    t
                    for n, t in enumerate(body[:-1])
                    if IDENT.fullmatch(t) and body[n + 1] == "(" and t not in KEYWORDS
                )
                i = start = last = end + 1
                continue
        if word == "{":
            depth += 1
        elif word == "}":
            depth -= 1
            if depth < 0:
                unit.balanced = False
                return unit
        elif (word == ";" or word.startswith("#")) and depth == 0:
            start = i + 1
        i += 1
    unit.outside += tokens[last:]
    unit.balanced = depth == 0
    return unit


def matching_paren(tokens: list[str], close: int) -> int | None:
    depth = 0
    for i in range(close, -1, -1):
        if tokens[i] == ")":
            depth += 1
        elif tokens[i] == "(":
            depth -= 1
            if depth == 0:
                return i
    return None


def matching_brace(tokens: list[str], opened: int) -> int | None:
    depth = 0
    for i in range(opened, len(tokens)):
        if tokens[i] == "{":
            depth += 1
        elif tokens[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def reachable(unit: Unit, entry: str = "main") -> set[str]:
    """The functions a stage's entry reaches through its calls (by name: GLSL overloads count as
    one)."""
    seen: set[str] = set()
    queue = [entry] if entry in unit.functions else []
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue += [c for c in unit.calls.get(name, ()) if c in unit.functions and c not in seen]
    return seen


# The premise check.


def changed_files(base: Mapping[str, bytes], cand: Mapping[str, bytes]) -> list[str]:
    """The files under shaders/ the candidate changes, adds or removes, by path, by their bytes."""
    return sorted(path for path in base.keys() | cand.keys() if base.get(path) != cand.get(path))


def printed(path: str) -> bool:
    """Whether a print shows what the file holds: GLSL (a stage or an include, whose text Iris
    compiles), shaders.properties (game/preprocessed.properties) or an ID map (its patched copy).
    A texture, its .mcmeta, a lang file or dimension.properties reach no print, so dump equality
    cannot speak for a change to one (offline.md#levels)."""
    pure = PurePosixPath(path)
    return pure.suffix in GLSL_ENDINGS or path in PRINTED_PROPERTIES


def changed_functions(
    base: str | None, cand: str | None
) -> tuple[list[str], list[str], str | None]:
    """One file's change: the functions it changes or adds (judged in the candidate's prints),
    those it removes (in the baseline's), and why the premise check cannot judge the file, if it
    cannot: a side that does not parse, text changed outside a function's, or a comment changed
    (Iris reads RENDERTARGETS, DRAWBUFFERS and option lists in comments, which no print shows)."""
    bu, cu = glsl_unit(base or ""), glsl_unit(cand or "")
    if not bu.balanced or not cu.balanced:
        return [], [], "it does not parse (its braces do not balance)"
    changed = sorted(n for n in cu.functions if cu.functions[n] != bu.functions.get(n))
    removed = sorted(n for n in bu.functions if n not in cu.functions)
    if offline.COMMENT.findall(base or "") != offline.COMMENT.findall(cand or ""):
        return changed, removed, "a comment changed (Iris reads directives in comments)"
    if bu.outside != cu.outside:
        return changed, removed, "text changed outside its functions'"
    if not changed and not removed:
        return changed, removed, "only its whitespace changed"
    return changed, removed, None


def stage_units(raw: Path, capture: dict, files: Mapping[str, str]) -> dict[str, Unit]:
    """A dump's stage files under raw/<run>/, each held to its recorded sha256, parsed."""
    folder = raw / capture["dump"]["folder"]
    found = {}
    for name, digest in files.items():
        key = stage_key(name)
        if not name.startswith(f"{PATCHED}/") or not STAGE_FILE.fullmatch(key.split("/", 1)[1]):
            continue
        path = folder / name
        try:
            data = path.read_bytes()
        except OSError as error:
            raise L1Error(f"{path}: {error}; fix: the run's raw folder as it wrote it") from None
        if hashlib.sha256(data).hexdigest() != digest:
            raise L1Error(f"{path} does not hash to its record's sha256; fix: rerun the dump")
        found[key] = glsl_unit(data.decode("utf-8", errors="replace"))
    return found


def premise(
    base: offline.Pack,
    cand: offline.Pack,
    paths: list[str],
    cand_units: Mapping[str, Mapping[str, Unit]],
    base_units: Mapping[str, Mapping[str, Unit]],
) -> dict:
    """The premise check of one candidate (D69) over the files it changes (`paths`): the functions
    each changes, and per changed function the dumped stages (by dimension) that define it and
    those whose main reaches it; the verdict: holds, not compiled, not executed, or undecided
    (why). The caller decides whether a verdict closes (premise_closes)."""
    if not paths:
        return {"verdict": "no source change", "files": [], "undecided": []}
    macros = {
        m["name"]
        for text in (*base.files.values(), *cand.files.values())
        for m in DEFINED.finditer(text)
    }
    files, undecided = [], []
    for units in (cand_units, base_units):
        if not units or any(not us for us in units.values()):
            undecided.append("a dimension's print holds no stage")
        if any(not u.balanced for us in units.values() for u in us.values()):
            undecided.append("a dumped stage does not parse")
    defined_any = reached_any = False
    for path in paths:
        if PurePosixPath(path).suffix not in GLSL_ENDINGS:
            files.append({"file": path, "functions": [], "removed": []})
            undecided.append(f"{path} is no GLSL")
            continue
        changed, removed, why = changed_functions(base.files.get(path), cand.files.get(path))
        entry: dict = {"file": path, "functions": [], "removed": []}
        if why is not None:
            undecided.append(f"{path}: {why}")
        for kind, names, units in (
            ("functions", changed, cand_units),
            ("removed", removed, base_units),
        ):
            for name in names:
                if name in macros:
                    undecided.append(f"{path}: {name} is also a #define's name")
                defined = {
                    d: sorted(k for k, u in us.items() if name in u.functions)
                    for d, us in units.items()
                }
                reached = {
                    d: sorted(k for k, u in us.items() if name in reachable(u))
                    for d, us in units.items()
                }
                defined_any |= any(defined.values())
                reached_any |= any(reached.values())
                entry[kind].append(
                    {
                        "name": name,
                        "defined": sum(len(v) for v in defined.values()),
                        "reached": sum(len(v) for v in reached.values()),
                        "reachedIn": {d: v for d, v in reached.items() if v},
                    }
                )
        files.append(entry)
    if undecided:
        verdict = "undecided"
    elif reached_any:
        verdict = "holds"
    elif defined_any:
        verdict = "not executed"
    else:
        verdict = "not compiled"
    return {"verdict": verdict, "files": files, "undecided": undecided}


def dead_only(
    base_units: Mapping[str, Unit], cand_units: Mapping[str, Unit], row: dict, dead: set[str]
) -> str | None:
    """Why a print's difference from the baseline's is not just the dead functions `dead` (None
    when it is): a stage only one side has, a differing file that is no stage, or a differing
    stage whose other text, or a function main reaches, differs too."""
    if row["baselineOnly"] or row["candidateOnly"]:
        return "a stage only one print has"
    for key in row["changed"]:
        bu, cu = base_units.get(key), cand_units.get(key)
        if bu is None or cu is None:
            return f"{key} is no stage, and differs"
        if bu.outside != cu.outside:
            return f"{key} differs outside its functions"
        live = reachable(cu)
        for name in bu.functions.keys() | cu.functions.keys():
            if bu.functions.get(name) != cu.functions.get(name) and (
                name not in dead or name in live or name in reachable(bu)
            ):
                return f"{key}: {name} differs and is no dead changed function"
    return None


# The impact matrix and the audit.


def includers(pack: offline.Pack) -> dict[str, set[str]]:
    """Each file of the pack with the program files that include it, directly or through other
    includes (itself, for a program file)."""
    found: dict[str, set[str]] = {}
    programs = [
        p
        for p in pack.files
        if any(offline.program_file(p, f) for f in ("", *offline.WORLD_FOLDERS.values()))
    ]
    for program in programs:
        seen, queue = set(), [program]
        while queue:
            path = queue.pop()
            if path in seen or path not in pack.files:
                continue
            seen.add(path)
            for line in offline.lines_of(pack.files[path]):
                include = offline.INCLUDE.match(line)
                if include is not None:
                    try:
                        queue.append(offline.resolve(path, include["path"]))
                    except offline.L0Error:
                        continue
        for path in seen:
            found.setdefault(path, set()).add(program)
    return found


def impact(
    pack: offline.Pack, paths: Iterable[str], options: Iterable[str], passes: list[dict]
) -> list[dict]:
    """The impact matrix (docs/offline.md#levels): each changed file with the program files that
    include it, the passes those programs are in their dimensions (each dimension's folder:
    offline.folders) and the views of those passes; each changed option with the passes that name
    it and their views."""
    places = offline.folders(pack)
    by_file = includers(pack)
    rows = []
    for path in paths:
        programs = sorted(by_file.get(path, ()))
        hit = []
        for found in passes:
            for dim in found["dimensions"]:
                folder = places.get(dim, "")
                for program in programs:
                    pf = offline.program_file(program, folder)
                    if pf is not None and pf[0] == found["program"] and found["name"] not in hit:
                        hit.append(found["name"])
        rows.append(matrix_row(path, programs, hit, passes))
    for option in options:
        hit = [p["name"] for p in passes if p.get("option") == option]
        rows.append(matrix_row(f"option {option}", [], hit, passes))
    return rows


def matrix_row(change: str, programs: list[str], hit: list[str], passes: list[dict]) -> dict:
    views = [v for p in passes if p["name"] in hit for v in p["views"]]
    return {
        "change": change,
        "programs": programs,
        "passes": hit,
        "views": list(dict.fromkeys(views)),
    }


def audit(passes: list[dict], properties: Mapping[tuple[str, str], str]) -> list[str]:
    """The pipeline audit per dump (variant, dimension) and its preprocessed.properties: each
    buffer an enabled pass samples written by an enabled pass before it (else it reads stale data
    or zero), each buffer one writes read after it (or the screen), each custom uniform a pass
    reads defined wherever it is enabled."""
    problems = []
    customs = {
        key: {m["name"] for m in CUSTOM_UNIFORM.finditer(text)} for key, text in properties.items()
    }
    every_custom = set().union(*customs.values()) if customs else set()
    for (vid, dim), text in sorted(properties.items()):
        disabled = {m["name"] for m in DISABLED.finditer(text)}
        on = [p for p in passes if dim in p["dimensions"] and p["program"] not in disabled]
        where = f"{vid} in {dim}"
        for n, reader in enumerate(on):
            for sampler in reader["inputs"]["samplers"]:
                fed = any(sampler in written(p) and before(p, n, reader, on) for p in on)
                if BUFFER.fullmatch(sampler) and not fed:
                    problems.append(
                        f"{where}: {reader['name']} samples {sampler}, which no enabled pass "
                        "writes before it"
                    )
            problems += [
                f"{where}: {reader['name']} reads custom uniform {uniform}, undefined there"
                for uniform in reader["inputs"].get("uniforms", [])
                if uniform in every_custom and uniform not in customs[(vid, dim)]
            ]
        for writer in on:
            for buffer in sorted(written(writer) - {SCREEN}):
                read = any(
                    buffer in p["inputs"]["samplers"] and before(writer, on.index(p), p, on)
                    for p in on
                )
                if not read:
                    problems.append(
                        f"{where}: {writer['name']} writes {buffer}, which no enabled pass reads "
                        "after it"
                    )
    return problems


def written(found: dict) -> set[str]:
    return {o["buffer"] for o in found["outputs"]}


def before(writer: dict, at: int, reader: dict, on: list[dict]) -> bool:
    """Whether `writer` runs before `reader` (at `at` in `on`): an earlier stage, or the same
    stage earlier in pipeline.json."""
    w, r = STAGE_ORDER.index(writer["stage"]), STAGE_ORDER.index(reader["stage"])
    return w < r or (w == r and on.index(writer) < at)
