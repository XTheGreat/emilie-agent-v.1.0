# Debugging techniques

Pick the cheapest technique that cuts the search space in half. Commands are read-only unless noted.

## 1. Reproduction

- **Smallest trigger.** Remove steps, data and features until removing one more makes the bug vanish. The remainder is
  the reproduction.
- **Make it deterministic.** Fix random seeds, freeze or inject the clock, use fixed fixtures, disable concurrency
  (one worker, one thread), pin the data.
- **Move it into a test.** A failing unit or integration test is the best reproduction: repeatable, fast, and it becomes the
  regression test.
- **Same environment.** Use the reporter's versions (lockfile, runtime, OS). A container or a fresh virtual environment
  rules out "my machine is different".
- **Record and replay.** For API-driven bugs capture the request (`curl -v`, a saved HAR file, a logged payload) and replay it.
- **Cannot reproduce?** Compare environments one difference at a time; ask for the input and the logs; propose one targeted
  log line for the user to enable; say plainly that the cause is unconfirmed.

## 2. Bisecting history (when did it start?)

```
git bisect start
git bisect bad                 # the current, broken revision
git bisect good <old-good-ref> # a revision known to work (tag, release, date: git rev-list -n1 --before=2026-10-01 HEAD)
# then either test by hand and answer `git bisect good` / `git bisect bad`, or automate:
git bisect run <script>        # script exits 0 = good, 1..127 (except 125) = bad, 125 = cannot test this revision, skip it
git bisect reset               # ALWAYS finish with this to return to your branch
```
A test script, POSIX: `#!/bin/sh` then `pytest -q tests/test_orders.py::test_total`. PowerShell:
`pytest -q tests/test_orders.py::test_total; exit $LASTEXITCODE`.
Exit 125 when the build itself fails at that revision. Bisecting moves the working tree: do it on a clean tree or in a
worktree (`git worktree add ../bisect <bad-ref>`), and never with uncommitted work.

## 3. Shrinking the input (delta debugging)

Halve the failing input, test, keep whichever half still fails, repeat. For structured input (JSON, CSV, a request) remove
one field or one record at a time. For a long test, bisect the *steps*. The smallest failing input usually names the cause.

## 4. Bisecting configuration, dependencies, environment

- **Config and flags:** turn off half of the non-default settings, test, narrow down.
- **Dependencies:** diff the lockfiles between good and bad (`git diff <good> -- package-lock.json`, `poetry.lock`, `go.sum`,
  `Cargo.lock`); `pip freeze` on both machines; upgrade or downgrade the single suspect.
- **Environment:** compare OS, runtime versions, locale, time zone, environment variables (names, not secrets), file
  permissions, path length, case sensitivity.
- **Layers:** call the lower layer directly (skip the controller, skip the cache, use a stub for the network). The bug is in
  the layer where the behaviour first goes wrong.

## 5. Looking inside the running program

| Need | Tool |
|---|---|
| Python | `breakpoint()` / `python -m pdb`, `python -X faulthandler`, `-X dev`, `logging.basicConfig(level=DEBUG)` |
| Node | `node --inspect-brk`, `NODE_DEBUG=...`, Chrome DevTools, `--trace-warnings`, `--unhandled-rejections=strict` |
| Go | `dlv debug`, `go test -race`, `GOTRACEBACK=all`, `pprof` |
| Rust | `RUST_BACKTRACE=1` (or `full`), `RUST_LOG=debug`, `cargo test -- --nocapture`, `lldb` |
| Java / Kotlin | `jdb`, remote debug `-agentlib:jdwp`, `jstack <pid>` for hangs, `-XX:+HeapDumpOnOutOfMemoryError` |
| C / C++ | `gdb` / `lldb`, AddressSanitizer and UBSan (`-fsanitize=address,undefined`), `valgrind` |
| .NET | Visual Studio / `dotnet-dump`, `dotnet-trace` |
| Web front end | browser DevTools: Network tab (status, payload), Console, Sources breakpoints, Performance |
| HTTP | `curl -v`, `curl -i`, a proxy such as mitmproxy |
| System | Windows: Process Monitor, `netstat -ano`, Event Viewer. Linux: `strace -f`, `lsof`, `ss -tlnp`, `dmesg`, `journalctl` |
| Database | the slow-query log, `EXPLAIN`, the transaction isolation level, lock views |

**Temporary logging** (needs the user's OK): log at decision points, not everywhere; include the inputs and the branch taken;
add a correlation id; mark every added line with a distinctive prefix such as `DEBUGTMP` so it is easy to find and remove,
and list them in your report.

## 6. Bug classes: symptom, likely cause, how to confirm

| Symptom | Usual suspects | Confirm by |
|---|---|---|
| `None` / `undefined` / null error | missing check, optional data, lookup that failed silently, async value not ready | print the value at each hop; find where it was first absent |
| Off by one, missing last item | `<` vs `<=`, slice bounds, zero- vs one-based indexes, fence-post | test with sizes 0, 1, 2 |
| Works for small data, fails for big | memory, timeouts, quadratic loops, pagination limits, integer overflow | scale the input; profile |
| Wrong number, tiny differences | floating point, rounding mode, integer division, currency stored as float | print with full precision; use decimals in the test |
| Wrong date or "one day off" | time zones, daylight saving, UTC vs local, month boundaries, leap years | test across midnight and a DST change; print the timezone-aware value |
| Garbled text, crashes on some names | encoding (UTF-8 vs cp1252), normalization, string length vs bytes | test with non-ASCII and emoji; check file and DB encodings |
| Works on one machine, not another | versions, paths (`\` vs `/`), case sensitivity, line endings, locale, env vars, permissions | diff the environments |
| Intermittent, order dependent | race condition, shared mutable state, unawaited async, test pollution, clock | run 50 times; run alone vs in the suite; race detector; add a delay to widen the window |
| Stale or "old" results | cache, memoization, CDN, browser cache, stale build output, `.pyc`/`dist` | clear the cache; rebuild from clean; disable the cache for one run |
| Passes locally, fails in CI | missing env var, different version, parallelism, network access, timing, leftover state | compare the CI log with the local run line by line |
| Mutation surprise | mutable default argument, shared object, shallow copy, aliasing | print `id()` or the reference; copy deliberately |
| Resource exhaustion | leaked connections, file handles, threads, listeners; unbounded queues | watch the count grow (handles, memory) over time |
| Unexpected permission or auth failure | clock skew, expired token, wrong scope, redirect dropping the header | inspect the actual request (`curl -v`) |
| Slow only sometimes | cold cache, lock contention, GC, N+1 queries, retry storms | trace one slow request end to end |
| "Impossible" behaviour | you are not running the code you think (old build, wrong branch, a different file shadowing the module, a mock) | print the file path and version at runtime; check `git status` and the build output |

## 7. Intermittent and race conditions

1. Make it fail more often: loop it (`for i in $(seq 200); do ...; done`), run in parallel, add CPU load, add random
   delays, shrink timeouts.
2. Turn on the detectors: Go `-race`, ThreadSanitizer, Java `-XX` concurrency checks, Python `-X dev` and `faulthandler`.
3. List the shared state and the ordering assumptions between tasks; check each for a missing lock, a missing `await`, or a
   check-then-act gap.
4. Prove it: force the bad interleaving with a deliberate pause at the suspected point and show the failure becomes
   deterministic.
5. A fix that "reduces the frequency" is not a fix.

## 8. When the evidence runs out

State what you ruled out and how. List the remaining hypotheses with the single most informative experiment for each.
Say what you need from the user (an input, a log, access to run something) and why. An honest "not yet known" with a next
step is worth more than a confident guess.
