# Root causes of flaky tests

For each cause: the symptom, how to confirm it, and the usual place to look.

| Cause | Typical symptom | How to confirm | Look at |
|---|---|---|---|
| **Asynchronous waiting** | Fails when the machine is slow or loaded; `sleep(n)` or fixed timeouts in the test; "element not found", "expected X got undefined", empty results | Add an artificial delay in the code under test; run under CPU load; run with `-n 100` | async code, background jobs, UI rendering, message queues, `setTimeout`, polling |
| **Order dependence / shared state** | Passes alone, fails in the suite (or the reverse); fails after a specific other test; fails with random or reversed order | Run the test alone; run in random/reversed order; bisect the set of preceding tests | module/class level variables, singletons, caches, class-level fixtures, global config, mocks not reset, database rows left behind |
| **Leaked process-wide state** | Later tests see changed environment, working directory, locale, time zone, logging level, monkeypatches | Print the state at the start of the failing test; compare when run alone | `os.environ`, `chdir`, `locale`, `TZ`, `sys.modules`, patched functions that are not undone |
| **Time** | Fails at midnight, month end, year end, DST change, weekend, or on a different time zone; "expired" or "in the future" checks | Set the clock/zone to the suspicious value (freeze time, `TZ=Asia/Jakarta`, `TZ=UTC`, Feb 29) | `now()`, date arithmetic, expiry/TTL, scheduled jobs, `datetime` without zone, comparisons of timestamps made in two calls |
| **Randomness** | Fails with a probability related to the range; different data per run | Seed fixed: does it fail only for some seeds? Log the seed on failure | random generators, UUIDs, shuffles, hash ordering (`PYTHONHASHSEED`), `Math.random`, property tests with a seed not printed |
| **Network and external services** | Fails on timeouts, rate limits, DNS errors, remote data changes; fails offline | Disconnect the network or block sockets; replay with latency injected | HTTP clients, databases on a shared host, third-party sandboxes, `localhost` services not started |
| **Concurrency (in the test or the product)** | Rare failures, different each time; deadlock or hang; data race reports; wrong totals | Run with `-race` (Go), thread sanitizers, `-count=1000`; add yields/delays at suspected points | threads, locks, async tasks not awaited, shared mutable objects, parallel test workers sharing a resource, non-atomic counters |
| **Resource leaks and ports** | "Address already in use", "too many open files", slows over time, fails late in the suite | Count open files/sockets/threads at start and end of each test; run the file twice in one process | unclosed files/connections, servers not stopped, fixed ports, temp files |
| **Test data collisions** | Unique-constraint errors, wrong counts, "already exists", interference between parallel runs | Run two copies in parallel; look for fixed ids, emails, names, file names | fixtures creating the same key, shared database, shared bucket/queue/topic |
| **Environment differences** | Only in CI or on one OS/machine: different CPU count, memory, Python/Node version, locale, file system case/line endings, path separators | Reproduce in a container with the CI image and CPU limit; compare versions | Windows vs Linux paths, case-insensitive file systems, encodings, `\r\n`, locale-dependent sorting/formatting, CPU-bound timing |
| **Floating point and rounding** | Off by 1e-16; passes on one machine, fails on another | Print with full precision; run on the other platform | exact `==` on floats, summation order, parallel reductions |
| **Unordered collections** | Different order each run; passes "usually" | Run with `PYTHONHASHSEED=random`; sort in the test | sets, dict/map iteration in some languages, directory listing, `SELECT` without `ORDER BY`, parallel results arriving out of order |
| **Test infrastructure** | Browser/UI tests fail on animations, focus, viewport size, download timing; docker/DB start races | Record video/screenshot/trace; run headed vs headless; add a readiness check | fixed waits for services, animations, third-party scripts, port readiness, cold caches |

## How to isolate (change one factor at a time)

1. **Alone vs. in suite**: run just that test (`pytest path::name`, `-t "name"`, `-run Name`). Different result → order/shared state.
2. **Order**: shuffle (`pytest -p randomly`, `--randomize`, `jest --randomize`, `go test -shuffle=on`), reverse, or run only the tests before it, then bisect that list until the culprit appears.
3. **Parallel / load**: run two instances at once, or with `stress`/CPU-burning loops, or limit to one CPU. Failure appears → timing or shared resources.
4. **Clock and zone**: freeze or shift the date; set `TZ` to a zone with DST and to UTC; try a midnight run.
5. **Seeds**: log the seed in the test setup; rerun with the failing seed (`--randomly-seed=N`, `PYTHONHASHSEED=N`, the property-test seed).
6. **Network off**: block sockets (a guard fixture) to find hidden calls.
7. **Repeat**: `-n 200` of a single test makes a 1-in-100 failure likely to appear.
8. **Evidence**: log timestamps, thread ids, resource counts; keep the artifacts (logs, screenshots, DB dump) of failing CI runs.

## Estimating how many runs you need

If a test fails with probability *p* per run, the chance that *n* clean runs happen is (1 - p)^n. To be 95% sure a *p* = 5% failure is gone you need about 60 runs
(3 / p). For 1%, about 300. Run under the same stress that made it fail. State the numbers in your report.

## Is it the test or the product?

- A failure that shows wrong data, a lost update, a deadlock or a crash under concurrency is likely a **product** bug: the test is right.
- A failure that depends on a sleep, on leftovers from another test or on the wall clock is a **test** bug.
- If a human could trigger the same thing in production by timing, treat it as a product bug and fix the code.
