# Estimation

Estimates are guesses with a spread. The honest output is a range and a confidence, plus the list of things that would change it.

## Rules

1. **Estimate effort, not elapsed time.** Hours of focused work, then convert to calendar time with the real availability
   (focus time per day is commonly 4 to 6 hours; account for review waits, meetings, deployment windows).
2. **Estimate small tasks.** Errors average out across many small items and explode on one big one. Anything over a day is
   a guess; split it.
3. **Use the most-likely value, not the best case.** Ask "if I did this ten times, what is the typical time?" and then ask what is
   the worst realistic case.
4. **Use past data.** Look at similar changes in the repository (`git log --stat`, merged pull requests) and compare size and time.
   Reference-class estimates beat intuition.
5. **Unknown means spike.** If you cannot estimate within a factor of two, create a time-boxed spike and estimate after.
6. **Do not estimate on behalf of someone else** without saying so; the person doing the work should confirm.
7. **Never present a single number as a commitment.** Say "likely 3 days, range 2 to 6, if the vendor API behaves as documented".

## Three-point estimate for a task or a total

| Case | Meaning |
|---|---|
| Best (B) | everything goes right; about 10% chance of beating it |
| Likely (L) | typical outcome |
| Worst (W) | realistic bad case (not a disaster), about 90% chance of finishing before |

Expected value is about (B + 4L + W) / 6 and the spread is about (W - B) / 6. For totals add expected values; add spreads as the
square root of the sum of squares (assuming independent tasks), then still keep a buffer for shared risks (one vendor, one reviewer).

## Buffer

- Known work in familiar code: +20 to 30%.
- New area or technology: +50 to 100%.
- Heavy outside dependency or unclear requirements: re-plan after the first slice and do not promise dates before it.
Show the buffer as its own line so it is visible and not eaten silently.

## Confidence flags

| Flag | Meaning | Action |
|---|---|---|
| High | done this before, code read | accept |
| Medium | similar work, some unknowns | note the assumption |
| Low | new technology, unclear spec | spike or split before committing |

## Size shortcuts (when a rough view is enough)

| Size | Roughly | Notes |
|---|---|---|
| XS | under 1 hour | config change, copy edit |
| S | 1 to 4 hours | one function with tests |
| M | about a day | one slice through the stack |
| L | 2 to 3 days | split it |
| XL | more than 3 days | must be split or spiked |

## Tracking and re-planning

- After each wave, compare actual to estimate and adjust the rest by the ratio you observed (if tasks run 1.5x, assume it continues).
- Re-plan when a risk fires, a spike changes the design, scope changes, or the critical path slips by more than the buffer.
- Keep a short log of actual vs estimated; it is the best input to the next estimate.
- Update the plan file (`[x]` for finished) and re-run `task_graph.py` to see what is ready now.

## Things estimates usually forget

Waiting for review, environment setup, flaky tests, merge conflicts, data cleanup, production-only differences, security review,
translations, accessibility fixes, documentation, bug fixes after the demo, and the time to explain the change to others.
