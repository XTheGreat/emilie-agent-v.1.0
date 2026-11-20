# Rollback decision

| Situation | Action |
|---|---|
| Bad code, no schema change | Redeploy previous artifact / `git revert` + redeploy |
| New feature behind a flag | Turn the flag off (fastest, no deploy) |
| Config or secret change | Restore previous config value, restart if needed |
| Additive migration (new nullable column/table) | Safe to roll back code; leave the schema |
| Destructive migration (drop/rename/type change) | Do NOT just roll back code; restore from backup or fix forward; get a DBA/owner |
| New data format already written | Check old code can read it; else fix forward or write a converter |
| Dependency or infra change | Pin the previous version / revert the infra change |
| Unknown cause, high impact | Roll back to last known good, investigate afterwards |

Commands (examples, show before running): `git revert <sha>` or `git revert -m 1 <merge>`; `kubectl rollout undo deployment/<name>`; `docker compose up -d` with the old tag; PaaS "redeploy previous release".
Expand/contract rule for future migrations: add -> deploy code that writes both -> backfill -> switch reads -> remove later, so rollbacks stay safe.
