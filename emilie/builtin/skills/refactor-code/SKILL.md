---
name: refactor-code
phase: bangun
description: Improve the structure of existing code without changing its behavior - choose targets with evidence (churn x complexity, duplication, size), pin current behavior with tests first, make small mechanical steps that each leave the tests green, keep refactoring commits separate from behavior changes, and prove behavior is unchanged. Includes a hotspot, complexity and duplication ranking script. Not for new behavior (build-feature), framework or version moves (migrate-code) or bug hunts (investigate-bug). Triggers - "refactor", "clean up", "simplify", "split this function", "too long", "duplicate code", "extract", "restructure", "rename across", "tidy", "make this maintainable".
---

# Refactor code

**Goal:** make the code easier to understand and change while its observable behavior stays exactly the same, and be able to
prove it.

## Ground rules

1. **Behavior must not change.** Refactoring changes structure only. If you find a bug, or want new behavior, write it down and do it
   as a separate change (`investigate-bug`, `build-feature`). Mixing them makes both unreviewable.
2. **Tests first or no refactoring.** Find the tests that cover the code you will touch and run them (Step 3). If coverage is thin, add
   characterization tests that pin what the code does today, bugs included. Without a safety net, tell the user the risk and ask.
3. **Evidence picks the target.** Refactor what is both hard to work with and often changed. Do not tidy code nobody touches because it
   looks ugly. Run the hotspot script (Step 2) and name the pain the refactoring removes.
4. **Small steps, always green.** One named transformation at a time (rename, extract function, move, inline, introduce parameter
   object). Run the tests after each. If one fails, undo that step rather than debugging a pile of changes.
5. **Mechanical when possible.** Prefer the editor or language tooling for renames and moves, or a precise search to list every reference.
   Search the whole repository (tests, docs, config, scripts, strings, reflection and dynamic access) before declaring a rename complete.
6. **Public surface is a contract.** Do not change exported functions, endpoints, CLI flags, file formats, database schemas, events or
   serialized names unless asked. If you must, use parallel change: add the new, migrate callers, then remove the old in a later step.
7. **Separate commits, separate concerns.** Refactoring commits contain no behavior changes and no formatting noise mixed with logic.
   Reformat in its own commit, or not at all if the project has no formatter.
8. **Stay in scope.** Agree the boundary up front (one function, one module, one pattern). Large restructurings are planned with
   `break-down-tasks` and done in slices that each ship.
9. **Prove it.** Run the full tests, linter and type checker before and after; compare. State what was not covered. Where possible compare real
   outputs before and after on sample inputs.
10. **Leave a trail.** Say what changed structurally, why, and how to review it (move vs change). Commit only when asked.

## Procedure

### Step 1 - Agree on the goal and the boundary

Write: what hurts today (slow to change, hard to read, fear of touching it, repeated bug class), what "better" means, what is in and out
of scope, constraints (public API frozen, no new dependencies, finish this week), and the pain you are measuring against. If the real
goal is new behavior or a version upgrade, switch to the right skill.

### Step 2 - Find and rank targets

```
python "<this skill's directory>/scripts/hotspots.py" [path] [--top 10] [--since "12 months ago"] [--min-dup 8]
```

It reports: hotspots (git churn x complexity), complex Python functions (length, parameters, nesting, cyclomatic complexity), large files for
all languages, and duplicated blocks. Other languages get size, duplication and churn only. Pick targets where complexity and churn overlap,
or where duplication means a bug fix must be made in several places. Read the code you picked in full before deciding anything.

### Step 3 - Build the safety net

1. Run `detect_commands.py` from `build-feature` (or read the CI file) to find the test, lint and type commands; record a **baseline**.
2. Find which tests exercise the target (search for its name, its module, its callers). Run them.
3. Add characterization tests for any behavior that is not pinned: feed representative inputs (including edge and error cases), record
   the current outputs, and assert them. Keep them even if the current behavior looks wrong; mark suspected bugs with a comment.
4. If the code has side effects (files, network, time, randomness), put a seam around them with the smallest possible change, itself
   covered by a test, so the logic can be tested.

