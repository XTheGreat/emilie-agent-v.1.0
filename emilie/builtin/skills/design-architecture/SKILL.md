---
name: design-architecture
phase: rencana
description: Design the structure of a new system, service or major feature - drivers and constraints first, the simplest architecture that meets them, component boundaries and responsibilities, data and control flow, failure modes, a quality-attribute check, and the decisions worth recording. Also reviews existing structure (cycles, coupling) with measured data. Not for choosing a library (evaluate-technology), schemas (design-database), endpoints (design-api) or screens (design-ui-ux). Triggers - "design the architecture", "system design", "how should we structure", "architecture for", "service boundaries", "monolith or microservices", "high-level design", "is this architecture ok".
---

# Design architecture

**Goal:** produce a structure the team can build, run and change: the smallest design that satisfies the real drivers,
with boundaries in the right places, failure handled on purpose, and every important decision traceable to a reason.

## Ground rules

1. **Drivers first.** Architecture is the response to requirements, scale, constraints and team. List them before drawing a
   box. If the needs are unclear, load `clarify-requirements` first; do not invent them.
2. **Simplest thing that meets the drivers.** Start from one deployable unit, one database and the stack the team already
   knows. Add a queue, cache, service split or new datastore only when a named driver forces it.
3. **Numbers or "unknown".** Scale, latency and availability targets must come from the user or be marked as assumptions with
   the value you used. Never design for "millions of users" because it sounds serious.
4. **Read before you design.** In an existing codebase, run the structure review (Step 2) and read the entry points first.
   Fit the design to what is there, and say where you deliberately depart from it.
5. **Boundaries follow change and ownership.** Split where things change for different reasons, at different speeds, or
   under different owners, not where the nouns happen to differ.
6. **Every box has one job and an owner.** If you cannot state a component's responsibility in one sentence, the boundary is
   wrong.
7. **Design the failures.** For each dependency say what happens when it is slow, down, or wrong. A diagram with only happy
   paths is not a design.
8. **Mark each fact.** **Given** (the user said so), **Checked** (read in the code or ran it), **Assumed** (your choice, stated),
   **Unknown**. Do not blur them.
9. **Record the decisions.** A choice with real alternatives gets a short rationale; offer `write-adr` for the big ones.
10. **No code changes.** This skill produces a design document. Implementation is `build-feature` or `scaffold-project`.
    If a script could not be run (needs approval, missing runtime, no network), say "not run" and why; never describe a plan, schema or contract as validated or linted unless the tool actually ran.

## Procedure

### Step 1 - Frame the problem

Write, in a few lines: what the system does and for whom, the **top 3 to 5 quality attributes** in priority order (from
`references/quality-attributes.md`: for example correctness, availability, latency, cost, security, changeability), the hard
constraints (language, hosting, budget, compliance, deadline, team size and skills), and the numbers you have or are assuming
(users, requests per second, data volume and growth, read/write ratio, acceptable downtime). Ask the user once for what is
missing and matters; otherwise list it under Assumptions.

### Step 2 - Understand what exists

Skip for a greenfield project. Otherwise:

1. Run `project-overview` if you have not, to learn the stack and entry points.
2. Measure the structure:
   ```
   python "<this skill's directory>/scripts/import_graph.py" <project-root> [--top 10] [--json]
   ```
   It reads Python, JavaScript and TypeScript imports and reports the module count, import cycles, the modules everything
   depends on (high fan-in), the modules that depend on everything (high fan-out), and the top-level packages with how much
   they depend on each other. Treat it as a map to question, not a verdict: dynamic imports, path aliases and generated code
   are only partly visible, and the tool says so.
3. Read the entry points and two or three central modules yourself. Note the real boundaries (where data crosses a layer or
   process) and any that exist only in the folder names.

### Step 3 - Generate options

Write down **two or three** structurally different candidates, always including the simplest one (usually a modular monolith
or the existing structure plus a small change). For each: a sentence on the shape, what it makes easy, what it makes hard.
Use `references/patterns.md` for the usual shapes and when each one pays off. Avoid straw men: each option must be one you
would defend.

