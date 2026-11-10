---
name: fix-flaky-tests
phase: cek-mutu
description: Find and fix tests that pass and fail without a code change - reproduce the failure on demand, classify the cause (timing, order, shared state, time, randomness, network, concurrency, environment), fix the root cause instead of adding retries or sleeps, and prove the fix with many repeated runs. Includes a script that scans for flakiness smells and measures failure rates over N runs. Not for new tests (write-tests) or a real product bug (investigate-bug). Triggers - "flaky", "intermittent", "sometimes fails", "fails randomly", "fail randomly", "passes locally fails in CI", "fails in CI", "passes on retry", "non-deterministic", "race condition in tests".
---

# Fix flaky tests

**Goal:** a test suite whose result depends only on the code. Every flaky test is either a test bug (bad isolation, bad waiting) or a real
product bug (a race, a leak) that the test is honestly reporting: find out which, and fix the cause, not the symptom.

## Ground rules

1. **Reproduce before you fix.** A fix you cannot show failing before and passing after is a guess. Get a command that fails often enough to measure
   (Step 3). Without a reproduction, say so and add instrumentation instead of changing code.
2. **Evidence over hunches.** Keep the failing output of a real failure; the traceback, the timing and the neighboring tests usually name the cause. Do not
   decide the cause from the smell list alone.
3. **Never "fix" with retries, longer sleeps or skips.** Retry-on-failure, `sleep(5)`, `@skip`, `xfail` and deleting the test hide the problem and keep the
   risk. A quarantine (a visible, tracked, time-limited skip with an owner) is allowed only as a temporary measure the user agrees to, with the root cause still planned.
4. **Suspect the product too.** If the failure is a real race, a leaked connection or a nondeterministic result in production code, the test is right.
   Switch to `investigate-bug`, fix the code, and keep the test.
5. **One cause at a time.** Change one thing, re-measure. Several simultaneous edits make it impossible to know what worked.
6. **Statistics, honestly.** A flaky test that fails 1 time in 20 needs about 60 clean runs to say it is probably fixed (about 3 divided by the failure rate). State the
   number of runs and the before/after rates; never claim "fixed" from one green run.
7. **Do not touch unrelated tests or loosen assertions** to make the run green. Keep the fix small and local.
8. **Mind the environment.** Running a command repeatedly is cheap but can load the machine; do not start servers or services you do not understand, and never run the
   suite against real production systems or paid APIs. Tell the user when a run is long.
9. **Say what was not verified**: CI differences (CPU count, parallelism, OS, locale, time zone) you could not reproduce locally.

## Procedure

### Step 1 - Describe the problem precisely

Collect: which test(s), how often, where (local, CI, one OS), since when (a commit, a dependency bump, a growing suite), the failure message and a captured log of at least one
failing run. Check the history: `git log --oneline -- <test file> <source file>` and whether failures started with a particular change. Get the exact test command from the
project (use `detect_commands.py` of the `build-feature` skill, or the CI config) and a baseline run.

### Step 2 - Scan for the usual suspects

```
python "<this skill's directory>/scripts/flaky.py" scan [tests-path] [--top 12]
```

It lists, per category, where tests use sleeps, the real clock, unseeded randomness, real network, fixed ports, shared temp files, environment or working-directory changes, global or
class-level state, threads without joins, `.only`/skip/xfail, order dependence, exact float comparison and unordered data. Treat the output as a list of suspects: look at the ones inside or near
the failing tests first.

### Step 3 - Reproduce on demand

```
python "<this skill's directory>/scripts/flaky.py" run -n 20 [--until-fail] [--env PYTHONHASHSEED=random] [--cwd DIR] -- <the test command>
```

It runs the command N times and reports, per test, in how many runs it failed, separating "fails every run" (broken) from "flaky" (fails sometimes), shows durations, and with `--until-fail` prints
the tail of the first failing run. Narrow it: run only the suspect test, then its file, then the file with its neighbors. Then vary one factor at a time (`references/root-causes.md`, "How to isolate"):

- run the test **alone** (passes alone, fails in the suite = order or shared state)
- run the suite in **random or reversed order** if the runner supports it
- run **in parallel** or under CPU load (two copies at once) for timing and shared-resource problems
- change the **time zone, locale or date** (`TZ=...`, freeze the clock at a month end or midnight)
- fix the **random seed** (log it on failure) and rerun with the failing seed
- run **many times in a loop** with the single test (`-n 200` for a 1-in-50 failure)

