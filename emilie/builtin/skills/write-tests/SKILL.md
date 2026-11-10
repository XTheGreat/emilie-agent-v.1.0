---
name: write-tests
phase: cek-mutu
description: Write tests that catch real bugs - find what is untested and risky, design cases from behavior (happy path, boundaries, invalid input, failures, state), follow the project's framework and style, keep tests fast and deterministic, and prove each test can fail by breaking the code on purpose. Includes a script that lists untested symbols and low-coverage files. Not for fixing intermittent failures (fix-flaky-tests), load or performance testing (load-test) or reviewing code (review-code). Triggers - "write tests", "add tests", "unit test", "test coverage", "improve coverage", "untested", "test this function", "integration test", "TDD", "regression test", "pytest", "jest".
---

# Write tests

**Goal:** tests that fail when behavior breaks and pass when it does not, that read like a specification, and that a teammate can
trust, run in seconds and maintain.

## Ground rules

1. **Behavior, not implementation.** Test what the code promises (inputs, outputs, side effects, errors) through its public
   interface. Tests that mirror the code line by line pass when the code is wrong and break on harmless refactors.
2. **Read the code and the existing tests first.** Learn the framework, fixtures, naming, assertion style, how external things
   (database, clock, network) are faked, and how the suite is run. Match them. Never introduce a second framework.
3. **Prove the test can fail.** After writing a test, break the code on purpose (change a condition, return a wrong value, delete a
   line), run the test, and watch it fail for the right reason; then restore the code. A test you never saw fail proves nothing.
4. **Pick risk, not numbers.** Coverage is a map of what was *not* run, not a measure of quality. Spend effort on logic with branches, money,
   security, data changes, parsing, and code that has broken before (`git log` for fix commits). Do not write tests just to raise a percentage.
5. **One reason to fail per test.** One behavior per test, a name that states it (`rejects_expired_token`), and an assertion that points at
   the cause. Prefer several small tests over one test with twenty asserts.
6. **Deterministic and isolated.** No real network, no dependence on the current date, random values, test order, files left by other tests, or the
   machine's locale and time zone. Control time, randomness and I/O at the boundary. Each test creates and cleans up its own state.
7. **Fast.** Unit tests in milliseconds; avoid sleeps and heavy setup. Share expensive fixtures safely or push the slow cases into a few integration tests.
8. **Fake only what you must.** Use real objects when cheap; fake the slow, unreliable or external (network, clock, payment provider). Over-mocking
   tests the mocks. Keep at least one test per integration against the real thing (or a faithful local substitute).
9. **Never weaken to pass.** Do not loosen an assertion, skip, `xfail`, or delete a failing test to get green. If a test exposes a real bug, report it
   and keep the test (mark it clearly) instead of hiding it.
10. **Report honestly.** Show the exact commands and their results; say what is not covered and what could not be run.

## Procedure

### Step 1 - Decide the target

Ask or infer: which function, module or behavior, and why now (new code, a bug fix, a refactor safety net, a coverage push). Name the level:
unit (one function or class), integration (several parts or a real database/service), or end-to-end (the whole flow). Default to the lowest level that can
catch the risk.

### Step 2 - Learn the project's testing setup

Run `detect_commands.py` from the `build-feature` skill, or read the README, CI file and config, to find the test command, the framework, fixtures and
helpers, and where tests live. Run the existing suite once to get a **baseline** (what passes, what already fails). Look at two or three existing tests
and copy their structure.

### Step 3 - Find the gaps

```
python "<this skill's directory>/scripts/find_gaps.py" [path] [--top 15] [--coverage coverage.xml]
```

It lists public functions, methods and classes that no test file mentions (ranked by size times branches), source files without a matching test file, and, if you
pass a coverage report (`coverage.xml`, `lcov.info`), the least covered files with their missing line ranges. A name mentioned in a test is not necessarily
well tested: read those tests. To make a coverage report, use the project's own tool (for example `python -m pytest --cov --cov-report=xml`, `npx vitest run --coverage`,
`go test -coverprofile=c.out ./...`) only if it is installed and the user agrees to install nothing new.

