"""Hook bodies (docs/workflow.md#hooks-and-guards), run as `python -m optilux.hooks <name>`.

Git runs commit_msg and pre_commit through the sh shims in .githooks/; Claude Code runs git_guard
(PreToolUse; exit 2 blocks) and post_edit (PostToolUse; never blocks) from .claude/settings.json.
"""

import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from optilux import REPO_ROOT, docs_check, prompts, repo

# main moves only by the user's rebase merge of a PR (docs/workflow.md#git).
MAIN = repo.MAIN
# docs/workflow.md#git (roadmap.md D33): one line, at most 72 characters, a Conventional Commits
# subject `type(scope)!: summary`, the scope optional and lowercase.
MAX_MESSAGE = 72
TYPES = ("feat", "fix", "perf", "refactor", "test", "docs", "build", "ci", "chore", "revert")
MESSAGE = re.compile(rf"(?:{'|'.join(TYPES)})(?:\([a-z0-9][a-z0-9-]*\))?!?: \S.*")
# What a subject never names: a milestone (M2) or phase (M2.P01), a release tag (v0.2.0) or a
# date; the version in VERSION is refused as well. A dependency's version passes (uv 0.12.23), so
# M0's and M1's phase IDs, shaped like it, are left to the format rule.
NAMES = re.compile(r"\bM\d+\b|\bv\d+\.\d+\.\d+\b|\b\d{4}-\d{2}-\d{2}\b")
# Attribution tokens (roadmap.md#decisions D4), whole words in any case. "Claude Code" names the
# tool whose hooks this repo configures (the 0.00.03 subject names it), so it passes unless "by",
# "with" or "via" make it an author; every attribution line the tool writes carries
# Co-Authored-By, Generated or anthropic.com, which stay refused.
ATTRIBUTION = re.compile(
    r"\b(?:co-authored-by|anthropic|generated)\b|\b(?:by|with|via)\s+claude\b"
    r"|\bclaude\b(?!\s+code\b)",
    re.IGNORECASE,
)

# Shell tokens: operators split commands; a newline is an operator too, so it is not whitespace.
OPERATOR_CHARS = "();<>|&\n"
REDIRECT_CHARS = set("<>&")
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"builtin", "command", "env", "exec", "nohup", "time"}
POSIX_SHELLS = {"bash", "dash", "sh", "zsh"}
POWERSHELLS = {"powershell", "pwsh"}
CMD = {"cmd"}
# git takes any unambiguous prefix of a long option (`--no-verif` is --no-verify): each guarded
# option with its shortest prefix the guard refuses. Shorter prefixes are ambiguous, which git
# refuses itself (`--fo`: --force or --follow-tags; `--no-ve`: --no-verify or --no-verbose).
SKIP_HOOKS = {"--no-verify": "--no-v"}
PUSH_FORCED = {"--force": "--for", "--force-with-lease": "--for", "--mirror": "--mi"}
PUSH_EVERY = {"--all": "--al", "--branches": "--br"}
# git's global options that take the next word as their value.
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
PUSH_VALUE_OPTIONS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
# commit's short options whose value follows in the same word or the next one, and those
# whose optional value can only follow in the same word (-u<mode>, -S<keyid>).
COMMIT_VALUE_LETTERS = set("mFCct")
COMMIT_ATTACHED_LETTERS = set("uS")
COMMIT_TEXT_OPTIONS = {"--message", "--trailer", "--author"}


def attribution(text: str) -> str | None:
    match = ATTRIBUTION.search(text)
    return match.group(0) if match else None


def commit_msg(text: str, version: str | None = None) -> list[str]:
    """Why git must refuse a commit message, each reason with its fix; empty when it passes.
    `version` is the release version in VERSION, which the subject must not name either."""
    message = "\n".join(line for line in text.splitlines() if not line.startswith("#")).strip()
    first = message.split("\n")[0]
    problems = []
    if "\n" in message:
        problems.append("more than one line: write one line, no body and no trailer")
    if len(first) > MAX_MESSAGE:
        problems.append(f"{len(first)} characters: cut it to {MAX_MESSAGE}")
    if not MESSAGE.fullmatch(first):
        problems.append(
            f"not `type(scope)!: summary`: start with one of {', '.join(TYPES)}, the scope "
            "optional and lowercase, e.g. `fix(status): read the handoff's last phase`"
        )
    named = [match.group(0) for match in NAMES.finditer(first)]
    if version and re.search(rf"(?<![\w.]){re.escape(version)}(?![\w.])", first):
        named.append(version)
    if named:
        problems.append(
            f"names {', '.join(repr(name) for name in named)}: a subject never names a "
            "milestone, phase, version or date; say what changed"
        )
    if token := attribution(message):
        problems.append(f"attribution token {token!r}: remove it (AGENTS.md, Rules)")
    return problems


