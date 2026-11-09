# Investigation log and report templates

## A. Working log (keep it while you investigate)

```markdown
**Report:** <expected vs actual, one line>
**Reproduction:** <command or steps> -> <exact output>   (status: reproduced | intermittent (n of m) | not reproduced)

| # | Hypothesis | If true I will see | If false I will see | Test | Result |
|---|---|---|---|---|---|
| H1 | the discount is applied twice | total = price x 0.8 x 0.8 | total = price x 0.8 | print the total at `pricing.py:58` and `:71` | **disproved**: applied once |
| H2 | cached price is stale | the cached value differs from the database | they match | read both for item 42 | **confirmed**: cache holds the old price |

**Ruled out:** <what and how>        **Changed for the investigation (to revert):** <none | list>
```

Update the table after every test. Do not delete disproved rows: they stop you repeating yourself and they are useful to the reader.

---

## B. Final report

```markdown
# Bug: <short title>

**Verdict:** <root cause in one sentence>   **Confidence:** high | medium | low   **Status:** confirmed | likely | unconfirmed

## Summary
Two or three sentences: what the user saw, why it happens, and the fix in one line.

## Reproduction
Exact steps or command, the environment (OS, runtime, versions, commit `abc1234`), and the output that shows the bug.
If it is intermittent: how often and under what conditions.

## Evidence (timeline)
1. 10:02:11 request arrives with `qty=0` (log line, `service.log:482`)
2. `app/orders.py:5` divides by `len(items)`, which is 0 -> `ZeroDivisionError`
3. the error handler at `app/api.py:40` returns a 500 instead of a 422

## Root cause
Explain the mechanism from cause to symptom, with `path:line` for each step. Name the wrong assumption
(for example: "the code assumes an order always has at least one item; the cart page can now submit an empty order").

## Why now
What change, data or condition exposed it: commit `9f3c1d2` (2026-10-30) removed the client-side check.

## Why it was not caught
No test covers an empty order; the validation lived only in the browser.

## Fix
**Recommended:** validate `items` at `api.py:34` and return 422 with a clear message. (Smallest change that removes the cause.)
**Alternative:** guard the division in `orders.py:5` (fixes the crash, but the API still accepts an invalid order).
**Risk:** callers that relied on the 500 (none found: searched with `find_symbol.py post`).
**Regression test:** `tests/test_orders.py::test_empty_order_is_rejected` fails before the fix and passes after.

## Other places affected
Same pattern at `app/refunds.py:22` and `app/reports.py:61` (divide by a possibly empty list).

## Not yet known
- Whether any client sends empty orders on purpose (ask the owner of the mobile app).

## Changes made during the investigation
None. (Or: temporary lines prefixed `DEBUGTMP` in `x.py`, removed.)
```

---

## C. A short message for the user (when they want the answer, not the report)

> **Cause:** <one sentence>. **Where:** `path:line`. **Why now:** <one clause>.
> **Fix I recommend:** <one line>, with the test <name>. Want me to apply it?
> (Full write-up available. Not yet verified: <the one thing>.)
