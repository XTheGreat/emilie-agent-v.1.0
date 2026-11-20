---
name: debug-production
phase: rawat
description: Diagnose a problem in a live or recently live system from evidence - define the symptom and timeline, correlate logs, metrics, deploys and config changes, form and test hypotheses with read-only commands, find the root cause, and propose a mitigation and a permanent fix with a regression test. Includes a log triage script. Read-only on production unless the user approves an action. Not for a bug reproducible locally (investigate-bug) or the rollback itself (emergency-rollback). Triggers - "production is down", "prod error", "500s in production", "it's slow in prod", "analyze these logs", "why did it crash", "memory leak in production", "incident", "outage".
---

# Debug production

**Goal:** find the real cause of a production problem quickly and safely, using evidence, without making things worse.

## Ground rules
1. **Read-only first.** Look before touching: logs, metrics, status, recent changes. Any restart, scale, config change, data fix or query that writes needs the user's explicit approval.
2. **Mitigate before diagnosing** if users are hurt (`emergency-rollback`); do not hold the fix hostage to a perfect explanation.
3. **Timeline is the key tool:** when did it start, and what changed then (deploy, config, flag, dependency, traffic, data, cert expiry, cron)?
4. **Hypotheses with tests:** write each hypothesis, the evidence that would confirm or kill it, and check it. Distinguish **Verified**, **Likely**, **Unknown**.
5. **Privacy:** logs contain personal data and secrets; do not paste them in full, mask tokens, minimize what leaves the machine.
6. **Preserve evidence** (copy logs, dumps) before restarting; do not run heavy profilers or debuggers on a struggling production host without approval.
7. **Do not guess root cause from one error line;** find the first error, not the loudest.

## Procedure
1. Frame: symptom, impact, start time, scope (all users? one region/endpoint/version?), what changed (`references/incident-triage.md`).
2. Triage logs: `python "<this skill's directory>/scripts/log_triage.py" <logfile|-> [--since "2026-11-15 10:00"]` - finds log format, level counts, error clusters (normalized messages), first occurrence, rate over time, top endpoints/status codes, slow requests.
3. Correlate with deploy history (`git log`, `rollback_plan.py`), metrics, dependencies' status.
4. Narrow: bisect by version, host, endpoint, tenant; reproduce in staging or locally if possible (`investigate-bug`).
5. State the root cause with the evidence chain; propose a mitigation now and a permanent fix + regression test; list monitoring gaps (`setup-monitoring`).
6. Write a short postmortem outline (impact, timeline, cause, fix, prevention) if asked.

## Definition of done
- [ ] Timeline and scope stated; hypotheses tested with evidence.
- [ ] Root cause identified or honestly marked unknown with next probes.
- [ ] Mitigation, permanent fix and prevention proposed; no production action taken without approval.

## Pitfalls
Blaming the last deploy by reflex. Restarting before capturing evidence. Trusting averages instead of percentiles. Missing a downstream dependency or expired certificate. Fixing the symptom and not the trigger.

## Hand-offs
| Next | Load |
|---|---|
| revert the change | `emergency-rollback` |
| reproduce and fix in code | `investigate-bug` |
| performance cause | `profile-performance` |
| detection gap | `setup-monitoring` |
