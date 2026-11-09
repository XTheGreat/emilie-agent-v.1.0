"""Permission policy: what passes automatically, what must be asked."""
import re
import shlex
from pathlib import Path
from .i18n import t as tr_, N_

READONLY_TOOLS = {"read_file", "grep", "glob", "todo_write", "use_skill", "web_search", "task", "tasks",   # task(s) = read-only sub-agents
                  "bg_output", "bg_stop"}                  # only touch background tasks Emilie itself started
MODES = ("ask", "trust", "plan")

READONLY_CMDS = {
    "ls", "pwd", "cat", "head", "tail", "wc", "echo", "which", "date", "tree", "stat",
    "du", "df", "uname", "whoami", "id", "file", "uniq", "diff", "basename", "dirname",
    "realpath", "printenv", "grep", "rg", "true", "false", "test", "[", "cd", "type",
    "hostname", "nproc", "free", "uptime", "ps", "sort",
    # Windows (cmd / PowerShell), read-only
    "dir", "get-childitem", "gci", "get-content", "gc", "select-string", "sls", "get-location", "gl",
    "where", "where.exe", "findstr", "get-date", "get-item", "gi", "test-path", "resolve-path",
    "get-command", "gcm", "write-output", "write-host", "measure-object", "get-process", "get-ps",
}
GIT_RO = {"status", "log", "diff", "show", "branch", "rev-parse", "remote", "ls-files", "blame"}
VERSIONED = {"python3", "python", "node", "npm", "pip", "pip3", "rustc", "cargo", "go",
             "java", "gcc", "make", "git"}

SAFE_ABS = ("/dev/null", "/usr", "/bin", "/lib", "/opt", "/tmp", "/etc/os-release")

DANGEROUS = [
    (r"\bsudo\b", N_('uses sudo')),
    (r"\b(Remove-Item|rmdir|rd|del|erase|Format-Volume|Stop-Computer|Restart-Computer|reg\s+(add|delete))\b",
     N_('deletes or changes the system')),
    (r"\b(winget|choco|scoop)\s+(install|uninstall|upgrade)\b", N_('changes system packages')),
    (r"\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^|;&]*\|\s*(iex|Invoke-Expression)\b",
     N_('downloads and runs a script')),
    (r"\bgit\s+push\b", N_('git push')),
    (r"\bgit\s+reset\s+--hard", N_('git reset --hard')),
    (r"\bgit\s+clean\b", N_('git clean')),
    (r"(curl|wget)[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b", N_('downloads and runs a script')),
    (r"\b(mkfs|shutdown|reboot|poweroff|systemctl)\b|\bdd\s+(if|of)=", N_('system command')),
    (r"\bchmod\s+-R|\bchown\b", N_('changes permissions in bulk')),
    (r"\b(apt|apt-get|dnf|yum|pacman|snap)\b", N_('changes system packages')),
    (r"npm\s+\w+\s+.*(-g|--global)\b|pip3?\s+install\s+.*(--user|--break-system-packages)",
     N_('global install')),
    (r"\b(pkill|killall)\b|\bkill\s+-9", N_('kills processes')),
    (r":\(\)\s*\{", N_('fork bomb')),
]

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2[ \t]*(?=\n|$)", re.S)


def _strip_heredocs(cmd: str) -> str:
    """Drop heredoc bodies (they are code/data, not path arguments)."""
    return _HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)


def _redirect_targets(cmd: str) -> list[str]:
    """Targets of `>`/`>>` redirects that are OUTSIDE quotes."""
    out, q, i = [], None, 0
    while i < len(cmd):
        c = cmd[i]
        if q:
            if c == q:
                q = None
        elif c in "'\"":
            q = c
        elif c == ">":
            j = i + 1
            while j < len(cmd) and cmd[j] in "> &":
                j += 1
            m = re.match(r"\S+", cmd[j:])
            if m:
                out.append(m.group(0).strip("'\""))
        i += 1
    return out


_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_REDIR_OK = re.compile(r"\d?>\s*/dev/null|2>&1|&>\s*/dev/null")


def is_readonly_cmd(cmd: str) -> bool:
    if "$(" in cmd or "`" in cmd:
        return False
    c = _REDIR_OK.sub("", cmd)
    if ">" in c or "<(" in c:
        return False
    segs = [s.strip() for s in _SPLIT.split(c) if s.strip()]
    if not segs:
        return False
    for s in segs:
        try:
            t = shlex.split(s)
        except ValueError:
            return False
        if not t:
            continue
        c0, rest = t[0], t[1:]
        if c0 == "sort" and any(a.startswith("-o") for a in rest):
            return False
        if c0 in READONLY_CMDS:
            continue
        if c0 == "find":
            if any(a in {"-delete", "-exec", "-execdir", "-ok", "-fprint"} for a in rest):
                return False
            continue
        if c0 == "git" and rest and rest[0] in GIT_RO:
            continue
        if c0 in VERSIONED and rest and (rest[0] in {"--version", "-V", "-v", "version"}
                                         or (c0 in {"pip", "pip3"} and rest[0] in {"list", "show", "freeze"})):
            continue
        return False
    return True


