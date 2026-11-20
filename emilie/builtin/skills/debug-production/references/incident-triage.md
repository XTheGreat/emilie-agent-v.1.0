# Incident triage checklist

1. Impact: who, how many, which feature, since when, still happening?
2. Changes in the window: deploys, config/flags, migrations, dependency or infra changes, traffic spikes, cron jobs, cert/DNS/credential expiry, third-party outages.
3. Four signals: errors, latency, traffic, saturation (CPU, memory, disk, connections, queues, file descriptors).
4. Scope: one host/pod? one version? one region/tenant/endpoint? -> narrows to a change or a data issue.
5. Dependencies: database (slow queries, locks, connections), cache, queue, external APIs, DNS.
6. Typical causes: connection pool exhaustion, memory leak -> OOM kills, unbounded queue, slow query after data growth, retry storms, timeouts without backoff, expired token, disk full, clock skew, bad config.
7. Commands (read-only): `kubectl logs/describe/top`, `docker logs`, `journalctl -u svc --since`, `ss -s`, `df -h`, `free -m`, `dmesg | grep -i oom`.
8. Close: mitigation confirmed by metrics, evidence saved, follow-ups ticketed.
