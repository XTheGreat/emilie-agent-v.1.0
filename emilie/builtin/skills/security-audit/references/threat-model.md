# Threat modeling and reporting

## Quick threat model (30 minutes)

1. **What are we protecting?** Assets: user data, credentials, payment data, intellectual property, availability, reputation. Rank them.
2. **Who might attack?** Anonymous internet user, authenticated user (curious or malicious), another tenant, insider/admin, compromised dependency or CI, compromised third-party service, a user's stolen device.
3. **Draw the system** as boxes and arrows: clients, services, databases, queues, third parties, admin tools. Mark **trust boundaries** where data or control crosses from lower to higher trust.
4. **List the entry points**: routes, forms, APIs, file uploads, webhooks, message consumers, CLI flags, scheduled imports, admin consoles, build and deploy pipelines.
5. **Apply STRIDE at each boundary** (table below), write the realistic threats, and ask: is there a control? Is it tested?
6. **Rank** by impact times likelihood; the top five drive the audit and the fixes.

## STRIDE prompts

| Threat | Question | Typical controls |
|---|---|---|
| **S**poofing | Can someone pretend to be another user, service or server? | strong authentication, mutual TLS, signed tokens/webhooks, secure sessions |
| **T**ampering | Can data or code be changed in transit, at rest or in the client? | integrity checks, signatures, server-side validation, TLS, immutable logs, least-privilege writes |
| **R**epudiation | Can an actor deny what they did? Can we prove what happened? | audit logs with identity and time, tamper-evident storage |
| **I**nformation disclosure | Can data leak (responses, errors, logs, caches, backups, side channels)? | access control, encryption, minimal responses, safe errors, secrets management |
| **D**enial of service | Can someone exhaust CPU, memory, storage, connections or money? | rate limits, quotas, timeouts, input size limits, autoscaling limits, backpressure |
| **E**levation of privilege | Can a low-privilege actor gain higher privileges? | authorization on every action, least privilege, input validation, sandboxing, no unsafe deserialization |

## Data flow worksheet

| # | Flow (from -> to) | Data | Boundary crossed | Authn | Authz | Encrypted | Validated | Logged | Threats / notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Browser -> API `/orders` | order, token | internet -> app | bearer token | owner check | TLS | schema | yes | IDOR on order id |

## Abuse cases (write at least five)

- A user changes the id in the URL to read another customer's invoice.
- A user sends a negative quantity or modifies the price in the request body.
- Two requests arrive at once and spend the same balance twice.
- A crafted file upload is executed or overwrites an existing file.
- A webhook endpoint is called by someone other than the provider.
- A compromised dependency or CI action steals secrets from the build.
- An insider exports the customer table through an admin tool without a trace.

## Severity rating

Rate by **impact x likelihood**, and state the scenario so others can judge.

| Severity | Typical meaning |
|---|---|
| **Critical** | Remote, unauthenticated or easily obtained access to all data or full control; exposed live secret with broad power |
| **High** | Authenticated attacker reads or changes other users' data, privilege escalation, injection with real impact, secrets for important systems |
| **Medium** | Needs conditions (specific role, user interaction, unusual config), limited data, or defense-in-depth failure that raises risk |
| **Low** | Hard to exploit, minimal impact, hardening gap |
| **Info** | Observation or best-practice note |

Factors: exposure (internet vs internal), authentication required, user interaction, complexity, data or function affected, available mitigations. Map to CWE and OWASP Top 10 category for reference.

## Finding template

```
[SEV-001] <title>                                  Severity: High   Confidence: Verified
Location: path/to/file.py:123            Category: CWE-639 / OWASP A01 Broken Access Control
Scenario: An authenticated user requests GET /api/invoices/<id> with another customer's id; the handler loads by id only.
Impact: Any logged-in user can read every customer's invoices (names, addresses, amounts).
Evidence: <code excerpt or local test that reproduces it, with fake data>
Fix: scope the query to the caller (Invoice.get(id, owner_id=user.id)), return 404 for others, add test_user_cannot_read_other_invoice.
References: <docs>
```

## Report outline

```
Security audit - <system> - <date>
1. Executive summary: overall risk in plain words; the top 3 actions.
2. Scope, authorization, method (threat model, scanner and version, manual review areas, dynamic testing yes/no)
3. Summary table: ID | title | severity | confidence | status
4. Findings (template above), ordered by severity
5. Positive observations (controls that work)
6. Not covered / limitations
7. Recommendations: quick wins, medium-term, process (secret scanning, dependency updates, security tests in CI, threat modeling in design, incident response)
8. Appendix: scanner summary, dependency vulnerability list, checklist coverage
```

## Responsible handling

- Keep the report confidential and share only with those who must fix it; do not post exploit details in public places.
- If an actively exploited issue or a leaked secret is found, say so first and recommend immediate containment (rotate, revoke, block) before anything else.
- Follow the organization's disclosure process for vulnerabilities in third-party software; do not test other people's systems.
