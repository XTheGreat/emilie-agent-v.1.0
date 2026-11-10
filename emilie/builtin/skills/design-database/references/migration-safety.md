# Safe schema changes

The aim: every deploy works with both the old and the new code, so you can roll the application back without touching data.
Pattern: **expand -> migrate/backfill -> switch -> contract**, each its own deploy.

## Lock awareness

Check what the engine does for each statement and version: some `ALTER`s rewrite the table or hold an exclusive lock that
queues every read behind it. Confirm in the docs for the version in use (Postgres, MySQL/InnoDB and SQLite differ a lot).
On large tables set a lock timeout and a statement timeout and retry, rather than waiting indefinitely.

## Recipes

| Change | Safe sequence |
|---|---|
| Add a nullable column | Add it (cheap). Code writes it. Backfill in batches. Later add `NOT NULL` once all rows are filled (Postgres: add a `CHECK ... NOT VALID`, then `VALIDATE`, then set `NOT NULL`). |
| Add a column with a default | On modern engines often cheap; on older ones it rewrites the table. Add nullable, backfill, then set the default. |
| Rename a column or table | Add the new name, write both, backfill, switch reads, stop writing the old, drop later. Never rename in place while old code runs (a view or generated column can bridge). |
| Change a column type | Add a new column of the new type, dual-write, backfill in batches, switch reads, drop the old. Widening (int to bigint) is the common case and rewrites the table in many engines. |
| Drop a column | First deploy code that no longer reads or writes it. Then drop in a later release. |
| Add an index | Build without blocking writes (`CREATE INDEX CONCURRENTLY` in Postgres, online DDL in MySQL). Cannot run inside a transaction in some engines; check. |
| Add a foreign key | Add it unvalidated (`NOT VALID`), clean the data, then validate. Ensure the child column is indexed. |
| Add a unique constraint | First find duplicates with a query and resolve them; then create a unique index concurrently, then attach it. |
| Split a table | Create the new table, dual-write, copy history in batches, switch reads, stop the old writes, drop later. |
| Delete lots of rows | Batches (for example 1,000 to 10,000 rows), with pauses; avoid one huge transaction (locks, replication lag, log growth). |

## Backfills

- Idempotent and resumable (safe to run twice, can continue from a checkpoint such as the last processed id).
- Batched, ordered by an indexed key, sleeping between batches; watch replication lag and lock waits.
- Run as a job, separate from the schema migration.
- Verify afterwards with counts and sampled comparisons; keep the query used.

## Every migration file states

1. What it changes and why.
2. Safe while old code runs? (yes/no and what it depends on)
3. Expected duration and locking on production-size data (measured on a copy if possible).
4. Rollback: the exact reverse, or "forward-fix only" with the reason.
5. Verification: the query that proves it worked.

## Process

- Test migrations on a copy of production-shaped data, including the rollback.
- Back up (or confirm point-in-time recovery) before a destructive step; confirm that restore works.
- Run in a quiet window if locks are unavoidable; have someone watching metrics.
- Keep migrations immutable once released; fix forward with a new one.
- Keep schema changes and large data changes in separate migrations.
- Seed and test data live apart from production migrations.