def segments(command: str) -> list[list[str]]:
    """The simple commands of a shell command line: words split at operators, redirects dropped."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=OPERATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:  # an unclosed quote: judge the plain words rather than nothing
        tokens = command.replace("\n", " ; ").split()
    found: list[list[str]] = [[]]
    skip = False
    for token in tokens:
        if skip:
            skip = False
        elif token and set(token) <= set(OPERATOR_CHARS):
            if set(token) <= REDIRECT_CHARS and token not in ("&", "&&"):
                skip = True  # the redirect's target is no argument
            else:
                found.append([])
        else:
            found[-1].append(token)
    return [words for words in found if words]


def program(word: str) -> str:
    return PurePosixPath(word.replace("\\", "/")).name.lower().removesuffix(".exe")


def git_calls(command: str) -> list[list[str]]:
    """The arguments of every git invocation in a command line, `sh -c` and `pwsh -c` included."""
    calls = []
    for words in segments(command):
        while words and (ASSIGNMENT.match(words[0]) or program(words[0]) in WRAPPERS):
            words = words[1:]
        if not words:
            continue
        name, args = program(words[0]), words[1:]
        if name == "git":
            calls.append(args)
        elif name in POSIX_SHELLS:
            for index, arg in enumerate(args[:-1]):
                if arg.startswith("-") and not arg.startswith("--") and "c" in arg:
                    calls += git_calls(args[index + 1])
                    break
        elif name in POWERSHELLS:
            for index, arg in enumerate(args):
                if arg.lower() in ("-c", "-command"):
                    calls += git_calls(" ".join(args[index + 1 :]))
                    break
        elif name in CMD:
            for index, arg in enumerate(args):
                if arg.lower() in ("/c", "/k"):
                    calls += git_calls(" ".join(args[index + 1 :]))
                    break
    return calls


def abbreviates(arg: str, options: dict[str, str]) -> str | None:
    """The guarded long option `arg` spells or abbreviates, None for any other."""
    name = arg.split("=", 1)[0]
    for option, shortest in options.items():
        if name.startswith(shortest) and option.startswith(name):
            return option
    return None


def split_git(args: list[str]) -> tuple[list[str], str | None, list[str]]:
    """(global options, subcommand, the subcommand's arguments) of one git invocation."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in GIT_VALUE_OPTIONS else 1
    if index >= len(args):
        return args, None, []
    return args[:index], args[index], args[index + 1 :]


def commit_parts(args: list[str]) -> tuple[bool, list[str]]:
    """(whether `-n` skips the hooks, the message, trailer and author texts) of `git commit`."""
    skips, texts = False, []
    index = 0
    while index < len(args) and args[index] != "--":
        arg = args[index]
        if arg.startswith("--"):
            name, equals, value = arg.partition("=")
            if name in COMMIT_TEXT_OPTIONS:
                if not equals and index + 1 < len(args):
                    index += 1
                    value = args[index]
                texts.append(value)
        elif arg.startswith("-"):
            for position, letter in enumerate(arg[1:], 1):
                if letter in COMMIT_ATTACHED_LETTERS:
                    break  # the rest of the word is its value
                if letter == "n":
                    skips = True
                if letter in COMMIT_VALUE_LETTERS:
                    value = arg[position + 1 :]
                    if not value and index + 1 < len(args):
                        index += 1
                        value = args[index]
                    if letter == "m":
                        texts.append(value)
                    break
        index += 1
    return skips, texts


def push_refusal(args: list[str], branch: Callable[[], str | None]) -> str | None:
    positionals = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals += args[index + 1 :]
            break
        if arg in PUSH_VALUE_OPTIONS:
            index += 2
            continue
        if abbreviates(arg, PUSH_FORCED):
            return f"`git push {arg}` rewrites remote history; push without force"
        if abbreviates(arg, PUSH_EVERY):
            return f"`git push {arg}` pushes every branch, main too; name the milestone branch"
        if arg.startswith("-") and not arg.startswith("--"):
            letters = arg[1:].split("o")[0]  # -o takes a value: what follows it is no flag
            if "f" in letters:
                return f"`git push {arg}` forces the push; push without -f"
        elif not arg.startswith("-"):
            positionals.append(arg)
        index += 1
    refspecs = positionals[1:]
    if not refspecs:
        if branch() == MAIN:
            return "a bare `git push` on main pushes main; switch to the milestone branch"
        return None
    for spec in refspecs:
        if spec.startswith("+"):
            return f"refspec `{spec}` forces the update; drop the leading +"
        sides = spec.split(":") if ":" in spec else [branch() if spec == "HEAD" else spec]
        if any(side and side.removeprefix("refs/heads/") == MAIN for side in sides):
            return f"`{spec}` pushes to main; main moves only by the user's merge of the PR"
    return None


def git_guard(command: str, branch: Callable[[], str | None]) -> str | None:
    """Why Claude Code must not run a shell command (docs/workflow.md#git); None lets it run.

    `branch` reads the current branch, needed only for a push without a refspec or with HEAD.
    """
    for args in git_calls(command):
        options, subcommand, rest = split_git(args)
        if any(abbreviates(arg, SKIP_HOOKS) for arg in rest):
            return "`--no-verify` skips the git hooks; fix what they refuse instead"
        for index, option in enumerate(options[:-1]):
            if option == "-c" and options[index + 1].lower().startswith("core.hookspath"):
                return "`-c core.hooksPath` skips the git hooks; fix what they refuse instead"
        if subcommand == "commit":
            skips, texts = commit_parts(rest)
            if skips:
                return "`git commit -n` skips the git hooks; fix what they refuse instead"
            for text in texts:
                if token := attribution(text):
                    return f"attribution token {token!r} in the commit; remove it"
        elif subcommand == "push":
            if reason := push_refusal(rest, branch):
                return reason
    return None


def ruff(paths: Sequence[Path], root: Path) -> list[str]:
    """ruff's lint and format findings on the given files, each with its fix."""
    names = [str(path) for path in paths]
    findings = []
    for check, fix in (
        (["check", "--output-format", "concise"], "uv run ruff check --fix"),
        (["format", "--check"], "uv run ruff format"),
    ):
        command = [sys.executable, "-m", "ruff", *check, *names]
        # S603: an argv list, no shell; the names are git's staged paths.
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)  # noqa: S603
        if result.returncode:
            output = (result.stdout + result.stderr).strip()
            findings.append(f"ruff {check[0]}:\n{output}\n  fix: `{fix} {' '.join(names)}`")
    return findings


