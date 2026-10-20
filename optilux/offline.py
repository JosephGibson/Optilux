"""docs/offline.md#levels' L0 (plans/m3.md M3.P04): a pack read as Iris 1.11.7 reads it, its
variant matrix preprocessed, compiled and linked by glslang per program and dimension, and the
profile check. `optilux check L0` adds verify's similarity check (optilux/verbs/check.py); `run`
runs it on an Optilux variant's zip in a child process, so no module here enters the measured
closure (docs/run-record.md#identity: harness).

Iris's rules, each read in the pinned jar with javap (M3.P04), never assumed:
- dimensions (ShaderPack): without dimension.properties a dimension takes its OptiFine folder
  (world0, world-1, world1) when that folder holds a program (a file of Iris's program names,
  ShaderPackSourceNames), else the base set: world0's when a world0 folder exists, the root's
  otherwise; never a merge. Iris defines no dimension macro. dimension.properties is not read
  here, so a pack whose file maps anything is refused.
- a program's source (ShaderPack's source provider): its includes expanded, absolute from shaders/
  or relative to the including file, every file's option lines edited to the variant's values
  (OptionAnnotatedSource.edit), then preprocessed with the environment defines (StandardMacros,
  IrisDefines). Iris runs JCPP, which never sees #version or #extension; L0 runs glslang -E with
  each define as -D, and glslang's preprocessor also defines __VERSION__ and a GL_ macro per
  extension it knows, so a conditional naming one is refused (unmodeled). Tessellation stages
  (read only under the TESSELLATION_SHADERS flag, ProgramSet) and compute programs are refused, as
  L0 does not build them.
- options (OptionAnnotatedSource, ParsedString, StringOption, OptionSet, ShaderPackOptions): a
  `#define NAME` with at most a comment after it is on/off (off when the line starts //); `#define
  NAME VALUE // ...[a b c]` is a value option whose values are the list split on single spaces,
  its default added; `const int|float|bool NAME = VALUE;` is an option only for Iris's 81 const
  names, a number needing the list. An on/off option, define or const, registers only when a file
  of its include-graph component tests NAME with `#ifdef NAME` or `#ifndef NAME` and nothing
  after; declarations of one name with different defaults drop the option, equal ones join their
  lists.
"""

import hashlib
import io
import os
import re
import subprocess
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SHADERS = "shaders"
# Iris's stage endings and glslang's names for them (glslang takes the stage from the ending).
STAGES = {"vsh": "vert", "tcs": "tesc", "tes": "tese", "gsh": "geom", "fsh": "frag", "csh": "comp"}
STAGE_NAMES = {
    "vsh": "vertex",
    "tcs": "tessellation control",
    "tes": "tessellation evaluation",
    "gsh": "geometry",
    "fsh": "fragment",
    "csh": "compute",
}
# The OptiFine folders a pack without dimension.properties maps (ShaderPack's constructor).
WORLD_FOLDERS = {
    "minecraft:overworld": "world0",
    "minecraft:the_nether": "world-1",
    "minecraft:the_end": "world1",
}
DIMENSION_PROPERTIES = "dimension.properties"
# OptionAnnotatedSource.VALID_CONST_OPTION_NAMES: the only consts Iris takes as options, 25 named
# and seven more for each shadow colour buffer 0 to 7.
CONST_OPTIONS = frozenset(
    [
        *"""
        shadowMapResolution shadowDistance voxelDistance shadowDistanceRenderMul
        entityShadowDistanceMul shadowIntervalSize generateShadowMipmap generateShadowColorMipmap
        shadowHardwareFiltering shadowtex0Mipmap shadowtexMipmap shadowtex1Mipmap
        shadowtex0Nearest shadowtexNearest shadow0MinMagNearest shadowtex1Nearest
        shadow1MinMagNearest wetnessHalflife drynessHalflife eyeBrightnessHalflife
        centerDepthHalflife sunPathRotation ambientOcclusionLevel superSamplingLevel
        noiseTextureResolution
        """.split(),  # noqa: SIM905 the jar's set, kept as its words
        *(
            name.format(n)
            for n in range(8)
            for name in (
                "shadowcolor{}Mipmap",
                "shadowColor{}Mipmap",
                "shadowcolor{}Nearest",
                "shadowColor{}Nearest",
                "shadowcolor{}MinMagNearest",
                "shadowColor{}MinMagNearest",
                "shadowHardwareFiltering{}",
            )
        ),
    ]
)
# Iris's program names (ProgramId's group and name, ProgramArrayId's prefixes 0 to 99): a file in
# the root or a dimension folder is a program only under one of them with a stage ending
# (ShaderPackSourceNames), compute ones as <name>.csh or <name>_<a-z>.csh.
PROGRAM_NAMES = frozenset(
    [
        "shadow",
        *(f"shadow_{n}" for n in ("solid", "cutout", "water", "entities", "lightning", "block")),
        *(
            f"gbuffers_{n}"
            for n in (  # noqa: SIM905 the jar's names, kept as its words
                "basic line textured textured_lit skybasic skytextured clouds terrain "
                "terrain_solid terrain_cutout damagedblock block block_translucent beaconbeam item "
                "entities entities_translucent lightning particles particles_translucent "
                "entities_glowing armor_glint spidereyes hand weather water hand_water"
            ).split()
        ),
        *(f"dh_{n}" for n in ("terrain", "water", "generic", "shadow")),
        "final",
        *(
            f"{prefix}{n or ''}"
            for prefix in ("setup", "begin", "shadowcomp", "prepare", "deferred", "composite")
            for n in range(100)
        ),
    ]
)
COMPUTE = re.compile(r"(?P<name>\w+?)(?:_[a-z])?")
# The stages L0 builds: Iris reads .tcs and .tes only under TESSELLATION_SHADERS (ProgramSet).
BUILT = ("vsh", "gsh", "fsh")
INCLUDE = re.compile(r'\s*#include\s+"(?P<path>[^"]+)"\s*$')
# Java's \R, which OptionAnnotatedSource splits a file on; trailing empty lines dropped, as split
# drops them.
LINE_BREAK = re.compile("\r\n|[\n\r\u000b\u000c\u0085\u2028\u2029]")
# A Java float as Float.parseFloat reads the characters takeNumber scanned (a trailing f or d too).
JAVA_FLOAT = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[fFdD]?")

