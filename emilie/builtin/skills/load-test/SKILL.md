---
name: load-test
phase: cek-mutu
description: Measure how a service behaves under load, safely - define targets (latency percentiles, throughput, error rate), pick the test type (smoke, load, stress, spike, soak), model realistic traffic, run it against a system you own, watch the server, and interpret saturation and the bottleneck into a verdict. Includes a stdlib HTTP load generator that refuses foreign hosts by default. Not for slow code inside a program (profile-performance) or functional tests (write-tests). Triggers - "load test", "stress test", "performance test", "how many requests", "capacity", "benchmark the api", "can it handle", "requests per second", "soak test".
---

# Load test

**Goal:** answer a specific question about capacity ("can this API serve 200 requests per second with p95 under 300 ms?") with measurements
you can trust, and say what the limit and its cause are.

## Ground rules

1. **Only systems you own, or have written permission to test.** Load against someone else's service is an attack, and against shared or
   third-party APIs it costs them money. The bundled generator refuses non-local hosts unless `--allow-remote` is given; use that flag only
   with the owner's explicit permission, and never on a vendor's production API.
2. **Not production without approval.** Prefer a staging environment that matches production (same instance size, config, data volume, TLS,
   caches, dependencies). If the user insists on production, agree on time window, ramp, abort criteria and who watches, and start tiny.
3. **A question before a test.** Write the target: expected traffic mix and rate, latency objective (percentile, not average), allowed error rate,
   and what "pass" means. Without a target the numbers have no meaning.
4. **Realistic workload.** A single hot URL with no data variation measures the cache, not the system. Mix endpoints in realistic proportions, vary ids,
   use realistic payload sizes, include authentication, think time and the slow operations (search, report, upload).
5. **Warm up, then measure.** Discard the first seconds (connection setup, JIT, caches). Run long enough for steady state (at least a minute for a
   rate; much longer for soak tests).
6. **Percentiles, not averages.** Report p50, p95, p99 and max, plus errors and throughput over time. Averages hide the tail users feel.
7. **Watch both sides.** Record client health (CPU, network) and server metrics (CPU, memory, connections, queue depth, database time, GC, errors in logs).
   A saturated load generator produces false results.
8. **Ramp up, stop on harm.** Increase load in steps; stop the test if error rates or latencies explode, if something outside the test is affected, or if the
   owner says stop. Never run unbounded loops; keep duration and worker caps.
9. **Isolate effects.** Change one thing between runs (a config, an index, a version) and repeat each run at least twice to see the noise.
10. **No data damage.** Load tests that write must use test accounts and disposable data; clean up afterwards. Do not trigger real payments, emails or SMS.
11. **Report honestly.** State exactly what was run (commands, versions, environment), what the limits of the method are, and anything not measured. Never present
    a number from a saturated generator, a cold cache or a toy environment as production capacity.

## Procedure

### Step 1 - Define the goal and the target

Ask or infer, and write down: the question; the endpoint(s) or journey; the expected peak load now and in the next 6 to 12 months (requests per second, concurrent
users, or events per minute, from real analytics if available); the latency objective (for example p95 under 300 ms, p99 under 1 s); the error budget (for example under 0.1%); the
environment to test; the data volume it must run against; the time window. If the user cannot provide the load numbers, derive them (daily active users times actions per user
divided by seconds in the busy hour, times a peak factor of 2 to 5) and mark them **Assumed**.

### Step 2 - Choose the test type

Use `references/test-types.md`: **smoke** (does it work at all under 1 to 2 users), **load** (expected peak held for a while), **stress** (above peak, to find the breaking point and
how it fails), **spike** (sudden jump and recovery), **soak** (hours at moderate load for leaks), **breakpoint** (ramp until a threshold fails). Start with a smoke test, then a load
test at the expected peak, then stress if you need the limit.

### Step 3 - Prepare the target and the workload

Confirm the target environment and that the user owns it. Check that monitoring is on (server CPU, memory, database, logs) so you can read it during the run. Prepare test data and
accounts. Write the request mix (method, path, headers, body, relative weight). For a simple endpoint use the bundled generator; for multi-step journeys, scripted scenarios, ramping
profiles or distributed load, use a dedicated tool (`references/tools.md`: k6, wrk/wrk2, hey, vegeta, Locust, Gatling, JMeter, Artillery) if it is installed and allowed, and tell
the user what you are about to install before installing anything.

### Step 4 - Run: smoke first, then step up

