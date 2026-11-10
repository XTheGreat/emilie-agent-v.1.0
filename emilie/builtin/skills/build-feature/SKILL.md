---
name: build-feature
phase: bangun
description: Implement a feature or change in an existing codebase safely - confirm scope, record a test baseline, learn and follow the project's patterns, build in small vertical steps with tests, run the real test/lint/type commands, review your own diff, and report exactly what changed and what was verified. Includes a script that finds the project's build, test and lint commands and the git state. Not for a brand-new project (scaffold-project), pure restructuring (refactor-code) or a bug hunt (investigate-bug). Triggers - "add a feature", "implement", "build this", "add support for", "make it so", "add an endpoint", "add a button", "new command".
---

# Build feature

**Goal:** deliver a working, tested change that looks like it belongs in this codebase, touches only what it must, and comes
with an honest account of what was verified.

## Ground rules

1. **Scope first.** Restate what will change and what will not, with acceptance criteria you can check. If the request is vague or
   large, clarify (`clarify-requirements`) or plan (`break-down-tasks`) before writing code.
2. **Baseline before changes.** Find the project's test, lint and type commands (Step 2), run them on the untouched tree, and record
   what already fails. You may only claim "I broke nothing" against a known baseline.
3. **Read before you write.** Find the closest existing feature, the modules you will touch, their tests, and the conventions
   (naming, error handling, logging, structure). Follow them. A different style needs a stated reason.
4. **Reuse, then extend.** Search for an existing helper, component or pattern before adding a new one. Never add a dependency without
   saying why, checking it (`evaluate-technology`) and getting the user's yes.
5. **Small vertical steps.** Make the thinnest working path first, then widen it. Each step compiles, passes its test, and could be
   committed alone.
6. **Tests are part of the feature.** Cover the new behavior, its edge cases and its failure paths, in the project's test style.
   Prefer writing the failing test first. A test you never saw fail proves nothing.
7. **Verify with real commands.** Run the tests, linter, type checker and build; read the output. "Should work" is not a result.
   If something cannot be run (no runtime, needs approval, needs network), say "not run" and why.
8. **Minimal diff.** No drive-by refactors, reformatting of untouched code, renamed files or unrelated fixes. Note them as follow-ups instead.
9. **Protect what exists.** Keep public interfaces, data formats and behavior compatible unless the change requires otherwise, and flag
   anything that is breaking. Never delete or overwrite user data, and never run destructive commands without the user's yes.
10. **Never hide a failure.** Do not weaken, skip or delete a test to make it pass, and do not claim success from partial output.
    Report failing checks with their output.
11. **Secrets and safety.** No credentials in code or logs; validate input at boundaries; follow the project's auth rules.
12. **Commit only when asked.** Leave changes in the working tree unless the user asks for a commit (`commit-and-pr`).

## Procedure

### Step 1 - Pin down the change

In a few lines: the behavior to add, who or what triggers it, inputs and outputs, error cases, what must stay unchanged, and the
acceptance checks. List open questions and assumptions; ask the user only about what blocks you or is risky to guess.

### Step 2 - Preflight

Run:

```
python "<this skill's directory>/scripts/detect_commands.py" [project-root]
```

It reads (and never runs) the manifests, Makefile, CI files, and prints the candidate install, test, lint, format, typecheck, build
and run commands with the file each came from, plus the commands the CI runs, and the git branch and cleanliness. Then:

1. Confirm the commands with the README or CI when they look unusual. Install dependencies only if needed and the user allows it.
2. Note the git state: if the tree already has uncommitted changes, say so, and keep your edits separable. Work on a feature branch
   if the project's convention calls for it and the user wants it.
3. Run the test, lint and type commands once to get the **baseline**. Record the result: pass/fail counts and each failing test.

### Step 3 - Learn the neighborhood

Find the closest existing feature and read it end to end: entry point, validation, business logic, storage, output, tests. Use
`trace-code` if the path is long. Note: where new code belongs, the naming and error-handling patterns, how config, logging and
i18n are done, how tests are structured and run. Search the codebase for existing helpers (`grep` for the verbs and nouns involved).

