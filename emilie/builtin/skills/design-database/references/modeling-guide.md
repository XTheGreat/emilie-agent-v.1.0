# Modeling guide

## Process in one page

1. Entities: nouns with their own identity and lifecycle (Customer, Order, Invoice).
2. Relationships: verbs between them, with cardinality and optionality on each side.
3. Attributes: facts about one entity. If a fact depends on another attribute rather than on the key, it belongs elsewhere.
4. Rules: write them as sentences, then as constraints.
5. Queries: write the SQL for the reads and writes that matter, then index (see SKILL.md Step 5).

## Normalization (use as a checklist)

- **1NF:** one value per column, no repeating groups (`tag1, tag2, tag3` or comma-separated lists belong in a child table).
- **2NF:** in a table with a composite key, every attribute depends on the whole key.
- **3NF:** attributes depend on the key, not on each other (`zip -> city` suggests a separate table, or accept it knowingly).
- **Denormalize** only for a named query, with a rule for staying correct. Typical: a stored total updated in the same
  transaction, a read model rebuilt from events, a snapshot of the price at purchase time (that last one is *not*
  denormalization: it is a historical fact and must be copied).

## Keys

| Choice | Good | Careful |
|---|---|---|
| Auto-increment integer | compact, fast, ordered | guessable in URLs; hard to merge databases |
| UUID v4 | no coordination, hard to guess | random order hurts insert locality in B-trees; larger |
| UUID v7 / ULID | time-ordered and unique | check library and database support |
| Natural key | no extra column | changes over time; risks duplicates; avoid as primary |

Rules: every table has a primary key; use a **surrogate** primary key plus **unique constraints** on natural identifiers;
keys are never reused; the foreign key type equals the referenced key type exactly; expose public ids (slugs, UUIDs) separately
if internal integers must not leak.

## Types

| Data | Use | Avoid |
|---|---|---|
| Money | `NUMERIC(p,s)` / `DECIMAL`, or integer minor units plus a currency code | `FLOAT`, `DOUBLE`, `REAL` |
| Instant in time | `TIMESTAMP WITH TIME ZONE` / UTC, ISO-8601 in JSON | local time without a zone; text dates |
| Calendar date (birthday) | `DATE` | timestamp at midnight |
| Duration | `INTERVAL` or integer seconds with the unit in the name | strings like "2h" |
| Boolean | `BOOLEAN` (SQLite: `INTEGER` 0/1 with `CHECK`) | `'Y'/'N'` text |
| Enumerated state | `CHECK (status IN (...))`, native enum, or a lookup table | free text |
| Free text | `TEXT` with a length `CHECK` if bounded | oversized `VARCHAR(255)` out of habit |
| Identifiers | the key's own type | numbers stored as text (leading zeros belong in text: phone, postcode) |
| Flexible payload | `JSON/JSONB` for opaque, rarely filtered data | JSON for data you join or constrain |
| Large files | object storage plus a reference column | blobs in the main table |

Unknown engine details (SQLite is dynamically typed, MySQL `TIMESTAMP` range, Postgres `JSONB` indexes): check the docs for
the version in use.

## Constraints

- `NOT NULL` by default; allow null only when absence is meaningful and documented.
- `UNIQUE` for every natural identifier; "unique per parent" as a composite (`UNIQUE (tenant_id, email)`).
- `CHECK` for ranges and states (`qty > 0`, `end_at > start_at`).
- Foreign keys always, with the delete rule chosen on purpose:
  - `RESTRICT`/`NO ACTION`: the parent cannot be deleted while children exist (default for valuable data).
  - `CASCADE`: children are meaningless without the parent (order lines of an order). Cascades are silent; use sparingly.
  - `SET NULL`: the link is optional history.
- Partial unique indexes enforce "one active row per X" (`UNIQUE (user_id) WHERE active`), where the engine supports them.

## Indexes

- A foreign key gets an index that **starts with** the key.
- Composite order: equality columns, then range column, then sort column. `(tenant_id, status, created_at)`.
- Unique constraints already create an index; do not add another on the same columns.
- Covering/partial/expression indexes are tools for measured problems, not defaults.
- Every index costs write time and space; drop unused and redundant (prefix) ones.
- Confirm with `EXPLAIN` on realistic row counts. A table of 100 rows will scan whatever you build.

## Common patterns

- **Many-to-many:** join table with the two foreign keys as a composite primary key (or unique), plus attributes of the link
  (role, added_at). Index the second column too if you query from that side.
- **Hierarchy (tree):** adjacency list (`parent_id`) for simple cases and recursive queries; closure table or materialized
  path when you read subtrees often; avoid nested sets unless reads dominate heavily.
- **History / audit:** append-only `*_history` table with `valid_from/valid_to`, or an event log. State who and when. Do not
  overwrite facts you may need to explain later (price at order time, address on an invoice).
- **Soft delete:** `deleted_at` plus partial unique indexes and a default filter (view or query helper); or move rows to an
  archive table. Decide separately how privacy deletion works (it must really delete).
- **Multi-tenancy:** `tenant_id` on every tenant-owned table, part of unique constraints and the leading column of
  indexes; enforce isolation in the data layer (row-level security or mandatory scoped queries), not only in the UI.
- **Flexible attributes:** typed columns for what you query; one `JSONB` column for the long tail; avoid entity-attribute-value.
- **State machine:** `status` with a `CHECK`, a `status_changed_at`, and a transitions table or code-level guard; log transitions
  if audits matter.
- **Ordering of items:** an explicit `position` integer (or fractional index) rather than relying on insert order.
- **Idempotency / deduplication:** a unique key on the external id or idempotency key.
- **Counters:** compute on read, or maintain in the same transaction; for hot counters use sharded or buffered updates.
- **Money ledger:** immutable entries with debit/credit and a balancing rule; balances are derived.

## Naming

One convention, applied everywhere: `snake_case`, singular or plural tables (pick one), `id` as primary key,
`<entity>_id` for foreign keys, `*_at` for timestamps, `is_`/`has_` for booleans, units in names (`size_bytes`, `duration_s`).
Avoid reserved words and quoted mixed case. Follow the existing convention if the project has one.

## Privacy

Mark each column: public, internal, personal, sensitive (health, finance, credentials). For personal data decide purpose,
retention period, deletion path (including backups and logs), who can read it, and whether to encrypt or tokenize it.
Never store plain passwords (salted slow hash), card numbers (use a payment provider's tokens) or secrets.