def doc_findings(root: Path) -> list[str]:
    return [violation.text() for violation in docs_check.check_tree(root).violations]


def staged(root: Path) -> list[str]:
    command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)  # noqa: S603 constant argv
    return [name for name in result.stdout.split("\0") if name]


def handoff_findings(root: Path) -> list[str]:
    """The staged handoff's `Last phase:` line against HEAD's (docs/workflow.md#running-a-
    milestone): when it changes, it names the phase after HEAD's, of the branch's milestone, so
    `optilux status` never skips or repeats one."""
    old = prompts.handoff_phase(repo.file_at(root, "HEAD", prompts.HANDOFF))
    new = prompts.handoff_phase(repo.file_at(root, "", prompts.HANDOFF))
    if new == old:
        return []
    where = f"{prompts.HANDOFF}'s `Last phase:`"
    if new is None:
        return [f"{where} line is gone; fix: keep it, naming the last phase done"]
    key = prompts.phase_key(new)
    if key is None:
        return [f"{where} {new} names no phase; fix: write M<N>.P<PP>, the phase just done"]
    milestone = repo.milestone_of(repo.current_branch(root))
    if milestone is not None and key[0] != milestone:
        return [f"{where} {new} is no phase of m{milestone}; fix: name a phase of M{milestone}"]
    if old is not None and prompts.phase_key(old) is not None:
        expected = prompts.next_phase(old, key[0])
        if prompts.phase_key(expected) != key:
            return [f"{where} {new} does not follow {old}; fix: write {expected}"]
    return []


def version_findings(root: Path) -> list[str]:
    """The staged VERSION against the fetched origin/main's (docs/workflow.md#release): newer,
    with its `## <version> <Name>` entry staged in CHANGELOG.md, so a milestone's or a patch's
    first commit carries both. Read locally, without the network; skipped without origin/main."""
    from optilux.verbs import pack  # pack imports this module: a deferred import breaks the loop

    if repo.resolve(root, f"refs/remotes/{repo.ORIGIN}/{repo.MAIN}") is None:
        return []
    main = repo.released_at(root, f"{repo.ORIGIN}/{repo.MAIN}")
    version = repo.version_at(root, "")
    if version is None:
        return [f"no {repo.VERSION_FILE} staged; fix: add it with the release version"]
    if (repo.version_key(version) or ()) <= (repo.version_key(main) or ()):
        detail = f"VERSION {version} is not newer than origin/main's {main}"
        return [f"{detail}; fix: {pack.bump_fix(main or version)}"]
    try:
        pack.changelog_entry(root, version, "")
    except pack.PackError as error:
        return [str(error)]
    return []


