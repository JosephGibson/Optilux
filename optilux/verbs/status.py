"""`optilux status`: a briefing on where the milestone stands, then the next prompt verbatim.

The briefing names the next prompt's kind (a planning step or not), its complexity (S/M/L/XL from
the plan's estimate), the model and effort to run it on, whether it offers a /critique or stops
for the user, what it needs of the machine, the milestone's progress, the last commit, the
phases after the next, the handoff's open questions and the repo's health.

Read-only, and always exit 0: the optilux-next skill injects its output, and an injected command
that fails cancels the skill (docs/workflow.md#skills). Every problem becomes a printed line with
its fix instead of an exit code.

The next prompt follows the milestone cycle (docs/workflow.md#running-a-milestone), from the last
phase done: docs/handoff.md's `Last phase:` line, or without one the newest `0.MM.PP.N: ` subject
(M0 and M1 named their phases there; roadmap.md D33):
- the milestone has no prompt set yet: the standing Plan prompt, which writes it;
- the set starts at the phase after the next one: the Plan prompt again, since the plan phase
  is the one before the set's first phase and is still in progress (its set is written, not
  committed); a set starting any later leaves a gap, which is a problem;
- the set has a prompt for the next phase: that prompt, sized by the phase's plan estimate;
- every phase is done and origin/main carries another version than VERSION: the standing
  Release prompt;
- every phase is done and origin/main carries this VERSION (merged): the block that switches to
  the next milestone's branch, then that milestone's Plan prompt.
"""

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from optilux import REPO_ROOT, prompts, repo
from optilux.verbs import Verb

# The hooks path the git hooks need (docs/workflow.md#hooks-and-guards).
HOOKS_PATH = ".githooks"
# The latest stop: its `Last phase: <phase>` line is where the milestone stands, and the briefing
# lists its open questions (docs/workflow.md#running-a-milestone).
HANDOFF = "docs/handoff.md"
LAST_PHASE = re.compile(r"^Last phase: (\S+)")
# The kinds of next prompt the briefing names (user, 2026-10-06), each with what it does.
PLANNING, IMPLEMENTATION, RELEASE = "planning", "implementation", "release"
KINDS = {
    PLANNING: "planning step (writes the plan and the prompt set; no code)",
    IMPLEMENTATION: "implementation (code, tests, its commits)",
    RELEASE: "release (the PR checklist; no code)",
}
# The model and effort suggested for a prompt, with the reason (user, 2026-10-06). Sources: the
# Claude API's model guidance, cached 2026-09-25: Opus 5.5 is the default model ($4/$20 per
# MTok), Sonnet 5.5 the cheaper one for everyday coding and agent work ($2/$10), Fable 5.1 the
# most capable, for the most demanding reasoning ($10/$50); xhigh is the best effort for most
# coding and agentic work, high the usual cost-quality sweet spot, max only where a measurement
# shows headroom (it bought little for a large multiple of the cost on long-horizon coding).
# The user's rules: Sonnet 5.5 xHigh for the smallest tasks, Fable only for the big-picture
# planning steps. Risk is already in the size: the plans' estimates carry ALC's 3x on mod phases
# (docs/plans/m1.md section 8).
SIZE_MODELS = {
    "S": ("Sonnet 5.5 xHigh", "small and well specified: the cheapest model that holds"),
    "M": ("Opus 5.5 high", "a typical phase: the default model, high is the sweet spot"),
    "L": ("Opus 5.5 xHigh", "a long coding run: xHigh is the coding and agentic setting"),
    "XL": ("Opus 5.5 Max", "past two typical phases: correctness over cost; consider a split"),
}
PLANNING_MODEL = (
    "Fable 5.1 xHigh",
    "big-picture planning: a premise read wrong here costs a whole milestone",
)
# A numbered step of a prompt that offers the critique, and one that stops for the user: the
# step's number, and for a stop its words up to the clause's end.
CRITIQUE_STEP = re.compile(r"^(\d+)\. .*?/critique")
STOP_STEP = re.compile(r"^(\d+)\. .*?((?:\b[Ii]f [^,;.]*, )?\bSTOP\b[^.;]*)")
# Briefing layout: the label column (the longest label, PROGRESS or COMPLEXITY, plus two), the
# rule and progress bar, the most bullets shown per row, and the cut width of a bullet. They keep
# every row under 100 columns, so a terminal or a chat block shows it without wrapping.
LABEL, RULE, BAR, SHOWN, CUT = 12, 78, 20, 4, 86


