#!/usr/bin/env python3
"""Generate a small, working project skeleton (tests, lint config, CI, README).

Usage:
  python scaffold.py --list
  python scaffold.py <stack> <name> [--dir PATH] [--dry-run]

Stacks: python-cli, node-cli, go-cli, rust-cli, static-web

Creates <PATH>/<name> (default: ./<name>). Never overwrites: if the target
directory exists and is not empty, or any file would be replaced, it stops and
changes nothing. Does not run installers, git, or the network. No license file
is written (choosing a license is the owner's decision). Prints the commands to
run next.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STACKS = {
    "python-cli": "Python 3.9+ package with a CLI entry point, pytest, ruff, src/ layout",
    "node-cli": "Node 18+ ES-module CLI, zero dependencies, built-in test runner",
    "go-cli": "Go 1.21+ module with a main package and a test",
    "rust-cli": "Rust (cargo) binary with unit tests",
    "static-web": "Accessible static page: HTML, CSS tokens (light/dark), small JS",
}

GITIGNORE = {
    "python-cli": "__pycache__/\n*.py[cod]\n.venv/\nvenv/\n*.egg-info/\ndist/\nbuild/\n.pytest_cache/\n.ruff_cache/\n.mypy_cache/\n.coverage\nhtmlcov/\n.env\n",
    "node-cli": "node_modules/\ndist/\ncoverage/\n.env\n*.log\n",
    "go-cli": "/bin/\n/dist/\n*.test\n*.out\n.env\n",
    "rust-cli": "/target/\n.env\n",
    "static-web": "node_modules/\n.env\n.DS_Store\n",
}
EDITORCONFIG = "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\ninsert_final_newline = true\ntrim_trailing_whitespace = true\nindent_style = space\nindent_size = 4\n\n[*.{js,json,yml,yaml,html,css}]\nindent_size = 2\n\n[Makefile]\nindent_style = tab\n"


def pkgname(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]", "_", name).strip("_").lower() or "app"


def readme(name: str, blurb: str, install: str, test: str, run: str) -> str:
    return f"""# {name}

{blurb}

## Quick start

```
{install}
{test}
{run}
```

## Project layout

See the folders in this repository; tests live next to the code they cover.

## Development

- Run the tests before every commit.
- CI runs the same commands as above (`.github/workflows/ci.yml`).

## License