### Step 4 - Choose the transformations

Map each problem to a known refactoring using `references/catalog.md` (long function -> extract function; deep nesting -> guard clauses;
repeated block -> extract and reuse; long parameter list -> parameter object; god class -> split by responsibility; feature envy -> move
method; magic numbers -> named constants; conditionals on type -> polymorphism or table; etc.). List the steps in order, smallest and
safest first, and what each leaves green. Read `references/safety.md` for large moves (parallel change, strangler, branch by abstraction).

### Step 5 - Refactor in small steps

For each step: make the one change; run the focused tests; run the wider suite; read `git diff`; keep going or revert. Rules of thumb:

- Rename and move before restructuring logic.
- Extract with the name of the intention, not the mechanics (`apply_discount`, not `part2`).
- Do not change a condition, a loop bound, an error message or an ordering "while you are there".
- Keep behavior-neutral signatures at first; tighten later in a separate step.
- Delete only what is proven unused (search, tests, coverage), and note dead code you find rather than removing it silently.

### Step 6 - Verify behavior is unchanged

Run the complete test suite, linter, formatter check and type checker; compare with the baseline. If you pinned outputs, diff the before and
after outputs for a set of sample inputs (record them from the original commit with `git stash` or a worktree). Run the program for real on
a typical path. Re-run the hotspot script on the target and report the change in the numbers (length, complexity, duplication). Report
anything not covered by tests.

### Step 7 - Report

State what was improved (before/after metrics), the sequence of structural changes, files touched, how to review (for example "pure moves in
commit 1, extractions in commit 2"), tests added, the commands run and results, what remains (follow-ups: next hotspot, suspected bugs found,
dead code noticed), and any risk the tests do not cover. Offer `review-code` and, if asked, `commit-and-pr`.

## Definition of done

- [ ] The goal, boundary and pain being removed are written down; the target was chosen with evidence.
- [ ] A baseline of tests, lint and types was recorded; relevant behavior is pinned by tests (existing or characterization).
- [ ] Each step was a single named transformation with tests green afterwards.
- [ ] No behavior, public interface, data format or message changed (or the change was agreed, separate and flagged).
- [ ] Every reference to renamed or moved items was found by search across code, tests, docs, config and scripts.
- [ ] The final run matches or improves the baseline; before/after metrics are reported.
- [ ] Bugs and extra ideas found along the way are listed as follow-ups, not mixed in.
- [ ] The report says what the tests do not cover.

## Pitfalls

- **Refactoring without tests.** "It's just a rename" is how production breaks. Pin behavior first.
- **The disguised rewrite.** A big-bang replacement labeled as cleanup. Keep steps small and reversible.
- **Fixing bugs on the way.** The diff now changes behavior and nobody can tell which part was intended.
- **Reformat-the-world.** Whitespace churn hides the real change and ruins `git blame`. Format separately or not at all.
- **Renaming via blind search and replace.** Matches inside strings, comments, other symbols, and dynamic lookups (`getattr`, reflection, JSON keys, templates).
- **Breaking the public contract** by changing exported names, endpoint paths or serialized fields.
- **Over-abstracting.** Interfaces and layers for a single use. Duplication is cheaper than the wrong abstraction; abstract after the third occurrence.
- **Refactoring cold code.** Spending days on ugly code that is stable and untouched.
- **Declaring victory by metrics.** Lower complexity numbers are not the goal; ease of change is. Check the result reads better.
- **No exit.** A long-running refactoring branch that diverges from main. Ship in slices.

## Hand-offs

| Next | Load |
|---|---|
| understand the code first | `trace-code`, `project-overview` |
| tests are missing or weak | `write-tests` |
| flaky tests block progress | `fix-flaky-tests` |
| plan a large restructuring | `break-down-tasks`, `design-architecture` |
| framework/version change | `migrate-code`, `upgrade-dependencies` |
| review the result | `review-code` |
| bug found along the way | `investigate-bug` |
| commit or PR | `commit-and-pr` |
| clear the backlog of debt | `pay-down-tech-debt` |