### Step 4 - Design the cases

For each target, list the cases before writing code, using `references/test-design.md`: the normal path, every branch, boundaries (empty, one, many, min, max, just
over), invalid and hostile input, each failure of a dependency, state changes and ordering, idempotency and repeats, permissions, and one case for each bug that was ever
fixed here. Write the list as test names. Remove duplicates that exercise the same branch.

### Step 5 - Write the tests

Follow arrange, act, assert. Use the project's idioms (parametrized tests for tables of inputs, fixtures for setup, builders for objects). Keep data minimal and meaningful;
name variables for their role. Assert the outcome (value, state, calls that matter), not private details. Fake time, randomness and network at the edge. See
`references/frameworks.md` for the idioms of pytest, unittest, Jest/Vitest, Go, JUnit, Rust and others. If the code is hard to test, introduce the smallest seam
(a parameter, an injectable clock, a function extracted from I/O) as its own small change and tell the user.

### Step 6 - Make them fail on purpose

For each new test or group: temporarily break the behavior it guards (flip a comparison, remove a validation, return a constant), run the test, confirm it fails with a
message that explains why, then restore the code exactly (`git diff` must show no change to the source). If a test still passes with broken code, strengthen its assertion.
For bug-fix tests, run them against the code *before* the fix (`git stash` the fix, or check out the old version) and see them fail.

### Step 7 - Run everything

Run the new tests alone, several times if anything looks timing- or order-dependent, then the full suite, linter and type checker. Compare with the baseline: nothing that
passed before may fail now. If you generated coverage, report the change for the files you targeted.

### Step 8 - Report

List: tests added (names, one line each on what they guard), the commands run and their results, the red-then-green evidence for the important ones, coverage change (if
measured), what remains untested and why, any bugs the tests uncovered (kept, with the failing output), and seams or small changes made to make the code testable.
Offer `review-code`, `fix-flaky-tests` if something is intermittent, or `commit-and-pr`.

## Definition of done

- [ ] The suite's baseline was recorded and the final run shows no new failures; commands and results are stated.
- [ ] Each case in the design list has a test, or the omission is explained.
- [ ] New tests assert behavior, use the project's framework and style, and have names that read as specifications.
- [ ] Each important test was seen failing against deliberately broken (or pre-fix) code, and the code was restored.
- [ ] Tests are deterministic: no real network or clock, no order dependence, no leftover state; repeated runs agree.
- [ ] No test was skipped, loosened or deleted to pass; real bugs found are reported.
- [ ] Source files are unchanged except for agreed seams; the diff contains only tests (and those seams).
- [ ] The report states what is still not tested.

## Pitfalls

- **Tests that re-implement the code** (computing the expected value with the same logic) and so can never disagree with it.
- **Assert nothing / assert too little**: calling the function and only checking that it did not raise.
- **Over-mocking**: everything replaced by mocks so the test checks the mocks' wiring, not behavior.
- **Hidden coupling**: tests that pass only in a certain order, on a certain date, or with leftovers from earlier tests.
- **Giant tests** with many steps and asserts: when they fail nobody knows why.
- **Snapshot overuse**: huge snapshots approved without reading; a change gets accepted blindly.
- **Chasing 100% coverage**: trivial getters tested while the risky branch is not.
- **Sleeping for async work** instead of waiting on a condition or controlling the clock.
- **Testing the framework** or the language instead of your code.
- **Fixing the test to match a bug** because the failure was inconvenient.
- **Leaving a broken experiment behind**: always diff the source after the "make it fail" step.

## Hand-offs

| Next | Load |
|---|---|
| a test fails sometimes | `fix-flaky-tests` |
| understand the code first | `trace-code` |
| new feature around the tests | `build-feature` |
| restructure with a safety net | `refactor-code` |
| review the change | `review-code` |
| speed or load questions | `profile-performance`, `load-test` |
| commit or PR | `commit-and-pr` |