# Iris 1.11.7's environment defines (StandardMacros.createStandardEnvironmentDefines, then
# IrisDefines.createIrisReplacements), set as the bench tier gives them: the game's 3.3.0 Core
# Profile context (docs/platform.md, L1: "using drivers: 3.3.0 Core Profile Context"), Windows, no
# Distant Horizons, Continuity or Monocle, allowUnknownShaders unset. The version macros and the
# mipmap level come from the platform file and suite.json (iris_macros). The read was of this jar:
IRIS_JAR = "iris-fabric-1.11.7+mc26.3.jar"
IRIS_SHA512 = (
    "d8d3312f77fc52a48e4a6cd836fda33669bdebcb4de0b8c0d30adc808b287330"
    "a533e0baef355cc1ce6336a26851d9775369a802a4666b7b7a6266af20088f42"
)
# The mods whose presence adds a define (StandardMacros: isModLoaded), absent from the bench tier.
MACRO_MODS = ("distanthorizons", "continuity", "monocle")
DH_BLOCKS = (  # noqa: SIM905 the jar's enum, kept as its words
    "UNKNOWN LEAVES STONE WOOD METAL DIRT LAVA DEEPSLATE SNOW SAND TERRACOTTA NETHER_STONE WATER "
    "GRASS AIR ILLUMINATED"
).split()
# WorldRenderingPhase's values, in order: MC_RENDER_STAGE_<name> is its ordinal.
RENDER_PHASES = (  # noqa: SIM905 the jar's enum, kept as its words
    "NONE SKY SUNSET CUSTOM_SKY SUN MOON STARS VOID TERRAIN_SOLID TERRAIN_CUTOUT_MIPPED "
    "TERRAIN_CUTOUT ENTITIES BLOCK_ENTITIES DESTROY OUTLINE DEBUG HAND_SOLID TERRAIN_TRANSLUCENT "
    "TRIPWIRE PARTICLES CLOUDS RAIN_SNOW WORLD_BORDER HAND_TRANSLUCENT"
).split()
# BiomeCategories' values, in order: CAT_<name> is its ordinal.
BIOME_CATEGORIES = (  # noqa: SIM905 the jar's enum, kept as its words
    "NONE TAIGA EXTREME_HILLS JUNGLE MESA PLAINS SAVANNA ICY THE_END BEACH FOREST OCEAN DESERT "
    "RIVER SWAMP MUSHROOM NETHER MOUNTAIN UNDERGROUND"
).split()
FIXED_MACROS: tuple[tuple[str, str | None], ...] = (
    ("MC_GL_VERSION", "330"),
    ("MC_OS_WINDOWS", None),
    ("IS_IRIS", None),
    ("IRIS_REQUIRES_SEPARATE_ENTITY_DRAWS", None),
    ("MAX_COLOR_BUFFERS", "32"),
    ("IRIS_HAS_TRANSLUCENCY_SORTING", None),
    ("IRIS_INLINE_GLINT", None),
    ("IRIS_TAG_SUPPORT", "2"),
    *((f"DH_BLOCK_{name}", str(n)) for n, name in enumerate(DH_BLOCKS)),
    ("MC_NORMAL_MAP", None),
    ("MC_SPECULAR_MAP", None),
    ("MC_RENDER_QUALITY", "1.0"),
    ("MC_SHADOW_QUALITY", "1.0"),
    ("MC_HAND_DEPTH", "0.125"),
    *((f"MC_RENDER_STAGE_{name}", str(n)) for n, name in enumerate(RENDER_PHASES)),
    *((f"CAT_{name}", str(n)) for n, name in enumerate(BIOME_CATEGORIES)),
    ("PPT_NONE", "0"),
    ("PPT_RAIN", "1"),
    ("PPT_SNOW", "2"),
)
# What Iris defines from what only the running game knows: the driver's GLSL version, vendor,
# renderer and extensions (MC_<extension>), the biome registry, the usable feature flags, a
# resource pack's texture format, the colour spaces of a pack that supports colour correction.
# L0 cannot set them, so a stage that names one (but the defines L0 passes and the pack's own)
# fails unchecked instead of passing on a guess; the other systems' MC_OS_* are known undefined.
UNSET = re.compile(r"\b(?:MC_\w+|BIOME_\w+|IRIS_FEATURE_\w+|COLOR_SPACE_\w+)\b")
KNOWN_UNDEFINED = frozenset(("MC_OS_MAC", "MC_OS_LINUX", "MC_OS_UNKNOWN"))
# glslang's preprocessor defines __VERSION__ and a GL_ macro per profile and extension it knows
# (GL_core_profile, GL_ARB_gpu_shader5, ...: seen with -E, M3.P04), which Iris's JCPP never has, as
# Iris hides #version and #extension from it behind #warning lines (JcppProcessor); a conditional
# naming one takes another branch in L0 than in the game.
CONDITIONAL = re.compile(r"\s*#\s*(?:if|ifdef|ifndef|elif)\b(?P<rest>.*)")
GLSLANG_OWN = re.compile(r"\b(?:__VERSION__|GL_\w+)\b")
DEFINES = re.compile(r"\s*(?://)?\s*#\s*define\s+(?P<name>\w+)")
COMMENT = re.compile(r"/\*.*?(?:\*/|\Z)|//[^\n]*", re.S)
GLSLANG_ERROR = re.compile(r"ERROR: (?:(?P<file>[^:\s]+):(?P<line>\d+): )?(?P<text>.*)")
# glslang's closing lines: the error count, and the "compilation terminated" an error ends on.
SUMMARY = re.compile(r"\d+ compilation errors\.\s+No code generated\.|'' : compilation terminated")
# A link's reflection (-q): its sections, each a name and its entries' names.
REFLECTION = re.compile(r"^(?P<name>[A-Z][A-Za-z ]+ reflection):$")
GLSLANG_TIMEOUT = 120
VERSION_LINE = re.compile(r"Glslang Version: \d+:(?P<version>\S+)")


