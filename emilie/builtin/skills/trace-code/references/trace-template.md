# Trace template

Keep it readable without opening the code. Quote only the lines that carry the point. Every hop has a `path:line` that you
read. Mark claims **Verified** (read or run), **Inferred**, or **Unknown**.

---

```markdown
# Trace: <the question, in the user's words>

**Scenario:** <input and conditions, e.g. "a logged-in user submits a valid cart with a discount code">
**Start -> end:** <trigger> -> <observable outcome>

## Short answer
Three lines at most: what happens, in plain words, and the one thing the user is most likely to be surprised by.

## Trace
| # | Where | What happens | Data in -> out |
|---|---|---|---|
| 1 | `app/api/orders.py:34` `post_order` | validates the body, loads the user | JSON -> `OrderRequest` |
| 2 | `app/services/orders.py:58` `create_order` | prices the cart, applies the discount, checks stock | `OrderRequest` -> `Order` |
| 3 | `app/db/repo.py:90` `save` | inserts the order and its lines in one transaction | `Order` -> row ids |
| 4 | `app/events.py:22` `publish` | emits `order.created` (async) | `Order` -> event |
| 5 | `app/api/orders.py:41` | builds the response | `Order` -> 201 JSON |

`request -> route -> service -> repository -> event -> response`

## Branches
- **Discount invalid:** `services/orders.py:71` raises `InvalidDiscount`; the route turns it into a 422 (`api/orders.py:48`).
- **Out of stock:** `services/orders.py:79` raises `OutOfStock` after the price is computed; nothing is written.

## Failure and recovery
Where errors are raised, where they are caught or translated, what the caller sees, what is retried or rolled back.
(Example: the database write and the order lines share one transaction, so a failure leaves no partial order.)

## Side effects
- Database: writes `orders`, `order_lines` (`repo.py:90`)
- Event: `order.created` consumed by `emails/handlers.py:15` (Verified) and possibly others (Unknown)
- Cache: invalidates `user_cart:{id}` (`cache.py:40`)
- Log/metrics: `orders_created` counter

## Gaps and assumptions
- `handlers[...]` at `events.py:30` is a registry filled at import time. I found three registrations; there may be more
  in plugins (Unknown).
- I did not read the payment client (`payments/client.py`): boundary.

## How this was checked
- Tests: `tests/test_orders.py:12` covers the happy path and the invalid discount; nothing covers out-of-stock.
- Ran: `pytest tests/test_orders.py -q` -> 6 passed. (or: "not run: commands were not allowed")

## Read next
`app/services/pricing.py` (the discount rules), `app/events.py` (everything that reacts to an order).
```

---

## Style notes

- Name each hop by what it *does*, not by what it is called.
- Show data shape changes; that is where most surprises live.
- One scenario per trace. If the user needs a second path, say "a second trace for <path>" and offer it.
- If you could not finish, say exactly where you stopped and what blocked you. A partial trace with honest gaps is useful;
  a complete-looking one with invented hops is harmful.
