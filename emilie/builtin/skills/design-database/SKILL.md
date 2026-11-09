---
name: design-database
phase: rencana
description: Design or review a data model - entities and relationships from the real workflows, keys, types, constraints and indexes chosen deliberately, normalization with justified exceptions, a safe migration path, and the main queries checked against the indexes. Includes a schema linter for SQL files and SQLite databases. Not for picking a database product by itself (evaluate-technology) or for HTTP interfaces (design-api). Triggers - "design the database", "database schema", "data model", "ER diagram", "tables for", "add a column", "which indexes", "normalize", "migration plan", "review this schema".
---

# Design database

**Goal:** a data model that keeps the data correct (the database refuses bad states), answers the real queries quickly,
and can change without downtime or data loss.

## Ground rules

1. **Workflows and queries first.** List what the system must store, the 5 to 10 most important reads and writes, and the
   rules that must always hold. A model drawn from nouns alone misses the queries and the rules.
2. **The database is the last line of defence.** Enforce what you can in the schema: primary keys, `NOT NULL`, foreign keys,
   unique constraints, `CHECK`s. Application code is bypassed by scripts, imports and other services.
3. **Existing schema first.** If tables exist, read them (Step 2) and follow their conventions unless you state why not.
   Never guess a column name or type: read the migration or run the linter.
4. **Normalize first, denormalize for a measured reason.** Start at third normal form. A copied or precomputed value needs a
   named query it speeds up, a rule for keeping it correct, and a note in the design.
5. **Every change is a migration.** Describe changes as ordered, reversible steps that are safe on a live system
   (`references/migration-safety.md`). No hand-edited production schema.
6. **Money, time and identity are not afterthoughts.** Decimal or integer minor units for money (never floats); timestamps
   with a stated time-zone rule (store UTC); stable surrogate keys that carry no business meaning.
7. **Personal data is a liability.** Mark sensitive columns, store the minimum, state retention and deletion, and never keep
   plain passwords, card numbers or secrets.
8. **Name the engine and version.** Features differ (partial indexes, `JSONB`, generated columns, `ALTER` locking). If unknown,
   ask once or state the assumption.
9. **No data changes without a go-ahead.** This skill designs and writes migration files; it does not run them against a real
   database unless the user says so, and never against production.
10. **Mark each fact** as **Given**, **Checked** (read from schema or code), **Assumed** or **Unknown**.
    If a script could not be run (needs approval, missing runtime, no network), say "not run" and why; never describe a plan, schema or contract as validated or linted unless the tool actually ran.

## Procedure

### Step 1 - Gather what the data must do

Write down in a few lines: the engine and version, the entities the business talks about, the workflows that create and
change them, the **rules that must always be true** ("an order has at least one line", "email is unique per tenant", "stock
never goes below zero"), expected volume and growth, retention and privacy rules, and who reads the data (the app, reports,
other services). Ask once for what is missing and matters.

### Step 2 - Read what exists

Skip for a new database. Otherwise:

1. Find the schema source: migration folders, `schema.sql`, ORM models (`models.py`, `schema.prisma`, entity classes), or a
   development database file.
2. Lint what is in SQL or SQLite form:
   ```
   python "<this skill's directory>/scripts/schema_lint.py" <file.sql | folder | file.db> [...]
   ```
   It prints each table with its primary and foreign keys, then flags: no primary key, unindexed foreign keys, mismatched key
   types, float money, dates stored as text, plain-looking passwords and secrets, free-text status columns, join tables
   without a composite key, duplicate or redundant indexes, and missing `ON DELETE` rules. Every finding is a question to
   answer, not a verdict. ORM-only definitions are not read: read those files yourself.
3. Note the conventions: key type, naming, timestamp columns, soft-delete style, how tenants are separated.

### Step 3 - Model the entities

For each entity: its identity (the key), its attributes with types, and what it is **not** (do not merge two things that
change for different reasons). For each relationship: cardinality (one-to-one, one-to-many, many-to-many), whether each side
is optional, and what happens to the children when the parent is deleted or archived. Use `references/modeling-guide.md`
for keys, types, constraints and the common patterns (many-to-many, hierarchies, history, soft delete, multi-tenancy,
flexible attributes, state machines).

