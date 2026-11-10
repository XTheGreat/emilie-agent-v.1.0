# Common causes and fixes

Pick from here **after** a profile points at the cause. Each entry: symptom, cause, fix, and what to verify.

## Algorithms and data structures

| Symptom | Cause | Fix | Verify |
|---|---|---|---|
| Time grows much faster than input (4x when input doubles) | quadratic loop; membership test on a list; nested loops over the same collection; repeated sorting | use a hash set/dict, sort once, index by key, a better algorithm (two pointers, heap, binary search) | time at n, 2n, 4n |
| Same result computed repeatedly | no memoization, recomputation in loops | compute once and reuse, memoize pure functions with bounded caches | correctness, cache size |
| Large sorts or scans for top-k | full sort when only k needed | heap / partial sort / index | |
| String work in loops | concatenation creating copies; regex recompiled | join parts; compile once; avoid regex for simple checks | |

## I/O and round trips

| Symptom | Cause | Fix | Verify |
|---|---|---|---|
| Many small queries (N+1) | loading related rows one at a time in a loop | join, `IN` query, eager loading (`select_related`, `joinedload`), batching | query count per request |
| Many small writes | insert/update in loops, commit per row | bulk insert, `executemany`, transactions, batching | durability needs |
| Slow query | missing index, full scan, function on indexed column, `SELECT *`, `OFFSET` pagination deep | `EXPLAIN ANALYZE`; add composite index in the right order; select needed columns; keyset pagination | plan before/after, write cost |
| Many HTTP calls | sequential calls to a service, no connection reuse | batch endpoints, concurrency with limits, keep-alive/session reuse, caching | rate limits, error handling |
| Reading/writing whole files | loading the file into memory | stream by line/chunk; memory-map | memory peak |
| Chatty serialization | huge JSON, repeated encode/decode | smaller payloads, pagination, binary formats where justified, field selection | |

## Caching

- Cache the expensive, pure or slowly changing things: results, rendered fragments, compiled regexes/templates, configuration, DNS/connection pools.
- Always define: **key**, **TTL**, **size bound**, **invalidation**, and what happens on a miss or stale read. Stampede protection for hot keys.
- Prefer fixing the slow thing over hiding it behind a cache. Cache bugs are hard bugs.
- Measure hit rate; a cache that rarely hits is cost without benefit.

## Memory

| Symptom | Cause | Fix |
|---|---|---|
| Peak memory is a multiple of data size | copies (`list()`, slicing, concatenation, pandas intermediate frames) | iterate lazily, generators, in-place operations, chunked processing |
| Memory grows without bound | unbounded caches, global lists, listeners/closures retained, large objects in sessions | bounded LRU, weak references, explicit cleanup, find retainers with snapshots |
| Heavy per-object overhead | millions of small objects/dicts | `__slots__`/dataclasses with slots, arrays/NumPy, tuples, struct of arrays |
| GC pauses | allocation churn | reuse buffers, reduce temporary objects, tune GC after measuring |

## CPU-bound work

- Vectorize numeric loops (NumPy, pandas operations, SQL aggregates) instead of Python loops.
- Use the standard library built-ins implemented in C (`sum`, `sorted`, `str.join`, `itertools`, `collections`).
- Move hot loops to a compiled extension (Cython, Rust/pyo3, C) or a faster runtime only when profiling shows a small hot spot and the gain justifies the complexity.
- Parallelism: processes for CPU-bound Python (GIL), threads/async for I/O-bound; measure the overhead and scaling; mind shared state.

## Concurrency and waiting

- Overlap independent I/O (async, thread pool) with limits; avoid holding locks during I/O.
- Contention: shrink critical sections, shard locks, use lock-free or immutable structures, queue and batch.
- Timeouts and retries with backoff so that slow dependencies do not pile up requests.

## Startup time

- Lazy-import heavy modules (`python -X importtime`), avoid work at import, defer loading data and plugins, cache compiled artifacts, trim dependencies, avoid scanning the file system on start.

## Web front end

| Problem | Fix |
|---|---|
| Large JavaScript bundles | code splitting, tree-shaking, remove unused dependencies, lazy-load routes and widgets, analyze with a bundle visualizer |
| Slow Largest Contentful Paint | optimize hero image (size, format, `fetchpriority`), preload critical assets, server-render or cache HTML, reduce render-blocking CSS/JS |
| Poor interaction latency (INP) | break up long tasks, debounce handlers, move work to workers, avoid synchronous layout (read/write batching), virtualize long lists |
| Layout shift (CLS) | reserve space (width/height or aspect-ratio), avoid late-injected content above the fold |
| Too many requests | HTTP/2, bundling where it helps, caching headers, CDN, image sprites/icon fonts replaced by inline SVG |
| Heavy images/fonts | responsive `srcset`, modern formats, lazy loading below the fold, subset fonts with `font-display: swap` |
| Re-render storms (React/Vue) | memoization where profiled, stable props, state colocated, avoid giant context updates |

Always verify with Lighthouse or the Performance panel on a throttled mid-range device.

## Databases (beyond queries)

- Connection pooling sized to the database's capacity; avoid opening a connection per request.
- Right-size result sets; paginate; avoid `COUNT(*)` on huge tables per request (use approximations or cached counts).
- Partition or archive old data; vacuum/analyze statistics; check lock waits and long transactions.
- Read replicas for read-heavy workloads with attention to replication lag.

## Anti-patterns (do not)

- Optimizing without a profile; micro-optimizing the cold path.
- Replacing clear code with cryptic code for a gain under measurement noise.
- Adding a cache before understanding why the work is slow.
- Parallelizing code that is waiting on one shared bottleneck (database, lock).
- Removing validation, logging or safety checks for speed without agreement.
- Comparing results from different machines, data, or load conditions.
- Declaring victory without re-running the tests and comparing outputs.
