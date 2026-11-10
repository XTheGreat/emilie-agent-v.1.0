# Risk assessment of a change

## Do you need a deep review? Score the change

Add one point for each that applies. 0 to 2: `review-code` is enough. 3 to 5: deep review of the risky parts. 6 or more: full deep review plus a staged rollout.

| Factor | Point |
|---|---|
| Touches authentication, authorization, sessions, permissions | 2 |
| Handles money, billing, inventory, or legal/compliance data | 2 |
| Handles personal or sensitive data (privacy, health, children) | 2 |
| Database migration, data backfill, deletion, format change | 2 |
| Concurrency, locking, queues, retries, distributed state | 2 |
| Public API, file or wire format, SDK used by others | 1 |
| Core module with many callers (high fan-in) | 1 |
| Large diff (over about 500 changed lines or 20 files) | 1 |
| Low test coverage in the area, or tests removed/weakened | 1 |
| Code with a history of bugs or reverts (fix-heavy) | 1 |
| Hard to roll back (irreversible data, external side effects, emails, charges) | 2 |
| Author is new to the area, or the area has no clear owner | 1 |
| Deadline pressure or a hotfix | 1 |
| Infrastructure, CI/CD, secrets management or deployment config | 1 |

## Blast radius questions

- How many users, requests or records can this affect if it is wrong?
- Is the failure loud (errors, crashes) or silent (wrong data, wrong money)? Silent is worse.
- How quickly would we notice, and how quickly can we stop it?
- Can the damage be undone (data restore, refunds, retraction) or is it permanent?

## Severity scale

| Severity | Definition | Examples |
|---|---|---|
| **Critical** | Security breach, data loss or corruption, money wrong at scale, outage of a core function, irreversible harm | auth bypass, migration drops a column in use, double charge |
| **High** | Serious malfunction in a common case, data exposure with limited reach, no rollback path, a break of a public contract | wrong results for a common input, crash on a typical request |
| **Medium** | Wrong behavior in a rare case, performance regression, missing validation with limited impact, weak tests on risky logic | off-by-one on a boundary, N+1 on a list page |
| **Low** | Minor defect, maintainability problem with a plausible future cost, small inefficiency | confusing naming that hides a real misuse risk, missing log context |

Confidence: **Verified** (reproduced or fully traced), **Likely** (plausible, not reproduced), **Suspected** (needs an answer).
Severity measures impact if true; confidence measures how sure you are. Report both.

## Rollout readiness checklist

- [ ] Feature flag or kill switch with a safe default, and the flag can change at runtime.
- [ ] Staged rollout plan (internal, small percentage, full) with the metrics watched at each stage and the stop criteria.
- [ ] Monitoring and alerts exist for the new failure modes (errors, latency, business metrics such as payments succeeded).
- [ ] Rollback tested: previous version runs against the new data; the migration has a down path or a safe forward-fix plan.
- [ ] Backups confirmed before destructive data changes; restore verified.
- [ ] Communication: who is on call, who approves, what users are told if needed.
- [ ] Runbook updated with symptoms and the first three actions.

## Reversibility classes

| Class | Examples | Required care |
|---|---|---|
| Reversible by redeploy | stateless code changes | normal review |
| Reversible with data steps | additive migrations, flags | tested rollback, expand/contract |
| Hard to reverse | dropping columns, rewriting data in place, renames in use, deleting files | staged, backups, dual-write, verification queries |
| Irreversible | sent emails/SMS, payments, external API side effects, deleted data without backup | explicit approval, dry-run, tiny first batch, monitoring |

## When to stop and escalate

- You find a Critical issue: report it immediately and clearly, do not wait for the end of the review.
- A real secret appears in the diff: say so (masked), recommend rotation and history cleanup.
- The change cannot be reviewed responsibly (too big, too tangled, no tests): say so, and recommend splitting or a walkthrough instead of approving.
