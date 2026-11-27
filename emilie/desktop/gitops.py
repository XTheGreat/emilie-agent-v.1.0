"""The Git panel: the state of the repository a session works in (staged, changed and untracked files, conflicts,
branches, stashes, recent commits) and what can be done to it (stage, unstage, discard, commit, switch or create a
branch, stash, fetch, pull, push, git init). Paths are relative to the repository root, as git's porcelain output
gives them; every command runs at the root."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .projkit import inside, run, run_full

GIT = ["git", "-c", "core.quotepath=off", "-c", "color.ui=false"]
MAX_ENTRIES = 5000
_REF = re.compile(r"^[A-Za-z0-9_./@{}^~+-]{1,200}$")
_GITHUB = re.compile(r"^(?:https://(?:[^@/]+@)?|git@|ssh://git@)github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/?$")
QUIET_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_EDITOR="true", GIT_MERGE_AUTOEDIT="no")


class GitError(Exception):
    pass


def _git(root: str, *args: str, timeout: float = 30, input: str | None = None) -> tuple[int, str, str]:
    return run_full([*GIT, *args], root, timeout, input, env=QUIET_ENV)


def _ok(root: str, *args: str, timeout: float = 60) -> str:
    """Run a git command that must succeed; its message is the error otherwise."""
    code, out, err = _git(root, *args, timeout=timeout)
    if code != 0:
        raise GitError((err or out).strip() or f"git {args[0]} failed")
    return (out + err).strip()


def ref_ok(r: str) -> bool:
    return bool(r) and bool(_REF.match(r)) and not r.startswith("-") and ".." not in r


def repo(cwd: str) -> tuple[str, str] | None:
    """(the repository root, its .git folder), or None outside a repository."""
    if not cwd or not os.path.isdir(cwd):
        return None
    code, out, _ = run_full(["git", "-C", cwd, "rev-parse", "--show-toplevel", "--absolute-git-dir"], cwd, 15)
    lines = [l for l in out.splitlines() if l.strip()]
    if code != 0 or len(lines) < 2:
        return None
    return os.path.normpath(lines[0]), os.path.normpath(lines[1])


def _root(cwd: str) -> str:
    r = repo(cwd)
    if not r:
        raise GitError("not a git repository")
    return r[0]


def _batches(paths: list[str], room: int = 6000):
    """Paths in groups short enough for one command line (Windows allows 32k characters)."""
    cur: list[str] = []
    size = 0
    for p in paths:
        if cur and size + len(p) + 3 > room:
            yield cur
            cur, size = [], 0
        cur.append(p)
        size += len(p) + 3
    if cur:
        yield cur


def _clean(paths) -> list[str]:
    out = []
    for p in paths or []:
        p = str(p).replace("\\", "/").strip()
        if p and not p.startswith("/") and ":" not in p[:2] and ".." not in p.split("/"):
            out.append(p)
    return out


# ---------------------------------------------------------------------------------------------------- status
def status(cwd: str) -> dict:
    r = repo(cwd)
    if not r:
        return {"repo": False, "can_init": bool(cwd) and os.path.isdir(cwd)}
    root, gitdir = r
    code, out, err = _git(root, "status", "--porcelain=v2", "--branch", "--show-stash", "-z", "--untracked-files=all",
                          timeout=60)
    if code != 0:
        return {"repo": True, "root": root, "error": (err or out).strip()}
    head = {"oid": "", "branch": "", "upstream": "", "ahead": 0, "behind": 0, "stashes": 0}
    staged: list[dict] = []
    changed: list[dict] = []
    conflicts: list[dict] = []
    untracked = 0
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if not e:
            continue
        if e.startswith("# "):
            k, _, v = e[2:].partition(" ")
            if k == "branch.oid":
                head["oid"] = v
            elif k == "branch.head":
                head["branch"] = v
            elif k == "branch.upstream":
                head["upstream"] = v
            elif k == "branch.ab":
                m = re.match(r"\+(\d+) -(\d+)", v)
                if m:
                    head["ahead"], head["behind"] = int(m.group(1)), int(m.group(2))
            elif k == "stash":
                head["stashes"] = int(v) if v.isdigit() else 0
            continue
        t = e[0]
        if t in "12":
            f = e.split(" ", 8 if t == "1" else 9)
            xy, path = f[1], f[-1]
            orig = ""
            if t == "2":
                orig = parts[i] if i < len(parts) else ""
                i += 1
            x, y = xy[0], xy[1]
            if x != "." and len(staged) < MAX_ENTRIES:
                staged.append({"path": path, "status": {"T": "M", "C": "A"}.get(x, x), "orig": orig})
            if y != "." and len(changed) < MAX_ENTRIES:
                changed.append({"path": path, "status": {"T": "M"}.get(y, y)})
        elif t == "u":
            f = e.split(" ", 10)
            conflicts.append({"path": f[-1], "status": f[1]})
        elif t == "?":
            untracked += 1
            if len(changed) < MAX_ENTRIES:
                changed.append({"path": e[2:], "status": "U"})
    g = Path(gitdir)
    state = ("merging" if (g / "MERGE_HEAD").exists() else
             "rebasing" if (g / "rebase-merge").is_dir() or (g / "rebase-apply").is_dir() else
             "cherry-picking" if (g / "CHERRY_PICK_HEAD").exists() else
             "reverting" if (g / "REVERT_HEAD").exists() else "")
    initial = head["oid"] in ("", "(initial)")
    return {"repo": True, "root": root, "branch": "" if head["branch"] == "(detached)" else head["branch"],
            "detached": head["branch"] == "(detached)", "oid": "" if initial else head["oid"][:9], "initial": initial,
            "upstream": head["upstream"], "ahead": head["ahead"], "behind": head["behind"],
            "staged": staged, "changed": changed, "untracked": untracked, "conflicts": conflicts, "state": state,
            "stash_count": head["stashes"], **_extras(root, initial, head["stashes"])}


def _extras(root: str, initial: bool, nstash: int) -> dict:
    """Branches, remotes, stashes and the recent commits."""
    _c, refs, _e = _git(root, "for-each-ref", "--sort=-committerdate",
                        "--format=%(HEAD)%00%(refname)%00%(refname:short)%00%(upstream:short)%00"
                        "%(upstream:track,nobracket)%00%(committerdate:relative)", "refs/heads", "refs/remotes")
    branches, remote_branches = [], []
    for line in refs.splitlines():
        f = line.split("\0")
        if len(f) < 6:
            continue
        if f[1].startswith("refs/remotes/"):
            if not f[1].endswith("/HEAD") and len(remote_branches) < 300:
                remote_branches.append({"name": f[2], "when": f[5]})
        elif len(branches) < 300:
            branches.append({"name": f[2], "current": f[0] == "*", "upstream": f[3], "track": f[4], "when": f[5]})
    _c, rem, _e = _git(root, "remote")
    remotes = [x.strip() for x in rem.splitlines() if x.strip()]
    web = ""
    if remotes:
        name = "origin" if "origin" in remotes else remotes[0]
        _c, url, _e = _git(root, "remote", "get-url", name)
        m = _GITHUB.match(url.strip())
        if m:
            web = f"https://github.com/{m.group(1)}"
    commits = []
    if not initial:
        _c, lg, _e = _git(root, "log", "-n", "60", "--format=%h%x1f%H%x1f%s%x1f%an%x1f%ar%x1f%D%x1e")
        for rec in lg.split("\x1e"):
            f = rec.strip("\n").split("\x1f")
            if len(f) == 6:
                commits.append({"hash": f[0], "full": f[1], "subject": f[2], "author": f[3], "when": f[4],
                                "refs": [x.strip() for x in f[5].split(",") if x.strip()]})
    stashes = []
    if nstash:
        _c, st, _e = _git(root, "stash", "list", "--format=%gd%x1f%s%x1f%cr")
        for line in st.splitlines():
            f = line.split("\x1f")
            if len(f) == 3:
                stashes.append({"ref": f[0], "subject": f[1], "when": f[2]})
    return {"branches": branches, "remote_branches": remote_branches, "remotes": remotes, "web": web,
            "commits": commits, "stashes": stashes}


# ---------------------------------------------------------------------------------------------------- diffs
def _body(diff: str) -> dict:
    """A diff without its header lines, with the counts the panel shows."""
    if re.search(r"^Binary files .* differ$", diff, re.M):
        return {"text": "", "added": 0, "removed": 0, "nodiff": "Binary file"}
    at = diff.find("\n@@")
    text = diff[at + 1:] if at >= 0 else ("" if diff.startswith("diff --git") else diff)
    text = text.rstrip("\n")
    lines = text.split("\n") if text else []
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    if len(text) > 1_500_000:
        text = text[:1_500_000] + "\n… (diff cut)"
    return {"text": text, "added": added, "removed": removed, "nodiff": "" if text else "No changes to show"}


def file_diff(cwd: str, path: str, staged: bool = False, untracked: bool = False) -> dict:
    root = _root(cwd)
    p = _clean([path])
    if not p:
        raise GitError("bad path")
    if untracked:
        f = Path(root) / p[0]
        if not inside(root, f) or not f.is_file():
            return {"text": "", "added": 0, "removed": 0, "nodiff": "Not a file"}
        if f.stat().st_size > 400_000:
            return {"text": "", "added": 0, "removed": 0, "nodiff": "Too large to show"}
        data = f.read_bytes()
        if b"\x00" in data[:8192]:
            return {"text": "", "added": 0, "removed": 0, "nodiff": "Binary file"}
        lines = data.decode("utf-8", errors="replace").splitlines()
        return {"text": f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + l for l in lines), "added": len(lines),
                "removed": 0, "nodiff": "" if lines else "Empty file"}
    args = ["diff", "--no-color", "--no-ext-diff", "-M"] + (["--cached"] if staged else []) + ["--", p[0]]
    code, out, err = _git(root, *args, timeout=30)
    if code != 0:
        raise GitError((err or out).strip())
    return _body(out)


def commit_files(cwd: str, h: str) -> dict:
    """What one commit changed: its full message and each file with its counts."""
    root = _root(cwd)
    if not ref_ok(h):
        raise GitError("bad commit")
    _c, meta, _e = _git(root, "show", "-s", "--format=%H%x1f%an%x1f%ae%x1f%ar%x1f%ad%x1f%B", "--date=format:%Y-%m-%d %H:%M", h)
    f = meta.split("\x1f", 5)
    _c, ns, _e = _git(root, "show", "-m", "--first-parent", "--format=", "--name-status", "-M", "-z", h)
    _c, num, _e = _git(root, "show", "-m", "--first-parent", "--format=", "--numstat", "-M", "-z", h)
    files: dict[str, dict] = {}
    parts = ns.lstrip("\n").split("\0")
    i = 0
    while i < len(parts):
        st = parts[i].strip()
        i += 1
        if not st:
            continue
        if st[0] in "RC" and i + 1 < len(parts):
            orig, path = parts[i], parts[i + 1]
            i += 2
        elif i < len(parts):
            orig, path = "", parts[i]
            i += 1
        else:
            break
        files[path] = {"path": path, "orig": orig, "status": st[0], "added": 0, "removed": 0}
    parts = num.lstrip("\n").split("\0")
    i = 0
    while i < len(parts):
        f2 = parts[i].split("\t")
        i += 1
        if len(f2) < 3:
            continue
        path = f2[2]
        if not path and i + 1 < len(parts):            # a rename: the old and new names follow
            path = parts[i + 1]
            i += 2
        if path in files:
            files[path]["added"] = int(f2[0]) if f2[0].isdigit() else 0
            files[path]["removed"] = int(f2[1]) if f2[1].isdigit() else 0
    return {"hash": f[0][:9] if f else h, "full": f[0] if f else h, "author": f[1] if len(f) > 1 else "",
            "email": f[2] if len(f) > 2 else "", "when": f[3] if len(f) > 3 else "", "date": f[4] if len(f) > 4 else "",
            "message": (f[5] if len(f) > 5 else "").strip(), "files": list(files.values())[:2000]}


# ---------------------------------------------------------------------------------------------------- actions
def init(cwd: str) -> dict:
    if not cwd or not os.path.isdir(cwd):
        raise GitError("folder not found")
    code, out = run(["git", "init"], cwd, 30)
    if code != 0:
        raise GitError(out.strip())
    return {"ok": True, "message": out.strip()}


def stage(cwd: str, paths: list[str] | None) -> dict:
    root = _root(cwd)
    ps = _clean(paths)
    if not ps:
        _ok(root, "add", "-A")
    for b in _batches(ps):
        _ok(root, "--literal-pathspecs", "add", "-A", "--", *b)
    return {"ok": True}


def unstage(cwd: str, paths: list[str] | None) -> dict:
    root = _root(cwd)
    ps = _clean(paths)
    has_head = _git(root, "rev-parse", "--verify", "-q", "HEAD")[0] == 0
    if not has_head:                                 # before the first commit there is no HEAD to go back to
        if not ps:
            _ok(root, "rm", "--cached", "-r", "-q", "--", ".")
        for b in _batches(ps):
            _ok(root, "--literal-pathspecs", "rm", "--cached", "-r", "-q", "--", *b)
        return {"ok": True}
    if not ps:
        _ok(root, "reset", "-q")
    for b in _batches(ps):
        _ok(root, "--literal-pathspecs", "reset", "-q", "HEAD", "--", *b)
    return {"ok": True}


def discard(cwd: str, paths: list[str] | None, untracked: list[str] | None) -> dict:
    """Throw away changes not staged: tracked files go back to what is staged (or committed); untracked files are
    deleted. The panel asks first."""
    root = _root(cwd)
    ps = _clean(paths)
    for b in _batches(ps):
        code, out, err = _git(root, "--literal-pathspecs", "restore", "--worktree", "--", *b)
        if code != 0:
            _ok(root, "--literal-pathspecs", "checkout", "--", *b)
    gone = 0
    for b in _batches(_clean(untracked)):
        # only what git itself still calls untracked (and not ignored) is deleted
        _c, out, _e = _git(root, "--literal-pathspecs", "ls-files", "-z", "--others", "--exclude-standard", "--", *b)
        for rel_path in [x for x in out.split("\0") if x]:
            f = Path(root) / rel_path
            if inside(root, f) and f.is_file() and not f.is_symlink():
                try:
                    f.unlink()
                    gone += 1
                except OSError as e:
                    raise GitError(f"could not delete {rel_path}: {e}")
    return {"ok": True, "deleted": gone}


def commit(job, cwd: str, message: str, amend: bool = False, all_: bool = False, push: bool = False) -> dict:
    root = _root(cwd)
    message = (message or "").strip()
    if not message and not amend:
        raise GitError("Write a commit message first.")
    if all_:
        job.say("$ git add -A")
        code, out = job.run([*GIT, "add", "-A"], cwd=root, env=QUIET_ENV)
        if code != 0:
            raise GitError(out.strip() or "git add failed")
    args = [*GIT, "commit"]
    tmp = None
    if message:
        fd, tmp = tempfile.mkstemp(prefix="emilie-commit-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(message + "\n")
        args += ["-F", tmp]
    if amend:
        args += ["--amend"] + ([] if message else ["--no-edit"])
    try:
        job.say("$ git commit" + (" --amend" if amend else ""))
        code, out = job.run(args, cwd=root, env=QUIET_ENV, timeout=600)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    if code != 0:
        raise GitError(_last_words(out) or "git commit failed")
    h = _git(root, "rev-parse", "--short", "HEAD")[1].strip()
    res = {"ok": True, "hash": h, "message": message.splitlines()[0] if message else ""}
    if push:
        res["push"] = sync(job, cwd, "push")
    return res


def _last_words(out: str) -> str:
    lines = [l for l in out.strip().splitlines() if l.strip()]
    return "\n".join(lines[-12:])


def sync(job, cwd: str, action: str) -> dict:
    root = _root(cwd)
    if action == "fetch":
        args = ["fetch", "--all", "--prune"]
    elif action == "pull":
        args = ["pull", "--no-edit"]
    elif action == "push":
        st = status(cwd)
        if not st.get("remotes"):
            raise GitError("This repository has no remote to push to.")
        if st.get("detached"):
            raise GitError("Not on a branch (detached HEAD): switch to a branch to push.")
        if st.get("upstream"):
            args = ["push"]
        else:
            remote = "origin" if "origin" in st["remotes"] else st["remotes"][0]
            args = ["push", "-u", remote, st["branch"]]
    else:
        raise GitError(f"unknown action {action}")
    job.say("$ git " + " ".join(args))
    code, out = job.run([*GIT, *args], cwd=root, env=QUIET_ENV, timeout=600)
    if code != 0:
        raise GitError(_last_words(out) or f"git {action} failed")
    return {"ok": True, "output": _last_words(out)}


def branch(cwd: str, action: str, name: str, start: str = "", force: bool = False) -> dict:
    root = _root(cwd)
    name = (name or "").strip()
    if action in ("create", "checkout", "delete", "track"):
        if not name:
            raise GitError("Give the branch a name.")
        if action == "create" and run_full(["git", "check-ref-format", "--branch", name], root, 10)[0] != 0:
            raise GitError(f"'{name}' is not a valid branch name.")
        if action != "create" and not ref_ok(name):
            raise GitError("bad branch name")
    if action == "checkout":
        code, out, err = _git(root, "switch", name, timeout=60)
        if code != 0:
            _ok(root, "checkout", name)
    elif action == "track":                           # a remote branch: make the local one that follows it
        local = name.split("/", 1)[1] if "/" in name else name
        exists = _git(root, "rev-parse", "--verify", "-q", f"refs/heads/{local}")[0] == 0
        if exists:
            _ok(root, "switch", local)
        else:
            _ok(root, "switch", "-c", local, "--track", name)
    elif action == "create":
        if start and not ref_ok(start):
            raise GitError("bad starting point")
        _ok(root, "switch", "-c", name, *([start] if start else []))
    elif action == "delete":
        _ok(root, "branch", "-D" if force else "-d", name)
    else:
        raise GitError(f"unknown action {action}")
    return {"ok": True}


def stash(cwd: str, action: str, ref: str = "", message: str = "") -> dict:
    root = _root(cwd)
    if ref and not ref_ok(ref):
        raise GitError("bad stash")
    if action == "push":
        _ok(root, "stash", "push", "--include-untracked", *(["-m", message.strip()] if message.strip() else []))
    elif action in ("pop", "apply", "drop"):
        _ok(root, "stash", action, *([ref] if ref else []))
    else:
        raise GitError(f"unknown action {action}")
    return {"ok": True}
