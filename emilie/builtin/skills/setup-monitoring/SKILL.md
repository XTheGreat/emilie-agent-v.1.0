---
name: setup-monitoring
phase: rawat
description: Make a service observable - choose signals (logs, metrics, traces, health checks), instrument the code with structured logging and the golden signals, define SLOs and actionable alerts with runbooks, and verify that a failure actually shows up. Includes a script that detects existing observability tooling and gaps. Not for investigating a live incident (debug-production) or load generation (load-test). Triggers - "add monitoring", "set up alerts", "observability", "add metrics", "health check endpoint", "structured logging", "prometheus", "grafana", "sentry", "SLO", "why didn't we notice".
---

# Set up monitoring

**Goal:** know the service is broken before users tell you, and have enough signal to find out why quickly - without drowning in noise.

## Ground rules
1. **Start from user impact:** the golden signals (latency, traffic, errors, saturation) and the key user journeys, not every internal counter.
2. **Every alert must be actionable:** it names the symptom, severity, owner and a runbook link; no alert without an action (`references/alerting.md`).
3. **Structured logs, no secrets or personal data;** include request/trace IDs; levels used consistently.
4. **Low cardinality metrics:** never use user IDs, URLs with ids, or free text as labels.
5. **Use what the project already has** (Prometheus, OpenTelemetry, Sentry, Datadog...) before adding a new vendor; ask before adding paid services or sending data to third parties.
6. **Prove it works:** trigger a controlled failure and confirm the signal and the alert fire.

## Procedure
1. Detect: `python "<this skill's directory>/scripts/monitor_detect.py" [path]` - logging style, metrics/tracing/error-tracking libraries, health endpoints, bare `print` logging, swallowed exceptions.
2. Define signals and SLOs (`references/signals.md`): availability and latency targets per journey, error budget.
3. Instrument: health/readiness endpoint, request middleware metrics, structured logger, error capture, tracing hooks; keep changes minimal and tested.
4. Alerts: symptom-based, with thresholds, `for:` durations, severity and runbook stubs (what to check first, how to mitigate).
5. Verify with a forced failure; report coverage, gaps and cost/volume concerns.

## Definition of done
- [ ] Golden signals and health checks exist; logs structured, safe.
- [ ] Alerts actionable with owners/runbooks; thresholds justified.
- [ ] A forced failure was observed end to end, or the gap is stated.

## Pitfalls
Alerting on causes (CPU 80%) instead of symptoms. Alert storms. High-cardinality labels. Logging secrets or whole payloads. Dashboards nobody owns. Health checks that never fail.

## Hand-offs
| Next | Load |
|---|---|
| incident ongoing | `debug-production` |
| performance numbers | `profile-performance`, `load-test` |
| deploy gates | `containerize-deploy` |
