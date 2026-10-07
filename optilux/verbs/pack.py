"""`optilux pack build` and `optilux pack release` (docs/workflow.md#release).

build: the release asset optilux-<version>.zip from shader/ plus LICENSE and README.md. One tree
gives one sha256 (docs/plans/m0.md#6-decisions D14): sorted entries, one fixed timestamp, deflate
at one level and no host-dependent attributes, so a build here and one on the CI runner are
byte-identical.

release: builds the zip, then creates the GitHub release v<version> at HEAD when it is absent,
its body the milestone's CHANGELOG entry; .github/workflows/release.yml runs it on every push to
main. `release --check` applies the same rules before the merge, here and in CI.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from optilux import REPO_ROOT, hooks, repo
from optilux.verbs import Verb
from optilux.verbs.install import shown

PREFIX = "optilux pack build"
RELEASE = "optilux pack release"
CHECK = "optilux pack release --check"
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
# roadmap.md#decisions D6: the tag is v<version>; the title names the product, the version and the
# milestone, whose name comes from its CHANGELOG heading (user, 2026-10-06).
TAG = "v{version}"
TITLE = "Optilux {version}: {name}"
# The release body is the milestone's user-facing entry under `## 0.MM <Name>`
# (docs/workflow.md#release).
CHANGELOG = "CHANGELOG.md"
# The GitHub CLI: logged in on this machine (docs/plans/m0.md P4); preinstalled on GitHub's hosted
# runners and authenticated there through GH_TOKEN (P28). Found on PATH like git.
GH = "gh"
# gh never prompts: a missing login fails at once, as git does under repo.NO_PROMPT.
GH_ENV = {"GH_PROMPT_DISABLED": "1"}
# `gh release view <tag>` exits 1 with this on stderr when the tag has no release (gh 2.102.0,
# checked on this repository 2026-10-06); any other failure (login, network) stays a failure.
NOT_FOUND = "release not found"
# The fix for a subject without a version prefix: `pack build` takes either option; `pack release`
# has neither, since only Rebase and merge keeps the phase subject on main (roadmap.md D7).
BUILD_FIX = "give --version, or --ref a commit that carries one"
RELEASE_FIX = "release from main's tip after a Rebase and merge, which keeps the phase subject"
# The outcomes of one `release --check` rule.
OK, SKIPPED, PROBLEM = "ok", "skipped", "problem"


@dataclass(frozen=True)
class Built:
    """One written zip: its path, version, sha256 and entry names in archive order."""

    path: Path
    version: str
    sha256: str
    entries: tuple[str, ...]


class PackError(RuntimeError):
    """A build or release that cannot proceed; the message names the problem and the fix."""


def check_version(text: str) -> str:
    """`text` when it is a release version (0.MM.PP); PackError otherwise."""
    if repo.version_of(f"{text}: ") != text:
        raise PackError(f"version {text!r} is not of the form 0.MM.PP; fix: give --version 0.MM.PP")
    return text


def version_from_git(root: Path, ref: str = "HEAD", fix: str = BUILD_FIX) -> str:
    """The prefix of ref's subject (`git log -1 --format=%s <ref>`); PackError without, naming
    `fix` when the subject carries no prefix."""
    subject = repo.subject(root, ref)
    if subject is None:
        raise PackError(
            f"`git log -1 {ref}` finds no commit in {root}; fix: commit, or give --version"
        )
    version = repo.version_of(subject)
    if version is None:
        raise PackError(f"the subject of {ref} {subject!r} carries no 0.MM.PP prefix; fix: {fix}")
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


def report(prefix: str, built: Built, root: Path) -> None:
    entries = len(built.entries)
    print(f"{prefix}: wrote {shown(built.path, root)} ({entries} entries, version {built.version})")
    print(f"sha256: {built.sha256}")


@dataclass(frozen=True)
class Entry:
    """A milestone's CHANGELOG section: its heading, the milestone name the heading carries
    after `## 0.MM `, and the text up to the next `## ` heading."""

    heading: str
    name: str
    text: str


def milestone_heading(version: str) -> str:
    """The CHANGELOG heading prefix of a version's milestone: 0.00.06 -> `## 0.00`."""
    return f"## {version.rsplit('.', 1)[0]}"