```
python "<this skill's directory>/scripts/loadtest.py" URL -c 2 -d 10                       # smoke
python "<this skill's directory>/scripts/loadtest.py" URL -c 20 -d 60 --warmup 10 --max-p95-ms 300 --max-error-rate 1     # closed loop: 20 concurrent users
python "<this skill's directory>/scripts/loadtest.py" URL --rps 200 -c 50 -d 120 --warmup 10                              # open loop: a fixed arrival rate
```

Closed loop shows what N concurrent clients get; **open loop** (`--rps`) answers "can it take N requests per second" and measures latency from the intended start, so a slow
server cannot hide queueing. Options: `-X`, `-H`, `--data`, `--ramp`, `--timeout`, `--json`, `--count-4xx`. Exit code 1 means a threshold failed or every request failed; 2 means
refusal or bad arguments. Repeat each level (for example 50, 100, 200, 400 req/s) with a pause between, and keep the output of each run.

### Step 5 - Observe the system while it runs

Record server-side numbers at each level (CPU per core, memory, open connections, thread/worker pool use, queue length, database CPU and slow queries, cache hit rate, GC pauses, disk and network)
and the application's own error logs. Note when latency starts to rise (the knee), when errors start, and which resource saturated first. If the client CPU is above about 70%, the generator is
the limit: reduce the rate, use more machines, or use a lighter tool.

### Step 6 - Interpret

Use `references/analysis.md`: compare results with the target; find the **knee** where latency rises faster than throughput; check Little's law (concurrency = throughput x latency) for
consistency; identify the bottleneck by the first saturated resource (CPU, database, connection pool, lock, network, downstream service); separate queueing delay from service time;
check error types (timeouts, resets, 5xx, 429); examine the tail (p99, max) and its causes (GC, cold paths, retries, noisy neighbors). Compute headroom against the expected peak and say what
the limit is in business terms.

### Step 7 - Recommend and (if asked) retest

State the verdict first (pass or fail against each target), the measured capacity (the highest rate that still met the objective), the bottleneck with the evidence, and the cheapest fixes in
order (caching, query or index fixes, connection pool sizes, async work, scaling out/up), with expected impact. After a change, rerun the same test and compare. For code-level causes,
hand off to `profile-performance`.

### Step 8 - Report

Use `references/analysis.md` (report template): goal and target, environment, workload, commands and versions, results table per level (rate, p50/p95/p99, errors), the graph or per-second table,
server observations, bottleneck, verdict, headroom, risks and what was not tested. Mention measurement limits and cleanup done.

## Definition of done

- [ ] The question, targets (percentile latency, throughput, error budget) and environment are written down; ownership and permission are confirmed.
- [ ] The workload is realistic or its simplifications are stated; a warm-up was excluded.
- [ ] A smoke run came first, then stepped load levels; every run's command and output were kept.
- [ ] Server-side metrics and client health were checked; the generator was not the bottleneck (or that is stated).
- [ ] Results use percentiles and show errors and throughput over time, with the knee and the bottleneck identified from evidence.
- [ ] Each level was repeated to see variance, or the lack of repeats is stated.
- [ ] The verdict compares with the targets and states headroom and the capacity limit; recommendations are ranked.
- [ ] No third-party system was loaded; test data was disposable and cleaned up.

## Pitfalls

- **Testing someone else's system** or a shared dependency. Fake or isolate third parties.
- **Averages.** A 120 ms average can hide a 4 s p99.
- **Coordinated omission.** A closed-loop client slows down when the server does, so the worst delays are never recorded. Use a fixed arrival rate to test capacity.
- **Cold or toy environment.** Empty database, tiny dataset, no TLS, no auth, debug mode: the result does not describe production.
- **Saturated generator.** The client is the bottleneck; the server looked fine because it was never loaded.
- **Single URL, no variation**: measures the cache. Randomize ids and mix endpoints.
- **Ignoring errors.** Fast 500s look great in latency charts. Always report errors beside latency.
- **One run, no repeats.** Noise (neighbors, GC, caches) can be 10 to 30%.
- **No server metrics.** You know it is slow but not why.
- **Load tests that mutate production data** or trigger real side effects.
- **Testing only the happy rate.** Capacity without a stress or spike test hides how it fails (graceful degradation or collapse).

## Hand-offs

| Next | Load |
|---|---|
| find the slow code or query | `profile-performance` |
| monitoring and alerts | `setup-monitoring` |
| production problem | `debug-production` |
| architecture changes for scale | `design-architecture` |
| database and indexes | `design-database` |
| add the test to CI | `setup-ci-cd` |
| record the decision | `write-adr` |
