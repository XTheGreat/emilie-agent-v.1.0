# Designing test cases

Write the case list as test names before you write code. Cover each category that applies, once.

## Case categories

| Category | Ask | Examples |
|---|---|---|
| Normal path | What is the typical successful use? | valid order totals correctly |
| Every branch | Which `if`, `elif`, `else`, early return, `except` exists? | one test per outcome |
| Boundaries | Where does behavior change? Test on and just beside the edge | 0, 1, 2, max-1, max, max+1; empty string; exactly the limit; first/last element |
| Equivalence classes | Which inputs behave the same? One representative each | negative / zero / positive; ascii / unicode; small / large |
| Invalid input | What if it is wrong, missing, or the wrong type? | None, empty, too long, malformed JSON, negative quantity, a string where a number is expected |
| Hostile input | What would an attacker or a bad file send? | SQL/HTML/shell characters, path traversal `../`, huge payloads, deeply nested data |
| Dependency failure | What if each collaborator fails or is slow? | timeout, 500, connection refused, malformed response, partial result |
| State and order | Does the result depend on earlier calls or order? | call twice (idempotent?), after close, concurrent access, out-of-order events |
| Time | Does it depend on now, time zones, DST, month ends, leap days? | inject the clock; 23:59:59, Feb 29, DST switch |
| Money and numbers | Rounding, overflow, precision | cents, half-up vs half-even, float error, very large values |
| Permissions | Who may and may not? | owner / other user / anonymous / admin |
| Past bugs | What broke before? | one regression test per fixed bug, named after the symptom |
| Contract | What do callers rely on? | error types and messages they match on, field names, ordering, defaults |

## Techniques

- **Table-driven / parametrized tests** for many input-output pairs of the same behavior. Give each row a readable id.
- **Property-based tests** (Hypothesis, fast-check, `testing/quick`, proptest) for rules that hold for all inputs: round-trips (`decode(encode(x)) == x`), idempotence
  (`f(f(x)) == f(x)`), invariants (sorted output, non-negative totals), comparison with a slow simple implementation. Keep the properties few and meaningful.
- **Characterization tests** for legacy code: record what it does today and assert it, before changing it (see `refactor-code`).
- **Golden files / snapshots** for large structured output; keep them small, review changes line by line, and never approve a snapshot you have not read.
- **Contract tests** for an API: validate real responses against the schema.
- **Test the failure message** when callers or users read it; otherwise assert the error type or code, not the exact text.

## Structure of a good test

```
name:    states the behavior and the condition   ->  rejects_order_when_stock_is_zero
arrange: smallest data that makes the case clear  ->  only fields that matter, named by role
act:     one call to the thing under test
assert:  the observable outcome                   ->  return value, state change, the one call that matters
```

- No logic (loops, branches) in tests; if you need a loop, parametrize.
- No test depends on another test's result or leftovers.
- Setup shared by many tests goes in a fixture or builder; values that explain the case stay visible in the test.
- Prefer real objects and in-memory fakes over mocks; use mocks to verify an interaction that *is* the behavior (an email was sent once).
- Time: pass a clock or `now` parameter; freeze it in tests. Randomness: seed it or inject the generator. Files: use a temporary directory per test.
  Network: record or fake at the boundary.

## Test pyramid (a guide, not a law)

| Level | Share | Speed | Catches |
|---|---|---|---|
| Unit | most | ms | logic errors, edge cases |
| Integration | some | 100 ms to s | wiring, queries, serialization, real framework behavior |
| End-to-end | few | seconds | the main journeys across the whole system |

When a bug slips through, add a test at the lowest level that would have caught it.

## "Make it fail" checklist (mutation by hand)

For the code a test guards, try one of these, run the test, expect a failure, then undo:

- flip a comparison (`>` to `>=`, `==` to `!=`) or a boolean
- change a constant or off-by-one in a loop bound
- remove a validation or an early return
- return a default or `None` instead of the computed value
- swap the order of two arguments
- delete a call to a dependency (save, send, log) that the test claims to check

If the test still passes, it does not guard that behavior: strengthen the assertion or add the missing case. Automated tools do this at scale (mutmut, Stryker, PIT,
cargo-mutants); use them if the project already has them.

## Smells

- Test name says `test1`, `works`, or the method name only.
- Assertions on private attributes or call counts unrelated to behavior.
- The expected value is computed by the same expression as the code.
- `sleep()` to wait for something.
- Catching an exception and asserting nothing about it; a bare `assert True`.
- A fixture that does a lot; tests that need to read it to understand what they are testing.
- Duplicate tests that exercise the same branch with trivially different data.
