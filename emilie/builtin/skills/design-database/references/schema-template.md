# Database design template

Copy, fill in, delete what does not apply. Mark facts: **Given**, **Checked**, **Assumed**, **Unknown**.

---

# <System> - data model

**Engine/version:** <e.g. PostgreSQL 16>  **Status:** draft | proposed | accepted  **Date:** <YYYY-MM-DD>

## 1. Summary

What data this holds, the main entities, and the one or two modeling decisions that matter most.

## 2. Rules that must always hold

| # | Rule (sentence) | Enforced by |
|---|---|---|
| R1 | An order has at least one line | application + test (cannot be a single-table constraint) |
| R2 | Email is unique per tenant | `UNIQUE (tenant_id, email)` |
| R3 | Quantity is positive | `CHECK (qty > 0)` |

## 3. Entities and relationships

```
tenant 1---* user
user   1---* order 1---* order_line *---1 product
```

Cardinality and optionality notes; delete behavior for each relationship.

## 4. Tables

### `orders`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | bigint identity | no | | primary key |
| tenant_id | bigint | no | | FK tenants(id) ON DELETE RESTRICT |
| user_id | bigint | no | | FK users(id) ON DELETE RESTRICT |
| status | text | no | 'new' | CHECK in ('new','paid','shipped','cancelled') |
| total_minor | bigint | no | | amount in minor units; currency in `currency` |
| currency | char(3) | no | | ISO 4217 |
| created_at | timestamptz | no | now() | |

Constraints: ... Sensitivity: ... Retention: ...

(Repeat per table.)

## 5. Indexes

| Index | Columns | Serves (query) | Notes |
|---|---|---|---|
| orders_tenant_status_created | (tenant_id, status, created_at) | "open orders for a tenant, newest first" | covers the dashboard |
| order_lines_order_id | (order_id) | load a basket; FK | |

Key queries (SQL) and their `EXPLAIN` summaries, if run.

## 6. Denormalization and derived data

| Value | Source | Why it exists | How it stays correct |
|---|---|---|---|

## 7. Privacy and security

Columns by class (personal, sensitive), purpose, retention, deletion path, encryption/masking, who may read.

## 8. Volume and growth

Rows per table now and in 12 months (assumed or measured), hot spots, partition or archive plan, backup and restore targets.

## 9. Migration plan

| Step | Change | Safe with old code? | Rollback | Verification |
|---|---|---|---|---|
| 1 expand | | | | |
| 2 backfill | | | | |
| 3 switch | | | | |
| 4 contract | | | | |

## 10. Linter output

Paste the `schema_lint.py` summary for the proposed DDL and the disposition of every warning (fixed / accepted + reason).

## 11. Risks and open questions

| # | Item | Owner / next step |
|---|---|---|
