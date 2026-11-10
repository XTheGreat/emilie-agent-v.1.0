---
name: clarify-requirements
phase: pahami
description: Turn a vague request into a short, testable specification - the goal, who it is for, what is in and out of scope, acceptance criteria, edge cases, constraints, assumptions and open questions - by first answering what the codebase can answer, then asking only the few questions that matter, each with a proposed default. Use before designing or building anything not yet precise. Not for choosing between technologies (evaluate-technology) or splitting an agreed spec into tickets (break-down-tasks). Triggers - "requirements", "acceptance criteria", "user story", "scope this", "spec this", "I have an idea", "not sure what I want", "turn this into a spec", "what should it do".
---

# Clarify requirements

**Goal:** replace "make X better" with something a developer could build and a tester could check: a short spec with
acceptance criteria, explicit scope, and a list of assumptions the user can correct in ten seconds. The aim is to be
**precise without interrogating**: fewer, better questions, each with a default you propose.

## Ground rules

1. **Look before you ask.** If the repository can answer a question (existing behaviour, conventions, data model, what
   users already see), read it and state the answer. Never ask the user something the code already says.
2. **Ask few, ask well.** At most five questions per round, ordered by how much the answer changes the work. Each question
   offers a recommended default ("I will assume X unless you say otherwise") so the user can reply with one word.
3. **Separate what was said from what you inferred.** Quote or paraphrase the user's own words for stated needs. Mark the
   rest *Assumption*. Never promote an assumption to a requirement silently.
4. **Describe behaviour, not implementation.** "A user can reset their password by email" is a requirement. "Add a
   `/reset` endpoint using JWT" is a design decision, and belongs to the design phase unless the user insisted on it.
5. **Testable or it does not count.** Every acceptance criterion must be something that can be shown true or false.
   "Fast" and "easy" become numbers or observable behaviour, or they become an open question.
6. **No one to answer? Do not stall.** If the user is away (autonomous mode, a non-interactive run, or they said to just go
   ahead), do not block on questions. Choose the safest reasonable defaults, write them down as assumptions at the top of
   the spec, and continue. Flag the assumptions with the highest risk of being wrong.

## Procedure

### Step 1 - Restate

In two or three sentences, say what you understood: the goal, who benefits, and the trigger for wanting it. This is the first
chance to catch a misunderstanding cheaply. If the request is already precise (clear behaviour, clear done-ness), say so and
offer to go straight to planning; do not manufacture questions.

### Step 2 - Gather what the code already knows

Find the parts of the project this touches (use `project-overview` or `trace-code` if you do not know it yet) and record:
current behaviour in that area, conventions to follow (naming, validation, error format, permissions), related features,
data that already exists, tests that describe today's behaviour, and anything that conflicts with the request. Note
`path:line` for what you rely on.

### Step 3 - Find the gaps

Run the request through the checklist in `references/question-bank.md`. For each category (users and goal, behaviour,
data, edge cases, errors, security and privacy, performance and scale, compatibility, operations, UX, out of scope), mark:
**answered** (by the user or the code), **assumable** (a safe default exists), or **needs the user** (the choice is
theirs, or the cost of guessing wrong is high). Only the last group becomes a question.

### Step 4 - Ask

Group the questions that need the user into one short message. For each: the question, why it matters in a clause, and your
recommended default.

> **1. Who can do this?** I assume any logged-in user (not only admins), because the existing `/profile` page works that way (`app/views.py:40`).
> **2. What happens when the file is larger than 5 MB?** I assume a clear error and no partial upload.
> Reply "defaults" to accept them all.

Do not ask about things you can reasonably assume and later correct cheaply. Do ask when a wrong guess means rework, a
security or privacy risk, data loss, or something visible to customers.

### Step 5 - Write the specification

Use `references/spec-template.md`. The core parts, in this order: **Goal**, **Users and scenarios**, **Scope** (in, out,
later), **Acceptance criteria** (observable, numbered, in Given / When / Then form where it helps), **Edge cases and errors**,
**Constraints** (technical, legal, performance, compatibility), **Assumptions**, **Open questions**, **Done means**.
Keep it to one or two pages. A spec nobody reads is not a spec.

### Step 6 - Test the spec

Before showing it, check it as a skeptical tester would: for each acceptance criterion, can you imagine the exact check?
Is there a case where two criteria contradict? Is anything in scope with no criterion, or a criterion with no matching scope
line? Could two developers read it and build different things? Fix what you find.

### Step 7 - Get a decision

Ask the user to confirm, correct or strike specific numbered items. Once confirmed, record "Confirmed by the user: <date>"
and hand off. If anything stayed open, say which items are still assumptions.

## Definition of done

- [ ] The goal and the user's reason for it are stated in their terms.
- [ ] Every acceptance criterion is observable (a person or a test could check it).
- [ ] Scope has an explicit **out of scope** list.
- [ ] Questions asked were only the ones the code could not answer, each with a default.
- [ ] Assumptions are listed and marked as such, riskiest first.
- [ ] The spec fits in one or two pages and contains no hidden design decisions.
- [ ] The user confirmed it, or the unconfirmed state is stated plainly.

## Pitfalls

- **Interrogation.** Twenty questions make the user stop answering. Prefer defaults they can accept in bulk.
- **Solution disguised as requirement.** "Use Redis" is not a need. "Page loads under 200 ms for 10k concurrent users" is.
- **Gold plating.** Adding likely-wanted features to the spec. Put them under "later", not "in scope".
- **Vague quality words** ("intuitive", "robust", "scalable") left unquantified.
- **Ignoring the unhappy paths.** Empty, huge, duplicate, concurrent, unauthorized, offline, slow, partial failure.
- **Missing the non-functional needs:** security, privacy, accessibility, audit, performance, data retention.
- **Re-asking.** If the user already answered something earlier in the conversation, use it.
- **Silent scope growth** between the request and the spec. Every addition is visible and labelled.

## Hand-offs

| Next | Load |
|---|---|
| the spec needs a technology choice | `evaluate-technology` |
| turn the spec into a design | `design-architecture`, `design-api`, `design-database`, `design-ui-ux` |
| split into ordered work | `break-down-tasks` |
| the spec is for a bug fix | `investigate-bug` |
| build it | `build-feature` |
