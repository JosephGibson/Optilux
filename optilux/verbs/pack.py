"""`optilux pack build [--out DIR] [--version V]`: the release asset optilux-<version>.zip from
shader/ plus LICENSE and README.md (docs/workflow.md#release). One tree gives one sha256
(docs/plans/m0.md#6-decisions D14): sorted entries, one fixed timestamp, deflate at one level and no
host-dependent attributes, so a build here and one on the CI runner are byte-identical."""

import argparse
import hashlib
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from optilux import REPO_ROOT, repo
from optilux.verbs import Verb

PREFIX = "optilux pack build"
# shader/ is zipped relative to itself, so shaders/ sits at the zip root where Iris looks for it;
# LICENSE and README.md ride along with the credit (docs/design.md#7-decisions-taken-user-2026-10-05
# D7).
PACK_DIR = "shader"
EXTRA_FILES = ("LICENSE", "README.md")
# D14: every entry carries the zip format's epoch, so source mtimes never reach the archive.
TIMESTAMP = (1980, 1, 1, 0, 0, 0)
# D14: deflate at one fixed level; 9 because the pack is small and read far more often than built.
COMPRESSION = zipfile.ZIP_DEFLATED
LEVEL = 9
# A fresh ZipInfo records the building OS (0 on Windows, 3 on Unix) and no mode bits; both are
# pinned so this machine and the ubuntu runner write the same bytes: Unix, regular file, rw-r--r--.
CREATE_SYSTEM = 3
EXTERNAL_ATTR = 0o100644 << 16
# build/ is gitignored (.gitignore), so a local build never dirties the tree.
DEFAULT_OUT = "build"
ASSET = "optilux-{version}.zip"


@dataclass(frozen=True)
class Built:
    """One written zip: its path, version, sha256 and entry names in archive order."""

    path: Path
    version: str
    sha256: str
    entries: tuple[str, ...]


class PackError(RuntimeError):
    """A build that cannot proceed; the message names the problem and the fix."""


def check_version(text: str) -> str:
    """`text` when it is a release version (0.MM.PP); PackError otherwise."""
    if repo.version_of(f"{text}: ") != text:
        raise PackError(f"version {text!r} is not of the form 0.MM.PP; fix: give --version 0.MM.PP")
    return text


def version_from_git(root: Path) -> str:
    """The prefix of the newest commit's subject (`git log -1 --format=%s`); PackError without."""
    subject = repo.subject(root, "HEAD")
    if subject is None:
        raise PackError(f"`git log -1` finds no commit in {root}; fix: commit, or give --version")
    version = repo.version_of(subject)
    if version is None:
        raise PackError(
            f"the newest commit's subject {subject!r} carries no 0.MM.PP prefix; "
            "fix: give --version"
        )
    return version


def sources(root: Path) -> list[tuple[str, Path]]:
    """(archive name, file) pairs sorted by name: shader/** relative to shader/, then the extras."""
    pack = root / PACK_DIR
    if not pack.is_dir():
        raise PackError(f"no {PACK_DIR}/ under {root}; fix: run inside the Optilux checkout")
    found = [
        (file.relative_to(pack).as_posix(), file) for file in pack.rglob("*") if file.is_file()
    ]
    if not found:
        raise PackError(f"{PACK_DIR}/ under {root} holds no file; fix: restore the pack")
    for name in EXTRA_FILES:
        file = root / name
        if not file.is_file():
            raise PackError(f"{name} is missing under {root}; fix: restore it")
        found.append((name, file))
    names = [name for name, _ in found]
    if len(set(names)) != len(names):
        twice = sorted({name for name in names if names.count(name) > 1})
        raise PackError(
            f"{PACK_DIR}/ holds a file named like a root file: {', '.join(twice)}; fix: rename it"
        )
    return sorted(found, key=lambda pair: pair[0])


def build(root: Path, out_dir: Path, version: str) -> Built:
    """Write out_dir/optilux-<version>.zip from root's sources; the facts of the written file."""
    entries = sources(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ASSET.format(version=version)
    with zipfile.ZipFile(path, "w") as archive:
        for name, file in entries:
            info = zipfile.ZipInfo(name, date_time=TIMESTAMP)
            info.create_system = CREATE_SYSTEM
            info.external_attr = EXTERNAL_ATTR
            info.compress_type = COMPRESSION
            archive.writestr(info, file.read_bytes(), compresslevel=LEVEL)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Built(path, version, digest, tuple(name for name, _ in entries))


def run_build(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    out_dir = (Path(args.out) if args.out else root / DEFAULT_OUT).resolve()
    try:
        version = check_version(args.version) if args.version else version_from_git(root)
        built = build(root, out_dir, version)
    except PackError as error:
        print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    path = built.path
    shown = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    print(f"{PREFIX}: wrote {shown} ({len(built.entries)} entries, version {built.version})")
    print(f"sha256: {built.sha256}")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    targets = parser.add_subparsers(dest="target", metavar="<target>", title="targets")
    targets.required = True
    target = targets.add_parser(
        "build",
        help="zip shader/ + LICENSE + README.md as optilux-<version>.zip",
        description="Write optilux-<version>.zip (one tree, one sha256) and print its sha256.",
    )
    target.add_argument(
        "--out", metavar="DIR", help=f"output directory (default: {DEFAULT_OUT}/ under the repo)"
    )
    target.add_argument(
        "--version",
        metavar="V",
        help="0.MM.PP (default: the prefix of the newest commit's subject)",
    )


def run(args: argparse.Namespace) -> int:
    return run_build(args)


VERB = Verb(name="pack", help="the shader zip (build)", run=run, configure=configure)
