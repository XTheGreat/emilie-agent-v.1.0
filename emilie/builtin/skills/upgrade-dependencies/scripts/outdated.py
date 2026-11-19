#!/usr/bin/env python3
"""Dependency inventory (read-only): ecosystems, outdated packages when tools exist, unpinned or URL dependencies.

Usage: python outdated.py [path]
Runs `pip list --outdated`, `npm outdated`, `go list -u -m all` only if the tool is installed (network may be used by them).
"""
from __future__ import annotations
import json, re, shutil, subprocess, sys
from pathlib import Path

def run(cmd, cwd, t=90):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=t)
        return r.stdout
    except Exception as e:
        return ""

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    found = False
    for f in root.glob("requirements*.txt"):
        found = True; print(f"[python] {f.name}")
        for l in f.read_text(errors="ignore").splitlines():
            s = l.strip()
            if not s or s.startswith(("#", "-")): continue
            if re.search(r"(git\+|https?://)", s): print("  URL/VCS dependency:", s[:80])
            elif "==" not in s: print("  not pinned:", s)
    pp = root / "pyproject.toml"
    if pp.is_file():
        found = True; t = pp.read_text(errors="ignore")
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', t)
        print("[python] pyproject requires-python:", m.group(1) if m else "not set")
        print("  unbounded deps:", [d for d in re.findall(r'"([A-Za-z0-9_.-]+)"\s*[,\]]', t)][:15])
    if shutil.which("pip") and found:
        out = run([sys.executable, "-m", "pip", "list", "--outdated", "--format=json"], root)
        try:
            for p in json.loads(out or "[]")[:40]: print(f"  outdated: {p['name']} {p['version']} -> {p['latest_version']}")
        except ValueError: pass
    pj = root / "package.json"
    if pj.is_file():
        found = True; print("[node] package.json")
        try: d = json.loads(pj.read_text())
        except ValueError: d = {}
        for sect in ("dependencies", "devDependencies"):
            for k, v in d.get(sect, {}).items():
                if v in ("*", "latest") or re.match(r"(git|https?)", v): print(f"  risky spec: {k}@{v}")
        if shutil.which("npm"):
            out = run(["npm", "outdated", "--json"], root)
            try:
                for k, v in list(json.loads(out or "{}").items())[:40]: print(f"  outdated: {k} {v.get('current')} -> {v.get('latest')}")
            except ValueError: pass
        eng = d.get("engines", {}).get("node"); print("  engines.node:", eng or "not set")
    if (root / "go.mod").is_file() and shutil.which("go"):
        found = True; print("[go]")
        for l in run(["go", "list", "-u", "-m", "all"], root).splitlines():
            if "[" in l: print("  outdated:", l)
    if (root / "Cargo.toml").is_file(): found = True; print("[rust] run `cargo outdated` / `cargo audit` if installed")
    if not found: print("no known dependency manifests found")
    print("\nnext: group updates by risk, upgrade one group, run tests, repeat.")
    return 0

if __name__ == "__main__": sys.exit(main())
