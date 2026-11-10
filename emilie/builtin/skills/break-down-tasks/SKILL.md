---
name: break-down-tasks
phase: rencana
description: Turn a goal, spec or design into an ordered plan of small, verifiable tasks - vertical slices that each end in something working, explicit dependencies, estimates with uncertainty, acceptance checks, risks pulled forward, and a milestone order. Includes a script that validates the plan (cycles, oversized or unchecked tasks), shows parallel waves and the critical path. Not for gathering requirements (clarify-requirements) or doing the work (build-feature). Triggers - "break this down", "task breakdown", "plan the work", "implementation plan", "split into tasks", "roadmap", "milestones", "estimate this", "how long will it take", "what are the steps", "work breakdown".
---

# Break down tasks

**Goal:** a plan another person (or a later session) can execute without asking: small steps in a sensible order, each with a
clear finish line, with the risky parts early and the uncertainty visible.

## Ground rules

1. **Know what "done" means for the whole goal.** Restate the outcome and its acceptance criteria first. If they are vague,
   load `clarify-requirements`; do not slice a fog.
2. **Read the code before you plan the work.** For existing systems, find the real files, interfaces and tests the change touches
   (use `trace-code` / `project-overview`). Plans made from memory name things that do not exist.
3. **Vertical slices, not layers.** Each task delivers a thin, working path through the stack (UI to storage), not "all the
   database", then "all the API", then "all the UI". Slices can be demoed and can change direction cheaply.
4. **Small and checkable.** A task fits in about a day (ideally 1 to 4 hours), has one owner, and ends in a check anyone can
   run: a test, a command and its output, a screenshot. Bigger than a day means split.
5. **Risk first.** Do the unknown, the integration with outside systems and the hard technical bet early, as a spike with a time box.
   Never leave the scariest part for the last week.
6. **Dependencies are explicit.** Write which task waits for which. Hidden dependencies cause the "blocked" surprises.
7. **Estimates are ranges with a confidence, not promises.** Estimate effort, not calendar time; mark unknowns as `?` and
   plan a spike to remove them; add a buffer; re-plan after the first slice.
8. **Include the invisible work.** Tests, migrations, configuration, documentation, review, deployment, monitoring, cleanup of
   temporary code, and data backfills are tasks, not afterthoughts.
9. **Order for learning and for value.** Walking skeleton first, then the slices that deliver the most value or retire the most risk.
10. **The plan is a living document.** State what would trigger re-planning. Do not start building until the user agrees with the plan,
    unless they asked for both.
    If a script could not be run (needs approval, missing runtime, no network), say "not run" and why; never describe a plan, schema or contract as validated or linted unless the tool actually ran.

## Procedure

### Step 1 - Restate the goal and its limits

Write: the outcome in one or two sentences, the acceptance criteria (observable), what is explicitly out of scope, the deadline
or capacity (people, hours, anything fixed), and the constraints (must not break X, must ship behind a flag, no downtime). Ask the
user once for what is missing and matters; otherwise list assumptions.

### Step 2 - Ground the plan in the code

Skip for greenfield. Otherwise find the files, modules, tests and interfaces the work touches, and note existing patterns to follow
and fragile areas to avoid. Run `git log --oneline -- <path>` on key files to see recent churn. Record each touched component so
tasks can name real paths.

### Step 3 - Find the slices

Use `references/slicing.md`. Start with the **walking skeleton**: the thinnest end-to-end path that proves the pieces connect (even
with hard-coded data). Then list slices by user-visible behavior or business rule (for example "guest can place an order with one item",
then "with several items", then "with a discount code", then "failed payment path"). Split by: workflow step, business rule, data
variation, interface, operation (create before edit/delete), performance, or happy path before edge cases. Do not split by layer.

### Step 4 - Write the tasks

For each task write a one-line **outcome-based title** and the line format the script reads:

```
- [ ] T3 | POST /orders creates an order for one item | 4h | after: T1, T2 | done: contract test passes and the row is in the table
```

