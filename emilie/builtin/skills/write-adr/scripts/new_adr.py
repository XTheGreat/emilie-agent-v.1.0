#!/usr/bin/env python3
"""Create the next numbered ADR from a template.

Usage: python new_adr.py "Decision title" [--dir docs/adr] [--status proposed] [--root .]
Finds an existing ADR folder (docs/adr, doc/adr, docs/decisions, adr) unless --dir is given; refuses to overwrite.
"""
from __future__ import annotations
import argparse, datetime, re, sys
from pathlib import Path

TEMPLATE = """# {num}. {title}

- Status: {status}
- Date: {date}
- Deciders: <names or roles>

## Context
<problem, forces, constraints, links to evidence>

## Options considered
1. <Option A> - pros / cons
2. <Option B> - pros / cons
3. Do nothing - consequences

## Decision
We will <decision> because <reason>.

## Consequences
<positive, negative, risks, follow-up work>

## Revisit when
<concrete trigger>
"""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("title"); ap.add_argument("--dir"); ap.add_argument("--status", default="proposed"); ap.add_argument("--root", default=".")
    a = ap.parse_args(); root = Path(a.root)
    d = Path(a.dir) if a.dir else next((root / c for c in ("docs/adr", "doc/adr", "docs/decisions", "doc/decisions", "adr") if (root / c).is_dir()), root / "docs/adr")
    d.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in d.glob("*.md") if (m := re.match(r"(\d{3,4})-", p.name))]
    n = max(nums, default=0) + 1; width = 4 if any(len(re.match(r"(\d+)", p.name).group(1)) == 4 for p in d.glob("[0-9]*.md")) else 4
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:60] or "decision"
    path = d / f"{n:0{width}d}-{slug}.md"
    if path.exists(): print("exists:", path); return 1
    path.write_text(TEMPLATE.format(num=f"{n:0{width}d}", title=a.title, status=a.status, date=datetime.date.today().isoformat()))
    print("created", path)
    return 0

if __name__ == "__main__": sys.exit(main())