@dataclass
class Next:
    """The next prompt: its kind, the phase it commits (None for the release), title, source
    file, estimate in agent hours with the file that gives it, text, the switch block that
    must run first (None when the branch is already right), and the plan's machine and
    attended notes for the phase."""

    kind: str | None = None
    phase: str | None = None
    title: str | None = None
    source: str | None = None
    estimate: float | None = None
    estimate_source: str | None = None
    prompt: str | None = None
    switch: list[str] | None = None
    machine: str | None = None
    attended: str | None = None


def local_version(root: Path) -> str | None:
    """The working tree's VERSION, as the plan step sets it before its commit; on a tree from
    before VERSION existed, the newest `0.MM.PP.N: ` subject prefix."""
    path = root / repo.VERSION_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or None
    return repo.newest_version(root)


def remote_version(root: Path, branch: str, problems: list[str]) -> tuple[str | None, str | None]:
    """(sha, version) of a branch on origin; the version needs the commit fetched."""
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
    if repo.subject(root, sha) is None:
        problems.append(f"origin/{branch} ({sha[:7]}) is not fetched; fix: `git fetch origin`")
        return sha, None
    return sha, repo.released_at(root, sha)


def last_phase(root: Path, problems: list[str]) -> tuple[str | None, str | None]:
    """(the last phase done, where it was read): the handoff's `Last phase:` line, else the
    newest `0.MM.PP.N: ` subject's phase (M0 and M1); (None, None) when neither has one."""
    for line in prompts.unfenced_lines(root / HANDOFF):
        if found := LAST_PHASE.match(line):
            if prompts.phase_key(found.group(1)) is None:
                fix = "write `Last phase: M<N>.P<PP>`, the phase the stop completed"
                problems.append(f"{HANDOFF}: `{line}` names no phase; fix: {fix}")
                return None, None
            return found.group(1), HANDOFF
    version = repo.newest_version(root)
    return (repo.phase_of(version), "git log") if version else (None, None)


def standing(
    root: Path,
    name: str,
    milestone: int,
    phase: str | None,
    version: str | None,
    problems: list[str],
) -> Next:
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
        prompt=prompts.fill(prompt.text, milestone, phase or "", version or ""),
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
    root: Path,
    milestone: int,
    last: str | None,
    local: str | None,
    main: str | None,
    problems: list[str],
) -> Next:
    """The next prompt in the milestone cycle (module docstring). A Plan prompt sets VERSION to
    the minor after origin/main's (docs/workflow.md#release)."""
    phase = prompts.next_phase(last, milestone)
    target = repo.next_minor(main)
    if not prompts.prompt_file(root, milestone).is_file():
        return standing(root, prompts.PLAN, milestone, phase, target, problems)
    try:
        prompt_set = prompts.load(root, milestone)
    except prompts.PromptError as error:
        problems.append(str(error))
        return Next(phase=phase)
    prompt = prompt_set.phase(phase)
    if prompt is not None:
        plan = prompts.plan_name(milestone)
        info = prompts.plan_phases(root, milestone).get(prompt.key)
        if info is None:
            fix = f"add `- Estimate: <h> h.` to `### {prompt.phase}` in {plan}"
            problems.append(f"no estimate for {prompt.phase} in {plan}; fix: {fix}")
        return Next(
            IMPLEMENTATION,
            prompt.phase,
            prompt.title,
            prompt_set.file,
            info.estimate if info else None,
            plan,
            prompt.text,
            machine=info.machine if info else None,
            attended=info.attended if info else None,
        )
    first, last_set = prompt_set.phases[0], prompt_set.phases[-1]
    key = prompts.phase_key(phase) or (milestone, 0)
    if prompts.phase_key(prompts.next_phase(phase, milestone)) == first.key:
        return standing(root, prompts.PLAN, milestone, phase, target, problems)
    if key <= last_set.key:
        fix = f"add `## {phase} <title>` to {prompt_set.file} (its phases end at {last_set.phase})"
        problems.append(f"no stored prompt for {phase}; fix: {fix}")
        return Next(phase=phase)
    if main is None or main != local:
        return standing(root, prompts.RELEASE, milestone, None, local, problems)
    following = milestone + 1
    first_phase = prompts.next_phase(None, following)
    step = standing(root, prompts.PLAN, following, first_phase, target, problems)
    step.switch = switch_lines(root, milestone)
    return step