class L0Error(RuntimeError):
    """A pack, a tool or a config that L0 cannot read; the message names the fix."""


# The pack's files.


@dataclass(frozen=True)
class Pack:
    """A pack's files under shaders/ by their path from there, as text; what it was read from and,
    for a zip, the zip's sha512."""

    label: str
    files: dict[str, str]
    sha512: str | None = None


def text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def from_sources(
    label: str, sources: Iterable[tuple[str, bytes]], sha512: str | None = None
) -> Pack:
    """A pack from (archive name, bytes) pairs, as `pack build` zips them: the entries under
    shaders/ (Iris reads nothing else)."""
    prefix = f"{SHADERS}/"
    files = {
        name.removeprefix(prefix): text(data)
        for name, data in sources
        if name.startswith(prefix) and not name.endswith("/")
    }
    if not files:
        raise L0Error(f"{label} holds no {SHADERS}/ folder; fix: a pack with shaders/ at its root")
    return Pack(label, dict(sorted(files.items())), sha512)


def from_zip(label: str, data: bytes) -> Pack:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            sources = [(info.filename, archive.read(info)) for info in archive.infolist()]
    except (zipfile.BadZipFile, OSError) as error:
        raise L0Error(f"{label} is no zip ({error}); fix: a pack's zip") from None
    return from_sources(label, sources, hashlib.sha512(data).hexdigest())


def from_folder(label: str, folder: Path) -> Pack:
    """A pack folder: one holding shaders/, as shader/ does."""
    home = folder / SHADERS
    if not home.is_dir():
        raise L0Error(f"{label} holds no {SHADERS}/ folder; fix: the folder that holds it")
    sources = [
        (f"{SHADERS}/{path.relative_to(home).as_posix()}", path.read_bytes())
        for path in sorted(home.rglob("*"))
        if path.is_file()
    ]
    return from_sources(label, sources)


def lines_of(source: str) -> list[str]:
    found = LINE_BREAK.split(source)
    while found and not found[-1]:
        found.pop()
    return found


# Iris's option rules.


def java_whitespace(char: str) -> bool:
    """Character.isWhitespace: the space separators but the no-break ones, and the controls Java
    names."""
    if char in " \t\n\x0b\x0c\r\x1c\x1d\x1e\x1f":
        return True
    return unicodedata.category(char) in ("Zs", "Zl", "Zp") and char not in "\xa0\u2007\u202f"


def java_trim(value: str) -> str:
    """String.trim: every character up to U+0020 off both ends."""
    start, end = 0, len(value)
    while start < end and value[start] <= " ":
        start += 1
    while end > start and value[end - 1] <= " ":
        end -= 1
    return value[start:end]


class Parsed:
    """Iris's ParsedString: a line consumed from its start."""

    def __init__(self, line: str) -> None:
        self.text = line

    def literal(self, value: str) -> bool:
        if not self.text.startswith(value):
            return False
        self.text = self.text[len(value) :]
        return True

    def whitespace(self) -> bool:
        if not self.text or not java_whitespace(self.text[0]):
            return False
        self.text = java_trim(self.text)
        return True

    def comments(self) -> bool:
        if not self.literal("//"):
            return False
        self.text = self.text.lstrip("/")
        return True

    def end(self) -> bool:
        return not self.text

    def word(self) -> str | None:
        count = 0
        while count < len(self.text) and (
            self.text[count].isdigit() or self.text[count].isalpha() or self.text[count] == "_"
        ):
            count += 1
        return self.take(count) if count else None

    def number(self) -> str | None:
        """takeNumber: every character that is a digit or precedes one, then an f or F that is
        not the last character, kept when Float.parseFloat reads them."""
        line, count = self.text, 0
        while count < len(line):
            ahead = count + 1 < len(line) and line[count + 1].isdigit()
            if not (line[count].isdigit() or ahead):
                break
            count += 1
        if count > 0 and count + 1 < len(line) and line[count] in "fF":
            count += 1
        if not JAVA_FLOAT.fullmatch(java_trim(line[:count])):
            return None
        return self.take(count)

    def word_or_number(self) -> str | None:
        found = self.number()
        return found if found is not None else self.word()

    def take(self, count: int) -> str:
        taken, self.text = self.text[:count], self.text[count:]
        return taken


@dataclass(frozen=True)
class Declaration:
    """A line that declares an option: on/off (bool) or a value, a define or a const, its default
    as text (true or false for an on/off option) and a value option's allowed values."""

    name: str
    kind: str
    form: str
    default: str
    allowed: tuple[str, ...] = ()


