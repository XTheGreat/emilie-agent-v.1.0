# Deployment checklist

Before: [ ] image tagged with version/commit (never only `latest`) [ ] vulnerability scan [ ] config and secrets in the platform store [ ] migrations backward compatible (expand, deploy, contract) [ ] resource requests/limits [ ] liveness and readiness probes [ ] logs to stdout [ ] backup of data.
Rollout: staging first; then canary or rolling update with max-unavailable 0 or blue/green; watch error rate, latency, saturation; define abort thresholds.
Rollback: keep the previous image; know the one command (`kubectl rollout undo`, `docker compose up -d <old tag>`); confirm DB migrations do not block it.
After: smoke test, dashboards, alert silence removed, notes recorded.