def model_for(kind: str | None, size: str | None) -> tuple[str, str] | None:
    """The suggested (model and effort, reason): Fable for a planning step, else by size; None
    when the size is unknown, which is never guessed."""
    if kind == PLANNING:
        return PLANNING_MODEL
    return SIZE_MODELS.get(size) if size else None


def prompt_steps(prompt: str | None) -> tuple[int | None, list[str]]:
    """The step of a prompt that offers the critique (None when none does) and the steps that
    stop for the user, each as `step N: <the clause with its STOP>`."""
    critique: int | None = None
    stops: list[str] = []
    for line in (prompt or "").splitlines():
        if critique is None and (found := CRITIQUE_STEP.match(line)):
            critique = int(found.group(1))
        if found := STOP_STEP.match(line):
            stops.append(f"step {found.group(1)}: {found.group(2)}")
    return critique, stops


def outlook(root: Path, milestone: int, last: str | None, phase: str | None) -> dict:
    """Progress through the milestone's prompt set (phases and agent hours done against all, the
    last phase done counting with every phase before it) and the two phases after `phase`. A set
    that does not load shows no progress: next_step reports its fault. Hours are None when any
    phase lacks an estimate, never summed around."""
    try:
        prompt_set = prompts.load(root, milestone)
    except prompts.PromptError:
        return {"progress": None, "upcoming": [], "last_title": None}
    plan = prompts.plan_phases(root, milestone)
    phases = prompt_set.phases
    hours = {p.key: plan[p.key].estimate for p in phases if p.key in plan}
    known = len(hours) == len(phases)
    current = prompts.phase_key(last)
    done = [p.key for p in phases if current is not None and p.key <= current]
    progress = {
        "first": phases[0].phase,
        "last": phases[-1].phase,
        "done": len(done),
        "total": len(phases),
        "hours_done": sum(hours[key] for key in done) if known else None,
        "hours_total": sum(hours.values()) if known else None,
    }
    after = prompts.phase_key(phase)
    upcoming = [
        {
            "phase": p.phase,
            "title": p.title,
            "hours": hours.get(p.key),
            "size": prompts.size(hours[p.key]) if p.key in hours else None,
        }
        for p in phases
        if after is not None and p.key > after
    ]
    title = next((p.title for p in phases if p.key == current), None)
    return {"progress": progress, "upcoming": upcoming[:2], "last_title": title}


def open_questions(root: Path) -> list[str]:
    """The bullets under `## Open questions` in the handoff; empty without one."""
    items: list[str] = []
    inside = False
    for line in prompts.unfenced_lines(root / HANDOFF):
        if line.startswith("#"):
            inside = line.lstrip("#").strip().lower() == "open questions"
        elif inside and line.startswith("- "):
            items.append(line[2:].strip())
    return items


