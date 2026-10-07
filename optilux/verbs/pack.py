"""`optilux pack build` and `optilux pack release` (docs/workflow.md#release).

build: the release asset optilux-<version>.zip from shader/ plus LICENSE and README.md. One tree
gives one sha256 (docs/plans/m0.md#6-decisions D14): sorted entries, one fixed timestamp, deflate
at one level and no host-dependent attributes, so a build here and one on the CI runner are
byte-identical.

release: checks the release rules on HEAD, builds the zip, then creates the GitHub release
v<version> at HEAD when it is absent, its body the version's CHANGELOG entry;
.github/workflows/release.yml runs it on every push to main. `release --check` applies the same
rules before the merge, here and on the PR in CI. The version is the root file VERSION at the
commit (docs/workflow.md#release), never a commit subject.
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
# pinned so any machine writes the same bytes: Unix, regular file, rw-r--r--.
CREATE_SYSTEM = 3
EXTERNAL_ATTR = 0o100644 << 16
# build/ is gitignored (.gitignore), so a local build never dirties the tree.
DEFAULT_OUT = "build"
ASSET = "optilux-{version}.zip"
# roadmap.md#decisions D6 and D33: the tag is v<version>; the title names the product, the
# version and the name in the version's CHANGELOG heading.
TAG = "v{version}"
TITLE = "Optilux {version}: {name}"
# The release body is the version's user-facing entry under `## <version> <Name>`
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
# The fix for a version that is released already or not newer than origin/main's.
BUMP_FIX = "set VERSION to {minor} for a milestone or {patch} for a patch (workflow.md#release)"
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
    """`text` when it is a release version, MAJOR.MINOR.PATCH; PackError otherwise."""
    if not repo.VERSION.fullmatch(text):
        raise PackError(
            f"version {text!r} is not of the form MAJOR.MINOR.PATCH; fix: write it as 0.2.0"
        )
    return text


def version_from_git(root: Path, ref: str = "HEAD") -> str:
    """The version in VERSION at ref; PackError when ref names no commit, has no VERSION or
    holds no MAJOR.MINOR.PATCH there."""
    if repo.resolve(root, ref) is None:
        raise PackError(f"{ref!r} names no commit in {root}; fix: commit, or give --version")
    text = repo.version_at(root, ref)
    if text is None:
        raise PackError(
            f"{ref} has no {repo.VERSION_FILE}; fix: add it with the release version, or give "
            "--version"
        )
    try:
        return check_version(text)
    except PackError as error:
        raise PackError(f"{repo.VERSION_FILE} at {ref}: {error}") from None


def bump_fix(version: str) -> str:
    """The fix for a version that cannot be released: the next minor or the next patch."""
    major, minor, patch = repo.version_key(version) or (0, 0, 0)
    return BUMP_FIX.format(minor=repo.next_minor(version), patch=f"{major}.{minor}.{patch + 1}")


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
    """A version's CHANGELOG section: its heading, the name the heading carries after
    `## <version> `, and the text up to the next `## ` heading."""

    heading: str
    name: str
    text: str


def changelog_entry(root: Path, version: str, ref: str | None = None) -> Entry:
    """The `## <version> <Name>` section of CHANGELOG.md, in the working tree or at ref;
    PackError when it is missing, names nothing or is empty."""
    prefix = f"## {version}"
    fix = f"add `{prefix} <Name>` with the release's user-facing entry"
    if ref is None:
        path = root / CHANGELOG
        text = path.read_text(encoding="utf-8") if path.is_file() else None
    else:
        text = repo.file_at(root, ref, CHANGELOG)
    if text is None:
        raise PackError(f"no {CHANGELOG} under {root}; fix: {fix}")
    lines = text.splitlines()
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
        detail = f"`{heading}` names no release"
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


@dataclass
class Examined:
    """The release rules on one commit: each finding as (outcome, text), and the facts a release
    needs from them, None where a rule could not read its fact."""

    found: list[tuple[str, str]]
    sha: str | None = None
    version: str | None = None
    entry: Entry | None = None
    released: dict | None = None  # the GitHub release of the version, at sha


def newer_than_main(root: Path, ref: str, sha: str, version: str) -> tuple[str, str]:
    """The rule that a release moves origin/main forward: ref's version newer than main's, or
    ref is main's tip (after the merge, in release.yml)."""
    try:
        main = live(lambda: repo.remote_sha(root, repo.MAIN))
    except PackError as error:
        return PROBLEM, str(error)
    if main is None:
        return OK, "origin has no main yet"
    if main == sha:
        return OK, f"{ref} ({sha[:7]}) is the tip of origin/main"
    if repo.subject(root, main) is None:
        return PROBLEM, f"origin/main ({main[:7]}) is not fetched; fix: `git fetch origin`"
    current = repo.released_at(root, main)
    if current is None:
        return OK, f"origin/main ({main[:7]}) carries no version"
    if (repo.version_key(version) or ()) > (repo.version_key(current) or ()):
        return OK, f"VERSION {version} is newer than origin/main's {current}"
    detail = f"VERSION {version} is not newer than origin/main's {current}"
    return PROBLEM, f"{detail}; fix: {bump_fix(current)}"