def java_split(value: str) -> list[str]:
    """String.split(" "): the whole string when it holds no space, else its parts with every
    trailing empty one dropped, so a list of spaces alone holds none."""
    if " " not in value:
        return [value]
    parts = value.split(" ")
    while parts and not parts[-1]:
        parts.pop()
    return parts


def allowed_values(comment: str | None, default: str) -> tuple[str, ...] | None:
    """StringOption.create's list: the comment's first [...], split on single spaces, the default
    added when it is not there; None without a list."""
    if comment is None or (start := comment.find("[")) < 0:
        return None
    end = comment.find("]", start)
    if end < 0:
        return None
    values = java_split(comment[start + 1 : end])
    return tuple(values) if default in values else (*values, default)


def parse_line(line: str) -> Declaration | str | None:
    """A line as OptionAnnotatedSource.parseLine reads it: an option's declaration, the name an
    #ifdef or #ifndef tests (a str), or None."""
    if not any(key in line for key in ("#define", "const", "#ifdef", "#ifndef")):
        return None
    parsed = Parsed(java_trim(line))
    if parsed.literal("#ifdef") or parsed.literal("#ifndef"):
        if not parsed.whitespace():
            return None
        name = parsed.word()
        parsed.whitespace()
        return name if name is not None and parsed.end() else None
    if parsed.literal("const"):
        return parse_const(parsed)
    if "#define" in parsed.text:
        return parse_define(parsed)
    return None


def parse_const(parsed: Parsed) -> Declaration | None:
    if not parsed.whitespace():
        return None
    if parsed.literal("int") or parsed.literal("float"):
        valued = True
    elif parsed.literal("bool"):
        valued = False
    else:
        return None
    if not parsed.whitespace() or (name := parsed.word()) is None:
        return None
    parsed.whitespace()
    if not parsed.literal("="):
        return None
    parsed.whitespace()
    value = parsed.word_or_number()
    if value is None:
        return None
    parsed.whitespace()
    if not parsed.literal(";"):
        return None
    parsed.whitespace()
    comment = None
    if parsed.comments():
        comment = java_trim(parsed.text)
    elif not parsed.end():
        return None
    if name not in CONST_OPTIONS:
        return None
    if not valued:
        return Declaration(name, "bool", "const", value) if value in ("true", "false") else None
    allowed = allowed_values(comment, value)
    return Declaration(name, "value", "const", value, allowed) if allowed is not None else None


def parse_define(parsed: Parsed) -> Declaration | None:
    commented = parsed.comments()
    parsed.whitespace()
    if not parsed.literal("#define") or not parsed.whitespace():
        return None
    name = parsed.word()
    if name is None:
        return None
    spaced = parsed.whitespace()
    if parsed.end() or parsed.comments():
        return Declaration(name, "bool", "define", "false" if commented else "true")
    if not spaced or commented:
        return None
    value = parsed.word_or_number()
    if value is None:
        return None
    parsed.whitespace()
    if parsed.end() or not parsed.comments():
        return None
    allowed = allowed_values(java_trim(parsed.text), value)
    return Declaration(name, "value", "define", value, allowed) if allowed is not None else None


def edited(line: str, values: Mapping[str, str]) -> str:
    """A line with the variant's values in place, as OptionAnnotatedSource.edit writes them: an
    on/off define uncommented or commented out, a value define rewritten as `#define NAME VALUE`,
    a const's value replaced after its `=`."""
    found = parse_line(line)
    if not isinstance(found, Declaration) or found.name not in values:
        return line
    value = values[found.name]
    if found.form == "define" and found.kind == "bool":
        bare = Parsed(line)
        bare.whitespace()
        bare.comments()
        return bare.text if value == "true" else f"//{bare.text}"
    if found.form == "define":
        return f"#define {found.name} {value}"
    at = line.index("=")
    return line[:at] + line[at:].replace(found.default, value, 1)


@dataclass(frozen=True)
class Option:
    """An option as Iris registers it: on/off or a value, its default text and its values (an
    on/off option's are true and false), the files that declare it."""

    name: str
    kind: str
    default: str
    values: tuple[str, ...]
    files: tuple[str, ...]


@dataclass
class Options:
    """A pack's registered options by name, and the names dropped for declarations whose defaults
    differ (OptionSet's merge)."""

    found: dict[str, Option] = field(default_factory=dict)
    conflicts: dict[str, list[str]] = field(default_factory=dict)


# Program folders and includes.


def folders(pack: Pack) -> dict[str, str]:
    """The folder each dimension's programs come from ("" the root), as ShaderPack picks it: its
    OptiFine folder when that holds a program, else the base set, world0's when a world0 folder
    exists, else the root's. L0Error for a dimension.properties that maps anything (Iris reads an
    empty one as absent)."""
    mapping = pack.files.get(DIMENSION_PROPERTIES)
    if mapping is not None and any(
        line.strip() and not line.lstrip().startswith(("#", "!")) for line in lines_of(mapping)
    ):
        raise L0Error(
            f"{pack.label}: {SHADERS}/{DIMENSION_PROPERTIES} maps its dimensions, which L0 does "
            "not read yet; fix: the world0, world-1 and world1 folders (docs/offline.md#levels)"
        )
    base = "world0" if any(path.startswith("world0/") for path in pack.files) else ""
    return {
        dimension: folder if any(program_file(path, folder) for path in pack.files) else base
        for dimension, folder in WORLD_FOLDERS.items()
    }


