---
name: profile-performance
phase: cek-mutu
description: Find and fix performance problems with measurements, not guesses - define the metric and a baseline, profile to find where time or memory really goes (cProfile, tracemalloc, language profilers, EXPLAIN, browser tools), change one thing at a time, and prove each gain with repeated timings and a confidence interval while the tests stay green. Includes a script for profiling Python, timing commands and comparing two commands fairly. Not for load capacity of a service (load-test) or writing tests (write-tests). Triggers - "slow", "too slow", "performance", "optimize", "speed up", "profile", "bottleneck", "high memory", "memory leak", "takes too long", "latency", "make it faster", "benchmark".
---

# Profile performance

**Goal:** make the program measurably faster or lighter where it matters, by finding the real bottleneck, changing as little as possible, and proving the improvement without breaking behavior.

## Ground rules

1. **Measure, do not guess.** Intuition about performance is usually wrong. No optimization without a baseline measurement and a profile that points at the cause.
2. **Define the metric and the target.** Latency of a request, throughput, startup time, memory peak, bundle size, page load? For which input and environment? What is "good enough"? Optimize only until the target is met.
3. **Representative workload.** Profile with realistic data sizes, inputs and settings (production-like, not a toy). Warm up caches and JITs, and run in the environment where it is slow (a slow query on the real database, not an empty local one).
4. **Find the bottleneck first (Amdahl's law).** Speeding up code that takes 5% of the time can gain at most 5%. Work on the largest item; re-profile after each fix because the next bottleneck moves.
5. **One change at a time, measured.** Apply a single change, re-measure with repeated runs, keep it only if the gain is real (beyond noise) and worth the added complexity. Revert the rest.
6. **Correctness first.** The tests (or a before/after output comparison) must pass after every optimization. A faster wrong answer is a bug. Add a test if the area is uncovered.
7. **Profilers distort.** They add overhead and change relative timings. Use them to see *where*; use plain timing (`perf.py time`/`compare`) to measure *how much*.
8. **Prefer algorithmic and design wins** (better algorithm, fewer calls, batching, caching, less I/O) over micro-optimizations. Micro-tuning is the last resort and must be justified by a profile.
9. **Readable code is a feature.** Do not trade clarity for a gain you cannot measure. Comment surprising optimizations with the measurement that justifies them.
10. **Report honestly**: baseline, method, environment, results with variance, what did not help, and what you did not measure. Never claim a speedup from a single run.

## Procedure

### Step 1 - Define the problem and the metric

Write: what is slow or heavy (a command, endpoint, page, job, query), how it is measured (wall time, p95 latency, CPU time, peak memory), the current number, the target, the input size, and the environment (hardware, versions, data). Ask the
user for the exact slow scenario and how to run it. Clarify whether the problem is CPU-bound, waiting on I/O (disk, network, database), memory pressure, lock contention, or startup.

### Step 2 - Get a reliable baseline

Make the scenario runnable with one command. Measure it several times:

```
python "<this skill's directory>/scripts/perf.py" time -n 10 --warmup 1 -- <the command>
```

It reports min, median, mean, stdev, p90 and max, flags high variance, and refuses to time a failing command. Record the baseline and the noise level. Check that the answer is correct, and save the output of a representative run to compare after
the change (or rely on the test suite).

### Step 3 - Profile to find where time or memory goes

Pick the tool for the language and the kind of problem (`references/method.md`).

**Python, CPU:**
```
python "<this skill's directory>/scripts/perf.py" cprofile --top 20 [--paths .] [--callers NAME] script.py [args]      # or: cprofile -m package.module [args]
```
Run it with the project's own interpreter (its virtualenv) so that imports resolve. It lists the hottest functions by own and cumulative time, marks your code, and shows what share of the time is yours vs libraries; `--callers NAME` shows who
calls a function. **Memory:** `perf.py memory --top 15 script.py` prints peak traced memory and the lines holding the most.

**Other languages and layers:** Node (`node --cpu-prof`, `--heap-prof`, Chrome DevTools), Go (`pprof`, `-benchmem`), Java (JFR, async-profiler), Rust (`cargo flamegraph`, criterion), browsers (Performance panel, Lighthouse, Web Vitals), SQL (`EXPLAIN ANALYZE`,
slow query log), system (`perf`, `strace -c`). Use what is installed; ask before installing anything.

Read the profile: the top items by own time, call counts that are suspiciously high (a function called a million times), time inside libraries called from your code (JSON, regex, ORM), I/O waits, and allocations.

### Step 4 - Form a hypothesis

State it precisely: "`dedupe` is quadratic: `x not in list` scans the list for each item; with n = 6000 that is 18M comparisons". Check the cause in the code (algorithmic complexity, repeated work, N+1 queries, unbatched I/O, missing index, needless copies,
unbounded caches, synchronous waits, serialization cost). Use `references/optimizations.md` for the usual causes and fixes.

### Step 5 - Change one thing, then measure

Make the smallest change that tests the hypothesis. Run the tests. Then compare old and new fairly:

```
python "<this skill's directory>/scripts/perf.py" compare -n 15 -- <command on the old code> -- <command on the new code>
```

It alternates runs to cancel drift, reports medians and a 95% bootstrap interval for the difference, and says "no clear difference" when the data cannot tell them apart. For the old code use `git stash` or a second worktree/checkout.
Keep the change only if the gain is clear and worthwhile; otherwise revert it. For memory, rerun `perf.py memory` and compare peaks.

### Step 6 - Repeat until the target is met

Re-profile after each accepted change (the bottleneck moves). Stop when the target is reached or when the remaining items are small, costly to change or outside your control (a third-party service, the network). Say what is left and why you stopped.

### Step 7 - Guard and document

Run the full test suite, linter and type checker; compare outputs for the scenario. Add a regression guard if cheap (a benchmark in CI with a generous threshold, a test on a complexity-sensitive function, a query-count assertion). Leave a short comment
where the code is non-obvious because of the optimization.

### Step 8 - Report

Give a short report: the scenario and metric; baseline and final numbers with variance (median and interval, number of runs); the profile findings (what dominated); the changes made and the gain of each; changes tried and rejected; correctness evidence (tests, output
comparison); environment details; limits of the measurement; and next candidates. Offer `load-test` if the question is capacity under concurrent load, and `write-tests` if coverage was thin.

## Definition of done

- [ ] The metric, target, workload and environment are defined; the baseline was measured repeatedly, with the noise level.
- [ ] A profile (or equivalent evidence) identified the bottleneck before any change.
- [ ] Each change was a single hypothesis, tested for correctness, and measured against the baseline with enough runs; rejected changes were reverted.
- [ ] Reported gains come from repeated measurements (median with interval), not one run; "no clear difference" is reported as such.
- [ ] The tests, linter and type checker pass; outputs match the baseline.
- [ ] The report lists what was tried, what worked, remaining bottlenecks and measurement limits; non-obvious optimizations are commented.

## Pitfalls

- **Optimizing without profiling**: spending time on code that does not matter.
- **Benchmarking a toy**: tiny inputs, empty database, warm caches, no network. The real bottleneck never shows up.
- **One run, or the first run**: noise, cold caches and CPU frequency changes. Use repeated runs and medians.
- **Profiling the profiler**: overhead skews small functions; confirm gains with timing.
- **Changing many things at once** and not knowing which helped (or which hurt).
- **Trading correctness for speed**: skipped validation, stale caches, swallowed errors. Tests first.
- **Premature caching**: caches add invalidation bugs and memory growth; fix the algorithm or the query first.
- **Micro-optimizations** (string concatenation tricks, manual loop unrolling) that gain nothing measurable and cost readability.
- **Ignoring I/O**: a CPU profile of a program that mostly waits shows nothing; look at wall time, queries and network calls.
- **Missing the big picture**: a 10x faster function that is called once per hour; or fixing the app when the database index is missing.
- **Comparing different machines or loads** (a laptop on battery vs. a CI server).

## Hand-offs

| Next | Load |
|---|---|
| capacity and latency under concurrency | `load-test` |
| a slow query or schema | `design-database` |
| tests before changing hot code | `write-tests` |
| restructure the code that is hot | `refactor-code` |
| a regression in production | `debug-production` |
| add monitoring for latency | `setup-monitoring` |
| review the optimization | `review-code` |