### Step 4 - Decide constraints and types

Per table, write the primary key, the foreign keys with their `ON DELETE` behavior, unique constraints (including
"unique per tenant"), `NOT NULL` for everything that is always present, defaults, and `CHECK`s for value ranges and states.
Choose types on purpose (`references/modeling-guide.md`, section Types). Record anything you intentionally leave to the
application and why.

### Step 5 - Design indexes from the queries

Take the queries from Step 1, write each as SQL, and give it an index that serves its filter, join and sort, or say why it
needs none. Foreign keys need an index that starts with the key. Prefer few, composite, well-ordered indexes (equality columns
first, then range, then sort) over many single-column ones, because each index slows writes and costs space. Verify with the
engine's plan (`EXPLAIN`) on realistic data volume when a database is available, and report what you ran.

### Step 6 - Consider scale, safety and operations

Note growth hot spots (large append-only tables, hot rows, counters), whether partitioning or archiving is needed, locking
behavior of planned changes, backup and restore, and how sensitive fields are protected (encryption, masking in logs, access
roles). Keep this to what the numbers justify.

### Step 7 - Plan the migration

Write ordered steps using `references/migration-safety.md`: expand (add nullable or defaulted, new tables, new indexes built
without blocking), backfill in batches, switch the code, contract (drop old). Each step names its rollback and whether it is
safe while the old code is still running. For data-moving changes, state how you will verify counts and sample rows before
and after. Write the migration files in the project's own tool and style; do not run them unless asked.

### Step 8 - Write the design

Use `references/schema-template.md`: summary, rules list, entity diagram (text), table definitions, index table with the query
each serves, migration plan, risks and open questions. Run the linter over the proposed DDL before presenting it, and fix or
explain every warning. Save it where the project keeps docs or offer a path.

### Step 9 - Hand off

Offer `design-api` (shapes built on this model), `write-adr` for notable choices, `break-down-tasks`, and `migrate-code` or
`build-feature` to implement.

## Definition of done

- [ ] The rules that must always hold are listed and each is enforced by a constraint, or its exception is stated.
- [ ] Every table has a primary key; every foreign key has an index and an explicit `ON DELETE` choice.
- [ ] Types are deliberate: decimal or integer money, real timestamps, no free-text state without a constraint.
- [ ] Each important query has an index or a reason it needs none, ideally confirmed with `EXPLAIN`.
- [ ] Denormalized values are listed with the query they serve and how they stay correct.
- [ ] The migration plan is ordered, reversible and safe on a live system, and nothing was run on real data.
- [ ] The linter was run on existing and proposed schema, and every warning is fixed or explained.
- [ ] Sensitive columns are marked, with retention and protection stated.

## Pitfalls

- **Modeling from the screen.** The UI shape is not the data shape. Model entities and rules, then derive views.
- **One giant "data" or JSON column** for things you will filter, join or constrain. Use it only for truly free-form payloads.
- **Natural keys as primary keys** (email, phone, national id). They change. Use a surrogate key and a unique constraint.
- **Nullable everything.** Each nullable column doubles the states to reason about. Make absence a deliberate choice.
- **Soft delete without a plan.** Unique constraints, joins and reports all need to ignore deleted rows; use partial unique
  indexes or archive tables.
- **Floating-point money; local-time timestamps; booleans stored as text.**
- **Index everything.** Slows every write and bloats memory; index for queries you can name.
- **Counters and totals computed from a stale copy.** Derive them, or update them in the same transaction as the source.
- **Big-bang migrations.** Renames and type changes that lock a hot table. Use expand and contract.
- **Trusting the ORM to hide the database.** Check the SQL it generates for the hot paths (N+1 queries, full scans).

## Hand-offs

| Next | Load |
|---|---|
| overall structure | `design-architecture` |
| interfaces over the model | `design-api` |
| record a decision | `write-adr` |
| implement and migrate | `build-feature`, `migrate-code` |
| plan the work | `break-down-tasks` |
| slow query in production | `profile-performance`, `debug-production` |
