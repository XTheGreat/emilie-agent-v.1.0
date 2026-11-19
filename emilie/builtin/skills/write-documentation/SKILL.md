---
name: write-documentation
phase: rawat
description: Write or repair project documentation from the real code - README, setup and usage guides, API/CLI reference, configuration tables, how-to guides and runbooks. Finds gaps with a script, verifies every command and example by running or reading the code, and keeps docs short and task-oriented. Not for architecture decision records (write-adr), onboarding paths (onboard-teammate) or explaining one piece of code (explain-code). Triggers - "write docs", "document this", "create a README", "update the documentation", "API docs", "usage guide", "docs are outdated", "add docstrings", "runbook".
---

# Write documentation

**Goal:** a reader can install, use, configure and troubleshoot the project from the docs alone, and every statement is true.

## Ground rules
1. **Docs come from the code.** Read the entry points, CLI help, config loading and tests; never document behavior you did not confirm.
2. **Verify examples.** Run each command and snippet (or say it was not run). A wrong example is worse than none.
3. **Know the reader and the task:** quick start (5 minutes), how-to (goal), reference (facts), explanation (why) - keep them separate (`references/doc-types.md`).
4. **Short, scannable, current:** headings, tables for options, code blocks with the language, no marketing, no stale screenshots; date or version only where it matters.
5. **Match the repo's language and format** (existing README language, docstring style, Markdown/RST).
6. **No secrets or private URLs** in examples; use obvious placeholders.
7. **Update, do not duplicate:** edit the existing doc; link instead of copying.

## Procedure
1. Gaps: `python "<this skill's directory>/scripts/doc_gaps.py" [path]` - README sections present/missing, undocumented public Python functions/classes, CLI flags and env vars found in code but absent from docs, broken relative links.
2. Plan the smallest doc set that closes the gaps; ask when the audience is unclear.
3. Write using the templates in `references/readme-template.md`.
4. Verify: run commands, check links and flags against the code, build docs if there is a generator.
5. Report what was added, what was verified, and what remains undocumented.

## Definition of done
- [ ] Install, usage, config and troubleshooting covered for the intended reader.
- [ ] Examples verified; flags/env vars match the code; links work.
- [ ] No stale or duplicated statements; no secrets.

## Pitfalls
Describing intent instead of behavior. Copying the code in prose. Missing prerequisites and supported versions. Walls of text. Docs that rot because no one owns them - note where they live and how to update.

## Hand-offs
| Next | Load |
|---|---|
| decisions and rationale | `write-adr` |
| new-joiner path | `onboard-teammate` |
| explain specific code | `explain-code` |
| release notes | `write-changelog` |