Each task has: an id, an outcome title (not "work on API"), an estimate (`30m`, `2h`, `1d`, or `?`), its dependencies, and a `done:`
check. Where useful add the files to touch and the test to write. Add the invisible work from rule 8 as its own tasks. Spikes
are tasks with a time box and a question to answer ("Can the vendor SDK stream 1 MB payloads? 2h").

### Step 5 - Estimate honestly

Use `references/estimation.md`: estimate effort per task as a most-likely value, flag anything below about 70% confidence, and
split or spike what you cannot estimate. Use ranges for the total (best, likely, worst). Compare with similar past work in the
repository history when you can (`git log`). State what is not included (review wait time, meetings, deployment windows).

### Step 6 - Validate and order

Save the task lines to a file in a scratch folder or the project's docs, and run:

```
python "<this skill's directory>/scripts/task_graph.py" <plan-file> [--workers N]
```

It rejects cycles, unknown dependencies and duplicate ids; warns about tasks with no estimate, over one day, without a `done:` check or with
vague titles; flags bottleneck tasks; and prints the build order as waves of tasks that can run in parallel, the critical path, the
total effort and the shortest possible duration. Fix every error and each warning you can, or explain it. Re-run until clean.

### Step 7 - Identify risks and milestones

List the top risks (unknown technology, external dependency, data quality, performance, unclear owner) with a mitigation or an early
spike for each, and the signal that tells you it is going wrong. Group the waves into 2 to 4 **milestones**, each a state you can
demonstrate (for example "skeleton running in staging", "core flow works", "edge cases and polish", "released"), and name the cut line:
what drops first if time runs out.

### Step 8 - Present and hand off

Deliver using `references/plan-template.md`: goal, assumptions, out of scope, milestones, the task table with order and estimates,
risks, and open questions. Keep it as short as the work allows. Ask the user to confirm or adjust. Offer to start with
`build-feature` (the first wave), or to record the plan in the project's task tracker or in Emilie's `tasks`. Mark each task finished
(`[x]`) as work completes and re-run the script to see what is ready next.

## Definition of done

- [ ] The goal, acceptance criteria, scope limits and constraints are written.
- [ ] Tasks are vertical slices with outcome titles; none is bigger than a day without a stated reason.
- [ ] Every task has an estimate (or is a spike with a time box), explicit dependencies and a `done:` check.
- [ ] Tests, migration, configuration, docs and deployment appear as tasks.
- [ ] `task_graph.py` reports no errors; each warning is fixed or explained.
- [ ] Risky or unknown work is in the first waves, with risks and mitigations listed.
- [ ] Milestones are demonstrable, and the cut line is named.
- [ ] Tasks that name files or functions were checked against the code (Checked), not guessed.

## Pitfalls

- **Layer slicing.** Nothing works end to end until the last task, so integration problems surface at the end.
- **Vague tasks** ("Handle errors", "Refactor", "Backend") that can never be finished or verified.
- **One 3-week task.** Progress becomes invisible; estimates become fiction.
- **No `done:` check.** The task is finished when someone says so, which is when arguments start.
- **Hidden work.** Migration, tests, review, release and rollback missing from the plan.
- **Optimistic single numbers.** Estimates are distributions; the tail is where schedules die. Show a range.
- **Risk last.** The integration or spike that could invalidate the design is saved for the end.
- **Planning past what you know.** Detail the next wave; keep later ones coarse and refine them as you learn.
- **Over-planning.** A two-hour change does not need a Gantt chart: three bullets are enough.
- **Dependencies on people, not tasks.** "Wait for Sam" is a risk; write the thing Sam must deliver.

## Hand-offs

| Next | Load |
|---|---|
| requirements are unclear | `clarify-requirements` |
| need the design first | `design-architecture`, `design-database`, `design-api`, `design-ui-ux` |
| start the first slice | `build-feature` |
| new project skeleton | `scaffold-project` |
| big migration or upgrade | `migrate-code`, `upgrade-dependencies` |
| record decisions | `write-adr` |
