# Overview template

Fill every section, but keep each one short. Tables beat paragraphs. If a section has nothing to say, write
"Not found" rather than deleting it: an absence is information (for example, "No CI configuration found").

Mark evidence in the **Evidence** column or inline: **Verified** (read or run), **Inferred** (from names or structure),
**Unknown**.

---

```markdown
# <Project name> - overview

**In one sentence:** <what it is and who uses it, in plain words>
**State:** <active | quiet | dormant>, last commit <date>, <N> commits, <N> contributors; <maturity hint: tests? CI? releases?>

## What it does
2 to 4 bullets in the user's vocabulary, not the code's. The main capability first.

## Stack
| Layer | Technology | Evidence |
|---|---|---|
| Language(s) | Python 3.11 (about 11k lines) | `pyproject.toml`, inventory - Verified |
| Framework | FastAPI | `pyproject.toml:12`, `app/main.py:5` - Verified |
| Data | PostgreSQL via SQLAlchemy | imports in `app/db.py` - Verified; version Unknown |
| Tooling | ruff, pytest, Docker | config files - Verified |

## Run, test, build
| Task | Command | Source | Ran it? |
|---|---|---|---|
| Install | `pip install -e .[dev]` | README, CI | no |
| Run | `uvicorn app.main:app --reload` | README | no |
| Test | `pytest -q` | CI `.github/workflows/ci.yml:18` | yes: 142 passed, 2 failed |
| Lint | `ruff check .` | CI | no |

## Structure
| Path | Responsibility |
|---|---|
| `app/api/` | HTTP routes, request validation |
| `app/services/` | Business rules (the core) |
| `app/db/` | Models and migrations |
| `tests/` | Mirrors `app/`; pytest |

## How one thing flows (entry to output)
Example: `POST /orders`
1. `app/api/orders.py:34` validates the body
2. `app/services/orders.py:58` applies pricing and stock rules
3. `app/db/repo.py:90` writes the row, then publishes an event
4. Response is built in `app/api/orders.py:41`

## Configuration and external dependencies
- Environment variables (names only): `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`
- External services: PostgreSQL, Redis, Stripe (`app/payments.py`)
- Secret-bearing files present and not opened: `.env`

## Conventions
Formatter and linter, naming, test layout, commit message style, branch hints.

## Health and risks
- Most-changed files (90 days): `app/services/orders.py` (14), `app/api/orders.py` (11)  -> the living core
- Tests: 38 test files for 61 source files; no tests for `app/payments.py`
- TODO/FIXME: 23; largest file: `app/services/orders.py` (41 KB)
- Risks: no CI, floating dependency versions, outdated lockfile, secrets in history (if seen), etc.

## Unknowns and questions for you
- <things you could not verify, and what you would need to settle them>

## Suggested next steps
1. <option tied to a finding> (skill: `trace-code`)
2. <option> (skill: `break-down-tasks`)
```

---

## Style notes

- Name things the way the project does (its own terms), and define a term the first time it appears.
- Use `path:line` for anything the user may want to open.
- Prefer one specific fact to three vague ones: "FastAPI app started in `app/main.py:5`" beats "uses a web framework".
- Do not praise or criticize the code in an overview. Report observations; judgement belongs to a review.
- If the user is a beginner, add a short glossary at the end. If an expert, drop the "What it does" bullets to one line.
