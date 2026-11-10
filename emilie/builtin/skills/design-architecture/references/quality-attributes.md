# Quality attributes

Pick the **3 to 5** that matter most for this system and rank them. You cannot maximize all of them; the ranking is what
makes the design decisions defensible. For each chosen attribute, write a *measurable* target (a scenario), not an adjective.

| Attribute | Ask | Example target (scenario) |
|---|---|---|
| Correctness | What must never be wrong? Money, stock, permissions? | "An order is never charged twice, even on retry." |
| Availability | How much downtime is acceptable, and when? | "99.9% monthly (about 43 min); planned maintenance allowed Sunday 02:00." |
| Latency | What does the user feel? Which percentile? | "p95 page load under 800 ms; search under 300 ms." |
| Throughput / scale | Peak load now and in 12 months? | "50 req/s average, 500 req/s peak; 2 TB data in 2 years." |
| Durability | What data loss is tolerable? | "No loss of committed orders; RPO 5 min, RTO 1 h." |
| Security | Who is the attacker, what is the asset? | "Tenant A can never read tenant B's data; PII encrypted at rest." |
| Privacy / compliance | Which law or audit applies? | "GDPR delete within 30 days; audit log kept 1 year." |
| Changeability | What will change most often? | "New payment providers monthly; pricing rules weekly." |
| Operability | Who runs it, with what tools? | "One on-call engineer; deploy and rollback in under 10 minutes." |
| Observability | How will you know it is broken? | "Alert before users report; trace a request across services." |
| Cost | Budget per month, or per user? | "Under 200 USD/month at launch." |
| Testability | Can you test it without the world? | "Core rules testable without a database or network." |
| Portability | Must it avoid lock-in? | "Can move cloud providers within one quarter." |
| Usability / accessibility | Who are the users and devices? | "Works on a 3G phone; WCAG AA." |

## Tension map (common trade-offs)

- Consistency vs availability vs latency across components: strong consistency across services costs latency and uptime.
- Changeability vs performance: layers and indirection ease change and add overhead.
- Cost vs availability: each extra "nine" and each extra region multiplies the bill.
- Security vs usability: every control adds friction; put it where the asset is.
- Time to market vs everything else: a deadline is a legitimate driver; say what you are deferring.

## How to use

1. List candidates for the project; strike what the user clearly does not need.
2. Rank the survivors. If the user says "all of them", ask which one wins in a conflict.
3. Write each as a scenario with a number or a clear pass/fail. Mark invented numbers as **Assumed**.
4. Use the ranked list to score options in Step 4 and to review in Step 7.
