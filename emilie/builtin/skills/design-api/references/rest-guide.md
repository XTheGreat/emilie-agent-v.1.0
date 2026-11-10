# HTTP API design guide

## Paths

- Plural nouns for collections: `/orders`, `/orders/{order_id}`. One casing style for all segments (kebab-case or snake_case).
- Nest once to show ownership (`/orders/{id}/lines`); beyond that use filters (`/lines?order_id=...`).
- No verbs, file extensions or trailing slash variants. Identifiers are opaque strings.
- Commands that do not fit CRUD: `POST /orders/{id}/cancel`, `POST /reports/{id}/runs`. Returns the new state or a job.
- Prefer stable public ids (UUID or slug) when internal ids should not leak or be enumerable.

## Methods

| Method | Meaning | Safe | Idempotent | Typical success |
|---|---|---|---|---|
| GET | read | yes | yes | 200 |
| HEAD / OPTIONS | metadata | yes | yes | 200/204 |
| POST | create, or run a command | no | no (use an idempotency key) | 201 + `Location`, or 200/202 |
| PUT | replace whole resource at a known URL | no | yes | 200/204 |
| PATCH | partial update (merge patch or JSON patch) | no | not guaranteed | 200 |
| DELETE | remove | no | yes | 204 |

GET and DELETE have no request body. Bodies on them are dropped by some clients and proxies.

## Status codes

| Code | Use |
|---|---|
| 200 | OK with body |
| 201 | Created; include `Location` and the resource |
| 202 | Accepted for asynchronous work; return a status URL |
| 204 | Success with no body |
| 301/308 | Permanent move |
| 304 | Not modified (conditional GET) |
| 400 | Malformed request (bad JSON, wrong types) |
| 401 | Not authenticated (no or invalid credentials) |
| 403 | Authenticated but not allowed |
| 404 | Not found (also use to avoid revealing that another user's object exists) |
| 405 | Method not allowed (include `Allow`) |
| 409 | Conflict with current state (duplicate, version mismatch) |
| 410 | Gone |
| 412 | Precondition failed (`If-Match`) |
| 413 / 414 / 415 | Too large / URI too long / unsupported media type |
| 422 | Well-formed but fails validation or business rules |
| 429 | Rate limited (`Retry-After`) |
| 500 | Server bug; never intentional |
| 502/503/504 | Upstream failure / unavailable / timeout (`Retry-After` for 503) |

Pick one of 400 or 422 for validation failures and use it everywhere.

## Request and response bodies

- JSON objects at the top level (never a bare array: you cannot add fields later). Consistent casing (`snake_case` or `camelCase`).
- Timestamps: ISO-8601 in UTC (`2026-03-04T10:15:00Z`). Dates: `YYYY-MM-DD`.
- Money: integer minor units plus `currency` (`{"amount": 1999, "currency": "USD"}`), or decimal strings. Never floats.
- Enumerations: documented, lowercase strings; clients must tolerate unknown values if you will add some.
- Absent vs null: document the difference, especially for PATCH. Omit fields you do not know instead of inventing values.
- Return the created or updated resource so clients need no extra GET.
- Expansion: allow `?expand=customer` or `?fields=` for needs that vary, instead of many bespoke endpoints.

## Errors

One shape for every error. RFC 9457 `application/problem+json` is a good base:

```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "code": "validation_failed",
  "detail": "2 fields are invalid",
  "request_id": "req_8f2a",
  "errors": [
    {"field": "email", "code": "invalid_format", "message": "Must be a valid email address"},
    {"field": "qty", "code": "too_small", "message": "Must be at least 1"}
  ]
}
```

Rules: stable machine `code`s (clients branch on them, never on message text); human messages in the client's language if
you localize; no internals; same shape for 4xx and 5xx; include a request id that also appears in logs.

## Pagination

- **Cursor** (`?limit=50&after=<opaque>`; response has `next_cursor`) for data that changes or is large. Stable order required
  (for example `created_at, id`). Cursors are opaque and may expire.
- **Offset/page** (`?page=3&per_page=50`) only for small, static, human-browsed data. It skips and repeats rows under writes
  and gets slow deep in a table.
- Always: a default and a maximum `limit`, a documented sort, and a way to know there is no next page. A total count is
  optional and costly; offer it on request.

## Filtering, sorting, search

`?status=open&created_after=2026-01-01`, `?sort=-created_at,name`, `?q=term`. Validate and whitelist fields; return 400 or 422
for unknown ones rather than ignoring them silently. Keep the same syntax across collections.

## Idempotency and retries

- Clients may retry anything on timeout. Writes that create or charge accept `Idempotency-Key: <uuid>`. The server stores the
  key with the response for a window (for example 24 h) and returns the same result for a repeat; a different body with
  the same key is an error (422 or 409).
- PUT and DELETE are idempotent by definition: deleting twice returns 204 or 404, document which.
- Say which errors are retryable (429, 502, 503, 504) and send `Retry-After`.

## Concurrency control

Return an `ETag` (or a `version` field). Updates send `If-Match` (or the version); mismatch gives 412 (or 409). This prevents
lost updates when two users edit the same object.

## Long-running work

Return `202 Accepted` with a status resource (`/jobs/{id}`) that reports `queued|running|succeeded|failed`, progress, the
result link, and the error object. Prefer polling with `Retry-After` hints, or a webhook for completion.

## Authentication and authorization

- Bearer tokens (OAuth 2.0/OIDC) for users and third parties; API keys only for server-to-server, sent in a header (never the URL).
- Short-lived access tokens, refresh tokens, scopes per capability.
- **Authorize every object access** on the server (can this caller read order 17?), not only the route. Enforce tenant
  isolation in the data layer.
- Rate limit per credential and per IP; return `429` with `Retry-After` and limit headers.
- Limit body size, array lengths, nesting depth and upload types.
- Log who did what, never secrets or full personal data.

## Webhooks (events you send)

Event envelope (`id`, `type`, `created_at`, `data`), signed payloads (HMAC with a timestamp to prevent replay), at-least-once
delivery with retries and backoff, unique event ids so receivers can dedupe, a way to replay missed events, versioned event
schemas, and a test event endpoint.

## When not to use REST

- **GraphQL:** many different clients needing different shapes of a graph; cost control (depth and complexity limits),
  caching and authorization per field become your job.
- **gRPC:** internal service-to-service with strong typing and streaming; browsers need a proxy.
- **Async messaging / events:** fire-and-forget workflows, fan-out; design the event schema like a public API.
- **Library or CLI interfaces:** the same ideas apply: small stable surface, explicit errors, documented exit codes or
  exceptions, additive changes.
