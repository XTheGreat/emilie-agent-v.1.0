# Design document template

Copy, fill in, delete sections that do not apply. Keep it as short as the system allows; a small service fits on one page.
Mark facts: **Given**, **Checked**, **Assumed**, **Unknown**.

---

# <System or feature name> - design

**Status:** draft | proposed | accepted  **Author:** <name>  **Date:** <YYYY-MM-DD>

## 1. Summary

Two or three sentences: what it is, who it is for, the chosen shape, the one reason it is shaped that way.

## 2. Context and goals

- **Problem:** <what hurts today / what is new>
- **Goals:** <measurable outcomes>
- **Non-goals:** <what this design deliberately does not cover>

## 3. Drivers

| Quality attribute (ranked) | Target scenario | Source |
|---|---|---|
| 1. <e.g. correctness> | <measurable> | Given / Assumed |
| 2. | | |

**Constraints:** <stack, hosting, budget, compliance, deadline, team size and skills>
**Numbers:** <users, requests/s, data volume and growth, read/write ratio, allowed downtime> (mark assumed ones)

## 4. Current state (if any)

Short description of what exists, with the structure facts you measured (module count, cycles, high fan-in modules) and
where they came from (`import_graph.py` output, files read).

## 5. Options considered

| Option | Shape | Easy | Hard | Verdict |
|---|---|---|---|---|
| A (simplest) | | | | |
| B | | | | chosen / rejected: <reason> |
| C | | | | |

**Decision:** option <X>, because <driver>. **Giving up:** <cost>. **Revisit when:** <trigger>.

## 6. Architecture

Diagram (text is fine):

```
 [Client] --HTTPS--> [API / app] --SQL--> [(Database)]
                        |
                        +--enqueue--> [Queue] --> [Worker] --> [Email provider]
```

### Components

| Component | Responsibility (one sentence) | Owns (data/state) | Exposes | Depends on | Owner |
|---|---|---|---|---|---|

### Rules between components

- Dependencies point <direction>; <component> never imports <component>.
- Synchronous: <calls>. Asynchronous: <events/jobs>, each idempotent, retried <n> times, then dead-lettered and alerted.
- Data access: each component reads only its own data; others use its interface.

## 7. Key flows

For each of 2 to 4 flows:

```
Flow: <name>
Trigger: <who/what>
1. Client -> API: <request>
2. API -> DB: <read/write>
3. API -> Queue: <message>
Failure: <what if step 2 fails / times out / is retried>
Result seen by caller: <status/message>
```

## 8. Failure, scale, security

| Concern | Decision |
|---|---|
| Timeouts and retries | |
| Idempotency | |
| Single points of failure | |
| Consistency across components | |
| AuthN / AuthZ at each boundary | |
| Secrets and config | |
| Backup, restore (RPO/RTO) | |
| Observability (logs, metrics, alerts) | |
| Deploy and rollback | |

## 9. Risks and open questions

| # | Risk or question | Likelihood / impact | Mitigation or owner |
|---|---|---|---|

## 10. Decisions to record

List decisions that deserve an ADR (`write-adr`): <decision> - <alternatives> - <why>.

## 11. Rollout plan (optional)

Phases, what is behind a flag, how to roll back, how to migrate existing data.
