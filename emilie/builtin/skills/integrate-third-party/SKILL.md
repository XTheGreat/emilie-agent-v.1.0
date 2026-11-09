---
name: integrate-third-party
phase: bangun
description: Connect an application to an outside service or API (payments, email, auth, storage, AI, webhooks) safely - read the vendor docs and limits, isolate the vendor behind your own interface, keep secrets out of code, set timeouts, bounded retries and idempotency, verify webhooks, test with sandbox keys and fakes. Includes an audit script for missing timeouts, disabled TLS, hard-coded secrets and unverified webhooks. Not for choosing the vendor (evaluate-technology). Triggers - "integrate", "integration with", "connect to", "stripe", "twilio", "oauth", "webhook", "third-party api", "sdk", "api key", "payment gateway", "send emails with".
---

# Integrate third-party service

**Goal:** a vendor integration that works in the normal case, degrades gracefully when the vendor is slow, down or wrong, keeps
credentials and customer data safe, and can be tested and replaced without touching the whole codebase.

## Ground rules

1. **Docs first, from the vendor, for the version you will call.** Read the official quick start, the authentication page, the
   endpoint reference you need, rate limits, error codes, webhooks, sandbox/test mode, pricing and the changelog or API version policy.
   Note the doc date and version. Do not code from memory or from old blog posts.
2. **Credentials are the user's, never in code.** Real keys come from the environment or a secret store. Never print them, log them, put them in
   URLs, commit them, paste them into chat, or type them into a form for the user. Use test/sandbox keys during development, and
   `.env.example` with placeholders. If a real secret is exposed, tell the user to rotate it.
3. **Do not act on live accounts.** No real charges, emails, SMS, deletions or production writes during development without the user's explicit yes
   for that specific action. Use sandbox mode, test cards and fake recipients.
4. **Isolate the vendor.** All vendor calls live behind one small module or interface that you own, expressed in your domain terms. The rest
   of the code never imports the vendor SDK. This makes testing, swapping and mocking easy.
5. **Assume the network fails.** Every outbound call has a timeout; retries are bounded, with exponential backoff and jitter, and only for
   idempotent operations or calls carrying an idempotency key; handle 429 using `Retry-After`; define what the user sees when the vendor is down.
6. **Never trust inbound data.** Verify webhook signatures with the provider's method and a constant-time comparison, check timestamps against replay,
   respond fast (2xx) and process asynchronously, and make handlers idempotent (events can arrive twice or out of order).
7. **Map the vendor's errors.** Translate vendor errors into your own small set (invalid input, auth, not found, rate limited, unavailable, unknown), keep
   the vendor request id for support, and never leak vendor internals to users.
8. **Data minimization.** Send the vendor only the data it needs; know where it is stored and what the contract says about retention and regions;
   do not log personal data or full payloads; handle deletion requests.
9. **Test without the vendor.** Unit tests use a fake behind your interface; a few contract tests check your assumptions against recorded or sandbox
   responses; the real vendor is only called in clearly marked integration tests with test keys.
10. **Plan for money and limits.** Know the price per call, quota and burst limits; add caching, batching or backpressure where needed; alert on spend and error rates.
11. **State what you could not verify.** If you could not run a call (no key, no network, no approval), say "not run" and why. Never report an integration as working
    from unexecuted code.

## Procedure

### Step 1 - Define the integration

Write: the vendor and product, why, which operations you need (3 to 6 concrete verbs), the data that crosses the boundary in each direction, who owns the vendor
account, environments (dev/staging/prod keys), the failure behavior you want (block, queue and retry, degrade), and non-functional needs (latency, volume, compliance).
If the vendor is undecided, use `evaluate-technology`.

### Step 2 - Read the vendor's documentation

Open the official docs with `web_search`/`web_fetch` and extract, into notes: base URL and API version; authentication method (API key, OAuth 2.0, signed requests) and token lifetime; the
exact endpoints, request and response shapes you need; idempotency support; pagination; rate limits and how they are reported; error format and codes; webhook events and the
signature scheme; sandbox/test credentials and test data; SDK availability and its maintenance state; pricing; deprecation policy. Use `references/checklist.md` as the list.
Prefer the official SDK when it is maintained and small; otherwise call the REST API with a thin client.

### Step 3 - Look at the codebase

Find how external calls are made today (HTTP client, config, error handling, logging, tests), where secrets are loaded, and whether a similar integration exists to copy.
Run:

```
python "<this skill's directory>/scripts/integration_check.py" [project-root]
```

It lists outbound calls without timeouts, disabled TLS verification, plain `http://` URLs, secret-looking strings (masked), `.env` handling, webhook handlers lacking signature checks,
and whether any retry logic exists. Use it on the existing code before adding to it, and again on your changes. It is textual: shared clients configured elsewhere are not seen.

### Step 4 - Design the seam

