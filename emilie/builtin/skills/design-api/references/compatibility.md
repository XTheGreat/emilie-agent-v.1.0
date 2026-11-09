# Compatibility and versioning

Assume every field and behavior you ship is used by someone. Classify every change before it ships.

## Non-breaking (safe, no version bump)

- Adding a new endpoint, optional request field, optional query parameter or header.
- Adding a field to a response (clients must ignore fields they do not know: write that in the contract).
- Adding a new enum value **only if** the contract told clients to tolerate unknown values.
- Relaxing validation (accepting more), raising limits.
- Making a required request field optional, adding a new error code inside an existing documented status.
- Performance improvements and bug fixes that make behavior match the documentation.

## Breaking (needs a new version or a migration window)

- Removing or renaming an endpoint, field, parameter, header or enum value.
- Changing a type, format, unit, time zone, casing, nullability, or the meaning of a field.
- Adding a **required** request field or tightening validation.
- Changing the default (page size, sort order, filter behavior).
- Changing status codes or the error format or error codes clients branch on.
- Changing authentication or scopes required.
- Changing ordering or pagination semantics that clients depend on.
- Making a previously idempotent operation non-idempotent.

When unsure, treat it as breaking.

## Versioning options

| Approach | Good | Careful |
|---|---|---|
| Path (`/v1/...`) | obvious, cacheable, easy to route | whole-API versions are heavy; duplicates code |
| Header or media type | clean URLs | invisible, harder to test by hand |
| Date-based version header | granular per-customer pinning | needs infrastructure to emulate old behavior |
| Additive-only, no versions | simplest for small or internal APIs | requires strict discipline and expansion by default |

Decide early, document it, and keep the number of live versions small (2 is plenty).

## Deprecation process

1. Announce with a changelog entry and, for public APIs, direct notice to known consumers.
2. Mark in responses: `Deprecation: <date>`, `Sunset: <date>`, and a `Link` header to the migration guide. Mark in the spec (`deprecated: true`).
3. Measure usage per consumer (log API key or client id with the old endpoint) so you know who is left.
4. Give a window sized to the consumers (internal: weeks; public: 6 to 12 months or per contract).
5. Brown-out tests (short planned failures) for stragglers, then remove. Keep a tombstone (`410 Gone` with a pointer) for a while.

## Keeping the contract honest

- The spec is the source of truth or is generated from code, never written once and forgotten.
- Contract tests in CI: validate real responses against the spec; fail the build on drift.
- A diff tool (for example `oasdiff` or `openapi-diff`) in CI flags breaking changes in pull requests.
- Consumer-driven contract tests (for example Pact) when you control both sides.
- Keep a human changelog next to the spec.

## Defensive consumer rules to publish

- Ignore unknown fields. Treat enumerations as open unless stated.
- Do not depend on field order or on the exact text of messages.
- Retry only retryable errors, with backoff and jitter; send idempotency keys on retried writes.
- Store ids as opaque strings.
