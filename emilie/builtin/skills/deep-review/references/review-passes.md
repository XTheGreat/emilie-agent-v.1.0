# Review passes

Each pass has one question. Do them separately; write down what you checked, even when you found nothing, so the report can say what was covered.

## Brief for a sub-agent (use with the `tasks` tool, one per lens)

```
You are reviewing a change for ONE concern: <LENS>. Read only; change nothing.
Change: <range or files>. Intent: <one or two sentences>. Impact map: <paste the key lines of change_impact.py>.
Read the changed code in full, its callers, and its tests. Look for defects of this kind only: <checklist for the lens>.
Return up to 8 candidates. For each: file:line, a concrete scenario (inputs/state/timing), the consequence, the evidence (what you read or ran), and your confidence
(verified / likely / suspected). Do not report style issues or pre-existing problems unrelated to the change. If nothing is found, say what you checked.
```

## 1. Correctness and logic

- Trace the main path with a concrete example, then the edges: empty, one, many, max, boundary +/-1, null, duplicate, unicode, very large, negative.
- Each branch: is the condition right (operator, negation, short-circuit order)? Is the else case handled?
- Error paths: what does each failure do to state? Is cleanup guaranteed? Are exceptions swallowed or converted wrongly?
- State machines and ordering: legal transitions only; repeated calls (idempotency); calls out of order; re-entrancy.
- Numbers and time: overflow, precision, rounding of money, time zones, DST, clock changes, expiry arithmetic.
- Resource lifetime: files, sockets, locks, transactions, temp files, subprocesses closed on every path.
- Assumptions about callers: nullability, units, ranges, who owns and may mutate shared objects.

## 2. Security and privacy

- Every new entry point (endpoint, message handler, CLI arg, file import, webhook): who may call it? Authenticated? Authorized for *this object*?
- Untrusted input flowing to sinks: SQL, shell, filesystem paths, templates/HTML, deserialization, regex (ReDoS), URLs fetched by the server (SSRF), redirects, file uploads (type, size, path).
- Secrets and tokens: not logged, not in URLs or errors, not in client bundles; rotation and scope.
- Data exposure: fields returned that should not be, verbose errors, logs with personal data, caches shared across users/tenants.
- Session and CSRF/CORS: cookies flags, token handling, origin checks, state-changing GETs.
- Crypto: standard primitives, secure randomness, constant-time comparison, key management.
- Dependencies: new packages, versions, install scripts, typosquats.
- Abuse: rate limits, resource exhaustion, enumeration, replay.

## 3. Data and migrations

- Does the migration run safely on production-size tables (locks, duration, batching)? Is it idempotent and resumable? Are there backfills mixed with schema changes?
- Order of deployment: can old code run against the new schema and new code against the old (during rollout and rollback)?
- Constraints and defaults: new NOT NULL on existing rows, unique constraints with existing duplicates, foreign keys with orphans, type changes that truncate.
- Is data destroyed or irreversibly transformed? Is there a backup/restore path and a verification query?
- Data written by the new code readable by old code and by other services, reports and exports.
- Transactions and consistency across tables/services; money and counters updated atomically.

## 4. Compatibility and contracts

- Changed signatures, return types, error types, exceptions, status codes, field names, ordering, pagination, defaults, units, formats.
- Who else consumes it (other services, mobile apps, scripts, plugins, saved files)? Search the repo and ask about external consumers.
- Versioning and deprecation handled? Feature flags default-safe?
- Behavior for old clients, old stored data, old configuration, missing optional fields.

## 5. Concurrency and failure

- Shared mutable state, caches, singletons, global config; lock scope and ordering; read-modify-write without atomicity; double submit.
- Async: unawaited tasks, fire-and-forget errors, cancellation, timeouts, backpressure, retries that duplicate side effects, at-least-once delivery and idempotency keys.
- Partial failure: the process crashes between two writes; one of two services is down; the third retry succeeds after the first partially did.
- Timeouts everywhere a network or lock is involved; retry storms; thundering herd on cache expiry.
- Startup, shutdown and deploy: in-flight requests, migrations running while old pods serve.

## 6. Performance and scale

- Complexity with realistic data sizes; nested loops over big collections; repeated work in loops.
- Queries in loops (N+1), missing indexes for new filters/sorts, unbounded result sets, large `IN` lists, full-table scans.
- Memory: loading whole files/results, unbounded caches or queues, leaks through listeners/closures.
- Locks and contention on hot rows/keys; serialization of parallel work.
- External calls on the request path; payload sizes; chatty protocols.
- Back-of-envelope: rate x cost per operation versus capacity; ask for a load test (`load-test`) if unclear.

## 7. Tests

- Does a test fail without the change (new behavior) or with a broken change (mutation by hand)? Run one or two to see.
- Cases for each risk found in passes 1 to 6; failure and concurrency paths; migration test on a copy; compatibility tests with old data.
- Tests removed, skipped, weakened or made order/time dependent in this change.
- Mocks hiding the real integration; fixtures that always pass.

## 8. Operations and rollout

- Can it be turned off without a deploy (flag)? Is the default safe? Is rollout staged?
- How will you know it is broken: logs, metrics, alerts, dashboards, error budgets, synthetic checks; do new failure modes have signals?
- Rollback: redeploy the old version safely? Data compatibility? Any irreversible step (dropped column, sent emails, charged cards)?
- Config and secrets across environments; documentation and runbook updates; on-call knowledge.

## Pre-mortem questions

1. If this caused an outage next week, what is the most likely reason? The second? The third?
2. What would we wish we had tested, monitored or made reversible?
3. Who or what is hurt first, and how quickly would we notice?
4. What is the cheapest change now that removes the biggest of those risks?

## Verification ladder (strongest first)

1. A failing test or script reproduces the defect (attach the output).
2. A traced execution with concrete values through the real code, including guards and callers.
3. A reading with named assumptions and a precise question for the author.
Findings at level 3 are **Suspected** and are written as questions.

## Report template

```
Deep review - <change> - <date>

Verdict: Ship | Ship after fixes | Do not ship | Need information
Scope: <range, files>, intent: <...>, risk factors: <...>
Passes done: correctness, security, data, compatibility, concurrency, performance, tests, operations  (note any skipped and why)

Top risks (max 3)
1. ...

Verified findings (ordered by severity)
[Critical|High|Medium|Low] <title>  (Verified|Likely)   <file:line>
  Scenario: <inputs/state/timing>
  Evidence: <test output / trace>
  Impact: <who, what, how likely>
  Fix: <suggestion>

Suspected issues (questions for the author)
- ...

Pre-mortem and readiness
  Likely failure modes: ...   Detection: ...   Rollback: code ..., data ...   Blast radius: ...

Tests to add: ...
Not reviewed / not verified: ...
```