def pre_commit(root: Path) -> list[str]:
    """ruff on the staged .py files, the doc rules when a .md is staged, the handoff's
    `Last phase:` line and VERSION against origin/main's; empty when clean."""
    files = staged(root)
    sources = [root / name for name in files if name.endswith(".py")]
    findings = ruff(sources, root) if sources else []
    if any(name.endswith(".md") for name in files):
        findings += doc_findings(root)
    if prompts.HANDOFF in files:
        findings += handoff_findings(root)
    return findings + version_findings(root)


def post_edit(path: Path, root: Path) -> list[str]:
    """ruff on an edited .py, the doc rules on an edited .md; empty when clean."""
    if path.suffix == ".py":
        return ruff([path], root)
    if path.suffix == ".md":
        return doc_findings(root)
    return []


def native(path: str) -> Path:
    """A path as Python reads it here: Git Bash's /c/x is C:/x on Windows."""
    match = re.fullmatch(r"/([A-Za-z])(/.*)?", path) if sys.platform == "win32" else None
    return Path(f"{match.group(1)}:{match.group(2) or '/'}") if match else Path(path)


def inside(path: str, root: Path) -> bool:
    return native(path).resolve().is_relative_to(root)


def names_repo(command: str, root: Path) -> bool:
    """Whether a command line names the repo by path (C:/x, C:\\x or Git Bash's /c/x)."""
    text = command.replace("\\", "/").lower()
    posix = root.as_posix().lower()
    msys = "/" + posix.replace(":", "", 1) if root.drive else posix
    return posix in text or msys in text


def current_branch(cwd: str) -> str | None:
    command = ["git", "symbolic-ref", "--short", "-q", "HEAD"]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)  # noqa: S603 constant argv
    return result.stdout.strip() or None


def read_event() -> dict | None:
    """The hook's JSON event from stdin; None when it cannot be read."""
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def run_git_guard(args: list[str]) -> int:
    event = read_event()
    if event is None:  # fails closed: the unread command could be a force push
        print(
            "optilux git guard: cannot read the hook's event (not a JSON object)", file=sys.stderr
        )
        return 2
    command = str((event.get("tool_input") or {}).get("command") or "")
    cwd = str(event.get("cwd") or ".")
    # Inert outside this repository, unless the command names it (a `cd` back into it).
    if not inside(cwd, REPO_ROOT) and not names_repo(command, REPO_ROOT):
        return 0
    reason = git_guard(command, lambda: current_branch(cwd))
    if reason is None:
        return 0
    print(f"optilux git guard: {reason} (docs/workflow.md#git)", file=sys.stderr)
    return 2


def run_post_edit(args: list[str]) -> int:
    event = read_event() or {}  # post_edit only adds context: an unread event edits nothing
    path = str((event.get("tool_input") or {}).get("file_path") or "")
    if not path or not inside(path, REPO_ROOT):
        return 0
    findings = post_edit(native(path).resolve(), REPO_ROOT)
    if findings:
        context = "optilux post-edit check:\n" + "\n".join(findings)
        output = {"hookEventName": "PostToolUse", "additionalContext": context}
        print(json.dumps({"hookSpecificOutput": output}))
    return 0


def run_commit_msg(args: list[str]) -> int:
    text = Path(args[0]).read_text(encoding="utf-8", errors="replace")
    # The shim runs this from the repository's root, where VERSION is the one being committed.
    version_file = Path(repo.VERSION_FILE)
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None
    problems = commit_msg(text, version)
    for problem in problems:
        print(f"commit-msg: refused: {problem}", file=sys.stderr)
    return 1 if problems else 0


def run_pre_commit(args: list[str]) -> int:
    findings = pre_commit(Path(args[0]) if args else Path.cwd())
    for finding in findings:
        print(f"pre-commit: {finding}", file=sys.stderr)
    return 1 if findings else 0


HOOKS: dict[str, Callable[[list[str]], int]] = {
    "commit_msg": run_commit_msg,
    "pre_commit": run_pre_commit,
    "git_guard": run_git_guard,
    "post_edit": run_post_edit,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in HOOKS:
        print(f"usage: python -m optilux.hooks {{{','.join(HOOKS)}}} [args]", file=sys.stderr)
        return 1
    return HOOKS[args[0]](args[1:])


if __name__ == "__main__":
    sys.exit(main())
