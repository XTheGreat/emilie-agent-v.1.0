---
name: pay-down-tech-debt
phase: rawat
description: Find, rank and reduce technical debt in a codebase - scan for hotspots (large files, long functions, TODO/FIXME, skipped tests, duplicated code, high churn), judge impact and cost with evidence, propose a prioritized and time-boxed plan, and fix the agreed items in small safe steps. Includes a scanner script. Not for restructuring one specific piece of code (refactor-code) or a security review (security-audit). Triggers - "tech debt", "technical debt", "code health", "what should we clean up", "codebase is messy", "legacy code", "cleanup backlog", "hotspots".
---

# Pay down tech debt

**Goal:** spend limited time on the debt that actually slows the team or risks the product, and leave a measurable improvement.

## Ground rules
1. **Measure before judging.** Use the scanner and git history; opinion without evidence is not a priority.
2. **Rank by interest, not ugliness.** Debt in code that changes often or breaks often costs more than ugly code nobody touches (`references/prioritization.md`).
3. **Propose before doing.** Present a ranked list with effort and payoff; the user picks. Do not start a rewrite.
4. **Small, safe steps.** Add characterization tests first, then refactor with `refactor-code` rules; one concern per commit.
5. **Time-box and stop.** Done is an agreed outcome, not "perfect".
6. **Record decisions:** accepted debt gets a ticket/ADR with a reason and a revisit trigger.

## Procedure
1. Scan: `python "<this skill's directory>/scripts/debt_scan.py" [path] [--top 15]` - largest files, longest functions (Python/JS heuristic), TODO/FIXME/HACK count, skipped tests, commented-out code, git churn hotspots, files that are both big and churning.
2. Interpret: classify items (design, code, test, dependency, docs, build/tooling, knowledge) and score each with impact x frequency / effort.
3. Present the top items, quick wins first, with the evidence and a proposed order.
4. Execute the approved items with tests green after each step; measure again.
5. Report before/after numbers and what was deliberately left.

## Definition of done
- [ ] Ranked list with evidence; user-approved scope.
- [ ] Each fix verified by tests; metrics before/after reported.
- [ ] Remaining debt recorded with reason.

## Pitfalls
Big-bang rewrites. Cleaning code that is stable and rarely touched. Refactoring without tests. Mixing cleanup with feature work in one commit. Treating every TODO as debt.

## Hand-offs
| Next | Load |
|---|---|
| restructure code | `refactor-code` |
| missing tests | `write-tests` |
| outdated packages | `upgrade-dependencies` |
| record a decision | `write-adr` |
