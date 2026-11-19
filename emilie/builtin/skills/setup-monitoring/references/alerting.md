# Alerting rules

Page a human only for user-visible, urgent, actionable problems; everything else is a ticket or dashboard.
Each alert: name, symptom, threshold + duration (avoid flapping), severity, owner, dashboard link, runbook link, first three checks, mitigation (rollback, scale, restart), escalation.
Good: "error rate > 2% for 5m on checkout". Bad: "CPU > 80%" (unless it predicts saturation with a clear action).
Review monthly: delete alerts that never fire or always get ignored; track pages per week and false-positive rate.
Runbook skeleton: Impact - Check - Mitigate - Escalate - Follow-up.
Prometheus example: `expr: sum(rate(http_requests_total{code=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.02`, `for: 5m`.