def resolve(including: str, target: str) -> str:
    """An include's path from shaders/: absolute when it starts with /, else from the including
    file's folder; . and .. resolved, never above shaders/."""
    parts = [] if target.startswith("/") else list(PurePosixPath(including).parent.parts)
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise L0Error(
                    f'{including}: #include "{target}" leaves {SHADERS}/; fix: a path in it'
                )
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def expand(
    pack: Pack, path: str, values: Mapping[str, str], stack: tuple[str, ...] = ()
) -> list[tuple[str, int, str]]:
    """A file with its includes in place, each line (file, line number, text) with the variant's
    values applied (edited)."""
    if path in stack:
        cycle = " -> ".join((*stack, path))
        raise L0Error(f"{SHADERS}/{path}: an include cycle ({cycle}); fix: guard or cut it")
    source = pack.files.get(path)
    if source is None:
        where = f"{SHADERS}/{stack[-1]} includes" if stack else "the program names"
        raise L0Error(f"{where} {SHADERS}/{path}, which {pack.label} lacks; fix: add it")
    found = []
    for number, line in enumerate(lines_of(source), start=1):
        line = edited(line, values)
        include = INCLUDE.match(line)
        if include is not None:
            found += expand(pack, resolve(path, include["path"]), values, (*stack, path))
        elif java_trim(line).startswith("#include"):
            raise L0Error(
                f'{SHADERS}/{path}:{number}: {java_trim(line)} is no #include "<path>" Iris '
                "expands; fix: quote the path"
            )
        else:
            found.append((path, number, line))
    return found


def graph(pack: Pack) -> tuple[dict[str, set[str]], list[str]]:
    """Iris's include graph: every file reachable from the program files of the root and the
    world folders, each with the files it includes or is included by (its links), and the
    includes it cannot follow, over any of which Iris refuses the whole pack (ShaderPack)."""
    starts = sorted(
        path
        for path in pack.files
        if any(program_file(path, folder) for folder in ("", *WORLD_FOLDERS.values()))
    )
    links: dict[str, set[str]] = {}
    missing = []
    queue = list(starts)
    while queue:
        path = queue.pop(0)
        if path in links:
            continue
        links[path] = set()
        for number, line in enumerate(lines_of(pack.files[path]), start=1):
            include = INCLUDE.match(line)
            if include is None:
                continue
            try:
                target = resolve(path, include["path"])
            except L0Error as error:
                missing.append(str(error))
                continue
            if target not in pack.files:
                missing.append(
                    f"{SHADERS}/{path}:{number} includes {SHADERS}/{target}, which {pack.label} "
                    "lacks, and Iris refuses the pack over it; fix: add it"
                )
                continue
            queue.append(target)
            links[path].add(target)
    for path, targets in list(links.items()):
        for target in targets:
            links.setdefault(target, set()).add(path)
    return links, missing


def program_file(path: str, folder: str) -> tuple[str, str] | None:
    """(program, stage ending) of a file directly in `folder` that Iris reads as a program: one of
    its program names with a stage ending, a compute one perhaps with _a to _z; else None."""
    pure = PurePosixPath(path)
    parent = "" if str(pure.parent) == "." else str(pure.parent)
    ending = pure.suffix[1:]
    if parent != folder or ending not in STAGES:
        return None
    stem = pure.stem
    if ending == "csh" and stem not in PROGRAM_NAMES:
        match = COMPUTE.fullmatch(stem)
        stem = match["name"] if match else stem
    return (stem, ending) if stem in PROGRAM_NAMES else None


def components(links: Mapping[str, set[str]]) -> dict[str, int]:
    """Each file's weakly connected component of the include graph, numbered from 0."""
    found: dict[str, int] = {}
    for start in sorted(links):
        if start in found:
            continue
        number = len(set(found.values()))
        queue = [start]
        while queue:
            path = queue.pop()
            if path not in found:
                found[path] = number
                queue.extend(links[path] - found.keys())
    return found


def unmodeled(source: str, macros: set[str], own: set[str]) -> list[str]:
    """The names a stage reads that L0 cannot set as the game does: Iris's run-time defines
    (UNSET) other than the ones L0 passes and the pack's own, and glslang's own macros in a
    conditional (GLSLANG_OWN)."""
    bare = COMMENT.sub(" ", source)
    found = {
        name
        for name in UNSET.findall(bare)
        if name not in macros and name not in own and name not in KNOWN_UNDEFINED
    }
    for line in bare.splitlines():
        conditional = CONDITIONAL.match(line)
        if conditional is not None:
            found |= set(GLSLANG_OWN.findall(conditional["rest"]))
    return sorted(found)


def declared(pack: Pack) -> Options:
    """The pack's options as Iris registers them: per weakly connected component of its include
    graph (ShaderPackOptions), an on/off option, define or const, only where a file of the same
    component tests it; then merged by name (OptionSet), different defaults dropping it."""
    links, _ = graph(pack)
    component = components(links)
    sites: dict[str, list[tuple[str, Declaration]]] = {}
    tested: dict[int, set[str]] = {}
    for path in sorted(links):
        for line in lines_of(pack.files[path]):
            found = parse_line(line)
            if isinstance(found, str):
                tested.setdefault(component[path], set()).add(found)
            elif found is not None:
                sites.setdefault(found.name, []).append((path, found))
    options = Options()
    for name, all_sites in sorted(sites.items()):
        kept = [
            (path, found)
            for path, found in all_sites
            if found.kind != "bool" or name in tested.get(component[path], set())
        ]
        if not kept:
            continue  # an on/off option no file of its component tests is no option
        if len({d.kind for _, d in kept}) > 1 or len({d.default for _, d in kept}) > 1:
            options.conflicts[name] = [f"{SHADERS}/{p}: {d.default}" for p, d in kept]
            continue
        first = kept[0][1]
        if first.kind == "bool":
            values: tuple[str, ...] = ("true", "false")
        else:
            values = tuple(dict.fromkeys(v for _, d in kept for v in d.allowed))
        files = tuple(dict.fromkeys(f"{SHADERS}/{p}" for p, _ in kept))
        options.found[name] = Option(name, first.kind, first.default, values, files)
    return options


