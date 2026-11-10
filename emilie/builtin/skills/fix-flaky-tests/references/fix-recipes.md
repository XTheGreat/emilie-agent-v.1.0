# Fix recipes

Fix the cause. The same shape applies in every language; examples are in Python and JavaScript.

## Waiting

**Replace sleeps with waiting for a condition**

```python
def wait_until(cond, timeout=5.0, interval=0.01):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        time.sleep(interval)
    raise AssertionError("condition not met within %.1fs" % timeout)

wait_until(lambda: job.status == "done")        # not: time.sleep(2)
```

```js
await vi.waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument());   // not setTimeout
await page.getByRole('button', { name: 'Save' }).click();                         // Playwright auto-waits; no waitForTimeout
```

Prefer an event, a promise, a future or a callback over polling. Timeouts are upper bounds that should never be reached, not durations to wait.

**Await everything**: every promise/task/thread started in a test is awaited or joined before the test ends; use `await Promise.all`, `asyncio.gather`, `thread.join(timeout)`, `WaitGroup`.

## Time

- Pass the clock in (`def make_token(now): ...`), or patch it in one place; freeze it (`freezegun`, `time-machine`, `vi.setSystemTime`, `jest.useFakeTimers`, `clock` interface in Go/Java).
- Compare against fixed instants, not `now() + 1 second`. Use UTC in tests, and add one test around DST and month end.
- Never measure elapsed real time with assertions on small values.

## Randomness and ordering

- Seed generators in the test (`random.seed(1234)`) and print the seed when it is random on purpose, so failures replay.
- Inject the random source; return fixed ids from a fake generator.
- Sort before comparing sets, maps, directory listings and unordered query results (`assert sorted(a) == sorted(b)`; `ORDER BY` in queries).

## Isolation and shared state

- Build fresh state per test: fixtures with function scope, factories, new objects in `setUp`/`beforeEach`.
- Give every test its own temporary directory (`tmp_path`, `t.TempDir()`, `mkdtemp`) and unique names/ids (`uuid4()` or the test name).
- Reset or restore singletons, caches and registries in teardown (`yield` fixtures, `afterEach`, `t.Cleanup`).
- Undo environment changes with scoped helpers (`monkeypatch.setenv`, `t.Setenv`, `vi.stubEnv`, `jest.replaceProperty`), never raw assignment.
- Database: run each test in a transaction that rolls back, or truncate known tables in setup; use separate schemas/databases per parallel worker.
- Do not let tests depend on the order of other tests. If tests really are steps of one scenario, make them one test.

## Ports, files and processes

- Bind servers to port 0 and read the chosen port; wait for a readiness signal (a health endpoint, a log line) instead of sleeping.
- Close sockets, files, servers and subprocesses in teardown, even on failure (`try/finally`, fixtures with `yield`, `afterAll`, `t.Cleanup`).
- Kill leftover child processes started by tests; assert the file-descriptor/thread count did not grow in leak-prone suites.

## Network and external services

- Fake the boundary (HTTP mock server, `responses`, `msw`, `httptest`) and keep a separate, clearly marked set of tests against the real sandbox, which is allowed to be slower and is not part of the main gate.
- Add a socket guard fixture that fails any real outbound connection in unit tests, so hidden calls are found.
- Replace shared remote resources with per-run ones (unique topic/bucket/prefix names).

## Concurrency

- If the product code has a race, fix it (lock, atomic operation, immutable data, single-writer queue) and add a deterministic test that forces the interleaving (barrier/latch, controlled scheduler).
- In tests, use barriers and events to order threads rather than sleeps; run with the race detector (`go test -race`) or sanitizers.
- Do not share mutable objects between parallel test workers.

## Floating point

`pytest.approx`, `math.isclose`, `toBeCloseTo`, `assertAlmostEqual`, `InDelta`; use `Decimal`/integers for money.

## UI and browser tests

- Use auto-waiting locators and assertions on visible state (role, text), not CSS selectors and fixed waits.
- Disable animations in the test environment; set a fixed viewport, locale and time zone; stub third-party scripts and time.
- Record trace/video/screenshot on failure in CI to diagnose the next occurrence.

## Environment differences

- Make paths and line endings platform-neutral (`pathlib`, `os.path.join`, `\n` handling); avoid case-sensitive assumptions.
- Set `TZ`, `LANG` and `PYTHONHASHSEED` explicitly in the test runner config so local and CI agree.
- Pin tool and dependency versions; reproduce in the CI image (a container with the same CPU limit) when it only fails there.

## What not to do

| Tempting | Why it fails |
|---|---|
| `@retry(3)` / "rerun failures" | hides the cause, hides real failures, doubles the time of the bad days |
| `sleep(5)` | slow, and still racy under load |
| widen a tolerance until it passes | the test no longer guards the behavior |
| `@skip` / delete | the risk remains and nobody remembers it |
| serialize the whole suite | slow, and the order dependence is still there |

## Quarantine (only if the user agrees, only temporarily)

Move the test to a clearly named group that runs but does not block (`@pytest.mark.quarantine`, a separate CI job), record: owner, ticket, reason, date, the failure rate and the plan to fix it, and a review date.
A quarantined test that nobody revisits is a deleted test.
