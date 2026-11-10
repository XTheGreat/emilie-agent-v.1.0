# Framework idioms

Use what the project already uses. Check the version in the lockfile before relying on a feature. Commands run the whole suite unless a path or filter is given.

## Python

**pytest** (`python -m pytest -q`, one test: `-k name` or `path::test_name`, stop at first failure: `-x`)

```python
import pytest
from billing import total, apply_discount

@pytest.mark.parametrize("price, code, expected", [
    (100, "A", 90), (100, "B", 80), (100, None, 100),
], ids=["A", "B", "none"])
def test_apply_discount(price, code, expected):
    assert apply_discount(price, code) == pytest.approx(expected)

def test_total_rejects_negative_tax():
    with pytest.raises(ValueError, match="tax"):
        total([], -1)

def test_writes_report(tmp_path):                 # tmp_path: a fresh directory per test
    out = tmp_path / "r.txt"
    write_report(out)
    assert out.read_text() == "ok\n"

def test_uses_env(monkeypatch):
    monkeypatch.setenv("MODE", "test")             # undone automatically
    assert mode() == "test"
```

- Fixtures (`@pytest.fixture`) for setup; `conftest.py` shares them. Scope `function` by default (isolated); widen only when safe.
- Freeze time with `freezegun`/`time-machine`, or better, pass a `now` parameter. `capsys`, `caplog` capture output and logs.
- Mock with `unittest.mock.patch` where the name is *used* (`patch("app.service.requests.get")`), not where it is defined.

**unittest** (`python -m unittest discover -v`): `class T(unittest.TestCase)`, `self.assertEqual`, `with self.assertRaises(E)`, `setUp/tearDown`, `subTest` for tables.

## JavaScript / TypeScript

**Jest / Vitest** (`npx jest`, `npx vitest run`; filter `-t "name"`; watch mode only for the user)

```ts
import { describe, it, expect, vi } from 'vitest';
import { applyDiscount } from './billing';

describe('applyDiscount', () => {
  it.each([[100, 'A', 90], [100, 'B', 80]])('%d with %s is %d', (p, c, want) => {
    expect(applyDiscount(p, c)).toBeCloseTo(want);
  });
  it('rejects an unknown code', () => {
    expect(() => applyDiscount(100, 'Z')).toThrow(/unknown code/);
  });
  it('sends the email once', async () => {
    const send = vi.fn().mockResolvedValue({ ok: true });
    await notify({ send }, 'a@b.c');
    expect(send).toHaveBeenCalledTimes(1);
  });
});
```

- Async: always `await` or `return` the promise; use `await expect(p).rejects.toThrow()`. Fake timers: `vi.useFakeTimers()` / `jest.useFakeTimers()` then restore.
- UI: Testing Library (`render`, `screen.getByRole`, `userEvent`) tests what the user sees; avoid querying by CSS class or internals.
- HTTP: `msw` or `nock` for the network boundary; `supertest` for Express handlers.
- Node's built-in runner: `node --test` with `node:test` and `node:assert/strict` (no dependencies).

## Go

`go test ./...` (`-run Name`, `-race` for data races, `-count=1` to bypass the cache, `-cover`).

```go
func TestApplyDiscount(t *testing.T) {
	cases := []struct{ name string; price float64; code string; want float64 }{
		{"A", 100, "A", 90}, {"B", 100, "B", 80}, {"none", 100, "", 100},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ApplyDiscount(c.price, c.code); got != c.want {
				t.Fatalf("got %v, want %v", got, c.want)
			}
		})
	}
}
```

Use `t.TempDir()`, `t.Setenv`, `httptest.NewServer`, interfaces for fakes, `t.Helper()` in helpers, `t.Cleanup` for teardown.

## Java / Kotlin

JUnit 5 (`mvn test`, `./gradlew test`, `-Dtest=ClassName#method`): `@Test`, `@ParameterizedTest` with `@CsvSource`, `assertThrows`, `@TempDir`, Mockito for collaborators (`verify` sparingly), Testcontainers for real databases.

## Rust

`cargo test` (`name_filter`, `-- --nocapture`). Unit tests in `#[cfg(test)] mod tests` beside the code; integration tests in `tests/`. `assert_eq!`, `#[should_panic(expected = "...")]`, `tempfile` crate for files, `proptest` for properties.

## .NET, Ruby, PHP

- .NET: xUnit (`dotnet test`), `[Theory]` with `[InlineData]`, `Assert.Throws<T>`.
- Ruby: RSpec (`bundle exec rspec`) or Minitest; `let`, `expect(...).to eq`, `allow(...).to receive`.
- PHP: PHPUnit (`vendor/bin/phpunit`), data providers, `expectException`.

## Databases, APIs and files in tests

- Prefer a real database in a container or an in-memory equivalent with the same engine features; roll back or truncate per test. Do not share rows between tests.
- For HTTP APIs, test at the router level (in-process test client) for speed, plus a few real-server tests.
- Use temp directories, never the project folder or the home directory. Clean up even when the test fails (fixtures/`finally`/`t.Cleanup`).
- Seed or inject random generators; log the seed on failure so it can be reproduced.

## Running subsets while developing

Run the failing test alone, then its file, then the package, then everything. Use the stop-on-first-failure flag while fixing, and always finish with the full suite.
