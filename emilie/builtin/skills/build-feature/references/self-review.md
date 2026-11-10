# Self-review of the diff

Run `git status` and `git diff` (plus read untracked files). Review as if someone else wrote it.

## 1. Scope and intent

- [ ] Every changed file is needed for the stated change. Unrelated edits are reverted or listed as follow-ups.
- [ ] No reformatting churn in lines you did not change.
- [ ] No unexpected changes in lockfiles, generated files, config, CI or environment files.
- [ ] No stray files (scratch scripts, logs, `.orig`, exports, screenshots, local databases).

## 2. Correctness

- [ ] Each acceptance check has a test or a demonstrated run.
- [ ] Off-by-one, boundary and empty-input cases are handled; loops and recursion terminate.
- [ ] Errors are handled where they can occur, with useful messages; resources are released on every path.
- [ ] No swallowed exceptions or blanket `catch` that hides failures.
- [ ] Concurrency, ordering and retries are safe (idempotent where repeated).
- [ ] Time, time zones, encodings and numeric precision (money) are handled deliberately.

## 3. Security and privacy

- [ ] Input from outside is validated and bounded; output is encoded for its context.
- [ ] Queries use parameters; paths and shell commands are not built from raw input.
- [ ] Authorization is checked on the server for each object and action.
- [ ] No secrets, tokens or personal data in code, logs, errors, tests or fixtures.
- [ ] New dependencies are justified, pinned, and from the real registry.

## 4. Compatibility

- [ ] Public functions, endpoints, CLI flags, file formats and database schemas stay compatible, or the break is flagged and documented.
- [ ] Migrations are safe on live data and reversible; ordering with the code deploy is stated.
- [ ] Defaults did not change silently.

## 5. Tests

- [ ] New tests fail without the change and pass with it.
- [ ] They assert behavior, not implementation details; no sleeps or dependence on test order.
- [ ] No test was skipped, loosened or deleted to get green.
- [ ] Failure paths and edges are covered, not only the happy path.

## 6. Readability and fit

- [ ] Names say what things are; functions do one thing; nesting is shallow.
- [ ] The code looks like its neighbors (style, structure, error handling).
- [ ] Comments explain why, and none are stale; no commented-out code, debug prints, or unexplained TODOs.
- [ ] No duplication of an existing helper.

## 7. Docs and operations

- [ ] README, usage docs, API docs, config examples and changelog reflect the change.
- [ ] Logging and metrics exist for new failure modes, without leaking data.
- [ ] Rollout, flags and rollback are described if the change is risky.

## Final report template

```
What changed: <behavior in one or two sentences>
Files: <path> - <why>  (one line each)
Tests added: <names>
Verified: <command> -> <result>   (tests, lint, types, build; baseline: <what already failed>)
Ran the feature: <how, and what I saw> | not run: <why>
Not verified / risks: <list>
Assumptions: <list>
Follow-ups noticed (not done): <list>
You need to: <migration, config, flag, review>
```
