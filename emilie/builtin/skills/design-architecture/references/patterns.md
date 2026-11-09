# Architecture patterns: when each pays off

Use as a menu of *shapes*, not a checklist. For each, the cost is as important as the benefit. Prefer the first rows until a
named driver pushes you down the list.

| Shape | Good when | Costs | Trigger to move on |
|---|---|---|---|
| **Single module / script** | One job, one developer, small data | Everything is coupled | A second team, or the file passes a few thousand lines |
| **Layered monolith** (UI / logic / data) | CRUD-like apps, small team | Layers leak; "service" classes grow | Unrelated change rates inside one layer |
| **Modular monolith** (modules with explicit interfaces, one deployable, one DB) | Most products for a long time | Needs discipline: enforce module boundaries in code review or with an import-rule check | One module needs independent scaling, release cycle or ownership |
| **Hexagonal / ports and adapters** | Core rules must be testable and outlive frameworks or vendors | More files and interfaces | Not needed for thin CRUD |
| **Background workers + queue** | Slow or retryable work (email, reports, media) | Eventual results, retries, idempotency, dead letters | Ordering or exactly-once needs get strict |
| **Event-driven (publish/subscribe)** | Many independent reactions to one fact | Hard to trace; schema evolution; eventual consistency | Need a global order or immediate consistency |
| **Services (few, coarse)** | Distinct teams, scale or release needs | Network failure, distributed data, ops cost | Chains of synchronous calls between services |
| **Microservices (many, fine)** | Large organization, many teams, strong platform support | Highest operational cost; needs tracing, CI per service, contract tests | Rarely a first step |
| **CQRS / read models** | Read and write shapes differ greatly, heavy reads | Two models to keep in sync | Do not add for symmetry |
| **Event sourcing** | Audit history is the product (ledgers) | Replays, versioning, complex queries | Almost never for ordinary apps |
| **Serverless functions** | Spiky or rare load, glue code | Cold starts, limits, local testing, vendor coupling | Steady high load (cost) |
| **Static site + API / BFF** | Content sites, SPA with a few endpoints | A second moving part | Pure content: skip the API |
| **Plugin / extension architecture** | Third parties add behaviour | Stable API surface to maintain forever | Only when outsiders really extend it |

## Cross-cutting choices (decide each explicitly)

- **Data ownership.** One writer per piece of data. Others read through the owner's interface or a replicated read model.
- **Sync vs async.** Synchronous when the caller needs the result now and the dependency is reliable; asynchronous when work
  is slow, retryable or fan-out. Every async hop needs: idempotent handlers, a retry limit, a dead-letter path, monitoring.
- **State.** Keep processes stateless; put state in the database, a cache with a miss path, or a queue.
- **Caching.** Say what is cached, the key, the time-to-live, how it is invalidated, and what happens on a miss or stale read.
  "Cache everything" is not a design.
- **Consistency.** Per operation: must it be immediately consistent? If not, state the staleness users can tolerate.
- **Identity and access.** Where users are authenticated, where authorization is enforced (at every boundary, never only in the UI).
- **Configuration and secrets.** Per environment; never in the repository.
- **Deployment.** Single artifact or several; how it is built, released, rolled back, and how schema changes roll out safely.
- **Observability.** Structured logs with a request id, metrics for the quality attributes you ranked, and one alert per
  user-visible failure.

## Smell checks on a proposed design

- A component whose name is "Manager", "Helper", "Common" or "Utils".
- Two services that always change together, or share a database table.
- A synchronous chain of more than two network calls on the user's request path.
- A queue with no consumer owner, no retry limit and no alert.
- A diagram with no mention of where data lives.
