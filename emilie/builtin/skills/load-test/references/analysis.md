# Reading load test results

## What to look at, in order

1. **Errors first.** Rate and kinds (timeouts, connection resets and refusals, 5xx, 429, 4xx caused by test data). Fast errors improve latency charts; never read latency without them.
2. **Throughput vs. offered load.** At each level did the system serve what was offered? If achieved < offered, it saturated (or the generator did).
3. **Latency percentiles per level.** p50, p95, p99, max. Compare with the objective. The tail matters more than the middle.
4. **The knee.** The load level at which latency starts rising much faster than throughput. Below it the system has capacity; past it requests queue.
5. **Over time.** Is latency flat in steady state, or creeping up (leak, filling cache, growing queue)? Do errors come in bursts (GC, restarts, deploys, autoscaling)?
6. **Server metrics.** Which resource saturated first at the knee: CPU, memory, database, connection pool, lock contention, network, disk, downstream service?

## Sanity checks

- **Little's law:** concurrency = throughput x average latency. For a closed loop with 20 workers and 50 ms latency, expect 400 req/s. If the numbers disagree, something is wrong (think time, errors,
  a slow client).
- **Generator health:** client CPU above about 70%, long local queueing or one-core pinning means the load generator limits the test. Reduce rate, use a faster tool, or distribute.
- **Coordinated omission:** in a closed loop, slow responses reduce the number of measured requests exactly when the server is worst. For capacity use a constant arrival rate and measure from the scheduled time.
- **Warm-up and caches:** compare the first minute with the rest; a cold cache or JIT inflates early latency, and a hot single key flatters results.
- **Variance:** repeat; if the same level differs by more than 10 to 15%, find the noise (neighbors, GC, autoscaling) before comparing changes.
- **Environment parity:** instance sizes, number of nodes, database size and configuration, TLS, auth, third-party stubs. Say where the test differs from production.

## Typical bottlenecks and signs

| Bottleneck | Signs | Next step |
|---|---|---|
| CPU-bound application | CPU near 100% on app nodes, latency grows with load, throughput flat | profile (`profile-performance`), cache, optimize hot paths, scale out |
| Database | DB CPU or I/O high, long queries, lock waits, connection pool exhausted, app idle waiting | slow query log, indexes, N+1 queries, pooling, read replicas, caching |
| Connection or thread pool exhausted | latency jumps at a sharp load, errors like "timeout waiting for connection", low CPU | size pools, shorten holds, make calls async, fix leaks |
| Memory / GC | latency spikes in pulses, rising memory, long GC pauses, OOM kills | heap profile, reduce allocation, tune GC, fix leaks |
| Lock contention / single-threaded section | CPU not saturated, throughput flat, latency grows | find the lock, shard or remove it, batch |
| Downstream service | time spent in outbound calls; errors correlate with its latency | timeouts, bulkheads, caching, circuit breakers, scale or fix the dependency |
| Network or load balancer | bandwidth near limit, resets, 502/503/504 from the proxy | payload size, compression, keep-alive, balancer limits |
| Disk | high I/O wait, slow writes, logs or temp files | async logging, faster storage, batching |
| Rate limiting (429) | many 429s | raise limits for the test or test under the limit; verify clients back off |
| Autoscaling lag | errors during ramp, fine afterwards | pre-warm, faster scaling rules, ramp more gently |

## Capacity statement

State capacity as "the highest rate that met the objective", for example "up to 320 req/s with p95 under 300 ms and under 0.1% errors on 2 x 4 vCPU nodes with the production-sized
database; at 400 req/s p95 reached 900 ms and the connection pool saturated". Add headroom: capacity divided by expected peak.

## How to explain results

- Lead with the verdict (pass or fail against each target) and the capacity number.
- Name the bottleneck and show the one or two charts or tables that prove it.
- Give ranked fixes with expected effect and effort; propose a retest plan.
- List limitations: environment differences, what was not tested (long soak, failure modes, third-party limits).

## Report template

```
Load test report - <service/endpoint> - <date>

Goal and targets
  Question: ...
  Targets: p95 < ... ms, p99 < ... ms, errors < ...%, throughput ... req/s at peak   (source: given / assumed)

Environment
  Target: <staging/prod-like>, <instances, sizes>, <db size>, <versions>; generator: <tool + version, machine, region>

Workload
  Mix: ...   Data variation: ...   Think time: ...   Model: open/closed   Warm-up: ... s

Results
  Level (req/s or users) | achieved | p50 | p95 | p99 | max | errors | notes
  ...

Observations (server side)
  CPU, memory, DB, pools, GC, logs at each level; the knee at ...; first saturated resource ...

Verdict
  Meets target: yes/no for each; capacity: ...; headroom: ...x

Bottleneck and evidence
  ...

Recommendations (ranked)  1. ...  2. ...  3. ...

Limits of this test
  ...
Commands run
  ...
```
