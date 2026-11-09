# Slicing work into tasks

## The walking skeleton

The thinnest end-to-end path that connects every major piece, with fake or minimal behavior: a button calls an endpoint that writes
one row and shows it back; the build and deploy pipeline runs; one test passes. It proves the architecture, the tooling and the
integration early, and gives every later slice a place to land.

## Vertical vs horizontal

| Horizontal (avoid) | Vertical (prefer) |
|---|---|
| "Create all tables" | "Store and show one order" |
| "Build the whole API" | "Create an order with one item via the API and the UI" |
| "Do the front end" | "Search returns results for one filter" |
| Done when the layer is finished | Done when a user-visible behavior works |

A vertical slice may touch five files in five layers and still be a few hours of work, because it implements only the smallest piece
of behavior.

## Ways to split a big item

1. **Workflow steps:** sign up, verify email, first login, profile. Ship the first step end to end before the next.
2. **Business rules:** full price, then discounts, then taxes, then rounding rules.
3. **Data variations:** one currency, then several; one file type, then others; one tenant, then many.
4. **Interface:** API first, then UI; or CLI first, then web; or read-only view before editing.
5. **Operations (CRUD):** read, create, update, delete; delete and bulk operations last.
6. **Happy path, then edge cases:** valid input first, then validation errors, then failure and retry paths.
7. **Simple then optimized:** correct and slow first with a measured target, then the optimization.
8. **Spike then build:** answer the single scary question first, time-boxed.
9. **Platform or environment:** one browser or OS first, then the rest.
10. **User role:** admin sees it first, then members, then guests.

A good slice is *independently demonstrable*, *testable*, and *valuable or risk-reducing* on its own.

## Typical invisible work (include as tasks)

- Tests: unit for rules, integration across boundaries, one end-to-end for the main path.
- Database migration plus rollback plus backfill (see `design-database`).
- Configuration, secrets, feature flag, environment variables and defaults.
- Logging, metrics, alert for the new behavior.
- Documentation: README, API docs, runbook, changelog entry.
- Code review and the fixes it prompts; rebase and merge conflicts for long branches.
- Deployment, smoke test, rollback plan, communication to users or teams.
- Cleanup: removing the flag, the old code path, temporary scripts.
- Data fixes for existing records and handling of old clients.

## Spikes (time-boxed learning)

Format: **question, time box, output**. "Can the vendor SDK upload 100 MB files without timeouts? 3h. Output: a yes/no and a note of
the limits." Spike results are decisions or facts, not production code. If the box expires without an answer, report what you learned
and re-plan; do not extend silently.

## Ordering heuristics

1. Walking skeleton.
2. Spikes that could kill or reshape the plan.
3. Blockers other tasks wait for (shared interfaces, schema, auth).
4. Highest value or highest risk slices.
5. Variations and edge cases.
6. Polish, optimization, cleanup, documentation (documentation of the core path should still happen alongside it).

Put independent tasks in different waves of work so several people or agents can work in parallel (`task_graph.py` shows the waves).
Avoid two tasks editing the same files at the same time.

## Task quality checklist

- Title says the outcome: "Order total includes shipping" (not "Shipping work").
- One owner, one finish line, runnable check in `done:`.
- Fits in a day; if not, split or justify.
- Names the files, functions or endpoints it touches when known (verified in the code).
- States what it depends on and what it unblocks.
- Includes the tests it needs.
