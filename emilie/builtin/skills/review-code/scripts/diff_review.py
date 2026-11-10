#!/usr/bin/env python3
"""Prepare a code review: summarize a change and flag lines that deserve a human look.

Usage:
  python diff_review.py                 # working tree vs HEAD (staged + unstaged + untracked files)
  python diff_review.py --staged        # only what is staged
  python diff_review.py main...HEAD     # a branch against its base (any `git diff` range)
  python diff_review.py HEAD~3..HEAD [--json] [--max-findings 60]

Reports: size of the change, files grouped by kind (source, tests, config/CI, dependencies, migrations, docs, generated),
whether source changed without tests, whitespace-only churn, and findings on ADDED lines with file:line: debug leftovers, TODO/FIXME,
secrets (masked), dangerous calls, swallowed errors, disabled lint/type checks, skipped or focused tests, removed assertions,
commented-out code, SQL built from strings. Read-only (runs `git diff`, `git ls-files`), standard library only.

A finding is a prompt to look, not a verdict: it cannot judge correctness, design or intent. Review the logic yourself.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress)(/|$)|\.(test|spec)\.[a-z]+$|_test\.(go|py|rb|rs)$|(^|/)test_[^/]*\.py$|Tests?\.(java|kt|cs)$|_spec\.rb$", re.I)
DEP_FILES = re.compile(r"(^|/)(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements[\w.-]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|go\.(mod|sum)|Cargo\.(toml|lock)|pom\.xml|build\.gradle(\.kts)?|Gemfile(\.lock)?|composer\.(json|lock)|\.csproj)$")
CI_FILES = re.compile(r"(^|/)(\.github/|\.gitlab-ci|azure-pipelines|Jenkinsfile|\.circleci/|Dockerfile|docker-compose|\.dockerignore|Makefile|\.pre-commit|tox\.ini|\.eslintrc|\.flake8|ruff\.toml|\.env)")
MIGRATION = re.compile(r"(^|/)(migrations?|alembic|db/migrate|flyway)(/|$)|\.sql$", re.I)
DOCS = re.compile(r"\.(md|rst|txt|adoc)$|(^|/)docs?/", re.I)
GENERATED = re.compile(r"(\.min\.(js|css)|\.lock|-lock\.json|_pb2\.py|\.pb\.go|\.generated\.|(^|/)(dist|build|vendor|node_modules)/)")
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".go", ".java", ".kt", ".rs", ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".swift", ".scala", ".sh", ".ps1", ".vue", ".svelte"}

RULES = [
    ("secret", "WARN", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\b[sr]k_live_[A-Za-z0-9]{16,}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}\b|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{32,}\b|\bAIza[0-9A-Za-z_-]{35}\b"),
     "looks like a real credential in the diff; remove it, rotate it, and load it from the environment"),
    ("secret", "WARN", re.compile(r"""(?i)\b\w*(api[_-]?key|secret|passwd|password|token|private[_-]?key)\w*\s*[:=]\s*['"][^'"\s]{8,}['"]"""),
     "hard-coded credential-like value"),
    ("danger", "WARN", re.compile(r"\beval\s*\(|\bexec\s*\(|os\.system\s*\(|shell\s*=\s*True|\bpickle\.loads?\(|yaml\.load\((?![^)]*Loader)|child_process\.exec\(|Runtime\.getRuntime\(\)\.exec|\binnerHTML\s*=|dangerouslySetInnerHTML|\bdocument\.write\(|verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|chmod\s+(-R\s+)?777"),
     "dangerous call or setting: check inputs are trusted and that there is no safer API"),
    ("sql", "WARN", re.compile(r"""(?i)(["'`])\s*(select|insert|update|delete)\b[^"'`]*\1\s*(\+|%|\.format\()|f["'](select|insert|update|delete)\b[^"']*\{|execute\(\s*f["']|(select|insert|update|delete)\b[^"'`\n]*\$\{"""),
     "SQL built from strings: use parameterized queries"),
    ("errors", "WARN", re.compile(r"except\s*:\s*(#.*)?$|except\s+\w*Exception\s*(as\s+\w+)?\s*:\s*(pass)?\s*$|catch\s*\(\s*\w*\s*\)\s*\{\s*\}|catch\s*\{\s*\}|\.catch\(\s*\(\)\s*=>\s*\{\s*\}\s*\)|rescue\s*=>?\s*\w*\s*$|_ = err\b"),
     "broad or empty error handler: failures are swallowed; handle or let them propagate"),
    ("suppress", "INFO", re.compile(r"eslint-disable|#\s*noqa|#\s*type:\s*ignore|@ts-ignore|@ts-nocheck|@ts-expect-error|#\s*nosec|#\s*pylint:\s*disable|//\s*nolint|@SuppressWarnings|#\s*pragma:\s*no cover|\bunsafe\s*\{"),
     "check or warning suppressed: is there a real reason, and is it explained?"),
    ("test-off", "WARN", re.compile(r"\b(it|test|describe)\.(only|skip)\(|\bx(it|describe)\(|\bfit\(|\bfdescribe\(|@pytest\.mark\.(skip|xfail)|@unittest\.skip|@Ignore\b|@Disabled\b|\bt\.Skip\(|\.only\("),
     "a test is skipped or focused: the rest of the suite may not run, or a failure is hidden"),
    ("debug", "INFO", re.compile(r"\bconsole\.(log|debug)\(|\bdebugger\b|\bbreakpoint\(\)|\bpdb\.set_trace|\bimport\s+pdb\b|System\.out\.print|\bvar_dump\(|\bdd\(|\bprintln!\(|\bfmt\.Print(ln|f)?\(\s*\"DEBUG|\bprint\(\s*['\"](debug|here|xxx|test|\*\*)"),
     "debug output left in the code"),
    ("todo", "INFO", re.compile(r"\b(TODO|FIXME|XXX|HACK)\b"), "unfinished marker: should it be done now or tracked as an issue?"),
]
COMMENTED_CODE = re.compile(r"^\s*(#|//)\s*(def |class |if |elif |else:|for |while |return\b|import |from \w+ import|const |let |var |function |try:|except|catch|\w+\s*=\s*[\w.(\[{\"']|\w+\([^)]*\)\s*;?$)")


def git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], capture_output=True, cwd=cwd, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)
    return r.returncode, r.stdout.decode("utf-8", errors="replace") + (r.stderr.decode("utf-8", errors="replace") if r.returncode else "")


def kind_of(path: str) -> str:
    if GENERATED.search(path):
        return "generated"
    if TEST_PATH.search(path):
        return "tests"
    if DEP_FILES.search(path):
        return "dependencies"
    if MIGRATION.search(path):
        return "migrations"
    if CI_FILES.search(path):
        return "config/CI"
    if DOCS.search(path):
        return "docs"
    if Path(path).suffix.lower() in CODE_EXT:
        return "source"
    return "other"


def parse_diff(text: str):
    files: dict[str, dict] = {}
    cur = None
    new_ln = 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur = None
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            if m:
                cur = files.setdefault(m.group(2), {"added": [], "removed": [], "status": "modified", "old": m.group(1), "binary": False})
        elif cur is None:
            continue
        elif line.startswith("new file mode"):
            cur["status"] = "added"
        elif line.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif line.startswith("rename from"):
            cur["status"] = "renamed"
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            cur["binary"] = True
        elif line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            new_ln = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            cur["added"].append((new_ln, line[1:]))
            new_ln += 1
        elif line.startswith("-") and not line.startswith("---"):
            cur["removed"].append(line[1:])
    return files


def mask(s: str) -> str:
    return re.sub(r"([A-Za-z0-9_\-+/=]{4})[A-Za-z0-9_\-+/=]{6,}", r"\1****", s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("range", nargs="?", default="")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-findings", type=int, default=60)
    ap.add_argument("--cwd", default=None)
    a = ap.parse_args()
    rc, out = git(["rev-parse", "--is-inside-work-tree"], a.cwd)
    if rc != 0 or out.strip() != "true":
        print("error: not inside a git repository", file=sys.stderr)
        return 1
    base = ["diff", "-U0", "--no-color", "--no-ext-diff", "--find-renames"]
    if a.range:
        args, label = base + [a.range], a.range
    elif a.staged:
        args, label = base + ["--cached"], "staged changes"
    else:
        rc0, _ = git(["rev-parse", "--verify", "HEAD"], a.cwd)
        args, label = (base + ["HEAD"], "working tree vs HEAD") if rc0 == 0 else (base + ["--cached"], "staged changes (no commits yet)")
    rc, text = git(args, a.cwd)
    if rc != 0:
        print(f"error: git diff failed: {text.strip()[:300]}", file=sys.stderr)
        return 1
    files = parse_diff(text)
    untracked = []
    if not a.range and not a.staged:
        rc, ut = git(["ls-files", "--others", "--exclude-standard"], a.cwd)
        base_dir = Path(a.cwd or ".")
        for rel in ut.splitlines():
            p = base_dir / rel
            try:
                if p.is_file() and p.stat().st_size < 400_000:
                    content = p.read_text(encoding="utf-8", errors="strict").splitlines()
                    files[rel] = {"added": list(enumerate(content, 1)), "removed": [], "status": "untracked", "old": rel, "binary": False}
                    untracked.append(rel)
            except (OSError, UnicodeDecodeError):
                files[rel] = {"added": [], "removed": [], "status": "untracked", "old": rel, "binary": True}
    if not files:
        print(f"No changes found ({label}).")
        return 0
    groups: dict[str, list] = defaultdict(list)
    add_total = rem_total = 0
    for f, d in files.items():
        groups[kind_of(f)].append(f)
        if kind_of(f) != "generated":
            add_total += len(d["added"])
            rem_total += len(d["removed"])
    findings = []
    removed_asserts = 0
    added_asserts = 0
    for f, d in files.items():
        k = kind_of(f)
        if k == "generated" or d["binary"]:
            continue
        for ln, src in d["added"]:
            s = src.strip()
            if not s:
                continue
            for cat, sev, rx, why in RULES:
                if k in ("docs",) and cat not in ("secret",):
                    continue
                if cat == "debug" and k == "tests":
                    continue
                if cat in ("debug", "todo") and k == "config/CI":
                    continue
                if rx.search(src):
                    findings.append({"severity": sev, "category": cat, "where": f"{f}:{ln}", "code": mask(s)[:120] if cat == "secret" else s[:120], "why": why})
                    break
            else:
                if k in ("source", "tests") and COMMENTED_CODE.match(src) and not s.startswith(("# type", "#!", "// @")):
                    findings.append({"severity": "INFO", "category": "commented-code", "where": f"{f}:{ln}", "code": s[:120], "why": "commented-out code: delete it (version control remembers)"})
            if re.search(r"\b(assert|expect|should)\b|\bassert\w+\(", src):
                added_asserts += 1
        if k == "tests":
            removed_asserts += sum(1 for r in d["removed"] if re.search(r"\b(assert|expect|should)\b|\bassert\w+\(", r))
        if d["status"] == "added" and k == "source" and len(d["added"]) > 400:
            findings.append({"severity": "INFO", "category": "size", "where": f, "code": f"{len(d['added'])} new lines in one file", "why": "very large new file: is it one concern? is it reviewable in one sitting?"})
    notes = []
    src_files = [f for f in groups.get("source", []) if files[f]["status"] != "deleted"]
    if src_files and not groups.get("tests"):
        notes.append("Source files changed but no test files changed. Is the behavior covered by existing tests? Ask for a test, or for the reason there is none.")
    if groups.get("tests") and removed_asserts > added_asserts:
        notes.append(f"Tests lost assertions: {removed_asserts} assertion lines removed vs {added_asserts} added. Check that coverage was not weakened.")
    if groups.get("dependencies"):
        notes.append("Dependency files changed: check each new package (name spelling, maintenance, license, size), versions pinned, lockfile consistent.")
    if groups.get("migrations"):
        notes.append("Database migration changed: is it reversible, safe on a live table (locks, backfill batching), and deployed in the right order with the code?")
    if groups.get("config/CI"):
        notes.append("CI, build or environment configuration changed: check permissions, secrets handling, and that checks are not weakened.")
    if add_total + rem_total > 800 or len([f for f in files if kind_of(f) != "generated"]) > 25:
        notes.append(f"Large change ({add_total} added, {rem_total} removed lines in {len(files)} files): hard to review well. Consider asking for smaller pieces or a walkthrough.")
    if not a.range and not a.staged:
        rc, ws = git(["diff", "-U0", "--no-color", "-w", "--shortstat", "HEAD"], a.cwd)
        rc2, full = git(["diff", "-U0", "--no-color", "--shortstat", "HEAD"], a.cwd)
        m1, m2 = re.search(r"(\d+) insertion", ws or ""), re.search(r"(\d+) insertion", full or "")
        if m1 and m2 and int(m2.group(1)) > 20 and int(m1.group(1)) < 0.6 * int(m2.group(1)):
            notes.append("Much of the change is whitespace or formatting only (ignoring it removes a large share of the diff): ask for formatting changes in a separate commit.")
    order = {"WARN": 0, "INFO": 1}
    findings.sort(key=lambda x: (order[x["severity"]], x["where"]))
    result = {"label": label, "files": len(files), "added": add_total, "removed": rem_total,
              "groups": {k: len(v) for k, v in groups.items()}, "notes": notes,
              "findings": findings[: a.max_findings], "findings_total": len(findings)}
    if a.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Review brief: {label}")
    print(f"{len(files)} file(s), +{add_total} / -{rem_total} lines (generated files excluded)" + (f", {len(untracked)} untracked file(s) included" if untracked else ""))
    print("Kinds: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))))
    print("\nFiles:")
    for k in ("source", "tests", "migrations", "dependencies", "config/CI", "docs", "other", "generated"):
        for f in sorted(groups.get(k, [])):
            d = files[f]
            print(f"  [{k:12}] {d['status']:9} {f}  (+{len(d['added'])}/-{len(d['removed'])})")
    if notes:
        print("\nThings to check:")
        for n in notes:
            print(f"  - {n}")
    print(f"\nFindings on added lines: {len(findings)}" + (f" (showing {a.max_findings})" if len(findings) > a.max_findings else ""))
    for f in findings[: a.max_findings]:
        print(f"  [{f['severity']}] {f['where']}  {f['category']}: {f['code']}\n          {f['why']}")
    if not findings:
        print("  none from the pattern checks")
    print("\nThis is triage, not a review. It cannot see logic errors, missing cases, bad design or intent: read the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