### Step 4 - Choose, and say why

Score the options against the ranked quality attributes (a small table, evidence in the cells, not bare numbers). Pick one and
write the rationale in plain words: which driver decided it, what you are giving up, and the **trigger** that would make you
revisit it (for example "split billing out when it needs its own release cycle, or when the team passes 8").

### Step 5 - Define the components

For each component: its single responsibility, what it owns (data, state), what it exposes (interface or events), what it
depends on, and who owns it. Then the rules between components: which direction dependencies may point, which calls are
synchronous, which data each component may read directly (ideally only its own). Keep it to the level a new teammate could
build from; detailed schemas go to `design-database`, endpoints to `design-api`.

### Step 6 - Trace the important flows

Pick the 2 to 4 flows that matter most (the main user journey, the riskiest write, the heaviest read, the background job) and
walk each through the components end to end: trigger, steps, data read and written, where it can fail, where it is retried,
and what the caller sees. Sequence diagrams in text are ideal (`references/design-template.md`). A flow you cannot trace
exposes a missing component or a wrong boundary: fix the design, not the story.

### Step 7 - Failure, scale and security pass

Run the checklist in `references/review-checklist.md` against the design: timeouts, retries with limits and idempotency,
back-pressure, single points of failure, data consistency across components, where state lives, secrets and access control,
authentication at each boundary, what is logged and measured, backup and restore, deploy and rollback. Write down each gap as
a fix, a risk you accept (with the owner) or an open question.

### Step 8 - Write the design

Use `references/design-template.md`. Lead with a one-paragraph summary and the diagram, then the sections in the order of the
template. Keep it as short as the system allows: a small service gets one page. Include the assumptions, the risks, the
decisions with their alternatives, and the open questions. Save it where the project keeps documents (look for `docs/`) or
offer a path; do not overwrite an existing file without asking.

### Step 9 - Hand off

Offer the next step: the data model (`design-database`), the interfaces (`design-api`), the screens (`design-ui-ux`), the
plan (`break-down-tasks`), and `write-adr` for each major decision.

## Definition of done

- [ ] Quality attributes are ranked and tied to numbers or labelled assumptions.
- [ ] Two or more real options were compared, including the simplest one, and the choice has a rationale and a revisit trigger.
- [ ] Every component has one responsibility, an owner, and clear dependencies pointing one way.
- [ ] The key flows are traced end to end, with the failure path stated.
- [ ] The failure, scale and security checklist was applied; every gap is fixed, accepted or open.
- [ ] Existing-code claims come from the code or the import-graph output, marked Checked.
- [ ] The document lists assumptions, risks and open questions, and no code was changed.

## Pitfalls

- **Resume-driven design.** Microservices, Kafka, Kubernetes and a graph database for a ten-user app. Make the driver name
  itself.
- **Boxes without data.** If you cannot say who owns each piece of data, the services will share a database and call it
  independence.
- **Distributed monolith.** Services that must be deployed together and call each other in chains have the costs of both
  styles.
- **The shared "common" or "utils" module.** It becomes the dependency everything points at. Name modules by what they do.
- **Happy-path diagrams.** Retries without idempotency, timeouts that are longer than the caller's, no limit on queues.
- **Designing around today's code layout.** Folder names are not boundaries. Check what really calls what.
- **Over-precision.** Exact instance sizes and shard counts before the first measurement. Give ranges and a way to measure.
- **Ignoring the team.** A design the team cannot run at 3 a.m. is a bad design, however elegant.
- **One option only.** If there was nothing to compare, you did not design, you transcribed a preference.

## Hand-offs

| Next | Load |
|---|---|
| needs unclear | `clarify-requirements` |
| pick the technology | `evaluate-technology` |
| data model | `design-database` |
| interfaces | `design-api` |
| screens | `design-ui-ux` |
| plan the work | `break-down-tasks` |
| record a decision | `write-adr` |
| start building | `scaffold-project`, `build-feature` |
