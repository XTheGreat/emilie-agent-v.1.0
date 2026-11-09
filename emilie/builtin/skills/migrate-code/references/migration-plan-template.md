# Migration plan template

Copy, fill in, delete what does not apply. Mark facts: **Given**, **Checked**, **Assumed**, **Unknown**.

---

# Migrate <from> to <to> - plan

**Status:** draft | agreed | in progress | done  **Owner:** <name>  **Date:** <YYYY-MM-DD>

## 1. Why and what

- **From:** <name and exact version>   **To:** <name and exact version>
- **Reason / deadline:** <end of support date, security issue, ...>
- **Scope:** <apps, packages, folders>   **Out of scope:** <list>
- **Must not change:** <public API, data format, behavior>
- **Exit criterion:** old usage = 0 in source, tests, docs, config; old dependency removed; guard in place.

## 2. Breaking changes that affect us

| Change (source: guide/changelog + version) | Where in our code | How to adapt | Tool (codemod / manual) |
|---|---|---|---|

## 3. Size (from `usage_inventory.py`)

Command used: `python usage_inventory.py --old "<regex>" --new "<regex>" <path>`

| Form of old usage | Count | Files | Replacement rule |
|---|---|---|---|

Totals: <hits> in <files> files (source <n>, tests <n>, docs <n>, config <n>). Hand-searched extras: <dynamic access, generated code, other repos, scripts>.

## 4. Strategy

Chosen: <in place / adapter / strangler / shadow / flag / rewrite>. Reason: <...>.
Coexistence mechanism: <adapter module path, flag name>. Guard against new old-API use: <lint rule/test>.

## 5. Batches

| # | Batch | Why this order | Verification | Rollback |
|---|---|---|---|---|
| 0 | Baseline + characterization tests + adapter | | tests green | revert |
| 1 | <leaf modules> | low risk, proves the pattern | | |
| 2 | <shared core> | | | |
| 3 | tests, docs, config | | | |
| 4 | remove old dependency and shim | | inventory = 0 | |

## 6. Behavior parity checks

| Behavior | How compared (test / snapshot / shadow) | Result | Decision |
|---|---|---|---|

## 7. Risks

| Risk | Likelihood | Impact | Mitigation | Signal |
|---|---|---|---|---|

## 8. Progress log

| Date | Inventory (old / new) | Notes |
|---|---|---|

## 9. Done checklist

- [ ] Inventory old = 0 (source, tests, docs, config, scripts, CI)
- [ ] Old dependency, config and flags removed; lockfile updated
- [ ] Adapter/shim removed; temporary tests removed
- [ ] Full verification on a clean checkout (tests, lint, types, build)
- [ ] Docs and README updated; guard added; ADR written