def pushed(root: Path, ref: str, sha: str) -> tuple[str, str]:
    """The rule that ref is on origin: a branch's tip, or behind one when a later push has
    superseded it while CI checked it (the tip's commit fetched)."""
    try:
        heads = live(lambda: repo.remote_refs(root, "--heads"))
    except PackError as error:
        return PROBLEM, str(error)
    names = {ref.removeprefix("refs/heads/"): tip for ref, tip in heads.items()}
    tips = sorted(name for name, tip in names.items() if tip == sha)
    if tips:
        return OK, f"{ref} ({sha[:7]}) is the tip of {', '.join(f'origin/{n}' for n in tips)}"
    behind = sorted(name for name, tip in names.items() if repo.is_ancestor(root, sha, tip))
    if behind:
        return OK, f"{ref} ({sha[:7]}) is on origin/{behind[0]}, behind its tip (a later push)"
    branch = repo.current_branch(root) or "<branch>"
    fix = f"push it (`git push origin {branch}`), or check a branch tip instead"
    return PROBLEM, f"{ref} ({sha[:7]}) is no branch tip on origin; fix: {fix}"


def examine(root: Path, ref: str, remote: bool) -> Examined:
    """Every release rule on ref (docs/workflow.md#release). `remote` False skips the GitHub
    release lookup, which needs gh's login; origin's tags and branches are read with git."""
    found: list[tuple[str, str]] = []
    result = Examined(found)
    sha = result.sha = repo.resolve(root, ref)
    if sha is None:
        fix = "give a ref that names a commit (HEAD; HEAD^2 on GitHub's pull_request merge commit)"
        found.append((PROBLEM, f"{ref!r} names no commit; fix: {fix}"))
    else:
        try:
            result.version = version_from_git(root, ref)
        except PackError as error:
            found.append((PROBLEM, str(error)))
        text = repo.message(root, sha) or ""
        subject = text.split("\n")[0]
        problems = hooks.commit_msg(text, result.version)
        found += [(PROBLEM, f"subject of {ref} {subject!r}: {problem}") for problem in problems]
        if not problems:
            found.append((OK, f"subject of {ref} ({sha[:7]}): {subject}"))
    version = result.version
    if sha is not None and version is not None:
        found.append((OK, f"VERSION at {ref}: {version}"))
        found.append(newer_than_main(root, ref, sha, version))
        try:
            entry = result.entry = changelog_entry(root, version, ref)
            title = TITLE.format(version=version, name=entry.name)
            lines = len(entry.text.splitlines())
            found.append((OK, f"{CHANGELOG} `{entry.heading}`: {lines} lines; title `{title}`"))
        except PackError as error:
            found.append((PROBLEM, str(error)))
        tag = TAG.format(version=version)
        try:
            tagged = live(lambda: repo.remote_tag(root, tag))
        except PackError as error:
            found.append((PROBLEM, str(error)))
            tagged = ""
        if tagged is None:
            found.append((OK, f"no tag {tag} on origin"))
        elif tagged == sha:
            found.append((OK, f"tag {tag} on origin is {ref} ({sha[:7]}) itself"))
        elif tagged:
            detail = f"{version} is released already: tag {tag} on origin is at {tagged[:7]}"
            found.append((PROBLEM, f"{detail}; fix: {bump_fix(version)}"))
        if not remote:
            found.append((SKIPPED, f"no GitHub release lookup for {tag} (--no-remote)"))
        else:
            try:
                existing = release_of(root, tag)
            except PackError as error:
                found.append((PROBLEM, str(error)))
            else:
                if existing is None:
                    found.append((OK, f"no GitHub release {tag}"))
                elif tagged is None:
                    detail = f"release {tag} exists but origin has no tag {tag} (a draft?)"
                    fix = "publish or delete the draft on GitHub, then rerun"
                    found.append((PROBLEM, f"{detail}; fix: {fix}"))
                elif tagged == sha:
                    result.released = existing
                    found.append((OK, f"release {tag} exists at {ref}: {existing['url']}"))
    if problem := dirty(root):
        found.append((PROBLEM, f"{problem}; fix: commit, or discard what the change does not need"))
    else:
        found.append((OK, "tree clean"))
    if sha is not None:
        found.append(pushed(root, ref, sha))
    result.found = list(dict.fromkeys(found))  # an unreadable origin fails three reads alike
    return result