def collect(root: Path) -> dict:
    """Every fact `optilux status` prints, JSON-ready; problems are listed, never raised."""
    problems: list[str] = []
    facts: dict = {"problems": problems}
    if not repo.is_repo(root):
        problems.append(f"{root} is not a git repository; fix: run inside the Optilux checkout")
        return facts
    branch = repo.current_branch(root)
    head = repo.head(root)
    local = local_version(root)
    facts.update(branch=branch, head=head, version_local=local)
    if branch is None:
        problems.append("HEAD is detached; fix: `git switch` to the milestone branch")
    if local is None:
        fix = "add it with the release version (docs/workflow.md#release)"
        problems.append(f"no {repo.VERSION_FILE} in the tree; fix: {fix}")
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
    last, last_source = last_phase(root, problems)
    milestone = repo.milestone_of(branch)
    if milestone is None:  # on main: the milestone of the last phase done
        key = prompts.phase_key(last)
        milestone = key[0] if key else 0
    step = next_step(root, milestone, last, local, main_version, problems)
    newer = repo.version_key(local) or (0, 0, 0)
    if step.kind in (IMPLEMENTATION, RELEASE) and newer <= (repo.version_key(main_version) or ()):
        fix = f"set it to {repo.next_minor(main_version)} (docs/workflow.md#release)"
        detail = f"VERSION {local} is not newer than origin/main's {main_version}"
        problems.append(f"{detail}; fix: {fix}")
    size = prompts.size(step.estimate) if step.estimate is not None else None
    model = model_for(step.kind, size)
    critique, stops = prompt_steps(step.prompt)
    facts.update(
        milestone=milestone,
        milestone_name=prompts.plan_title(root, milestone),
        next_kind=step.kind,
        next_phase=step.phase,
        next_title=step.title,
        next_source=step.source,
        next_estimate=step.estimate,
        next_estimate_source=step.estimate_source,
        next_size=size,
        next_model=model[0] if model else None,
        next_model_why=model[1] if model else None,
        next_critique_step=critique,
        next_stops=stops,
        next_machine=step.machine,
        next_attended=step.attended,
        prompt=step.prompt,
        switch=step.switch,
        last_phase=last,
        last_phase_source=last_source,
        last_commit=repo.subject(root, head) if head else None,
        open_questions=open_questions(root),
        **outlook(root, milestone, last, step.phase),
    )
    try:
        changes = repo.changes(root)
    except repo.GitError as error:
        changes = [str(error)]
        problems.append(f"{error}; fix: run inside the Optilux checkout")
    facts.update(clean=not changes, changes=changes)
    hooks = repo.hooks_path(root)
    facts.update(hooks_path=hooks, hooks_set=hooks == HOOKS_PATH)
    if hooks != HOOKS_PATH:
        problems.append(
            f"hooks path not set; fix: `git config --local core.hooksPath {HOOKS_PATH}`"
        )
    return facts


def cut(text: str, width: int = CUT, asides: bool = True) -> str:
    """The text cut to the width. A text that is too long first drops its parentheticals, which
    carry cites and asides, not the point (unless `asides` is False: a commit subject's scope is
    part of it); one still too long ends in an ellipsis at a word."""
    while asides and len(text) > width and (shorter := re.sub(r"\s*\([^()]*\)", "", text)) != text:
        text = shorter
    if len(text) <= width:
        return text
    return text[: width - 3].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def rows(label: str, items: list[str]) -> list[str]:
    """A label with its first item, the others under it; the label alone for no items."""
    pad = " " * LABEL
    return [f"{label:<{LABEL}}{item}" if i == 0 else f"{pad}{item}" for i, item in enumerate(items)]


def decision_rows(facts: dict) -> list[str]:
    """The briefing's rows on the next prompt: what it is, how big, on which model, whether it
    offers a critique, what it needs of the user and of the machine."""
    kind = facts["next_kind"]
    if kind is None:
        return rows("NEXT", ["no next prompt: see PROBLEM below"])
    name = " ".join(filter(None, (facts["next_phase"], facts["next_title"])))
    source = facts["next_source"] or prompts.prompt_name(facts["milestone"])
    hours, size = facts["next_estimate"], facts["next_size"]
    complexity = "unknown (no estimate for this prompt)"
    if hours is not None:
        complexity = f"{size} ({hours:g} h agent estimate, {facts['next_estimate_source']})"
    model = "unknown (no size to choose by)"
    if facts["next_model"]:
        model = f"{facts['next_model']} ({facts['next_model_why']})"
    step = facts["next_critique_step"]
    critique = "no" if step is None else f"offered at step {step} (/critique; you decide)"
    needs = [cut(stop) for stop in facts["next_stops"]]
    if facts["next_attended"]:
        needs.append(f"attended: {cut(facts['next_attended'])}")
    out = rows("NEXT", [f"{name} ({source})"])
    if facts["switch"]:
        out += rows("SWITCH", [f"first run the switch block to m{facts['milestone'] + 1} below"])
    out += rows("KIND", [KINDS[kind]])
    out += rows("COMPLEXITY", [complexity])
    out += rows("MODEL", [model])
    out += rows("CRITIQUE", [critique])
    out += rows("NEEDS YOU", needs[:SHOWN] or ["nothing: it runs unattended"])
    if kind == IMPLEMENTATION:
        out += rows("MACHINE", [facts["next_machine"] or "none stated in the plan"])
    return out


