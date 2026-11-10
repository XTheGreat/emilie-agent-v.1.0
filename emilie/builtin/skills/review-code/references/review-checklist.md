# Review checklist

Not every item applies to every change. Skim the headings, go deep where the change is. For each "no" or "unsure", write a finding or a question.

## 1. Intent and scope

- [ ] The change does what the description and issue ask, and nothing important beyond it.
- [ ] Unrelated edits (formatting churn, drive-by refactors, renamed files) are absent or split out.
- [ ] Acceptance criteria are each demonstrated (by a test, a screenshot, a run).
- [ ] The approach fits the problem; a simpler one was considered (or you can say why not).

## 2. Correctness

- [ ] Conditions and loops: off-by-one, inverted logic, wrong operator, wrong variable, missing `else`.
- [ ] Edge cases: empty, one, many, max, null/None, zero, negative, unicode, very long input, duplicates.
- [ ] Error paths: every call that can fail is handled (or deliberately propagates); no swallowed exceptions; failures do not leave half-done state.
- [ ] Resources are released on every path (files, connections, locks, transactions, temp files).
- [ ] State and ordering: initialization before use, idempotency of retried operations, ordering assumptions.
- [ ] Concurrency: shared mutable state, races, lock order and deadlocks, async calls awaited, thread-safety of caches and singletons.
- [ ] Time and numbers: time zones, DST, clock reads in logic, integer overflow, floating-point equality, rounding of money (use integers or decimals).
- [ ] Types and nullability: new `None`/`null` cases are handled; casts are justified.
- [ ] Behavior of changed shared code for all other callers (search the callers).

## 3. Security and privacy

- [ ] Input from outside (HTTP, files, env, CLI args, messages, database content from users) is validated and bounded before use.
- [ ] No injection: SQL parameterized; shell commands without string-built input; HTML/JS output encoded; paths normalized and confined (no `../` escape); no unsafe deserialization; no `eval`.
- [ ] Authentication and authorization on the server for every new endpoint or action, including object-level checks (can this user see this record?). Roles tested.
- [ ] Secrets: none in code, logs, URLs, error messages or tests; configuration read from the environment or a secret store.
- [ ] Personal data: minimal collection, not logged, encrypted where required, retention and deletion considered.
- [ ] Network: TLS verification on, timeouts set, redirects and SSRF considered when fetching user-supplied URLs.
- [ ] New dependencies: name is correct (typosquats), maintained, license acceptable, version pinned.
- [ ] Cryptography: standard libraries, no homemade schemes, strong algorithms, random from a secure source, no hard-coded keys or IVs.

## 4. Data, migrations and compatibility

- [ ] Schema changes are safe on a live system (no long locks, backfills batched, nullable-then-fill) and reversible; deployment order with code is clear.
- [ ] Public interfaces (function signatures, endpoints, CLI flags, events, file/serialization formats) stay compatible, or the break is intentional, flagged and versioned.
- [ ] Defaults did not change silently; configuration additions have sensible defaults and documentation.
- [ ] Existing data and old clients still work; stored values are validated when read back.

## 5. Tests

- [ ] New behavior has tests for the happy path, edges and failures; bug fixes include a test that fails without the fix.
- [ ] Tests assert behavior, are deterministic (no sleeps, real clock, network, order dependence) and fast.
- [ ] No test was skipped, loosened or deleted to make the suite pass; assertions were not removed.
- [ ] Mocks are limited to boundaries; the real logic is exercised.
- [ ] The suite, linter and type checker pass (ran or reported).

## 6. Performance and scale

- [ ] No I/O or queries inside loops (N+1); batching where it matters; indexes exist for new queries.
- [ ] No unbounded memory or result sets (pagination, streaming, limits); no quadratic behavior on large inputs.
- [ ] Caches have bounds, keys, invalidation and a stated staleness; cache misses are handled.
- [ ] Hot paths avoid needless allocation and serialization; expensive work is not repeated.
- [ ] Timeouts, retries (bounded, with backoff) and backpressure exist for remote calls.

## 7. Design and readability

- [ ] Names say what things are and do; functions are small and do one thing; nesting is shallow.
- [ ] Responsibilities are in the right module; dependencies point the right way; no new cycles.
- [ ] No duplication of an existing helper; no premature abstraction or dead options.
- [ ] Comments explain why (non-obvious decisions), not what; stale comments and commented-out code removed.
- [ ] Consistent with the codebase conventions (error handling, logging, structure, naming).

## 8. Operations

- [ ] Logging is useful and safe (levels, context ids, no secrets or personal data); new failure modes are observable (metrics, alerts).
- [ ] Configuration, feature flags, and rollout/rollback are described for risky changes.
- [ ] Background jobs, schedules and migrations are idempotent and safe to run twice.
- [ ] CI, build and deployment files changed in a way that keeps the safeguards.

## 9. Documentation

- [ ] README, usage docs, API docs, config examples, changelog and migration notes reflect the change.
- [ ] Public functions and tricky internals have accurate docstrings or comments.

## What to look for around the diff

- Callers and implementers of changed functions (`grep`), other places with the same pattern that should change too, tests that exercise the old behavior, code that parses what the change now writes, and documentation or scripts that mention old names.
- `git log -p` / `git blame` of the lines being edited: why were they written that way? A "weird" check often fixes a past incident.
