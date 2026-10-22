"""L2, the compiler view (docs/offline.md#levels, plans/m3.md D70): RGA 2.15 in OpenGL mode for
gfx1101 (P7) on each program a dump run printed, its stages as Iris compiled them.

- Programs: a print's stage files grouped by program (a name without Iris's NNN_ counter), each
  held to its recorded sha256; one RGA run per distinct program, however many dumps share it.
- Per run: `rga -s opengl -c gfx1101` with every output the plan names (ISA, the statistics,
  live VGPRs and SGPRs, the CFG) under results/raw/<run>/l2/<program>-<sha>/, and per stage its
  VGPRs and SGPRs used, spills, scratch, ISA bytes and the live-register peaks.
- RGA exits 0 when a build fails: a program without "Building for gfx1101... succeeded." or a
  stage without its statistics is a known offline failure (gpu-iris.md#toolchain-quirks), listed
  with RGA's lines; L2 explains and never gates (offline.md#decision-powers).
"""

import csv
import hashlib
import io
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from optilux import l1

ASIC = "gfx1101"
FLAGS = {"vsh": "--vert", "tcs": "--tesc", "tes": "--tese", "gsh": "--geom", "fsh": "--frag"}
# RGA's name for each stage in its output files (gfx1101_<output>_<stage>.<ending>).
NAMES = {"vsh": "vert", "tcs": "tesc", "tes": "tese", "gsh": "geom", "fsh": "frag"}
# Each output as RGA's flag and the file name RGA prefixes with the ASIC and suffixes the stage.
OUTPUTS = (
    ("--isa", "isa.txt"),
    ("-a", "stats.csv"),
    ("--livereg", "livereg.txt"),
    ("--livereg-sgpr", "livereg_sgpr.txt"),
    ("--cfg", "cfg.dot"),
)
SUCCEEDED = f"Building for {ASIC}... succeeded."
LIVE_VGPRS = re.compile(
    r"Maximum # VGPR used\s+(?P<used>\d+), VGPRs allocated by HW:\s+(?P<hw>\d+)"
)
LIVE_SGPRS = re.compile(r"Maximum # SGPR used\s+(?P<used>\d+), SGPRs allocated\s*:\s+(?P<hw>\d+)")
STATS = {
    "vgprs": "USED_VGPRs",
    "sgprs": "USED_SGPRs",
    "vgprSpills": "VGPR_SPILLS",
    "sgprSpills": "SGPR_SPILLS",
    "scratch": "SCRATCH_MEM",
    "isaBytes": "ISA_SIZE",
}
RGA_TIMEOUT = 120


class L2Error(RuntimeError):
    """A record or a tool L2 cannot use; the message names the fix."""


@dataclass(frozen=True)
class Program:
    """A printed program: its name, its stage files by ending, and the sha256 over its stages'
    sha256s (one RGA run per distinct program)."""

    name: str
    stages: dict[str, Path]
    digest: str


def programs(raw: Path, capture: dict, files: Mapping[str, str]) -> list[Program]:
    """A dump's programs: its stage files under raw/<run>/ grouped by name, each held to its
    recorded sha256; a compute stage, which RGA's OpenGL mode builds alone, is no part of L2 yet."""
    folder = raw / capture["dump"]["folder"]
    grouped: dict[str, dict[str, tuple[Path, str]]] = {}
    for name, digest in sorted(files.items()):
        if not name.startswith(f"{l1.PATCHED}/"):
            continue
        staged = l1.STAGE_FILE.fullmatch(l1.stage_key(name).split("/", 1)[1])
        if staged is None or staged["ending"] not in FLAGS:
            continue
        path = folder / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise L2Error(f"{path} does not hash to its record's sha256; fix: rerun the dump")
        grouped.setdefault(staged["program"], {})[staged["ending"]] = (path, digest)
    found = []
    for program, stages in grouped.items():
        joined = "".join(f"{e}:{stages[e][1]}\n" for e in FLAGS if e in stages)
        found.append(
            Program(
                program,
                {e: stages[e][0] for e in FLAGS if e in stages},
                hashlib.sha256(joined.encode("ascii")).hexdigest(),
            )
        )
    return found


def command(exe: Path, program: Program, out: Path) -> list[str]:
    """RGA's command line for one program (P7): OpenGL, gfx1101, every output, each stage's file."""
    args = [str(exe), "-s", "opengl", "-c", ASIC]
    for flag, name in OUTPUTS:
        args += [flag, str(out / name)]
    for ending, path in program.stages.items():
        args += [FLAGS[ending], str(path)]
    return args


def parse_stats(text: str) -> dict[str, int]:
    """RGA's statistics CSV, one header and one row for the ASIC: the fields L2 reports."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) != 1:
        raise L2Error(f"RGA's statistics hold {len(rows)} rows, not one; fix: read its file")
    row = rows[0]
    try:
        return {key: int(row[column]) for key, column in STATS.items()}
    except (KeyError, ValueError) as error:
        raise L2Error(f"RGA's statistics lack {error}; fix: read its file") from None


def parse_live(text: str, pattern: re.Pattern[str]) -> int | None:
    """The live-register peak a livereg file states (`Maximum # VGPR used ...`), or None."""
    found = pattern.search(text)
    return int(found["used"]) if found else None


def analyze(exe: Path, program: Program, out: Path) -> dict:
    """One program through RGA into `out`: per stage its statistics and live-register peaks, or
    the known offline failure with RGA's lines (RGA exits 0 on a failed build)."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run(  # noqa: S603 the pinned RGA, no shell
            command(exe, program, out),
            capture_output=True,
            timeout=RGA_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"program": program.name, "failed": [f"RGA did not run: {error}"], "stages": {}}
    text = done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")
    (out / "rga.txt").write_text(text, encoding="utf-8", newline="\n")
    stages: dict[str, dict] = {}
    failed: list[str] = []
    if SUCCEEDED not in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        at = next((n for n, line in enumerate(lines) if line.startswith("Building for")), 0)
        failed = lines[at:][:12] or [f"RGA exited {done.returncode} with no output"]
    for ending in program.stages:
        stats = out / f"{ASIC}_stats_{NAMES[ending]}.csv"
        if not stats.is_file():
            failed = failed or [f"RGA wrote no statistics for {ending}"]
            continue
        found: dict[str, int | None] = {
            **parse_stats(stats.read_text(encoding="utf-8", errors="replace"))
        }
        for key, name, pattern in (
            ("liveVgprs", "livereg", LIVE_VGPRS),
            ("liveSgprs", "livereg_sgpr", LIVE_SGPRS),
        ):
            live = out / f"{ASIC}_{name}_{NAMES[ending]}.txt"
            found[key] = (
                parse_live(live.read_text(encoding="utf-8", errors="replace"), pattern)
                if live.is_file()
                else None
            )
        stages[ending] = found
    return {"program": program.name, "failed": failed, "stages": stages}