Not chosen yet. Add a `LICENSE` file before publishing.
"""


def python_cli(name: str) -> dict[str, str]:
    p = pkgname(name)
    return {
        "pyproject.toml": f"""[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
description = "TODO: one-line description"
readme = "README.md"
requires-python = ">=3.9"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7", "ruff>=0.5"]

[project.scripts]
{name} = "{p}.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
""",
        f"src/{p}/__init__.py": '"""' + name + '."""\n\n__version__ = "0.1.0"\n',
        f"src/{p}/__main__.py": f"from {p}.cli import main\n\nraise SystemExit(main())\n",
        f"src/{p}/cli.py": f'''"""Command-line interface."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


def greet(who: str) -> str:
    return f"Hello, {{who}}!"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{name}", description="TODO: describe the tool")
    parser.add_argument("--version", action="version", version=f"%(prog)s {{__version__}}")
    parser.add_argument("who", nargs="?", default="world", help="whom to greet (default: world)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(greet(args.who))
    return 0
''',
        "tests/test_cli.py": f'''from {p}.cli import greet, main


def test_greet():
    assert greet("Ada") == "Hello, Ada!"


def test_main_prints_greeting(capsys):
    assert main(["Ada"]) == 0
    assert capsys.readouterr().out == "Hello, Ada!\\n"


def test_main_default(capsys):
    assert main([]) == 0
    assert "world" in capsys.readouterr().out
''',
        "README.md": readme(name, "TODO: what this tool does.", 'python -m venv .venv && . .venv/bin/activate   # Windows: .venv\\Scripts\\activate\npip install -e ".[dev]"', "python -m pytest\nruff check .", f"{name} --help"),
        ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: python -m pytest
""",
    }


def node_cli(name: str) -> dict[str, str]:
    return {
        "package.json": f"""{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "TODO: one-line description",
  "type": "module",
  "bin": {{ "{name}": "bin/{name}.js" }},
  "exports": "./src/index.js",
  "engines": {{ "node": ">=18" }},
  "scripts": {{
    "test": "node --test",
    "start": "node bin/{name}.js"
  }},
  "files": ["bin", "src"]
}}
""",
        "src/index.js": "export function greet(who = 'world') {\n  return `Hello, ${who}!`;\n}\n",
        f"bin/{name}.js": "#!/usr/bin/env node\nimport { greet } from '../src/index.js';\n\nconst args = process.argv.slice(2);\nif (args.includes('--help') || args.includes('-h')) {\n  console.log('usage: " + name + " [name]');\n  process.exit(0);\n}\nconsole.log(greet(args[0]));\n",
        "test/index.test.js": "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\nimport { greet } from '../src/index.js';\n\ntest('greets by name', () => {\n  assert.equal(greet('Ada'), 'Hello, Ada!');\n});\n\ntest('defaults to world', () => {\n  assert.equal(greet(), 'Hello, world!');\n});\n",
        "README.md": readme(name, "TODO: what this tool does.", "npm install", "npm test", f"node bin/{name}.js Ada"),
        ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [18, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm test
""",
    }


def go_cli(name: str) -> dict[str, str]:
    return {
        "go.mod": f"module {name}\n\ngo 1.21\n",
        "main.go": '''package main

import (
	"fmt"
	"os"
)

// Greet returns a greeting for who.
func Greet(who string) string {
	return fmt.Sprintf("Hello, %s!", who)
}

func main() {
	who := "world"
	if len(os.Args) > 1 {
		who = os.Args[1]
	}
	fmt.Println(Greet(who))
}
''',
        "main_test.go": '''package main

import "testing"

func TestGreet(t *testing.T) {
	got := Greet("Ada")
	want := "Hello, Ada!"
	if got != want {
		t.Fatalf("Greet() = %q, want %q", got, want)
	}
}
''',
        "README.md": readme(name, "TODO: what this tool does.", "go mod tidy", "go test ./...\ngo vet ./...", "go run . Ada"),
        ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.22"
      - run: go vet ./...
      - run: go test ./...
""",
    }


def rust_cli(name: str) -> dict[str, str]:
    return {
        "Cargo.toml": f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\ndescription = "TODO: one-line description"\n\n[dependencies]\n',
        "src/main.rs": '''/// Returns a greeting for `who`.
fn greet(who: &str) -> String {
    format!("Hello, {who}!")
}

fn main() {
    let who = std::env::args().nth(1).unwrap_or_else(|| "world".to_string());
    println!("{}", greet(&who));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn greets_by_name() {
        assert_eq!(greet("Ada"), "Hello, Ada!");
    }
}
''',
        "README.md": readme(name, "TODO: what this tool does.", "cargo build", "cargo test\ncargo clippy --all-targets", "cargo run -- Ada"),
        ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: clippy
      - run: cargo clippy --all-targets -- -D warnings
      - run: cargo test
""",
    }


def static_web(name: str) -> dict[str, str]:
    return {
        "index.html": f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name}</title>
  <meta name="description" content="TODO: one-sentence description for search results">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header>
    <h1>{name}</h1>
  </header>
  <main id="main">
    <p>TODO: replace with real content.</p>
    <button type="button" id="hello">Say hello</button>
    <p id="out" role="status"></p>
  </main>
  <footer><p>&copy; <span id="year"></span> {name}</p></footer>
  <script src="script.js" defer></script>
</body>
</html>
""",
        "style.css": """:root {
  --bg: #ffffff; --text: #14181f; --muted: #4b5563; --accent: #0b5bd3; --accent-contrast: #ffffff; --surface: #f6f7f9;
  --space: 1rem; --radius: 8px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --text: #eceff4; --muted: #a6adbb; --accent: #6ea8ff; --accent-contrast: #0f1115; --surface: #181b22;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 1rem/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
header, main, footer { max-width: 60rem; margin-inline: auto; padding: var(--space); }
footer p { color: var(--muted); }
button {
  min-height: 44px; padding: 0.5rem 1rem; border: 0; border-radius: var(--radius);
  background: var(--accent); color: var(--accent-contrast); font: inherit; cursor: pointer;
}
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.skip { position: absolute; left: -999px; }
.skip:focus { left: var(--space); top: var(--space); background: var(--surface); padding: 0.5rem; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
""",
        "script.js": "document.getElementById('year').textContent = new Date().getFullYear();\ndocument.getElementById('hello').addEventListener('click', () => {\n  document.getElementById('out').textContent = 'Hello!';\n});\n",
        "README.md": readme(name, "TODO: what this site is.", "# no install needed", "# open index.html in a browser", "python -m http.server 8000   # then visit http://localhost:8000"),
    }


BUILDERS = {"python-cli": python_cli, "node-cli": node_cli, "go-cli": go_cli, "rust-cli": rust_cli, "static-web": static_web}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stack", nargs="?")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.stack:
        for k, v in STACKS.items():
            print(f"  {k:12} {v}")
        return 0
    if a.stack not in BUILDERS:
        print(f"error: unknown stack '{a.stack}'. Use --list.", file=sys.stderr)
        return 1
    if not a.name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", a.name):
        print("error: name must start with a letter and use only letters, digits, '-' and '_' (max 64).", file=sys.stderr)
        return 1
    target = Path(a.dir) / a.name
    files = BUILDERS[a.stack](a.name)
    files[".gitignore"] = GITIGNORE[a.stack]
    files[".editorconfig"] = EDITORCONFIG
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        print(f"error: {target} already exists and is not empty. Nothing was written.", file=sys.stderr)
        return 1
    print(("Would create" if a.dry_run else "Creating") + f" {target} ({a.stack}):")
    for rel in sorted(files):
        print(f"  {rel}")
    if a.dry_run:
        return 0
    for rel, content in files.items():
        f = target / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8", newline="\n")
    print(f"\nDone: {len(files)} files. Next (nothing has been installed or run):")
    nxt = {
        "python-cli": ["cd " + a.name, "python -m venv .venv", "pip install -e \".[dev]\"", "python -m pytest"],
        "node-cli": ["cd " + a.name, "npm test"],
        "go-cli": ["cd " + a.name, "go test ./..."],
        "rust-cli": ["cd " + a.name, "cargo test"],
        "static-web": ["cd " + a.name, "python -m http.server 8000"],
    }[a.stack]
    for c in nxt:
        print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
