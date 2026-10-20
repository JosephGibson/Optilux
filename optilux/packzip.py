"""The pack's zip (docs/plans/m0.md#6-decisions D14): shader/ zipped relative to itself, so
shaders/ sits at the zip root where Iris looks for it, with LICENSE and README.md beside it; one
tree gives one sha256: sorted entries, one fixed timestamp, deflate at one level and no
host-dependent attributes, so a build here and one on the CI runner are byte-identical.

The sources are the working tree's (`pack build`, `run`'s variant `optilux`) or a commit's, read
from git's objects (`pack build --ref`, `run`'s variant `optilux@<ref>`: docs/plans/m3.md D63).
This module stays apart from verbs/pack.py so the measured session imports the zip writer alone,
not the release code (docs/run-record.md#identity: harness).
"""

import io
import os
import subprocess
import zipfile
from pathlib import Path

from optilux import repo

PACK_DIR = "shader"
EXTRA_FILES = ("LICENSE", "README.md")
# D14: every entry carries the zip format's epoch, so source mtimes never reach the archive.
TIMESTAMP = (1980, 1, 1, 0, 0, 0)
# D14: deflate at one fixed level; 9 because the pack is small and read far more often than built.
COMPRESSION = zipfile.ZIP_DEFLATED
LEVEL = 9
# A fresh ZipInfo records the building OS (0 on Windows, 3 on Unix) and no mode bits; both are
# pinned so any machine writes the same bytes: Unix, regular file, rw-r--r--.
CREATE_SYSTEM = 3
EXTERNAL_ATTR = 0o100644 << 16
# The git tree modes the zip takes from a commit: a regular file, executable or not (a link or a
# submodule has no bytes of its own to zip).
FILE_MODES = ("100644", "100755")

Source = tuple[str, bytes]


class PackError(RuntimeError):
    """A build or release that cannot proceed; the message names the problem and the fix."""


def ordered(found: list[Source], where: str) -> list[Source]:
    """The sources sorted by archive name; PackError for a name taken twice."""
    names = [name for name, _ in found]
    if len(set(names)) != len(names):
        twice = sorted({name for name in names if names.count(name) > 1})
        raise PackError(
            f"{PACK_DIR}/ {where} holds a file named like a root file: {', '.join(twice)}; fix: "
            "rename it"
        )
    return sorted(found, key=lambda pair: pair[0])


def tree_sources(root: Path) -> list[Source]:
    """(archive name, bytes) pairs from the working tree: shader/** relative to shader/, then the
    extras, sorted by name."""
    pack = root / PACK_DIR
    if not pack.is_dir():
        raise PackError(f"no {PACK_DIR}/ under {root}; fix: run inside the Optilux checkout")
    found = [
        (file.relative_to(pack).as_posix(), file.read_bytes())
        for file in pack.rglob("*")
        if file.is_file()
    ]
    if not found:
        raise PackError(f"{PACK_DIR}/ under {root} holds no file; fix: restore the pack")
    for name in EXTRA_FILES:
        file = root / name
        if not file.is_file():
            raise PackError(f"{name} is missing under {root}; fix: restore it")
        found.append((name, file.read_bytes()))
    return ordered(found, f"under {root}")


def git_bytes(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """A git call's raw stdout in root (blobs are bytes, not text); PackError naming git's reason
    when it exits non-zero."""
    env = {**os.environ, **repo.NO_PROMPT}
    command = ["git", *args]
    done = subprocess.run(  # noqa: S603 argv list, no shell
        command, cwd=root, env=env, input=stdin, capture_output=True, check=False
    )
    if done.returncode:
        reason = done.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = reason[0] if reason else f"git exited {done.returncode}"
        raise PackError(f"`git {args[0]}` failed in {root}: {detail}; fix: check the checkout")
    return done.stdout


def commit_sources(root: Path, ref: str, label: str | None = None) -> list[Source]:
    """The same pairs as tree_sources, read from the commit `ref` names (its objects, so neither the
    working tree nor the index plays a part); `label` names it in the messages (default: ref), when
    the caller resolved a ref once and passes the sha."""
    sha = repo.resolve(root, ref)
    shown = label or ref
    if sha is None:
        raise PackError(f"{shown!r} names no commit in {root}; fix: a branch, a tag or a sha")
    listing = git_bytes(root, "ls-tree", "-r", "-z", "--full-tree", sha, "--", PACK_DIR)
    listing += git_bytes(root, "ls-tree", "-z", "--full-tree", sha, "--", *EXTRA_FILES)
    entries = []
    for record in listing.decode("utf-8").split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode, kind, oid = meta.split()
        if kind != "blob" or mode not in FILE_MODES:
            raise PackError(
                f"{path} at {shown} ({sha[:7]}) is a {kind} of mode {mode}, not a file; fix: "
                "commit the file itself"
            )
        entries.append((path, oid))
    paths = [path for path, _ in entries]
    if not any(path.startswith(f"{PACK_DIR}/") for path in paths):
        raise PackError(
            f"{PACK_DIR}/ at {shown} ({sha[:7]}) holds no file; fix: a commit with the pack"
        )
    for name in EXTRA_FILES:
        if name not in paths:
            raise PackError(f"{name} is missing at {shown} ({sha[:7]}); fix: a commit that has it")
    batch = git_bytes(
        root, "cat-file", "--batch", stdin="".join(f"{o}\n" for _, o in entries).encode()
    )
    found, at = [], 0
    for path, oid in entries:
        header_end = batch.index(b"\n", at)
        got, kind, size = batch[at:header_end].decode("ascii").split()
        if got != oid or kind != "blob":
            raise PackError(
                f"git cat-file answered {got} {kind} for {path}; fix: check the checkout"
            )
        start = header_end + 1
        data = batch[start : start + int(size)]
        at = start + int(size) + 1  # the blob's trailing LF
        name = path.removeprefix(f"{PACK_DIR}/") if path.startswith(f"{PACK_DIR}/") else path
        found.append((name, data))
    return ordered(found, f"at {shown} ({sha[:7]})")


def zip_bytes(sources: list[Source]) -> bytes:
    """The zip of `sources` in their order, every entry with D14's fixed attributes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in sources:
            info = zipfile.ZipInfo(name, date_time=TIMESTAMP)
            info.create_system = CREATE_SYSTEM
            info.external_attr = EXTERNAL_ATTR
            info.compress_type = COMPRESSION
            archive.writestr(info, data, compresslevel=LEVEL)
    return buffer.getvalue()