def last_text(facts: dict) -> str:
    """The last phase done, where it was read, and the newest commit: a phase may take several
    commits, and commits after it are the next phase's work in progress."""
    head = "no phase done yet"
    if facts["last_phase"] is not None:
        name = " ".join(filter(None, (facts["last_phase"], facts["last_title"])))
        head = f"{name} done ({facts['last_phase_source']})"
    room = max(CUT - len(head) - len('; newest ""'), 24)
    return f'{head}; newest "{cut(facts["last_commit"] or "none", room, asides=False)}"'


def state_rows(facts: dict) -> list[str]:
    """The briefing's rows on the milestone: progress, the last phase done, what follows the
    next prompt and the handoff's open questions."""
    progress = facts["progress"]
    bar = "no plan or prompt set yet"
    if progress:
        filled = round(BAR * progress["done"] / progress["total"])
        counts = f"{progress['done']} of {progress['total']} phases"
        span = f"{progress['first']} to {progress['last']}"
        hours = "hours unknown"
        if progress["hours_total"] is not None:
            hours = f"{progress['hours_done']:g} of {progress['hours_total']:g} h agent"
        bar = f"[{'#' * filled}{'.' * (BAR - filled)}] {counts} ({span}), {hours}"
    out = rows("PROGRESS", [bar])
    out += rows("LAST", [last_text(facts)])
    then = []
    for phase in facts["upcoming"]:
        cost = "no estimate"
        if phase["hours"] is not None:
            cost = f"{phase['size']}, {phase['hours']:g} h"
        then.append(f"{phase['phase']} {cut(phase['title'], 48)} ({cost})")
    if then:
        out += rows("THEN", then)
    # Each question as its first clause: the handoff words them in full, one per bullet.
    questions = [cut(question.split(";")[0]) for question in facts["open_questions"]]
    more = len(questions) - SHOWN
    if more > 0:
        questions = [*questions[:SHOWN], f"(+{more} more in {HANDOFF})"]
    out += rows("OPEN", questions or [f"none in {HANDOFF}"])
    return out


def check_rows(facts: dict) -> list[str]:
    """The briefing's last rows: the tree and the hooks, then every problem."""
    changes = facts["changes"]
    shown = "; ".join(change.strip() for change in changes[:SHOWN])
    tree = "clean" if not changes else cut(f"{len(changes)} changes: {shown}")
    checks = ["hooks set" if facts["hooks_set"] else "hooks not set"]
    out = rows("TREE", [tree]) + rows("CHECKS", [" | ".join(checks)])
    for problem in facts["problems"]:  # a label on each: a problem is read alone
        out += rows("PROBLEM", [problem])
    return out


def briefing(facts: dict) -> list[str]:
    """The lines that open `optilux status`, up to the first blank line, for a human: no blank
    line inside, ASCII only (the Windows console would choke on more)."""
    if "branch" not in facts:
        return rows("PROBLEM", [facts["problems"][0]])
    pushed = {True: "pushed", False: "not pushed", None: "no push check on main"}[facts["pushed"]]
    main = facts["version_main"] or (facts["main_sha"] or "absent")[:7]
    name = facts["milestone_name"] or f"M{facts['milestone']}"
    head = f"OPTILUX {name} | branch {facts['branch'] or 'detached'}, {pushed}"
    head += f" | {facts['version_local'] or 'none'} local, {main} on origin/main"
    return [
        head,
        "=" * RULE,
        *decision_rows(facts),
        "-" * RULE,
        *state_rows(facts),
        "-" * RULE,
        *check_rows(facts),
    ]


def print_text(facts: dict) -> None:
    print("\n".join(briefing(facts)))
    if "branch" not in facts:
        return
    if facts["switch"]:
        print(f"\nswitch to m{facts['milestone'] + 1} first, paste:")
        print("\n".join(facts["switch"]))
    if facts["prompt"] is not None:
        name = " ".join(filter(None, (facts["next_phase"], facts["next_title"])))
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
    help="a briefing on the milestone's state and the next prompt, with its kind, size and model",
    run=run,
    structured=True,
)