def check(root: Path, ref: str, remote: bool) -> list[tuple[str, str]]:
    """Every release rule on ref, before the merge: (outcome, text) pairs, the outcome OK, SKIPPED
    or PROBLEM, a problem's text naming its fix."""
    return examine(root, ref, remote).found


def release(root: Path, out_dir: Path) -> None:
    """Create release v<version> at HEAD unless it exists there, after the rules of `--check`
    pass on HEAD and HEAD is origin/main's tip; PackError lists every rule that refuses."""
    head = repo.head(root) or ""
    # A release cut from a milestone branch would tag a commit the rebase merge replaces, and the
    # tag never moves; D6: the workflow tags main's head.
    main = live(lambda: repo.remote_sha(root, repo.MAIN))
    if main != head:
        tip = main[:7] if main else "absent"
        raise PackError(
            f"HEAD {head[:7]} is not the tip of origin/main ({tip}); fix: release.yml releases "
            "after the user's merge; before it, run `optilux pack release --check`"
        )
    examined = examine(root, "HEAD", remote=True)
    problems = [text for outcome, text in examined.found if outcome == PROBLEM]
    if problems:
        raise PackError("\n".join(problems))
    version, entry = examined.version, examined.entry
    if version is None or entry is None:  # examine reports each absence as a problem
        raise PackError(
            "no version or CHANGELOG entry at HEAD; fix: `optilux pack release --check`"
        )
    tag = TAG.format(version=version)
    if examined.released is not None:
        url = examined.released["url"]
        print(f"{RELEASE}: release {tag} exists at HEAD {head[:7]}: {url}; nothing to do")
        return
    built = build(root, out_dir, version)
    report(RELEASE, built, root)
    title = TITLE.format(version=version, name=entry.name)
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
            for line in str(error).splitlines():
                print(f"{RELEASE}: {line}", file=sys.stderr)
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
        help="MAJOR.MINOR.PATCH (default: VERSION at --ref)",
    )
    source.add_argument(
        "--ref",
        metavar="R",
        default="HEAD",
        help="the commit whose VERSION gives the version (default: HEAD; HEAD^2 on GitHub's "
        "pull_request merge commit)",
    )
    target = targets.add_parser(
        "release",
        help="check the release rules, build the zip and create release v<version> at HEAD",
        description="Apply the --check rules to HEAD, which must be origin/main's tip; build "
        "build/optilux-<version>.zip from VERSION; create release v<version> at HEAD titled "
        "`Optilux <version>: <Name>`, with the CHANGELOG `## <version> <Name>` entry as its "
        "body, unless it exists there. --check applies the rules before the merge instead.",
    )
    target.add_argument(
        "--check",
        action="store_true",
        help="check the release rules (subject, VERSION newer than origin/main's, CHANGELOG "
        "entry, no tag or release elsewhere, tree clean, pushed) and create nothing",
    )
    target.add_argument(
        "--no-remote", action="store_true", help="with --check: skip the GitHub release lookup"
    )
    target.add_argument(
        "--ref",
        metavar="R",
        help="with --check: the commit to check (default: HEAD)",
    )


TARGETS = {"build": run_build, "release": run_release}


def run(args: argparse.Namespace) -> int:
    return TARGETS[args.target](args)


VERB = Verb(name="pack", help="the shader zip (build, release)", run=run, configure=configure)
