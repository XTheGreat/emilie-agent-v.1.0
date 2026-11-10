"""/review, /commit and /pr: gather the git facts locally, then hand the model a focused brief.

The model does the thinking; these helpers only collect context (status, diff, log) with plain git, clip it to a sane
size, and say what is and is not allowed. Nothing here pushes or creates a PR: that stays a separate, asked step.
"""
import re
import shutil
import subprocess


def _git(*args: str, cwd: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=30)
        return r.returncode, r.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def in_repo(cwd: str | None = None) -> bool:
    code, out = _git("rev-parse", "--is-inside-work-tree", cwd=cwd)
    return code == 0 and out == "true"


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[diff cut: {len(text) - limit} more characters; look at the rest with git diff <file>]"


def _untracked(cwd: str | None) -> list[str]:
    return [l for l in _git("ls-files", "--others", "--exclude-standard", cwd=cwd)[1].splitlines() if l]


def review_brief(arg: str, limit: int, cwd: str | None = None) -> str | None:
    """Brief for /review. arg = '' (uncommitted changes), a branch/commit (changes since it), or a PR number (with gh).
    None when there is nothing to review or this is not a git repository."""
    if not in_repo(cwd):
        return None
    arg = arg.strip()
    if arg and (arg.startswith("-") or not looks_like_ref(arg)):     # a ref, never an option
        return None
    if arg.isdigit() and shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "pr", "diff", arg], cwd=cwd, capture_output=True, timeout=60)
            diff, what = r.stdout.decode("utf-8", errors="replace"), f"pull request #{arg}"
        except (OSError, subprocess.TimeoutExpired):
            return None
    elif arg:
        code, diff = _git("diff", f"{arg}...HEAD", cwd=cwd)
        what = f"the changes since {arg}"
        if code != 0 or not diff:
            return None
    else:
        _, diff = _git("diff", "HEAD", cwd=cwd)
        what = "the uncommitted changes"
        new = _untracked(cwd)
        if not diff and not new:
            _, diff = _git("show", "--format=fuller", "HEAD", cwd=cwd)
            what = "the last commit (there are no uncommitted changes)"
        elif new:
            diff += "\n\n# New, untracked files (not in the diff above; read them if they matter):\n" + "\n".join(new)
    if not diff.strip():
        return None
    return (f"Review {what}. Read the diff below, and open the surrounding code with read_file / grep when a change "
            "cannot be judged from the diff alone.\n\n"
            "Report only real problems, most serious first, each as: `file:line` - what is wrong - why it matters - the fix. "
            "Look for: bugs and wrong logic, unhandled errors and edge cases, security (injection, secrets, unsafe input), "
            "data loss, performance traps, broken or missing tests, and risky behaviour changes. Skip style nitpicks. "
            "If something is fine, say so in one line. Do NOT edit any file: this is a review.\n\n"
            f"```diff\n{_clip(diff, limit)}\n```")


def commit_brief(hint: str, limit: int, cwd: str | None = None) -> str | None:
    """Brief for /commit: write the message from the real changes, stage what belongs, commit. Never pushes."""
    if not in_repo(cwd):
        return None
    _, status = _git("status", "--short", cwd=cwd)
    if not status:
        return None
    _, staged = _git("diff", "--cached", cwd=cwd)
    _, unstaged = _git("diff", cwd=cwd)
    _, log = _git("log", "-8", "--format=%s", cwd=cwd)
    new = _untracked(cwd)
    body = staged if staged else unstaged
    which = "the STAGED changes" if staged else "the working-tree changes (nothing is staged yet)"
    return ("Make a git commit.\n"
            f"1. Look at {which} below and write a commit message in the style of the recent ones: a short imperative "
            "subject (about 50-70 characters) and, when the change has several parts or a non-obvious reason, a blank "
            "line and a few lines saying what changed and WHY.\n"
            "2. If nothing is staged, stage only the files that belong to ONE logical change with `git add <files>` "
            "(never `git add -A` blindly: skip secrets such as .env, build output and unrelated edits, and say what you "
            "left out).\n"
            "3. Run `git commit` with the message (use a here-string or -F, not a long -m on one line).\n"
            "4. Do NOT push. Finish by showing the commit hash and subject.\n"
            + (f"The user's hint for the message: {hint.strip()}\n" if hint.strip() else "")
            + f"\nRecent commit subjects:\n{log}\n\nStatus:\n{status}\n"
            + (f"\nUntracked files: {', '.join(new[:20])}\n" if new else "")
            + f"\n```diff\n{_clip(body, limit)}\n```")


def pr_brief(base: str, limit: int, cwd: str | None = None) -> str | None:
    """Brief for /pr: draft a title and description from the branch's commits and diff. Does not push or create it."""
    if not in_repo(cwd):
        return None
    base = base.strip()
    if base and (base.startswith("-") or not looks_like_ref(base)):
        return None
    if not base:
        for cand in ("origin/main", "origin/master", "main", "master"):
            if _git("rev-parse", "--verify", "--quiet", cand, cwd=cwd)[0] == 0:
                base = cand
                break
    if not base:
        return None
    _, branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    _, commits = _git("log", f"{base}..HEAD", "--format=%h %s", cwd=cwd)
    _, stat = _git("diff", "--stat", f"{base}...HEAD", cwd=cwd)
    _, diff = _git("diff", f"{base}...HEAD", cwd=cwd)
    if not commits and not diff:
        return None
    gh = bool(shutil.which("gh"))
    return (f"Draft a pull request for branch `{branch}` into `{base}`.\n"
            "Write: (1) a title under 70 characters; (2) a description with a short summary, a bullet list of the "
            "notable changes and why, and a short 'how to test'. Base it only on the commits and diff below.\n"
            "Show the title and description in your answer. Do NOT push the branch and do NOT create the PR yet: "
            + ("the `gh` CLI is installed, so after showing the text offer to run `gh pr create` and wait for a yes."
               if gh else "the `gh` CLI is not installed, so tell the user the title and body can be pasted into GitHub.")
            + f"\n\nCommits ({base}..HEAD):\n{commits}\n\nFiles:\n{stat}\n\n```diff\n{_clip(diff, limit)}\n```")


def looks_like_ref(s: str) -> bool:
    return bool(re.fullmatch(r"[\w./@^~-]+", s.strip())) if s.strip() else True
