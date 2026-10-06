"""`optilux status`: where the milestone stands, and the next prompt verbatim with a heads-up on
its kind and size.

Read-only, and always exit 0: the optilux-next skill injects its output, and an injected command
that fails cancels the skill (docs/workflow.md#skills). Every problem becomes a printed line with
its fix instead of an exit code.

The next prompt follows the milestone cycle (docs/workflow.md#running-a-milestone):
- the milestone has no prompt set yet: the standing Plan prompt, which writes it;
- the set has a prompt for the next phase: that prompt, sized by the phase's plan estimate;
- every phase is committed and origin/main lacks the newest: the standing Release prompt;
- every phase is committed and merged: the block that switches to the next milestone's branch,
  then that milestone's Plan prompt.
"""

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from optilux import REPO_ROOT, docs_check, prompts, repo
from optilux.verbs import Verb

# The docs whose Status lines say where the milestone stands (docs/workflow.md#running-a-milestone).
STATUS_DOCS = ("AGENTS.md", "docs/roadmap.md")
# The hooks path the git hooks need (docs/workflow.md#hooks-and-guards).
HOOKS_PATH = ".githooks"
# The kinds of next prompt the heads-up names (user, 2026-10-06).
PLANNING, IMPLEMENTATION, RELEASE = "planning", "implementation", "release"


@dataclass
class Next:
    """The next prompt: its kind, the phase it commits (None for the release), title, source
    file, estimate in agent hours with the file that gives it, text, and the switch block that
    must run first (None when the branch is already right)."""

    kind: str | None = None
    phase: str | None = None
    title: str | None = None
    source: str | None = None
    estimate: float | None = None
    estimate_source: str | None = None
    prompt: str | None = None
    switch: list[str] | None = None


def status_line(path: Path) -> str | None:
    """A doc's Status line outside fenced code, None when it has none or does not exist."""
    if not path.is_file():
        return None
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    lines = docs_check.unfenced(docs_check.split_lines(text))
    return next((line for _, line in lines if line.startswith(docs_check.STATUS)), None)


def remote_version(root: Path, branch: str, problems: list[str]) -> tuple[str | None, str | None]:
    """(sha, version prefix) of a branch on origin; the version needs the commit fetched."""
    try:
        sha = repo.remote_sha(root, branch)
    except repo.GitError as error:
        problems.append(f"{error}; fix: check the network and `git remote -v`")
        return None, None
    except subprocess.TimeoutExpired:
        limit = repo.REMOTE_TIMEOUT
        problems.append(
            f"`git ls-remote origin` gave no answer in {limit} s; fix: check the network"
        )
        return None, None
    if sha is None:
        return None, None
    version = repo.newest_version(root, sha) if repo.subject(root, sha) else None
    if version is None:
        problems.append(f"origin/{branch} ({sha[:7]}) is not fetched; fix: `git fetch origin`")
    return sha, version


def standing(root: Path, name: str, milestone: int, phase: str | None, problems: list[str]) -> Next:
    """The standing Plan or Release prompt, filled in for the milestone."""
    try:
        prompt = prompts.load_standing(root)[name]
    except prompts.PromptError as error:
        problems.append(str(error))
        return Next(phase=phase)
    return Next(
        kind=PLANNING if name == prompts.PLAN else RELEASE,
        phase=phase,
        title=f"{name} M{milestone}",
        source=prompts.STANDING,
        estimate=prompt.estimate,
        estimate_source=prompts.STANDING,
        prompt=prompts.fill(prompt.text, milestone, phase or ""),
    )


def switch_lines(root: Path, milestone: int) -> list[str]:
    """The commands from a merged milestone to the next one's branch: cut it, then delete the
    merged branch where it still exists (the rebase merge gave main new SHAs, hence -D)."""
    old = repo.branch_name(milestone)
    lines = [f"uv run optilux milestone start {milestone + 1}"]
    if repo.local_branch_exists(root, old):
        lines.append(f"git branch -D {old}")
    try:
        on_origin = repo.remote_sha(root, old) is not None
    except (repo.GitError, subprocess.TimeoutExpired):
        on_origin = False  # origin/main's read already reported the remote
    if on_origin:
        lines.append(f"git push origin --delete {old}")
    return lines


def next_step(
    root: Path, milestone: int, local: str | None, main: str | None, problems: list[str]
) -> Next:
    """The next prompt in the milestone cycle (module docstring)."""
    phase = prompts.next_phase(local, milestone)
    if not prompts.prompt_file(root, milestone).is_file():
        return standing(root, prompts.PLAN, milestone, phase, problems)
    try:
        prompt_set = prompts.load(root, milestone)
    except prompts.PromptError as error:
        problems.append(str(error))
        return Next(phase=phase)
    prompt = prompt_set.phase(phase)
    if prompt is not None:
        plan = prompts.plan_name(milestone)
        estimate = prompts.phase_estimate(root, milestone, phase)
        if estimate is None:
            fix = f"add `- Estimate: <h> h.` to `### {phase}` in {plan}"
            problems.append(f"no estimate for {phase} in {plan}; fix: {fix}")
        return Next(
            IMPLEMENTATION, phase, prompt.title, prompt_set.file, estimate, plan, prompt.text
        )
    last = prompt_set.phases[-1].version
    if phase <= last:
        fix = f"add `## {phase} <title>` to {prompt_set.file} (its phases end at {last})"
        problems.append(f"no stored prompt for {phase}; fix: {fix}")
        return Next(phase=phase)
    if main is None or main != local:
        return standing(root, prompts.RELEASE, milestone, None, problems)
    following = milestone + 1
    step = standing(root, prompts.PLAN, following, prompts.next_phase(None, following), problems)
    step.switch = switch_lines(root, milestone)
    return step