# Iris's macros.


def version_string(version: str) -> str:
    """StandardMacros.formatVersionString: major, then minor and patch as two digits each."""
    parts = version.split(".")
    if len(parts) < 2:
        raise L0Error(f"version {version!r} has no minor part; fix: the platform file's version")
    minor = parts[1] if len(parts[1]) != 1 else f"0{parts[1]}"
    patch = parts[2] if len(parts) > 2 else "00"
    patch = patch if len(patch) != 1 else f"0{patch}"
    return parts[0] + minor + patch


def iris_macros(
    minecraft: str, iris_version: str, mipmap_levels: str
) -> list[tuple[str, str | None]]:
    """Iris's environment defines in its order, a name with its value or None when defined empty:
    MC_VERSION from the platform's Minecraft (26.3 -> 260300: platform.md, R8), MC_MIPMAP_LEVEL
    from the options.txt the harness writes, IRIS_VERSION from the pinned Iris (1.11.7 -> 11107),
    then FIXED_MACROS."""
    semver = re.match(r"(\d+)\.(\d+)\.*(\d*)", iris_version)
    if semver is None:
        raise L0Error(f"Iris version {iris_version!r} is no semantic version; fix: the pin")
    iris = f"{semver[1]}.{semver[2]}.{semver[3] or '0'}"
    return [
        ("MC_VERSION", version_string(minecraft)),
        ("MC_MIPMAP_LEVEL", mipmap_levels),
        ("IRIS_VERSION", version_string(iris)),
        *FIXED_MACROS,
    ]


def define_flags(macros: Iterable[tuple[str, str | None]]) -> list[str]:
    return [f"-D{name}" if value is None else f"-D{name}={value}" for name, value in macros]


# The matrix.


@dataclass(frozen=True)
class Variant:
    """A point of the matrix: the options it sets off their defaults (none: the defaults)."""

    values: tuple[tuple[str, str], ...] = ()

    @property
    def label(self) -> str:
        return ", ".join(f"{n} {v}" for n, v in self.values) if self.values else "defaults"


def settings(options: Options, variant: Variant) -> dict[str, str]:
    """Every option's value at a variant: the defaults with its values over them."""
    return {name: o.default for name, o in sorted(options.found.items())} | dict(variant.values)


def variants(options: Options) -> list[Variant]:
    """The defaults, then each option switched alone to each of its other values."""
    found = [Variant()]
    for name, option in sorted(options.found.items()):
        found += [Variant(((name, value),)) for value in option.values if value != option.default]
    return found


@dataclass(frozen=True)
class Build:
    """One program built in one dimension at one variant, from its dimension's folder."""

    program: str
    dimension: str
    folder: str
    variant: Variant


@dataclass
class Failure:
    """What failed in one compiled build: the step (preprocess, unmodeled, link), the stage file,
    glslang's lines mapped to the pack's files."""

    step: str
    stage: str
    lines: list[str]


@dataclass
class Compiled:
    """A distinct build's outcome: the stage files, the failures, the reflection's sections."""

    program: str
    folder: str
    variant: Variant
    stages: list[str]
    failures: list[Failure] = field(default_factory=list)
    reflection: dict[str, list[str]] = field(default_factory=dict)
    runs: int = 0


@dataclass
class Matrix:
    """L0's matrix over a pack: its options, the builds (program x dimension x variant), each
    distinct build's outcome, the glslang runs and the seconds they took."""

    options: Options
    variants: list[Variant]
    builds: list[Build]
    compiled: list[Compiled]
    macros: list[tuple[str, str | None]]
    seconds: float
    problems: list[str] = field(default_factory=list)

    @property
    def runs(self) -> int:
        return sum(c.runs for c in self.compiled)

    @property
    def failed(self) -> list[Compiled]:
        return [c for c in self.compiled if c.failures]


def programs(
    pack: Pack, passes: list[dict], places: Mapping[str, str]
) -> tuple[list[Build], list[str]]:
    """Every pass's program in each of its dimensions, from that dimension's folder; the problems
    when pipeline.json and the pack disagree (a program file of a folder in use that no pass
    names, or that no dimension of its pass takes, would go unchecked; a pass whose program a
    dimension's folder lacks), and a stage L0 does not build."""
    problems = []
    named = {p["program"] for p in passes}
    used = {
        (places[d], p["program"]) for p in passes for d in p["dimensions"] if d in WORLD_FOLDERS
    }
    for path in pack.files:
        for folder in sorted(set(places.values())):
            found = program_file(path, folder)
            if found is None:
                continue
            program, ending = found
            if ending not in BUILT:
                why = (
                    "Iris reads it only under the TESSELLATION_SHADERS feature flag"
                    if ending in ("tcs", "tes")
                    else "compute programs are no part of the matrix yet"
                )
                problems.append(
                    f"{SHADERS}/{path}: a {STAGE_NAMES[ending]} stage, which L0 does not build "
                    f"({why}); fix: build it in L0 first (docs/offline.md#levels)"
                )
            elif program not in named:
                problems.append(
                    f"{SHADERS}/{path}: no pass of config/pipeline.json names program {program}; "
                    "fix: add its pass (docs/shader.md#pipeline-spec)"
                )
            elif (folder, program) not in used:
                problems.append(
                    f"{SHADERS}/{path}: no dimension of {program}'s pass takes its programs from "
                    f"{folder or 'the root'}; fix: its pass's dimensions"
                )
    builds = []
    for found in passes:
        for dimension in found["dimensions"]:
            folder = places.get(dimension)
            if folder is None:
                problems.append(
                    f"pass {found['name']}: {dimension!r} is no dimension; fix: one of "
                    f"{', '.join(WORLD_FOLDERS)}"
                )
                continue
            stages = program_stages(pack, folder, found["program"])
            if "vsh" not in stages or "fsh" not in stages:
                where = f"{SHADERS}/{folder + '/' if folder else ''}{found['program']}"
                problems.append(
                    f"pass {found['name']}: {where} lacks its .vsh or .fsh in {dimension}; fix: "
                    "both stages (a lone .fsh runs on Iris's own #version 120 vertex stage, which "
                    "L0 does not build)"
                )
                continue
            builds.append(Build(found["program"], dimension, folder, Variant()))
    return builds, problems