def changelog_entry(root: Path, version: str) -> Entry:
    """The `## 0.MM <Name>` section of CHANGELOG.md for version's milestone; PackError when it is
    missing, names no milestone or is empty."""
    prefix = milestone_heading(version)
    fix = f"add `{prefix} <Name>` with the milestone's user-facing entry"
    path = root / CHANGELOG
    if not path.is_file():
        raise PackError(f"no {CHANGELOG} under {root}; fix: {fix}")
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.rstrip() == prefix or line.startswith(f"{prefix} ")
    ]
    if not starts:
        raise PackError(f"{CHANGELOG} has no `{prefix} <Name>` section; fix: {fix}")
    heading = lines[starts[0]].rstrip()
    name = heading.removeprefix(prefix).strip()
    if not name:
        detail = f"`{heading}` names no milestone"
        title = TITLE.format(version="<version>", name="<Name>")
        raise PackError(f"{CHANGELOG}'s {detail}; fix: head it `{prefix} <Name>` (title `{title}`)")
    body = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    text = "\n".join(body).strip()
    if not text:
        raise PackError(f"{CHANGELOG}'s `{heading}` section is empty; fix: {fix}")
    return Entry(heading, name, text + "\n")


def run_gh(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run gh in root, which names the repository through its origin remote; the caller judges
    the exit code. The tests replace this function with a fake gh."""
    env = {**os.environ, **GH_ENV}
    command = [GH, *args]
    try:
        return subprocess.run(  # noqa: S603 argv list, no shell
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=repo.REMOTE_TIMEOUT,
        )
    except FileNotFoundError:
        raise PackError(f"`{GH}` is not on PATH; fix: install the GitHub CLI") from None
    except subprocess.TimeoutExpired:
        limit = repo.REMOTE_TIMEOUT
        raise PackError(
            f"`gh {' '.join(args[:2])}` gave no answer in {limit} s; fix: check the network"
        ) from None


def gh_failure(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr.strip() or result.stdout.strip()).splitlines()
    return text[0] if text else f"gh exited {result.returncode}"


def release_of(root: Path, tag: str) -> dict | None:
    """The GitHub release of tag ({tagName, url}), read live with `gh release view`; None when
    the tag has none."""
    result = run_gh(root, "release", "view", tag, "--json", "tagName,url")
    if result.returncode == 0:
        return json.loads(result.stdout)
    if NOT_FOUND in result.stderr:
        return None
    fix = "`gh auth status` here; on a runner, GH_TOKEN from the workflow token"
    raise PackError(f"`gh release view {tag}` failed: {gh_failure(result)}; fix: {fix}")


def live[T](read: Callable[[], T]) -> T:
    """A live read of origin through `git ls-remote`; its failure as a PackError with the fix."""
    try:
        return read()
    except repo.GitError as error:
        raise PackError(f"{error}; fix: check the network and `git remote -v`") from None
    except subprocess.TimeoutExpired:
        limit = repo.REMOTE_TIMEOUT
        raise PackError(
            f"`git ls-remote origin` gave no answer in {limit} s; fix: check the network"
        ) from None


def dirty(root: Path) -> str | None:
    """What makes the tree unclean, None when it is clean."""
    try:
        changes = repo.changes(root)
    except repo.GitError as error:
        return str(error)
    if not changes:
        return None
    listed = "; ".join(change.strip() for change in changes[:5])
    return f"the tree is not clean ({len(changes)} changes: {listed})"


def release(root: Path, out_dir: Path) -> None:
    """Build the zip from HEAD's tree, then create release v<version> at HEAD unless it exists;
    PackError when a rule refuses (HEAD not origin/main's tip, an existing tag elsewhere, a dirty
    tree, no CHANGELOG entry)."""
    version = version_from_git(root, fix=RELEASE_FIX)
    head = repo.head(root) or ""  # version_from_git found HEAD's commit
    # A release cut from a milestone branch would tag a commit the rebase merge replaces, and the
    # tag never moves; D6: the workflow tags main's head.
    main = live(lambda: repo.remote_sha(root, repo.MAIN))
    if main != head:
        tip = main[:7] if main else "absent"
        raise PackError(
            f"HEAD {head[:7]} is not the tip of origin/main ({tip}); fix: release.yml releases "
            "after the user's merge; before it, run `optilux pack release --check`"
        )
    if problem := dirty(root):
        raise PackError(
            f"{problem}; fix: the zip is built from the tree, so commit or discard first"
        )
    built = build(root, out_dir, version)
    report(RELEASE, built, root)
    entry = changelog_entry(root, version)
    title = TITLE.format(version=version, name=entry.name)
    tag = TAG.format(version=version)
    existing = release_of(root, tag)
    tagged = live(lambda: repo.remote_tag(root, tag))
    if tagged is not None and tagged != head:
        raise PackError(
            f"tag {tag} on origin is at {tagged[:7]}, not HEAD {head[:7]}; "
            "fix: never move a tag: commit the next phase, whose version gets its own release"
        )
    if existing is not None:
        if tagged is None:
            raise PackError(
                f"release {tag} exists but origin has no tag {tag} (a draft?); "
                "fix: publish or delete the draft on GitHub, then rerun"
            )
        print(
            f"{RELEASE}: release {tag} exists at HEAD {head[:7]}: {existing['url']}; nothing to do"
        )
        return
    with tempfile.TemporaryDirectory() as temp:
        notes_file = Path(temp) / "notes.md"
        notes_file.write_bytes(entry.text.encode("utf-8"))
        asset = shown(built.path, root)
        result = run_gh(
            root,
            "release",
            "create",
            tag,
            asset,
            "--title",
            title,
            "--notes-file",
            str(notes_file),
            "--target",
            head,
        )
    if result.returncode:
        fix = "read gh's reason; the workflow needs `permissions: contents: write` and GH_TOKEN"
        raise PackError(f"`gh release create {tag}` failed: {gh_failure(result)}; fix: {fix}")
    url = (result.stdout.strip().splitlines() or ["(gh printed no URL)"])[-1]
    print(f"{RELEASE}: created release {tag} '{title}' at {head[:7]} with {built.path.name}: {url}")


def check(root: Path, ref: str, remote: bool) -> list[tuple[str, str]]:
    """Every release rule on ref, before the merge: (outcome, text) pairs, the outcome OK, SKIPPED
    or PROBLEM, a problem's text naming its fix. `remote` False skips the GitHub release lookup."""
    found: list[tuple[str, str]] = []
    sha = repo.resolve(root, ref)
    version = None
    if sha is None:
        fix = "give a ref that names a commit (HEAD; HEAD^2 on GitHub's pull_request merge commit)"
        found.append((PROBLEM, f"{ref!r} names no commit; fix: {fix}"))
    else:
        text = repo.message(root, sha) or ""
        subject = text.split("\n")[0]
        problems = hooks.commit_msg(text)
        found += [(PROBLEM, f"subject of {ref} {subject!r}: {problem}") for problem in problems]
        if not problems:
            version = repo.version_of(subject)
            found.append((OK, f"subject of {ref} ({sha[:7]}): {subject}"))
    if version is not None:
        try:
            entry = changelog_entry(root, version)
            lines = len(entry.text.splitlines())
            found.append((OK, f"{CHANGELOG} `{entry.heading}`: {lines} lines"))
        except PackError as error:
            found.append((PROBLEM, str(error)))
        tag = TAG.format(version=version)
        if not remote:
            found.append((SKIPPED, f"no release and no tag {tag} on GitHub (--no-remote)"))
        else:
            try:
                existing = release_of(root, tag)
                tagged = live(lambda: repo.remote_tag(root, tag))
            except PackError as error:
                found.append((PROBLEM, str(error)))
            else:
                next_phase = "fix: commit the next phase, whose version has none"
                if existing is not None:
                    url = existing["url"]
                    found.append((PROBLEM, f"release {tag} exists already ({url}); {next_phase}"))
                elif tagged is not None:
                    detail = f"tag {tag} exists on origin ({tagged[:7]}) without a release"
                    found.append((PROBLEM, f"{detail}; {next_phase}"))
                else:
                    found.append((OK, f"no release and no tag {tag} on GitHub"))
    if problem := dirty(root):
        found.append(
            (PROBLEM, f"{problem}; fix: commit the phase, or discard what it does not need")
        )
    else:
        found.append((OK, "tree clean"))
    if sha is not None:
        try:
            branches = live(lambda: repo.remote_branches_at(root, sha))
        except PackError as error:
            found.append((PROBLEM, str(error)))
        else:
            if branches:
                tips = ", ".join(f"origin/{branch}" for branch in branches)
                found.append((OK, f"{ref} ({sha[:7]}) is the tip of {tips}"))
            else:
                branch = repo.current_branch(root) or "<branch>"
                fix = f"push it (`git push origin {branch}`), or check a branch tip instead"
                found.append((PROBLEM, f"{ref} ({sha[:7]}) is no branch tip on origin; fix: {fix}"))
    return found


def run_check(root: Path, ref: str, remote: bool) -> int:
    found = check(root, ref, remote)
    for outcome, text in found:
        print(f"{outcome + ':':<9}{text}")
    counts = {
        outcome: sum(1 for kind, _ in found if kind == outcome)
        for outcome in (OK, SKIPPED, PROBLEM)
    }
    print(f"{CHECK}: {counts[OK]} ok, {counts[SKIPPED]} skipped, {counts[PROBLEM]} problems")
    return 1 if counts[PROBLEM] else 0


def run_build(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    out_dir = (Path(args.out) if args.out else root / DEFAULT_OUT).resolve()
    try:
        version = check_version(args.version) if args.version else version_from_git(root, args.ref)
        built = build(root, out_dir, version)
    except PackError as error:
        print(f"{PREFIX}: {error}", file=sys.stderr)
        return 1
    report(PREFIX, built, root)
    return 0


def run_release(args: argparse.Namespace) -> int:
    root = REPO_ROOT
    if not args.check:
        if args.no_remote or args.ref is not None:
            fix = "add --check, or drop them"
            print(
                f"{RELEASE}: --no-remote and --ref belong to --check; fix: {fix}", file=sys.stderr
            )
            return 1
        try:
            release(root, root / DEFAULT_OUT)
        except PackError as error:
            print(f"{RELEASE}: {error}", file=sys.stderr)
            return 1
        return 0
    return run_check(root, args.ref or "HEAD", remote=not args.no_remote)


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
    source = target.add_mutually_exclusive_group()
    source.add_argument(
        "--version",
        metavar="V",
        help="0.MM.PP (default: the prefix of the subject of --ref)",
    )
    source.add_argument(
        "--ref",
        metavar="R",
        default="HEAD",
        help="the commit whose subject gives the version (default: HEAD; HEAD^2 on GitHub's "
        "pull_request merge commit)",
    )
    target = targets.add_parser(
        "release",
        help="build the zip and create GitHub release v<version> at HEAD when absent",
        description="Build build/optilux-<version>.zip, then create release v<version> at HEAD "
        "titled `Optilux <version>: <Name>`, with the CHANGELOG `## 0.MM <Name>` entry as its "
        "body, unless it exists; an existing tag must be at HEAD. --check applies the release "
        "rules before the merge instead.",
    )
    target.add_argument(
        "--check",
        action="store_true",
        help="check the release rules (subject, CHANGELOG entry, no release yet, tree clean, "
        "pushed) and create nothing",
    )
    target.add_argument(
        "--no-remote", action="store_true", help="with --check: skip the GitHub release lookup"
    )
    target.add_argument(
        "--ref",
        metavar="R",
        help="with --check: the commit whose subject gives the version (default: HEAD)",
    )


TARGETS = {"build": run_build, "release": run_release}


def run(args: argparse.Namespace) -> int:
    return TARGETS[args.target](args)


VERB = Verb(name="pack", help="the shader zip (build, release)", run=run, configure=configure)