def collect(root: Path) -> dict:
    """Every fact `optilux status` prints, JSON-ready; problems are listed, never raised."""
    problems: list[str] = []
    facts: dict = {"problems": problems}
    if not repo.is_repo(root):
        problems.append(f"{root} is not a git repository; fix: run inside the Optilux checkout")
        return facts
    branch = repo.current_branch(root)
    head = repo.head(root)
    local = repo.newest_version(root)
    facts.update(branch=branch, head=head, version_local=local)
    if branch is None:
        problems.append("HEAD is detached; fix: `git switch` to the milestone branch")
    if local is None:
        problems.append("no commit with a `0.MM.PP: ` subject; fix: commit the first phase")
    main_sha, main_version = remote_version(root, repo.MAIN, problems)
    facts.update(main_sha=main_sha, version_main=main_version)
    pushed = None
    if branch is not None and branch != repo.MAIN:
        branch_sha, _ = remote_version(root, branch, [])  # unfetched is fine: only the sha counts
        pushed = branch_sha == head
        facts["branch_sha"] = branch_sha
        if not pushed:
            problems.append(f"HEAD is not on origin/{branch}; fix: `git push -u origin {branch}`")
    facts["pushed"] = pushed
    milestone = repo.milestone_of(branch)
    if milestone is None:
        match = prompts.VERSION.fullmatch(local or "")
        milestone = int(match.group(1)) if match else 0
    step = next_step(root, milestone, local, main_version, problems)
    facts.update(
        milestone=milestone,
        next_kind=step.kind,
        next_phase=step.phase,
        next_title=step.title,
        next_source=step.source,
        next_estimate=step.estimate,
        next_estimate_source=step.estimate_source,
        next_size=prompts.size(step.estimate) if step.estimate is not None else None,
        prompt=step.prompt,
        switch=step.switch,
    )
    facts["status_lines"] = {doc: status_line(root / doc) for doc in STATUS_DOCS}
    for doc, line in facts["status_lines"].items():
        if line is None:
            problems.append(f"{doc} has no Status line; fix: add one under its title")
    changes = repo.changes(root)
    facts.update(clean=not changes, changes=changes)
    hooks = repo.hooks_path(root)
    facts.update(hooks_path=hooks, hooks_set=hooks == HOOKS_PATH)
    if hooks != HOOKS_PATH:
        problems.append(
            f"hooks path not set; fix: `git config --local core.hooksPath {HOOKS_PATH}`"
        )
    return facts


def heads_up(facts: dict) -> str:
    """The kind and size of the next prompt, in one line."""
    kind = facts["next_kind"]
    if kind is None:
        return "no next prompt: see the problems below"
    hours, source = facts["next_estimate"], facts["next_estimate_source"]
    if hours is None:
        return f"{kind}, size unknown (no estimate)"
    return f"{kind}, size {facts['next_size']} ({hours:g} h estimate, {source})"


def print_text(facts: dict) -> None:
    if "branch" not in facts:
        print(f"problem: {facts['problems'][0]}")
        return
    print(f"heads-up:   {heads_up(facts)}")
    pushed = {True: "pushed", False: "not pushed", None: "no push check on main"}[facts["pushed"]]
    print(f"branch:     {facts['branch'] or 'detached'}, {pushed}")
    main = facts["version_main"] or (facts["main_sha"] or "absent")[:7]
    print(f"version:    {facts['version_local'] or 'none'} local, {main} on origin/main")
    name = " ".join(filter(None, (facts["next_phase"], facts["next_title"])))
    source = facts["next_source"] or prompts.prompt_name(facts["milestone"])
    print(f"next phase: {name} ({source})")
    for doc, line in facts["status_lines"].items():
        print(f"{doc}: {line or 'no Status line'}")
    changes = facts["changes"]
    shown = "; ".join(change.strip() for change in changes[:5])
    tree = "clean" if not changes else f"{len(changes)} changes: {shown}"
    print(f"tree:       {tree}")
    hooks = facts["hooks_path"] or "unset"
    print(f"hooks path: {hooks} ({'set' if facts['hooks_set'] else 'not set'})")
    for problem in facts["problems"]:
        print(f"problem:    {problem}")
    if facts["switch"]:
        print(f"\nswitch to m{facts['milestone'] + 1} first, paste:")
        print("\n".join(facts["switch"]))
    if facts["prompt"] is not None:
        print(f"\nnext prompt, {name}, verbatim:")
        print(facts["prompt"], end="")


def run(args: argparse.Namespace) -> int:
    facts = collect(REPO_ROOT)
    if args.json:
        print(json.dumps(facts))
    else:
        print_text(facts)
    return 0


VERB = Verb(
    name="status",
    help="where the milestone stands and the next prompt, with its kind and size",
    run=run,
    structured=True,
)