def program_stages(pack: Pack, folder: str, program: str) -> list[str]:
    """The stage endings L0 builds (BUILT) of a program present in `folder`, in pipeline order."""
    return [
        ending
        for ending in BUILT
        if f"{folder + '/' if folder else ''}{program}.{ending}" in pack.files
    ]


def plan(pack: Pack, passes: list[dict]) -> tuple[Options, list[Variant], list[Build], list[str]]:
    """L0's matrix (docs/offline.md#levels) before anything compiles: the pack's options, the
    defaults and each option switched alone, every pass's program in each of its dimensions from
    that dimension's folder; the problems found on the way (pipeline.json against the pack, an
    option Iris drops)."""
    options = declared(pack)
    bases, problems = programs(pack, passes, folders(pack))
    problems += graph(pack)[1]
    problems += [
        f"{name}: declared with different defaults ({'; '.join(sites)}), which Iris drops; fix: "
        "one default"
        for name, sites in options.conflicts.items()
    ]
    points = variants(options)
    return (
        options,
        points,
        [Build(b.program, b.dimension, b.folder, v) for v in points for b in bases],
        problems,
    )


def build_matrix(
    pack: Pack,
    passes: list[dict],
    macros: list[tuple[str, str | None]],
    glslang: Path,
    workers: int | None = None,
) -> Matrix:
    """The matrix's builds (plan), each distinct (folder, program, variant) preprocessed,
    compiled and linked once, as a dimension changes only the folder."""
    started = time.perf_counter()
    options, points, builds, problems = plan(pack, passes)
    distinct = list(dict.fromkeys((b.folder, b.program, b.variant) for b in builds))
    flags = define_flags(macros)

    def one(key: tuple[str, str, Variant]) -> Compiled:
        return compile_build(pack, key[0], key[1], key[2], flags, glslang)

    with ThreadPoolExecutor(max_workers=workers or min(8, os.cpu_count() or 1)) as pool:
        compiled = list(pool.map(one, distinct))
    return Matrix(
        options, points, builds, compiled, macros, time.perf_counter() - started, problems
    )


def compile_build(
    pack: Pack, folder: str, program: str, variant: Variant, flags: list[str], glslang: Path
) -> Compiled:
    """One distinct build: each stage expanded at the variant's values and preprocessed with
    glslang -E and Iris's macros, then the stages compiled and linked with -l, reflected with -q
    and their interface checked with --validate-io (a fragment input no vertex output writes fails
    to link in the driver: gpu-iris.md#programs-and-alpha-tests)."""
    values = dict(variant.values)
    prefix = f"{folder}/" if folder else ""
    stages = program_stages(pack, folder, program)
    done = Compiled(program, folder, variant, [f"{SHADERS}/{prefix}{program}.{e}" for e in stages])
    origins: dict[str, list[tuple[str, int, str]]] = {}
    shown_as: dict[str, str] = {}
    macros = {flag[2:].split("=", 1)[0] for flag in flags}
    for ending in stages:  # every stage read before glslang runs on any
        name = f"{program}.{STAGES[ending]}"
        shown_as[name] = shown = f"{SHADERS}/{prefix}{program}.{ending}"
        try:
            origins[name] = expand(pack, f"{prefix}{program}.{ending}", values)
        except L0Error as error:
            done.failures.append(Failure("expand", shown, [str(error)]))
            continue
        lines = [line for _, _, line in origins[name]]
        own = {m["name"] for line in lines if (m := DEFINES.match(line))}
        names = unmodeled("\n".join(lines), macros, own)
        if names:
            done.failures.append(
                Failure(
                    "unmodeled",
                    shown,
                    [
                        f"names {', '.join(names)}, which only the game sets as Iris does (its "
                        "run-time defines, or glslang's own in a conditional); fix: leave it out "
                        "or model it in optilux/offline.py"
                    ],
                )
            )
    if done.failures:
        return done
    with tempfile.TemporaryDirectory(prefix="optilux-l0-") as scratch:
        work = Path(scratch)
        (work / "in").mkdir()
        preprocessed = []
        for name, lines in origins.items():
            shown = shown_as[name]
            source = "\n".join(line for _, _, line in lines) + "\n"
            (work / "in" / name).write_text(source, encoding="utf-8", newline="\n")
            ran = glslang_run(glslang, ["-E", *flags, f"in/{name}"], work)
            done.runs += 1
            if ran.returncode:
                found = errors(ran.stderr + ran.stdout)
                lines = mapped(found, name, lines) + [text for where, _, text in found if not where]
                done.failures.append(Failure("preprocess", shown, lines))
                continue
            (work / name).write_text(
                "\n".join(lines_of(ran.stdout)) + "\n", encoding="utf-8", newline="\n"
            )
            preprocessed.append((name, shown))
        if done.failures or not preprocessed:
            return done
        names = [name for name, _ in preprocessed]
        ran = glslang_run(glslang, ["-l", "-q", "--validate-io", *names], work)
        done.runs += 1
    output = ran.stdout + ran.stderr
    if ran.returncode:
        found = errors(output)
        for name, shown in preprocessed:
            lines = mapped(found, name, origins[name])
            if lines:
                done.failures.append(Failure("compile and link", shown, lines))
        loose = [text for where, _, text in found if not where]
        if loose or not done.failures:
            stages = " + ".join(shown for _, shown in preprocessed)
            done.failures.append(Failure("link", stages, loose or [output.strip()]))
        return done
    done.reflection = reflection(output)
    return done