Record the best reproduction command and its failure rate. If nothing reproduces after a fair effort, say so and propose instrumentation (log timestamps, thread ids, seeds, resource counts)
and a CI job that collects failing logs.

### Step 4 - Find the root cause

Match the evidence to a cause in `references/root-causes.md`: asynchronous waiting, order dependence or shared state, time, randomness, network or external services, concurrency, resource
leaks and ports, environment differences, test data collisions, floating point, unordered collections. Read the test and the code it exercises together; trace where state is created and where it
is cleaned up. Confirm the hypothesis by making the failure **happen on purpose** (insert a delay at the suspected race, force the order, set the clock to the bad value). If you can make it fail
deterministically, you have the cause.

### Step 5 - Fix the cause

Choose the fix from `references/fix-recipes.md`: wait on a condition or event instead of sleeping, inject or freeze the clock, seed or inject randomness, fake the network boundary, bind to port
0, give each test its own temporary directory and database rows, undo environment changes with scoped helpers, remove shared mutable state, sort before comparing, use approximate comparison for
floats, join threads and await tasks explicitly, make the product code thread-safe if the race is real. Keep the change minimal and explain why it removes the cause.

### Step 6 - Prove it

Re-run the reproduction from Step 3 with at least the number of runs that gives confidence (about 3 divided by the old failure rate, never fewer than 30 for a 1-in-10 problem), under the same
stress conditions that made it fail (parallel, random order, loaded machine). Run the whole suite and the linter, compare with the baseline, and make sure you did not turn the test into one that
can no longer fail (break the code on purpose and see it fail). Report before and after: runs, failures, rates.

### Step 7 - Prevent the return

Where it fits the project: enable random test ordering, run tests in parallel in CI, fail the build on `.only`, forbid real network in tests (a socket guard), forbid `sleep` in tests via a lint rule,
keep a flaky-test tracker, and make failing-run logs and seeds visible. Suggest only what the project can maintain.

### Step 8 - Report

State: the test(s), the reproduction command and rate, the root cause with the evidence, the fix, the verification (runs and results), anything left quarantined (with owner and date), the
conditions you could not reproduce, and recommended safeguards. If the cause was a product bug, say so clearly and what was changed.

## Definition of done

- [ ] A reproduction command exists with a measured failure rate, or the lack of one is stated with a plan to collect evidence.
- [ ] The root cause is identified from evidence and, ideally, triggered on purpose.
- [ ] The fix removes the cause; it is not a retry, a longer sleep, a skip or a weaker assertion.
- [ ] After the fix, the reproduction ran enough times (statistically meaningful, under the same stress) with zero failures; before and after numbers are reported.
- [ ] The full suite, linter and type checker still pass versus the baseline; the test can still fail when the behavior breaks.
- [ ] Any quarantine is visible, owned and dated; unverified environments are listed.
- [ ] If production code had the bug, it is fixed and covered by a deterministic test.

## Pitfalls

- **Adding retries** (`@flaky`, rerun-failures). The suite goes green and the bug stays, now costing time on every run.
- **`sleep` to make it pass.** Slower, and still racy on a slow machine.
- **Calling it "CI is flaky".** Usually the test is order- or timing-dependent and CI just exposes it (parallelism, fewer cores, different clock).
- **Fixing the symptom in one test** while a shared fixture or leaked global keeps breaking others.
- **Stopping at one green run**, or declaring victory after 5 runs of a 1-in-20 failure.
- **Reproducing without the failing condition** (alone, quiet machine, same order) and concluding there is no bug.
- **Mocking away the thing that is flaky** so the test no longer tests anything.
- **Shared test database or fixtures** that parallel runs or earlier tests modify.
- **Ignoring product races.** A flaky test of concurrent code is often a correct alarm.
- **Quarantine forever.** A skip without owner or date is deletion in slow motion.

## Hand-offs

| Next | Load |
|---|---|
| the product code is wrong | `investigate-bug` |
| the test needs rewriting or more cases | `write-tests` |
| understand what the test exercises | `trace-code` |
| slowness is the cause | `profile-performance` |
| CI changes (parallelism, retries policy) | `setup-ci-cd` |
| review the fix | `review-code` |
