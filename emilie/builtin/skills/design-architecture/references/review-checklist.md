# Failure, scale and security checklist

Walk each section against the design. For every "no" or "unknown", write one of: **fix** (change the design), **accept**
(risk and owner), or **open** (question and who answers).

## Dependencies and failure

- [ ] Every network call has a timeout, shorter than the caller's own timeout.
- [ ] Retries are bounded, use backoff with jitter, and only repeat operations that are idempotent (or carry an idempotency key).
- [ ] There is a stated behavior when each dependency is down or slow (fail fast, degrade, queue, serve stale).
- [ ] No unbounded queue, buffer, list or fan-out; there is back-pressure or a limit.
- [ ] Single points of failure are listed, with the accepted risk or the redundancy.
- [ ] A poison message or bad record cannot block everything (dead-letter path, skip-and-alert).
- [ ] Startup order and cold-start behavior are defined (what if the database is not ready yet?).

## Data and consistency

- [ ] Every piece of data has exactly one writer/owner.
- [ ] Multi-step operations across components have a plan for partial failure (compensation, outbox, saga, or a single transaction).
- [ ] Derived data and caches have a stated staleness limit and a rebuild path.
- [ ] Schema changes can roll out without downtime (add, backfill, switch, remove).
- [ ] Backups exist, restore has been tried, RPO and RTO are stated.
- [ ] Data retention and deletion rules are stated, including copies in logs, caches and backups.

## Scale and performance

- [ ] The bottleneck for the ranked load scenario is identified (CPU, memory, database, network, a third party).
- [ ] Hot paths avoid per-item remote calls and unbounded queries.
- [ ] There is a way to measure the target (a metric, a load test plan) before building the optimization.
- [ ] Growth plan: what is the first thing that breaks at 10x, and what is the cheapest fix?

## Security and privacy

- [ ] Users and services are authenticated at every boundary; authorization is checked on the server for each action and object.
- [ ] Tenant or user isolation is enforced in the data layer, not only in the UI.
- [ ] Input is validated at the edge; output is encoded for its context.
- [ ] Secrets come from the environment or a secret store, are rotatable, and never appear in logs or the repository.
- [ ] Data in transit and at rest is encrypted as required; sensitive fields are identified.
- [ ] Third-party scopes and credentials are the minimum needed.
- [ ] Audit trail for sensitive actions; logs contain no secrets or unnecessary personal data.
- [ ] Threats considered for the main assets (see `security-audit` for a full review).

## Operations

- [ ] Logs are structured and carry a request or correlation id across components.
- [ ] Metrics exist for each ranked quality attribute; alerts exist for user-visible failure, not just CPU.
- [ ] Health checks distinguish "alive" from "ready".
- [ ] Deploy is automated, rollback is tested, and migrations are compatible with the previous version.
- [ ] Configuration differs per environment without code changes; a staging environment resembles production.
- [ ] Someone owns each component and knows how to be paged for it; runbook for the top three failures.

## Changeability

- [ ] The parts expected to change most are isolated behind a boundary.
- [ ] Core rules are testable without the database, network or framework.
- [ ] Module dependency direction is enforced by something (an import-rule test, lint rule or review checklist), not only by intent.
- [ ] Third-party services sit behind an interface you own, so replacing one touches one module.