def glslang_run(glslang: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 argv list, no shell
            [str(glslang), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GLSLANG_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise L0Error(f"glslang did not run ({error}); fix: `uv run optilux install`") from None


def errors(output: str) -> list[tuple[str | None, int, str]]:
    """glslang's ERROR lines as (file, line, text): the file None for a link's own error, an
    indented line after one joined to it; the closing count and "compilation terminated" left
    out."""
    found: list[list] = []
    for raw in output.splitlines():
        if raw.startswith("ERROR: "):
            match = GLSLANG_ERROR.fullmatch(raw.strip())
            text = match["text"].strip() if match else raw.strip()
            if SUMMARY.fullmatch(text):
                found.append([None, 0, None])  # closes the one before it
                continue
            line = int(match["line"]) if match and match["line"] else 0
            found.append([match["file"] if match else None, line, text])
        elif raw[:1].isspace() and raw.strip() and found and found[-1][2] is not None:
            found[-1][2] += f" {raw.strip()}"
    return [(f, n, t) for f, n, t in found if t is not None]


def mapped(
    found: list[tuple[str | None, int, str]], name: str, lines: list[tuple[str, int, str]]
) -> list[str]:
    """One stage file's errors (glslang names it, or 0 for a lone string), each line number mapped
    to the pack's file and line it came from: glslang -E keeps the expanded file's numbering."""
    shown = []
    for where, number, text in found:
        if where is None or not (where.endswith(name) or where == "0"):
            continue
        origin = lines[number - 1] if 0 < number <= len(lines) else None
        at = f"{SHADERS}/{origin[0]}:{origin[1]}" if origin else f"{name}:{number}"
        shown.append(f"{at}: {text}")
    return shown


def reflection(output: str) -> dict[str, list[str]]:
    """The -q reflection's sections (Uniform reflection, Pipeline input reflection, ...), each the
    names of its entries."""
    found: dict[str, list[str]] = {}
    section = None
    for line in output.splitlines():
        header = REFLECTION.match(line.strip())
        if header is not None:
            section = header["name"]
            found[section] = []
        elif section is not None and ":" in line:
            found[section].append(line.split(":", 1)[0].strip())
    return found


def glslang_version(glslang: Path) -> str:
    """The version `glslang --version` prints first (Glslang Version: 11:16.6.0 -> 16.6.0)."""
    if not glslang.is_file():
        raise L0Error(f"{glslang} is missing; fix: `uv run optilux install` unpacks glslang")
    ran = glslang_run(glslang, ["--version"], glslang.parent)
    match = VERSION_LINE.search(ran.stdout)
    if ran.returncode or match is None:
        raise L0Error(f"{glslang} --version printed no version; fix: `uv run optilux install`")
    return match["version"]


# The profile check.


def profile_keys(data: dict) -> list[tuple[str, str, str | bool | None]]:
    """Every option a profile names: (block, name, value), the value None where the block names the
    option alone (iso's kept and dropped switches, the notes)."""
    found: list[tuple[str, str, str | bool | None]] = [
        (block, name, value)
        for block in ("options", "defaultsKept")
        for name, value in (data.get(block) or {}).items()
    ]
    named = {
        "dropped": data.get("dropped") or [],
        "droppedNotes": data.get("droppedNotes") or {},
        "kept.keys": (data.get("kept") or {}).get("keys") or {},
    }
    found += [(block, name, None) for block, names in named.items() for name in names]
    for row in (data.get("ablations") or {}).get("rows") or []:
        name, _, value = str(row.get("set", "")).partition("=")
        found.append(("ablations", name, {"true": True, "false": False}.get(value, value)))
    return found


def check_profile(where: str, data: dict, options: Options) -> tuple[int, list[str]]:
    """A profile's options against its pack's (docs/offline.md#levels): each name declared, each
    value one of the option's values as the pack's text (true or false for an on/off option). The
    count of names checked and each problem."""
    keys = profile_keys(data)
    problems = []
    for block, name, value in keys:
        option = options.found.get(name)
        if option is None:
            why = (
                "declared with different defaults" if name in options.conflicts else "not declared"
            )
            problems.append(
                f"{where} {block}: {name} is {why} by the pack; fix: one of its options"
            )
        elif value is None:
            continue
        elif option.kind == "bool" and not isinstance(value, bool):
            problems.append(
                f"{where} {block}: {name} {value!r} for an on/off option; fix: true or false"
            )
        elif option.kind == "value" and (isinstance(value, bool) or value not in option.values):
            problems.append(
                f"{where} {block}: {name} {value!r} is not among its values "
                f"[{' '.join(option.values)}]; fix: one of them, as the pack's own text"
            )
    return len(keys), problems
