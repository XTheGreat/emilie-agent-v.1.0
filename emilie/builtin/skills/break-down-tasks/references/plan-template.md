# Implementation plan template

Copy, fill in, delete what does not apply. A small change needs only sections 1, 4 and 5. Mark facts: **Given**, **Checked**,
**Assumed**, **Unknown**.

---

# <Goal> - implementation plan

**Status:** draft | agreed | in progress  **Owner:** <name>  **Date:** <YYYY-MM-DD>

## 1. Goal and acceptance

**Outcome:** <one or two sentences>
**Acceptance criteria:**
- [ ] <observable check 1>
- [ ] <observable check 2>

**Out of scope:** <list>
**Constraints:** <deadline, capacity, must not break, flag/rollout rules>
**Assumptions:** <list, each with how to verify>

## 2. Where the change lands (from the code)

| Component | Files / modules | Notes (pattern to follow, fragile area) |
|---|---|---|

## 3. Approach in brief

Two to five sentences: the walking skeleton, then the order of slices, and the design decisions this relies on
(link to the architecture, database and API documents).

## 4. Tasks

Plan lines (validated with `scripts/task_graph.py`):

```
- [ ] T1 | Walking skeleton: button -> endpoint -> row -> shown back | 4h | after: - | done: demo works locally, one test passes
- [ ] T2 | Spike: vendor SDK handles 100 MB uploads | 2h | after: - | done: yes/no and limits written in the plan
- [ ] T3 | ... | ... | after: T1 | done: ...
```

| Wave | Tasks | Notes |
|---|---|---|
| 1 | T1, T2 | parallel; T2 may reshape T5 |

**Critical path:** <from the script>   **Effort:** <total>   **Duration with N workers:** <range>   **Buffer:** <x%>

## 5. Milestones

| # | Demonstrable state | Tasks | Target |
|---|---|---|---|
| M1 | Skeleton running in staging | T1 to T3 | |
| M2 | Core flow works end to end | T4 to T8 | |
| M3 | Edge cases, docs, monitoring | T9 to T14 | |
| M4 | Released and verified | T15 | |

**Cut line:** if time runs out, drop <items> first.

## 6. Risks

| Risk | Likelihood | Impact | Mitigation / early spike | Warning sign |
|---|---|---|---|---|

## 7. Rollout and rollback

Flag, staged rollout, monitoring to watch, how to roll back, who decides.

## 8. Open questions

| # | Question | Owner | Blocks |
|---|---|---|---|

## 9. Re-plan triggers

List what causes a re-plan (a spike result, scope change, critical-path slip beyond the buffer) and who is told.
