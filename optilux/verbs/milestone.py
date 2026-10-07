"""`optilux milestone start <MM>`: cut the milestone branch m<MM> from origin/main with
`--no-track` (docs/workflow.md#git). Scripted, like every multi-step git operation, so a hand-made
branch cannot skip a step."""

import argparse
import sys
from pathlib import Path

from optilux import REPO_ROOT, prompts, repo
from optilux.verbs import Verb

PREFIX = "optilux milestone start"


def configure(parser: argparse.ArgumentParser) -> None:
    targets = parser.add_subparsers(dest="target", metavar="<target>", title="targets")
    targets.required = True
    start = targets.add_parser(
        "start",
        help="cut m<MM> from origin/main with --no-track",
        description="Refuse a dirty tree or an existing branch; fetch; switch to a new m<MM>.",
    )
    start.add_argument("milestone", metavar="<MM>", help="the milestone number (0, 1, ...)")


def refuse(problem: str, fix: str) -> int:
    print(f"{PREFIX}: {problem}; fix: {fix}", file=sys.stderr)
    return 1


def start(root: Path, number: int) -> int:
    """Cut m<number> from origin/main; 1 with the reason and the fix when a check refuses."""
    branch = repo.branch_name(number)
    if not repo.is_repo(root):
        return refuse(f"{root} is not a git repository", "run inside the Optilux checkout")
    if not repo.has_remote(root):
        return refuse("no `origin` remote", "`git remote add origin <url>` first")
    try:
        changes = repo.changes(root)
    except repo.GitError as error:
        return refuse(str(error), "run inside the Optilux checkout")
    if changes:
        shown = "; ".join(change.strip() for change in changes[:5])
        return refuse(f"the tree is not clean ({len(changes)} changes: {shown})", "commit first")
    if repo.local_branch_exists(root, branch):
        return refuse(f"branch {branch} exists locally", f"`git switch {branch}` to continue it")
    try:
        remote = repo.remote_sha(root, branch)
    except repo.GitError as error:
        return refuse(str(error), "check the network and `git remote -v`")
    if remote is not None:
        fix = f"`git switch -c {branch} --no-track origin/{branch}` to continue it"
        return refuse(f"origin has {branch} already ({remote[:7]})", fix)
    fetched = repo.git(root, "fetch", repo.ORIGIN)
    if fetched.returncode:
        return refuse(f"`git fetch origin` failed: {repo.failure(fetched)}", "check the network")
    switched = repo.git(root, "switch", "-c", branch, "--no-track", f"{repo.ORIGIN}/{repo.MAIN}")
    if switched.returncode:
        return refuse(
            f"`git switch -c {branch}` failed: {repo.failure(switched)}", "read git's reason"
        )
    head = repo.head(root) or "?"
    print(f"{PREFIX}: on {branch} at {head[:7]} (origin/main), no upstream")
    first = prompts.next_phase(None, number)
    if prompts.prompt_file(root, number).is_file():
        print(f"next: paste the `## {first}` prompt of {prompts.prompt_name(number)}")
    else:
        print(
            f"next: write docs/plans/m{number}.md and {prompts.prompt_name(number)} (phase {first})"
        )
    print(f"then: `optilux status`; the first commit pushes with `git push -u origin {branch}`")
    return 0


def run(args: argparse.Namespace) -> int:
    text = args.milestone
    if not (text.isdigit() and len(text) <= 2):
        return refuse(
            f"milestone {text!r} is not a number", "give the MM of 0.MM.PP (0, 1, ... 99)"
        )
    return start(REPO_ROOT, int(text))


VERB = Verb(
    name="milestone", help="milestone branches (start: cut m<MM>)", run=run, configure=configure
)
