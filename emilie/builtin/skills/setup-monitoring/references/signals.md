# Signals and SLOs

Golden signals: **latency** (p50/p95/p99, split success/failure), **traffic** (requests/s), **errors** (rate of failed requests), **saturation** (CPU, memory, queue depth, connections, disk).
RED (services): rate, errors, duration. USE (resources): utilization, saturation, errors.
SLO example: 99.9% of requests succeed and 95% finish under 300 ms over 30 days; error budget = 0.1%. Alert on burn rate (fast: 14x over 1h, slow: 6x over 6h) not on single spikes.
Logs: JSON lines with timestamp, level, service, version, request_id, user hash (not email), message, error with stack. Log at boundaries; one line per request.
Traces: propagate W3C `traceparent`; span per outbound call and DB query.
Health: `/healthz` (process alive, cheap) vs `/readyz` (dependencies reachable).
