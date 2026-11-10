# API contract template

Copy, fill in, delete what does not apply. Where the project uses OpenAPI, express the operations as OpenAPI and keep this
file for the narrative parts. Mark facts: **Given**, **Checked**, **Assumed**, **Unknown**.

---

# <API name> - contract v<version>

**Status:** draft | proposed | accepted  **Owner:** <team>  **Date:** <YYYY-MM-DD>

## 1. Purpose and consumers

| Consumer | Calls from | Tasks |
|---|---|---|
| Web app | browser | list orders, place order, cancel order |
| Partner X | server | export orders daily |

Volume and latency expectations: <numbers or assumptions>.

## 2. Conventions (apply to every operation)

- Base URL and versioning: `https://api.example.com/v1`; breaking changes bump the version, additive changes do not.
- Format: JSON, `snake_case` fields, ISO-8601 UTC timestamps, money as `{amount (integer, minor units), currency}`.
- Auth: `Authorization: Bearer <token>`; scopes: `orders:read`, `orders:write`. Object-level checks: caller may access only
  their tenant's objects.
- Errors: `application/problem+json` with `code`, `detail`, `request_id`, `errors[]` (see section 6).
- Pagination: cursor, `limit` default 50, max 200, `next_cursor` in the response.
- Idempotency: `Idempotency-Key` on every `POST` that creates or charges; stored 24 h.
- Concurrency: `ETag` / `If-Match` on `PUT`/`PATCH`.
- Rate limits: 600 requests per minute per token; `429` with `Retry-After`.

## 3. Resources

| Resource | Id | Notes |
|---|---|---|
| order | `ord_...` | belongs to a tenant; status machine new -> paid -> shipped, cancel allowed until shipped |

## 4. Operations

| Operation | Method and path | Auth/scope | Success | Errors |
|---|---|---|---|---|
| List orders | `GET /v1/orders?status=&after=&limit=` | orders:read | 200 | 400, 401, 403, 429 |
| Create order | `POST /v1/orders` | orders:write | 201 + `Location` | 400, 401, 403, 409, 422, 429 |
| Get order | `GET /v1/orders/{id}` | orders:read | 200 | 401, 403, 404 |
| Cancel order | `POST /v1/orders/{id}/cancel` | orders:write | 200 | 401, 403, 404, 409 |

### Create order - `POST /v1/orders`

Request:

```json
{ "customer_id": "cus_123", "lines": [ { "sku": "SKU-1", "qty": 2 } ] }
```

| Field | Type | Required | Rules |
|---|---|---|---|
| customer_id | string | yes | must belong to the caller's tenant |
| lines | array | yes | 1 to 100 items |
| lines[].qty | integer | yes | 1 to 1000 |

Response `201 Created`, `Location: /v1/orders/ord_9`:

```json
{ "id": "ord_9", "status": "new", "total": { "amount": 3998, "currency": "USD" }, "created_at": "2026-03-04T10:15:00Z" }
```

Failure example `422`:

```json
{ "status": 422, "code": "validation_failed", "detail": "1 field is invalid", "request_id": "req_8f2a",
  "errors": [ { "field": "lines[0].qty", "code": "too_small", "message": "Must be at least 1" } ] }
```

(Repeat per operation. Keep examples real enough to paste into a test.)

## 5. Task walk-throughs

For each task in section 1: the exact call sequence, the data passed between calls, and what the consumer does on each failure.

## 6. Error catalogue

| HTTP | code | Meaning | Retryable | Client action |
|---|---|---|---|---|
| 400 | malformed_request | body is not valid JSON | no | fix request |
| 401 | unauthenticated | missing or invalid token | after refresh | re-authenticate |
| 403 | forbidden | not allowed for this object | no | |
| 404 | not_found | does not exist or not visible | no | |
| 409 | state_conflict | state does not allow the action | no | refetch |
| 422 | validation_failed | field errors | no | show field messages |
| 429 | rate_limited | too many requests | yes | wait `Retry-After` |
| 503 | unavailable | try again | yes | backoff + jitter |

## 7. Compatibility and lifecycle

Breaking vs non-breaking rules (link `compatibility.md`), deprecation window, how consumers are notified, changelog location,
contract test setup.

## 8. Security and privacy notes

Personal data fields and why they are needed, retention, logging rules, input limits, webhook signature (if any).

## 9. Linter output

Paste the `api_lint.py` summary for this contract and the disposition of every warning.

## 10. Open questions

| # | Question | Owner |
|---|---|---|
