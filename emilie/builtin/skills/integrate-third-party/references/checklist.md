# Vendor documentation checklist

Fill this in from the vendor's official documentation before writing code. Record the URL and the date you read each item.
Mark each fact **Checked** (read in the docs), **Tested** (ran against the sandbox) or **Unknown**.

## Basics

- [ ] Product and API name; API version you will call; how versions are selected (path, header, account setting).
- [ ] Base URLs for sandbox/test and production; whether they use different keys and accounts.
- [ ] Official SDK for our language: maintained? last release? size? license? Or REST only?
- [ ] Status page URL and support channel; known incident history if public.

## Authentication

- [ ] Method: API key, bearer token, OAuth 2.0 (which grant), signed requests, mutual TLS.
- [ ] Where it goes (header name; never the URL), how many keys, permissions or scopes per key, restricted keys.
- [ ] Token lifetime, refresh process, revocation, rotation procedure.
- [ ] OAuth: redirect URIs, state parameter, PKCE, scopes needed (minimum), consent screen requirements.

## Requests and responses

- [ ] The operations you need: method, path, parameters, request body, response body, with examples.
- [ ] Required vs optional fields, formats (dates, money as integer minor units or decimal), maximum sizes.
- [ ] Pagination style and limits; filtering and sorting; expandable fields.
- [ ] Idempotency: header or parameter, retention window, behavior on key reuse with a different body.
- [ ] Eventual consistency: can a read right after a write return stale data?

## Errors and limits

- [ ] Error format; list of codes and which are retryable; how to get the vendor request id.
- [ ] Rate limits (per second/minute/day, per key/account/endpoint), burst behavior, headers reporting remaining quota, `Retry-After` on 429.
- [ ] Timeouts the vendor recommends; maximum request duration; payload size limits.
- [ ] Behavior on partial failure in batch operations.

## Webhooks / events

- [ ] Event types you need and their payload shapes; the delivery guarantee (at-least-once?), ordering guarantee, retry schedule, timeout expected from you.
- [ ] Signature scheme: header name, algorithm, signed content (raw body), secret per endpoint, timestamp tolerance; library helper available.
- [ ] How to replay or list missed events; how to test (CLI forwarding, test event button).
- [ ] Source IP ranges (optional extra check, not a replacement for signatures).

## Sandbox and testing

- [ ] Sandbox/test mode: how to get keys, differences from production, test data (test card numbers, magic values for failures), limits.
- [ ] Can you simulate failures (declines, timeouts, 5xx)? Is there a mock server or recorded fixtures?
- [ ] Does sandbox data reset? Are test emails/SMS really sent?

## Business and compliance

- [ ] Pricing model: per call, per message, per seat, minimums, overage; free tier limits; how to cap spend or set budget alerts.
- [ ] Data handled: personal data, regions and data residency, retention, subprocessors, deletion API, DPA/GDPR terms, PCI/HIPAA scope.
- [ ] SLA and support level; terms of use restrictions (rate scraping, resale, AI training, content rules).
- [ ] Deprecation and versioning policy: notice period, how you will hear about changes (changelog feed, email).
- [ ] Exit plan: data export, how hard to switch, what is proprietary.

## Decide before coding

| Question | Answer |
|---|---|
| Sync call or queued job? | |
| What does the user see when the vendor is down? | |
| What do we store locally (ids, status) and what never (card numbers, secrets)? | |
| How do we reconcile if a webhook is missed? | |
| Which environment variables are needed (names)? | |
| Kill switch or feature flag? | |