### Step 4 - Plan the steps

List 3 to 8 small steps, each ending in something verifiable (a passing test or a visible behavior). For anything bigger, write a
proper plan with `break-down-tasks`. State the plan to the user in a few lines before editing when the change touches more than a
couple of files or any shared interface. Decide the test list now: happy path, boundaries, invalid input, failure of each dependency,
permissions, idempotency/retries if relevant.

### Step 5 - Build in loops

For each step, repeat (details in `references/workflow.md`):

1. Write or extend a test that expresses the step; run it and watch it fail for the right reason.
2. Write the smallest code that makes it pass, in the project's style.
3. Run the focused tests, then the wider suite. Fix what you broke immediately.
4. Re-read your diff for the step (`git diff`) before moving on.

Handle the edges as you go: input validation, errors with useful messages, empty and large inputs, concurrency or ordering, time zones and
encodings, and permissions. Update docs, config examples, migrations and changelog entries that the change affects.

### Step 6 - Verify the whole change

Run the full set from Step 2: tests, linter, formatter check, type checker, build. Compare against the baseline: new failures are yours.
Exercise the feature for real when you can (run the CLI, call the endpoint, open the page) and look at the actual output, including one
failure case. If a UI is involved, check keyboard use and an empty/error state. Report anything you could not run.

### Step 7 - Self-review the diff

Go through `references/self-review.md` on `git diff` (and untracked files from `git status`): correctness, scope, security, tests,
naming, leftovers (debug prints, TODOs, commented-out code, stray files), compatibility, and docs. Fix what you find; do not leave it for
the reviewer.

### Step 8 - Report

Give a short, honest summary: what the feature does now; files changed and why (one line each); tests added; the exact commands run
with results (and baseline comparison); what you did **not** verify; assumptions you made; follow-ups you noticed but left alone; and
anything the user must decide or do (a migration to run, a config value, a flag to flip). Offer the next step: `review-code`,
`write-tests` if coverage is thin, `commit-and-pr`.

## Definition of done

- [ ] The change matches the confirmed scope and each acceptance check is demonstrated.
- [ ] A baseline was recorded; the final run shows no new failures, with the commands and results stated.
- [ ] New behavior has tests for the happy path, edges and failures, and those tests were seen failing before passing (or the reason they could not be is stated).
- [ ] Code follows the project's patterns; no unexplained new dependency; no unrelated changes in the diff.
- [ ] Lint, format and type checks pass (or pre-existing failures are listed as such).
- [ ] The diff was reviewed for leftovers, security and compatibility.
- [ ] Docs, config examples and migrations affected by the change are updated.
- [ ] The report lists what was not verified and every assumption.

## Pitfalls

- **Coding before reading.** You reinvent a helper that exists and ignore the project's error handling.
- **No baseline.** You cannot tell whether a failing test is yours.
- **Big-bang implementation.** One huge edit, then twenty failures at once. Work in loops.
- **Testing the implementation, not the behavior.** Tests that mirror the code pass even when it is wrong; assert outcomes.
- **Green by weakening.** Loosening an assertion, adding a skip or a broad `try/except` so the run passes.
- **Scope creep.** "While I was here" changes bury the real change and break review.
- **Happy-path only.** Empty input, missing permission, a timeout and a retry are where features fail in production.
- **Claiming unverified results.** Say "tests pass" only after running them and reading the output.
- **Leaving debris:** debug prints, temp files, commented code, a `.env` edit, a changed lockfile you did not intend.
- **Silent breaking change.** A renamed field or changed default that other code or users rely on.

## Hand-offs

| Next | Load |
|---|---|
| requirements are fuzzy | `clarify-requirements` |
| the change is large | `break-down-tasks` |
| need the design first | `design-architecture`, `design-api`, `design-database`, `design-ui-ux` |
| restructure first | `refactor-code` |
| external service involved | `integrate-third-party` |
| more or better tests | `write-tests` |
| review the result | `review-code` |
| commit or open a PR | `commit-and-pr` |
| something fails strangely | `investigate-bug` |
