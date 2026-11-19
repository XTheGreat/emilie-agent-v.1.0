---
name: emergency-rollback
phase: rilis
description: Recover quickly when a release is hurting users - decide rollback versus fix-forward, identify the last good version, check migrations and data compatibility, execute the smallest safe revert with approval, verify recovery with real signals, and write the incident notes. Includes a script that lists recent tags, deploy-like commits and migrations to choose the rollback target. Stabilize first, root cause later. Not for finding the underlying bug (debug-production, investigate-bug). Triggers - "roll back", "revert the release", "production is broken after deploy", "undo the deploy", "emergency", "hotfix", "bad release", "back out this change".
---

# Emergency rollback

**Goal:** restore service with the least risk and least delay, with clear communication; analysis comes after recovery.

## Ground rules
1. **Stop the bleeding first.** Prefer the fastest safe action: feature flag off, traffic shift, redeploy previous version, `git revert`. Do not debug live while users are failing unless rollback is impossible.
2. **Every destructive or production-affecting command needs the user's explicit approval,** shown first with its blast radius. You never run it silently.
3. **Rollback vs fix-forward:** roll back when the cause is the release and the old version is compatible with current data; fix forward only if rollback is riskier (irreversible migration, data already written in a new format).
4. **Data first.** Check migrations and writes since the release (`references/rollback-decision.md`). Never drop or edit data to "make rollback work" without a backup and approval.
5. **Prefer `git revert`** (new commit) over history rewriting or force-push on shared branches.
6. **Verify with signals,** not hope: error rate, latency, health checks, a smoke test of the broken path.
7. **Communicate:** short factual status updates (impact, action, next update time); no blame, no speculation.

## Procedure
1. Triage in 2 minutes: what is broken, since when, blast radius, what changed (release, config, flag, dependency, data).
2. Brief: `python "<this skill's directory>/scripts/rollback_plan.py" [path]` - recent tags and commits since the last tag, migration files added, config/dependency/lockfile changes, and the suggested last good tag.
3. Choose with the decision table; write the exact commands and the undo-of-the-undo.
4. Get approval, execute, then verify (signals above) and keep watching for the agreed window.
5. Preserve evidence (logs, versions, timeline) before it rotates; open the follow-up: root cause (`debug-production`), regression test (`write-tests`), notes (`write-adr` or postmortem).

## Definition of done
- [ ] Impact stopped and confirmed by signals; previous version identified and recorded.
- [ ] Data/migration impact checked; approval obtained for each production action.
- [ ] Status communicated; evidence saved; follow-ups created.

## Pitfalls
Rolling back code but not config/flags. Ignoring a one-way migration. Rolling back during a partial deploy and leaving mixed versions. Force-pushing over teammates. Declaring victory before metrics recover. Skipping the follow-up so it happens again.

## Hand-offs
| Next | Load |
|---|---|
| find the root cause | `debug-production` |
| regression test | `write-tests` |
| record the decision | `write-adr` |
| prevent recurrence | `setup-monitoring`, `setup-ci-cd` |
