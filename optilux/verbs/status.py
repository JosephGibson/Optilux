"""`optilux status`: where the milestone stands, and the next stored prompt verbatim.

Read-only, and always exit 0: the optilux-next skill injects its output, and an injected command
that fails cancels the skill (docs/workflow.md#skills). Every problem becomes a printed line with
its fix instead of an exit code.
"""

import argparse
import json
import subprocess
from pathlib import Path

from optilux import REPO_ROOT, docs_check, prompts, repo
from optilux.verbs import Verb

# The docs whose Status lines say where the milestone stands (docs/workflow.md#running-a-milestone).
STATUS_DOCS = ("AGENTS.md", "docs/roadmap.md")
# The hooks path the git hooks need (docs/workflow.md#hooks-and-guards).
HOOKS_PATH = ".githooks"


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


def next_prompt(
    root: Path, milestone: int, phase: str, problems: list[str]
) -> prompts.Prompt | None:
    try:
        prompt_set = prompts.load(root, milestone)
    except prompts.PromptError as error:
        problems.append(str(error))
        return None
    prompt = prompt_set.phase(phase)
    if prompt is None:
        last = prompt_set.phases[-1].version
        fix = f"add `## {phase} <title>` to {prompt_set.file} (its phases end at {last})"
        if phase > last:
            fix += f", or start the next milestone: `optilux milestone start {milestone + 1}`"
        problems.append(f"no stored prompt for {phase}; fix: {fix}")
    return prompt


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
    phase = prompts.next_phase(local, milestone)
    prompt = next_prompt(root, milestone, phase, problems)
    facts.update(
        milestone=milestone,
        next_phase=phase,
        next_title=prompt.title if prompt else None,
        prompt_file=prompts.prompt_name(milestone),
        prompt=prompt.text if prompt else None,
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


def print_text(facts: dict) -> None:
    if "branch" not in facts:
        print(f"problem: {facts['problems'][0]}")
        return
    pushed = {True: "pushed", False: "not pushed", None: "no push check on main"}[facts["pushed"]]
    print(f"branch:     {facts['branch'] or 'detached'}, {pushed}")
    main = facts["version_main"] or (facts["main_sha"] or "absent")[:7]
    print(f"version:    {facts['version_local'] or 'none'} local, {main} on origin/main")
    title = f" {facts['next_title']}" if facts["next_title"] else ""
    print(f"next phase: {facts['next_phase']}{title} ({facts['prompt_file']})")
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
    if facts["prompt"] is not None:
        print(f"\nnext prompt, {facts['next_phase']}{title}, verbatim:")
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
    help="where the milestone stands and the next stored prompt",
    run=run,
    structured=True,
)