Define the interface in your terms (`PaymentGateway.charge(amount, currency, customer, idempotency_key) -> ChargeResult`), the config it needs (read once, from the environment),
the error types, and the domain events you will emit. Decide sync vs async (queue for slow or retryable work), what you store locally (vendor ids, status, timestamps, never raw card
data or full secrets), and how local state is reconciled with the vendor when they disagree. Write down the flows with `references/patterns.md`: outbound call, webhook in, retry, reconcile.

### Step 5 - Implement

Follow the project's patterns (`build-feature` loop). Concretely:

1. Config: read keys and URLs from the environment; fail fast with a clear message if missing; add placeholders to `.env.example`; make sure `.env` is git-ignored.
2. Client: one shared HTTP client/session with timeouts (connect and read), a `User-Agent`, TLS verification on, and a bounded retry policy with backoff and jitter.
3. Idempotency: generate an idempotency key per logical operation (not per attempt) and store it with the local record.
4. Rate limits: honor `Retry-After`; queue or throttle bulk work; never loop tightly on errors.
5. Errors: map to your error types; log the vendor request id and status, not the payload.
6. Webhooks: raw-body signature verification, timestamp tolerance, dedupe by event id, quick 2xx, async processing, ordering tolerance.
7. Observability: structured logs, metrics for latency, error rate and retries per operation, and an alert for sustained failures.
8. Feature flag or kill switch so the integration can be turned off without a deploy when practical.

### Step 6 - Test

Unit tests with a fake of your interface cover the business logic and failure paths (timeout, 429, 5xx, malformed response, duplicate webhook, bad signature). Contract tests run the real
client against recorded responses or the vendor's sandbox using test keys (skipped when keys are absent). Run a manual end-to-end in sandbox mode when the user supplies test credentials
(never ask them to paste live secrets into chat). Re-run `integration_check.py`, the project's tests, linter and type checker, and compare with the baseline.

### Step 7 - Operate and hand over

Document: required environment variables (names only), how to get sandbox keys, how to run the integration tests, the vendor dashboards to watch, the runbook for outage and for
leaked keys (rotate, revoke, redeploy), cost and quota notes, and the upgrade path for the vendor API version. Add a calendar-worthy note for key rotation and API deprecations.

### Step 8 - Report

Summarize what was integrated and how it is isolated, files changed, configuration needed, tests added and run (with results), what was verified against the real sandbox and what was
not, assumptions, risks (vendor lock-in, cost, outage behavior), and next steps (`security-audit` for sensitive flows, `setup-monitoring`, `write-documentation`).

## Definition of done

- [ ] Vendor docs for the exact API version were read; limits, errors, auth and webhook scheme are recorded.
- [ ] All vendor calls pass through one interface owned by the project; no vendor types leak out.
- [ ] Credentials come from the environment; `.env` is ignored; `.env.example` has placeholders; no secret appears in code, logs, tests or history.
- [ ] Every outbound call has timeouts; retries are bounded, backed off, and only for safe operations; 429 handling exists.
- [ ] Webhooks verify signatures and replays, dedupe events, and answer quickly.
- [ ] Failure behavior is defined and tested (timeout, rate limit, 5xx, bad payload, duplicate event).
- [ ] Tests run without the real vendor; sandbox contract tests exist or the gap is stated.
- [ ] `integration_check.py` shows no new warnings; anything unverified is reported as "not run".
- [ ] Cost, quota, data-sharing and outage behavior are documented.

## Pitfalls

- **No timeout.** One slow vendor freezes every worker. The default of most HTTP libraries is "wait forever".
- **Retrying non-idempotent calls** (double charges, duplicate emails). Use idempotency keys or do not retry.
- **Trusting webhooks.** Unsigned endpoints let anyone fake "payment succeeded".
- **Secrets in the repository or in logs**, or sent to the wrong environment (live key in staging).
- **SDK everywhere.** Vendor types spread through the code; swapping or testing becomes a rewrite.
- **Treating the vendor's response as the source of truth for local state without reconciliation.** Webhooks get lost; build a periodic reconcile.
- **Ignoring rate limits and cost.** A loop that calls an AI or SMS API per row can burn money in minutes.
- **Testing only the happy path** against the sandbox, which behaves better than production.
- **Parsing HTML or undocumented endpoints** because it works today. Use documented APIs.
- **Unpinned SDK versions and unread changelogs.** Breaking changes arrive in minor releases of some vendors.
- **Collecting extra personal data** "just in case", or sending it to a vendor outside your allowed regions.

## Hand-offs

| Next | Load |
|---|---|
| choose the vendor | `evaluate-technology` |
| overall design | `design-architecture` |
| your own endpoints for the callbacks | `design-api` |
| implement the feature around it | `build-feature` |
| security review of auth/payments | `security-audit` |
| tests | `write-tests` |
| monitoring and alerts | `setup-monitoring` |
| something fails in production | `debug-production` |
| documentation | `write-documentation` |
