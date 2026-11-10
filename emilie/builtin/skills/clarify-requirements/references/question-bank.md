# Question bank

Use it to *find gaps*, not as a script to read out. For each line first ask: can the code or the conversation answer this?
Only what is left, and only where a wrong guess is costly, becomes a question for the user.

Mark each item **A** answered, **D** safe default exists, or **U** needs the user.

## 1. Goal and users
- What problem does this solve, and what happens if we do nothing?
- Who uses it: roles, how often, how technical? Who is *not* meant to use it?
- What does success look like, and how would we measure it?
- Is there a deadline or an event driving this?

## 2. Behaviour
- What is the main scenario, step by step? What starts it, what ends it?
- What does the user see and receive at each step?
- What are the alternatives and variations (other roles, other inputs, other entry points)?
- Is it one-off, repeated, scheduled, or triggered by events?

## 3. Data
- What data goes in, comes out, and is stored? Formats, sizes, required vs optional?
- Validation rules: allowed values, lengths, uniqueness, formats?
- Existing data: must it be migrated, backfilled, or kept compatible?
- Retention: how long is it kept, can it be deleted, who can see it?

## 4. Edge cases (ask about the ones that fit)
- Empty, missing, null, zero, one, many, huge.
- Duplicates and repeated actions (double click, retry).
- Concurrent use of the same record by two people.
- Partial failure: it worked for some items but not others.
- Time: time zones, daylight saving, leap days, clocks that disagree, expiry.
- Text: unicode, very long strings, right-to-left, case, whitespace, injection characters.
- Numbers: money and rounding, negative values, overflow, units.
- Offline, slow, or interrupted connections.

## 5. Errors and recovery
- What should the user see when it fails? Can they retry? Is anything left half-done?
- What must be logged or alerted? Who is told?
- What is the rollback plan if this misbehaves in production?

## 6. Security and privacy
- Who is allowed to do this, and how is that checked? What must be impossible?
- Personal or sensitive data involved? Consent, masking, audit trail, legal constraints?
- Abuse cases: spam, scraping, enumeration, brute force, privilege escalation.
- Secrets or credentials handled? Where do they live?

## 7. Performance and scale
- Expected volume now and in a year (users, requests, rows, file sizes)?
- Response-time or throughput expectations, stated as numbers?
- Is it acceptable to do the work in the background and notify?

## 8. Compatibility and integration
- Must it keep working with existing clients, API versions, browsers, devices, data formats?
- Which other systems does it call or feed? Who owns them, what are their limits?
- Breaking changes allowed? Feature flag or gradual rollout?

## 9. Operations
- How is it deployed, configured, monitored? New environment variables or infrastructure?
- Who supports it, and what do they need (docs, dashboards, runbook)?

## 10. UX and content
- Existing patterns to match (layout, wording, error messages, language)?
- Accessibility needs (keyboard, screen reader, contrast)? Languages and locales?
- Empty states, loading states, confirmation for destructive actions?

## 11. Boundaries
- What is explicitly *not* part of this? What can wait?
- What is the smallest version that is still useful (a first slice)?

## Choosing the questions

Rank each **U** item by: (cost if guessed wrong) x (chance of guessing wrong). Ask the top few (at most five per round).
Always ask when the answer involves: security or permissions, money, personal data, deleting or overwriting data,
something customers will see, or an irreversible migration.

## Question style

- One decision per question. "Should X be allowed, and for how long?" is two questions.
- Offer a default and say why: "I assume A, because the existing code does that (`path:line`). Is that right?"
- Give the options when there are few: "Hard delete, or soft delete with a 30-day recovery?"
- Avoid jargon the user did not use. Prefer an example to a definition.
- Never ask for something you could look up.

## Turning a vague word into a requirement

| They said | Ask or propose |
|---|---|
| "fast" | a target and a condition: "under 300 ms for the 95th percentile with 1,000 items" |
| "easy to use" | the task and a success measure: "a new user finishes checkout without help in under 2 minutes" |
| "secure" | the threats that matter and the controls: roles, encryption, audit, rate limits |
| "scalable" | the expected growth and the first thing that will break |
| "like <other product>" | which specific behaviours to copy, and which not to |
| "better" | better for whom, measured how, compared with today's behaviour |
| "support X" | read, write, or both; which versions or formats; what happens with unsupported input |
