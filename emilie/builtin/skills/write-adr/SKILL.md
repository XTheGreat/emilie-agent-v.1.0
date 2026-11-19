---
name: write-adr
phase: rawat
description: Record an architecture or technical decision as a short, numbered ADR - context, options considered with trade-offs, the decision, consequences, and status - based on evidence from the code and the discussion, stored with the project's docs. Includes a script that creates the next numbered ADR file from a template. Not for the architecture design itself (design-architecture) or comparing technologies in depth (evaluate-technology). Triggers - "write an ADR", "document this decision", "architecture decision record", "why did we choose", "record the trade-offs", "decision log", "supersede decision".
---

# Write ADR

**Goal:** a future maintainer understands why the system is the way it is, what was rejected, and when to revisit.

## Ground rules
1. **Capture a real decision,** one per record; state the question it answers.
2. **Context before choice:** forces, constraints, requirements, deadlines; facts from the code and docs, not memory.
3. **Honest options:** at least two real alternatives, including "do nothing"; list pros, cons and why rejected.
4. **State consequences,** good and bad, and what must change; add a revisit trigger.
5. **Immutable history:** never edit an accepted ADR's decision; write a new one that **supersedes** it and link both.
6. **Short:** one page; link to evidence (issues, benchmarks, commits). Do not invent rationale the user did not give; ask or mark "unknown".

## Procedure
1. Find the project's ADR folder and format (`docs/adr`, `doc/decisions`, `adr/`); keep it, else use `docs/adr` with the template in `references/adr-template.md`.
2. Create the file: `python "<this skill's directory>/scripts/new_adr.py" "Use PostgreSQL for orders" [--dir docs/adr] [--status proposed]` (next number, slug, date).
3. Fill the sections from evidence and the user's input; ask about missing drivers.
4. Mark status (proposed/accepted/deprecated/superseded), update the index and any superseded record's status line.
5. Show the user the text; do not commit unless asked.

## Definition of done
- [ ] One decision, clear context, real alternatives, consequences, status, revisit trigger.
- [ ] Linked evidence; numbering consistent; superseded records updated.

## Pitfalls
Writing it after the fact as justification. Only one option listed. Vague consequences. Editing history. Decisions hidden in chat threads.

## Hand-offs
| Next | Load |
|---|---|
| design behind the decision | `design-architecture` |
| technology comparison | `evaluate-technology` |
| docs | `write-documentation` |
