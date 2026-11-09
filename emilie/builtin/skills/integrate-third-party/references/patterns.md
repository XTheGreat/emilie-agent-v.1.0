# Integration patterns

Code is shown in Python for brevity; the ideas apply in every language. Adapt to the project's own style and libraries.

## 1. The seam (adapter)

```python
# payments/gateway.py  - the only module that knows the vendor exists
from dataclasses import dataclass

class PaymentError(Exception): ...
class PaymentDeclined(PaymentError): ...
class PaymentUnavailable(PaymentError): ...      # timeouts, 5xx, rate limits after retries

@dataclass(frozen=True)
class ChargeResult:
    id: str
    status: str            # "succeeded" | "pending" | "failed"

class PaymentGateway:
    def charge(self, *, amount_minor: int, currency: str, customer_id: str, idempotency_key: str) -> ChargeResult: ...
```

Application code depends on `PaymentGateway`. Tests inject a fake. A `StripeGateway` (or any vendor) implements it. Swapping vendors means writing one class.

## 2. Configuration

- Read once at startup from environment variables (`VENDOR_API_KEY`, `VENDOR_BASE_URL`, `VENDOR_WEBHOOK_SECRET`); fail fast with a clear error naming the variable (not its value).
- Separate keys per environment; test keys by default in development.
- Redact on logging: never log headers, bodies or config objects wholesale.

## 3. Outbound call with timeouts and bounded retries

```python
import random, time, requests

def call_vendor(session, method, url, *, retries=3, **kw):
    kw.setdefault("timeout", (3.05, 10))            # (connect, read) seconds
    for attempt in range(retries + 1):
        try:
            r = session.request(method, url, **kw)
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                delay = float(r.headers.get("Retry-After", 0)) or min(2 ** attempt, 20)
                time.sleep(delay + random.uniform(0, 0.5))
                continue
            return r
        except (requests.Timeout, requests.ConnectionError):
            if attempt == retries:
                raise
            time.sleep(min(2 ** attempt, 20) + random.uniform(0, 0.5))
```

Rules: retry only idempotent requests or ones with an idempotency key; cap attempts and total time; add jitter; surface the final failure as your own error type; stop retrying on 4xx other than 408/409/429.
Use the library's own retry (`urllib3.Retry`, `axios-retry`, SDK settings) when it exists, configured the same way.

## 4. Idempotency keys

- One key per **logical operation** (for example the order id plus the attempt purpose), saved with the local record before the first call.
- Retrying the same operation reuses the key; a new operation gets a new one.
- Store the vendor's resulting id so you can reconcile.

## 5. Webhook receiver

```python
def handle_webhook(request):
    raw = request.body                                    # raw bytes, not parsed JSON
    sig = request.headers.get("X-Vendor-Signature", "")
    ts  = request.headers.get("X-Vendor-Timestamp", "")
    if abs(time.time() - int(ts)) > 300:                  # replay window
        return 400
    expected = hmac.new(SECRET, ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):            # constant-time
        return 401
    event = json.loads(raw)
    if already_processed(event["id"]):                    # dedupe
        return 200
    enqueue(event)                                        # process asynchronously
    return 200                                            # answer quickly
```

Use the vendor's official verification helper when one exists instead of hand-rolling. The processor must be idempotent and tolerate out-of-order events (compare event timestamps or fetch the latest object state).

## 6. Reconciliation

Webhooks are lost sometimes. Run a periodic job that lists recent objects from the vendor (by updated time) and fixes local records that disagree. Log mismatches; alert if they exceed a threshold.

## 7. OAuth 2.0 (user connects their account)

- Authorization Code flow with PKCE; random `state` stored in the session and checked on return; exact redirect URI registered.
- Request the minimum scopes; store tokens encrypted; refresh before expiry; handle revoked tokens by prompting reconnection.
- Never put tokens in URLs or logs. Never ask the user to paste a password or token into chat.

## 8. Rate limiting and bulk work

- Respect documented limits with a client-side limiter (token bucket) set a little below the cap.
- For bulk jobs: batch endpoints where offered, concurrency caps, a queue with backpressure, checkpoints to resume.
- Cache read-only responses with a sensible TTL; invalidate on webhooks.

## 9. Circuit breaker and fallbacks

After N consecutive failures stop calling for a cool-down period (fail fast), then probe with one request. Decide the fallback per feature: queue and retry later (email), show cached data (maps), disable the option with an honest message (payments), or block (auth).

## 10. Testing layers

| Layer | What | Vendor involved? |
|---|---|---|
| Unit | business logic against a fake gateway; error mapping with canned vendor errors | no |
| Contract | recorded real responses (cassettes) or sandbox calls verifying parsing and assumptions | sandbox only, test keys, skipped without keys |
| Webhook | signed sample payloads (valid, wrong signature, old timestamp, duplicate) | no |
| Failure injection | timeouts, 429 with Retry-After, 500, malformed JSON, partial success | no (fake transport) |
| End-to-end | full flow in sandbox before release | sandbox |

## 11. Observability

Log per call: operation, status, duration, retry count, vendor request id (no payloads or personal data). Metrics: latency percentiles, error rate by class, retries, circuit state, queue depth, spend. Alerts on sustained error rate, rising latency, and webhook failures.

## 12. Leaving the vendor

Keep vendor ids in dedicated columns (not mixed into business fields), keep an export of your data, and document the steps to replace the adapter. Run the migration as in `migrate-code` if you ever switch.
