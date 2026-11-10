# Measurement method and tools

## The loop

```
define metric + target  ->  baseline (many runs)  ->  profile  ->  hypothesis  ->  one change  ->  tests  ->  measure (compare)  ->  keep or revert  ->  re-profile
```

## Taking a trustworthy measurement

- **Same conditions**: same machine, power mode, data, versions, and a quiet system (close heavy apps; plug in laptops). Note the environment in the report.
- **Warm-up**: discard the first run(s): file cache, JIT, connection pools, lazy imports.
- **Repeat**: at least 10 runs for fast commands; use the **median** and the spread (stdev, p90). Large variance means more runs or a quieter machine, not a conclusion.
- **Alternate A and B** when comparing (ABAB...) so drift (thermal throttling, background jobs) hits both equally. `perf.py compare` does this and reports a bootstrap confidence interval.
- **Wall vs CPU time**: wall time includes waiting (I/O, locks, sleep); CPU time excludes it. If wall >> CPU, the program is waiting.
- **Throughput vs latency**: report both when relevant; percentiles (p50/p95/p99) for latency.
- **Use realistic data volume**: algorithmic problems show up only at scale. Try n, 2n, 4n and see how time grows (linear, n log n, quadratic).
- **Do not trust one profile**: profile twice; check that the top items are stable.

## Reading profiles

- **Own (self) time** of a function: time spent in the function body. The top of this list is where the CPU actually goes.
- **Cumulative time**: includes callees; useful to find expensive subtrees and the call path from your code to a slow library call.
- **Call counts**: millions of calls to a cheap function = a loop that should be vectorized, batched or removed.
- **Flame graphs** show stacks by width = time. Look for wide plateaus.
- **Wait time** (I/O, locks, GC) is invisible to a CPU profiler: compare wall vs CPU; use tracing, query logs, network timing.

## Tools by environment

| Area | Tools | Typical use |
|---|---|---|
| Python CPU | `cProfile` + `pstats` (stdlib), `py-spy` (sampling, no code change), `pyinstrument`, `scalene`, `line_profiler` | `python -m cProfile -o out.prof script.py`; `py-spy record -o flame.svg -- python script.py` |
| Python memory | `tracemalloc` (stdlib), `memray`, `objgraph`, `pympler` | peak and top allocation lines; leaks via snapshots diff |
| Node.js | `node --cpu-prof`, `--heap-prof`, `--inspect` + Chrome DevTools, `clinic`, `0x`, `perf_hooks` | flame graphs, event-loop delay, heap snapshots |
| Go | `pprof` (cpu, heap, goroutine, mutex, block), `go test -bench . -benchmem`, `go tool trace` | `go test -bench . -cpuprofile cpu.out` |
| JVM | JFR, async-profiler, VisualVM, `jcmd`, GC logs | flame graphs, allocation profiling, GC pauses |
| Rust / C / C++ | `cargo flamegraph`, `perf`, `criterion`, valgrind/callgrind, heaptrack | `perf record -g`; `cargo bench` |
| .NET | `dotnet-trace`, `dotnet-counters`, PerfView, BenchmarkDotNet | |
| Browser front end | DevTools Performance and Memory panels, Lighthouse, WebPageTest, Core Web Vitals (LCP, INP, CLS), bundle analyzers (source-map-explorer, webpack-bundle-analyzer) | long tasks, layout thrash, large bundles, render blocking resources |
| Databases | `EXPLAIN (ANALYZE, BUFFERS)`, slow query log, `pg_stat_statements`, index usage stats, connection and lock views | find sequential scans, missing indexes, N+1 patterns |
| System | `top/htop`, `vmstat`, `iostat`, `strace -c`/`dtruss`, `perf stat`, Windows Performance Monitor / Resource Monitor | CPU, memory, disk, syscalls |
| Network / HTTP | browser network tab, `curl -w` timing, tracing (OpenTelemetry) | DNS, connect, TLS, TTFB, payload size |

Install nothing without asking; use what exists.

## Quick checks before deep profiling

1. Is the slow path doing I/O? Count queries, file reads, network calls (log them). Most "slow code" is too many round trips.
2. Does time grow with input size? Time n, 2n, 4n: doubling that quadruples time = quadratic.
3. Is it the first call only (cold start, imports, cache fill)? Measure the second call.
4. Is the machine swapping, throttled or busy? Check CPU, memory, disk activity.
5. Did it get slow recently? `git bisect` with the timing command as the test finds the commit.

## Python-specific quick wins to check

- `x in list` inside loops: use a `set`/`dict`.
- String building in loops: `''.join(parts)`.
- Repeated attribute lookups, regex compiled in a loop (`re.compile` once), repeated parsing of the same data.
- `list(...)` copies, `sorted` inside loops, `+` on lists in loops.
- Reading whole files into memory: iterate lines or chunks; generators instead of lists.
- Pure-Python numeric loops: use NumPy/vectorization or built-ins (`sum`, `min`, `sorted(key=...)`).
- Disk and network per item: batch (bulk insert, `executemany`, one request with many ids).
- Import time: heavy imports at module top; lazy-import rarely used ones (`python -X importtime -c "import app"`).

## `git bisect` for regressions

```
git bisect start; git bisect bad HEAD; git bisect good <known-good>
git bisect run sh -c 'test $(python timing_script.py) -lt 2000'      # exits 0 when fast enough
```
Use only with a deterministic, fast pass/fail script and a clean working tree.

## Report template

```
Performance report - <scenario> - <date>
Metric and target: ...        Environment: <hardware, OS, versions, data size>
Baseline: median 4.20s (stdev 0.08, n=10)
Profile: 72% of time in dedupe() (quadratic membership test), 18% in build(), rest negligible.
Changes
  1. dedupe uses a set: 4.20s -> 1.35s (median, n=15, 95% CI -2.9..-2.8s)   kept
  2. build() uses a generator: no clear difference (CI includes 0)             reverted
Final: 1.35s (3.1x faster). Target 2s: met.
Correctness: tests pass (n/n); output of the scenario identical to baseline.
Remaining: build() 40% of the rest; would need streaming the output. Not measured: memory, behaviour under concurrency.
```
