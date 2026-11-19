#!/usr/bin/env python3
"""Detect stack, commands and existing CI configuration (read-only).

Usage: python ci_detect.py [path]
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

def read(p):
    try: return p.read_text(errors="ignore")
    except OSError: return ""

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    stacks, cmds = [], {}
    if (root / "package.json").is_file():
        stacks.append("node")
        try: scripts = json.loads(read(root / "package.json")).get("scripts", {})
        except ValueError: scripts = {}
        pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        for k in ("lint", "typecheck", "test", "build"):
            if k in scripts: cmds[k] = f"{pm} run {k}"
        cmds["install"] = {"npm": "npm ci", "yarn": "yarn --frozen-lockfile", "pnpm": "pnpm i --frozen-lockfile"}[pm]
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file() or (root / "setup.py").is_file():
        stacks.append("python"); t = read(root / "pyproject.toml")
        cmds.setdefault("install", 'pip install -e ".[dev]"' if (root / "pyproject.toml").is_file() else "pip install -r requirements.txt")
        if "ruff" in t: cmds["lint"] = "ruff check ."
        if "mypy" in t: cmds["typecheck"] = "mypy ."
        cmds.setdefault("test", "pytest -q")
    for f, name, c in (("go.mod", "go", "go test ./..."), ("Cargo.toml", "rust", "cargo test"), ("pom.xml", "java-maven", "mvn -B verify"), ("Gemfile", "ruby", "bundle exec rake test")):
        if (root / f).is_file(): stacks.append(name); cmds.setdefault("test", c)
    if (root / "Makefile").is_file():
        for tgt in re.findall(r"(?m)^(test|lint|build|check):", read(root / "Makefile")): cmds.setdefault(tgt, f"make {tgt}")
    print("stacks:", stacks or "unknown"); print("commands:", json.dumps(cmds, indent=2))
    ci = list((root / ".github/workflows").glob("*.y*ml")) + [p for p in (root / ".gitlab-ci.yml", root / "Jenkinsfile", root / ".circleci/config.yml", root / "azure-pipelines.yml") if p.exists()]
    print("existing CI:", [str(p.relative_to(root)) for p in ci] or "none")
    for p in ci:
        t = read(p); rel = p.relative_to(root)
        if "pull_request_target" in t: print(f"WARN {rel}: pull_request_target - never check out untrusted code with it")
        if re.search(r"\$\{\{\s*github\.(event|head_ref)[^}]*\}\}", t) and re.search(r"run:", t): print(f"WARN {rel}: github.event/head_ref expression - check it is not inside a run: script")
        if "permissions:" not in t and p.suffix in (".yml", ".yaml") and ".github" in str(p): print(f"WARN {rel}: no permissions block (defaults may be broad)")
        for m in re.finditer(r"uses:\s*([\w./-]+)@(\w[\w.-]*)", t):
            if m.group(2) in ("main", "master", "latest"): print(f"WARN {rel}: action {m.group(1)} pinned to a moving ref")
    for f in ("Dockerfile", ".env.example", "tox.ini", ".pre-commit-config.yaml"):
        if (root / f).exists(): print("found:", f)
    return 0

if __name__ == "__main__": sys.exit(main())