class Policy:
    def __init__(self, workspace: str):
        self.ws = Path(workspace).resolve()
        self.mode = "ask"          # ask | trust | plan
        self.always: set[str] = set()

    @property
    def trusted(self) -> bool:
        return self.mode == "trust"

    @trusted.setter
    def trusted(self, v: bool) -> None:
        self.mode = "trust" if v else "ask"

    def cycle_mode(self) -> str:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        return self.mode

    # --- helpers ---
    def _inside(self, p: Path) -> bool:
        try:
            p.resolve().relative_to(self.ws)
            return True
        except ValueError:
            return False

    def _abs(self, tok: str) -> Path:
        p = Path(tok).expanduser()
        return p if p.is_absolute() else self.ws / p

    def _outside_reason(self, tok: str) -> str | None:
        if not (tok.startswith(("/", "~", ".."))):
            return None
        p = self._abs(tok)
        if self._inside(p) or any(str(p).startswith(s) for s in SAFE_ABS):
            return None
        return tr_('touches outside the working folder: {tok}', tok=tok)

    def _is_skill_script(self, tok: str, prev: str) -> bool:
        """`bash <skill folder>/scripts/x.sh`: running a loaded skill's own script. ONLY that exact shape counts: the
        skill folder is instructions that get executed, so it must never become a place the agent may write to."""
        if prev not in ("bash", "sh", "python", "python3", "node") or not tok.startswith(("/", "~")):
            return False
        try:
            from . import skills
            p = Path(tok).expanduser().resolve()
            return any((s.path.parent / "scripts").resolve() in p.parents for s in skills.SKILLS.values())
        except Exception:
            return False

    def danger_reason(self, cmd: str) -> str | None:
        for rx, why in DANGEROUS:
            if re.search(rx, cmd):
                return tr_(why)
        body = _strip_heredocs(cmd)
        try:
            toks = shlex.split(body)
        except ValueError:
            toks = body.split()
        for i, tok in enumerate(toks):
            if i and self._is_skill_script(tok, toks[i - 1]):
                continue
            r = self._outside_reason(tok)
            if r:
                return r
        for tgt in _redirect_targets(body):
            r = self._outside_reason(tgt)
            if r:
                return r
        # rm: only specific targets inside the working folder are allowed
        for seg in _SPLIT.split(cmd):
            try:
                t = shlex.split(seg.strip())
            except ValueError:
                continue
            if t and t[0] == "rm":
                for a in (x for x in t[1:] if not x.startswith("-")):
                    if a in {"*", ".", "..", "~", "/"} or a.endswith("/*") or self._abs(a).resolve() == self.ws:
                        return tr_('bulk deletion')
                    if not self._inside(self._abs(a)):
                        return tr_('deletes outside the working folder: {a}', a=a)
        return None

    # --- decision ---
    # --- persistent rules: ~/.emilie/settings.json -> {"permissions": {"allow": [...], "deny": [...]}} ---
    # Rule = "tool" or "tool(arg pattern)"; patterns are case-insensitive globs: "mcp__browser__*", "bash(git *)",
    # "web_fetch(*github.com*)". For bash the arg is the command, for files the path, for web_fetch the url.
    @staticmethod
    def _rules(kind: str) -> list[str]:
        from . import effort
        perms = effort.load_settings().get("permissions")
        rules = perms.get(kind) if isinstance(perms, dict) else None
        return [r for r in rules if isinstance(r, str)] if isinstance(rules, list) else []

    @staticmethod
    def _rule_match(rule: str, name: str, args: dict) -> bool:
        import fnmatch
        m = re.fullmatch(r"\s*([^()\s]+)\s*(?:\((.*)\))?\s*", rule, re.S)
        if not m:
            return False
        tool, pat = m.group(1).lower(), m.group(2)
        if not fnmatch.fnmatchcase(name.lower(), tool):
            return False
        if pat is None:
            return True
        arg = args.get("command") or args.get("path") or args.get("url") or ""
        return fnmatch.fnmatchcase(str(arg).lower(), pat.strip().lower())

    def check(self, name: str, args: dict) -> tuple[str, str]:
        """return ("allow"|"ask"|"deny", alasan)"""
        plan = self.mode == "plan"
        for r in self._rules("deny"):                 # first, so a deny rule can also block read tools (e.g. .env files)
            if self._rule_match(r, name, args):
                return "deny", tr_('blocked by your rule: {r}', r=r)
        if name == "exit_plan_mode":                  # the user must approve a plan; outside plan mode it is a no-op
            return ("ask", "") if plan else ("allow", "")
        if name in READONLY_TOOLS:
            return "allow", ""
        if not plan and any(self._rule_match(r, name, args) for r in self._rules("allow")):
            if name not in ("bash", "bash_bg") or not self.danger_reason(args.get("command", "")):   # a dangerous command still asks
                return "allow", ""
        if name in ("bash", "bash_bg"):
            cmd = args.get("command", "")
            why = self.danger_reason(cmd)
            ro = is_readonly_cmd(cmd)
            if plan:
                return ("allow", "") if (ro and not why) else ("deny", tr_('plan mode: only read commands are allowed'))
            if why:
                return "ask", why
            if ro or self.trusted or name in self.always:
                return "allow", ""
            return "ask", ""
        if name in {"write_file", "edit_file"}:
            if plan:
                return "deny", tr_('plan mode: files cannot be changed')
            path = args.get("path", "")
            if not self._inside(self._abs(path)):
                return "ask", tr_('outside the working folder: {path}', path=path)
            if self.trusted or name in self.always:
                return "allow", ""
            return "ask", ""
        if name.startswith("mcp__"):          # external server tool: its effect is unknown -> always ask
            if plan:
                return "deny", tr_('plan mode: MCP tools are blocked')
            return ("allow", "") if name in self.always else ("ask", "")
        if name == "web_fetch":
            from urllib.parse import urlparse
            if self.trusted or name in self.always:
                return "allow", ""
            return "ask", tr_('network access: {0}', urlparse(args.get('url', '')).netloc or args.get('url', ''))
        return "ask", ""
