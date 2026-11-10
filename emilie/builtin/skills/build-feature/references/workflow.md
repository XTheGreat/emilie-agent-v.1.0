# Build loop: details

## The loop for one step

1. **Express the step as a test.** Name it after the behavior (`rejects_order_with_no_items`, not `test_3`). Put it next to the tests of
   the nearest feature, using the same fixtures and helpers.
2. **Run it; it must fail for the right reason.** A failure from a typo or a missing import is not the failure you want. Read the message:
   it should say the behavior is missing.
3. **Write the smallest change that passes.** Hard-coding the answer is acceptable at first if the next test forces the general form.
4. **Run the focused test, then the neighbors, then the suite** (fast to slow). Stop and fix as soon as something breaks; the cause is
   in the last change.
5. **Clean up while green:** rename, remove duplication in your own new code, keep behavior unchanged. Run the tests again.
6. **`git diff`** the step. If it contains anything you cannot explain in a sentence, remove it.

## When the test is hard to write

- **No seams:** the code under change does something hard to isolate (network, clock, filesystem, global state). Introduce the smallest
  seam (pass the dependency in, wrap the call), covered by a test, in its own small step. Do not mock what you do not own without
  also having one test against the real thing.
- **Slow or flaky suite:** run the focused tests during the loop and the full suite at the end. A flaky failure is not "unrelated" until
  you have re-run it and shown it fails without your change (`fix-flaky-tests`).
- **No tests exist:** write a characterization test around the existing behavior you are about to touch (assert what it does today), then
  make the change. Tell the user the coverage is thin.
- **UI or visual work:** test the logic that drives it; verify the rest by running it and looking, and say so.

## Matching the codebase

Before writing, collect, from two or three neighbor files:

- File and function naming; where similar things live; how modules import each other.
- Error handling (exceptions vs result types; messages; logging levels).
- Validation (where, which library); configuration (env vars, files); dependency injection.
- Test layout, fixtures, naming, assertion style; how external services are faked.
- Formatting tools (run the formatter; do not hand-format against it).
- Comment and docstring style: match density and tone; explain why, not what.

## Edge checklist (pick the ones that apply)

Empty, one, many, huge; zero, negative, maximum; unicode, very long strings, whitespace; missing, null, wrong type; duplicates and
repeated submits; ordering and concurrency; partial failure in the middle of a multi-step operation; time zones, daylight saving, clock
skew; locale and encoding; permissions and tenants; timeouts, retries, and idempotency; resource cleanup on error; backward
compatibility with existing data and clients; feature flags and rollout.

## Handling blockers

| Situation | Do |
|---|---|
| Requirement is ambiguous in a way that changes the design | Ask one precise question, offering your default |
| A needed dependency or permission is missing | Say what and why; propose the smallest alternative; do not work around safeguards |
| The baseline is already red | Report it, do not "fix" unrelated tests silently; offer a separate task |
| The change needs a migration or a data backfill | Write it, do not run it on real data; describe the safe order (`design-database`) |
| You discover the design is wrong | Stop, explain what you learned, propose the revision; do not push through |
| Another bug appears | Note it, add a failing test if cheap, keep the feature diff clean |
| Time is running out | Cut scope from the end of the plan, not tests or safety checks; say what was dropped |

## Working with generated and shared files

- Do not hand-edit generated files (lockfiles, compiled output, schemas generated from code); regenerate with the project's tool.
- A lockfile or snapshot changing unexpectedly is a signal: find out why before keeping it.
- Do not touch CI, deployment or shared configuration unless the task requires it; flag it prominently if it does.

## Feature flags and rollout

For risky or user-visible changes: add the flag first (default off), build behind it, test both states, document how to turn it on,
and how to remove the flag later. Mention the plan in the report.
