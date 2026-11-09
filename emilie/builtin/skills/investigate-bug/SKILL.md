---
name: investigate-bug
phase: pahami
description: Find the root cause of a bug, crash, wrong result or regression with a disciplined loop - reproduce, gather evidence, isolate, form falsifiable hypotheses, test them one at a time, confirm the mechanism, then report the cause with a proposed fix and a regression test. Never guesses, and never changes code just to "see if it helps". Not for writing the fix (build-feature) or live-incident response (debug-production). Triggers - "bug", "crash", "exception", "traceback", "stack trace", "not working", "doesn't work", "broken", "regression", "why does it fail", "unexpected result".
---

# Investigate a bug

**Goal:** find out *why* it happens, not just make the symptom go away. Finish with a cause you can explain from start to
finish, the evidence that proves it, and a fix and a test that would have caught it.

## Ground rules

1. **Reproduce first.** Without a reproduction you have a theory, not a diagnosis. If you cannot reproduce it, say so, and say
   what you would need (the input, the environment, the logs).
2. **Evidence over theory.** Label statements **Observed** (you saw it in output or in code) or **Inferred**. A cause is
   confirmed only by an experiment that could have shown it false.
3. **One change at a time, and none without a hypothesis.** Shotgun debugging (trying things until it works) hides the cause
   and creates new bugs.
4. **Falsifiable hypotheses.** For each guess, write what you would see if it is true and what you would see if it is false,
   and test the cheapest one first.
5. **Cause, not symptom.** Keep asking "why" until you reach something you can change, such as a wrong assumption, a missing
   check or a bad default. A null check around a crash is rarely the fix.
6. **Read-only by default.** Investigation does not edit the project. Temporary logging or experiments need the user's OK,
   happen in a scratch copy or a clearly marked revertable change, and are listed for removal.
7. **Keep a log** (a hypothesis table, or `todo_write`) so you do not test the same idea twice.
8. **Never claim a command was denied or unavailable unless you ran it and saw the refusal.** Read-only git (`log`, `show`,
   `diff`, `blame`) works even when other commands need approval, so always try it. "Could not check" is only honest after
   an attempt.
9. **Time-box.** After three hypotheses fail, stop and re-examine your assumptions: is it the right file, the right
   version, the right environment, the right input? Then ask the user a precise question.

## Procedure

### Step 0 - Understand the report

Pin down: **expected vs actual**, how to trigger it, how often, since when (or since which change), where (which
environment, platform, data), and the impact. Collect the exact error text. If something essential is missing, ask at most
three short questions (the error text, the steps, the environment); otherwise state your assumptions and go.

### Step 1 - Triage the evidence you already have

If there is a stack trace or error text, run the helper (read-only):

```
python "<this skill's directory>/scripts/triage.py" --trace <file>      # or:  --trace -   (stdin)   or:  --text "..."
```
(On Windows `python` or `py -3`.) It finds the frames that belong to this repository, shows the code around each, the commit that
last changed that line, and recent changes to those files, plus toolchain versions. Note **where the throw site is** and the
**first error** in the log: later errors are often a consequence of the first.

**If the helper cannot run** (no Python, or commands are limited), do its work by hand with read-only git, which is always
worth doing: read each frame's file, then run
`git log --oneline -15 -- <file>` and `git log -p -3 -- <file>` for every file in the frames, and `git blame -L <n>,<n> <file>`
for the failing line. Read the diffs for a **removed check**, a changed default, a new caller, or a changed type.

### Step 2 - Reproduce

Find the smallest reliable way to trigger it. Run it and capture the **command and the exact output**. Make it deterministic
(fixed seed, fixed input, fake clock). If it is intermittent, characterize it: how often, under what conditions, and try a
loop or a stress run. If a test can express the failure, write that failing test (in a scratch location, or propose it) because
it is both your reproduction and your regression test. If commands are not allowed, ask the user to run specific commands
and paste the output, or continue with static reasoning and say your confidence is lower.

### Step 3 - Gather evidence

Logs around the failure (timeline, not just the last line), the inputs and the state at the time, versions of the runtime
and dependencies, what changed recently (`git log`, lockfile and config diffs), and whether it also fails elsewhere (another
machine, another input, another branch). Write the facts down as a short timeline.

### Step 4 - Isolate

Shrink the search space until the cause has nowhere to hide. Choose the cheapest cut for this bug
(`references/techniques.md` has recipes):

- **When:** `git bisect` between a good and a bad revision.
- **What input:** shrink the input to the smallest case that still fails.
- **Which component:** bypass or replace layers (a stub, a direct call, a fixed value).
- **Which configuration or dependency:** flip one setting or version at a time; diff against a working environment.
- **Which environment:** OS, path separators and case, locale, time zone, permissions, versions.

### Step 5 - Hypothesize and test

List two to five hypotheses, most likely and cheapest first, in a table: *idea, what I would see if true, what I would see
if false, the test*. Run the cheapest decisive test. Update the table with the result. A hypothesis is **confirmed** only when
a test that could have disproved it did not. If a test is inconclusive, design a better one rather than rationalizing.
Use `trace-code` to follow the exact path when you need to see what really runs.

### Step 6 - Confirm the mechanism

Explain it end to end: from the root cause, through each step, to the symptom the user saw. Answer three more questions:
**why now** (what change, data or condition exposed it), **why was it not caught** (the missing test or check), and
**where else** (search for the same pattern: `find_symbol.py` or `grep`). If your explanation has a gap, you are not done.

- **"Why now" must come from evidence:** a commit you read (`git log -p`), a data or config change you saw, a version bump. If
  you did not look, write "not checked". The words "presumably" and "probably" mean you have not checked yet.
- **Ask who owns the invariant.** When code crashes on an input, ask where that input *should* have been stopped, and
  whether that check once existed. A crash inside a helper is often the visible end of a validation that was removed or
  never added upstream. The fix usually belongs where the rule is owned, not where it blew up.

### Step 7 - Propose the fix

The smallest change that removes the *cause*, with one alternative and the risk of each. Name the regression test that
fails before the fix and passes after. Do **not** apply the fix unless the user asked. If they did: write the failing test
first, make the change, run the tests, and report the output. For larger changes, hand off to `build-feature`.

### Step 8 - Report

Use `references/report-template.md`: summary, reproduction, evidence timeline, root cause with `path:line`, why now and why
undetected, the fix and test, other places affected, and what remains unknown. Lead with the answer.

## Definition of done

- [ ] There is a reproduction (or a clear statement that there is not, and what is needed).
- [ ] The root cause is explained from cause to symptom, with `path:line` evidence.
- [ ] The confirming experiment could have failed (it was a real test, not a coincidence).
- [ ] "Why now" is backed by history or data you actually looked at (or marked "not checked"); "why undetected" is answered.
- [ ] A regression test is named or written, and other occurrences were searched for.
- [ ] Anything you changed for the investigation is listed and reverted.
- [ ] Claims are marked Observed or Inferred; unknowns are stated.

## Pitfalls

- **Confirmation bias.** You like a theory and read every result as support. Design tests that could embarrass it.
- **Fixing the symptom.** Wrapping the crash in `try/except` or a null check and calling it solved.
- **Skipping the history.** Reading only the current code misses the change that caused it. Always look at `git log` for
  the files involved before writing "why now".
- **Trusting the last error.** The first failure is usually the cause; the rest are fallout.
- **"It works now."** A change that made it pass without an explanation is not a fix: it may have hidden the bug (timing,
  caching, a stale build, a different input).
- **Changing many things at once,** so you cannot tell which one mattered.
- **Debugging the wrong thing:** an old build, a cached result, the wrong branch, the wrong environment, a mock that hides
  the real behaviour.
- **Dismissing flaky bugs.** Intermittent means a race, hidden state or an environment dependency. It is a real defect.
- **Blaming the library** before ruling out your own use of it.
- **No regression test,** so it returns in three months.

## Hand-offs

| Next | Load |
|---|---|
| it only happens in production, or an incident is live | `debug-production` |
| it is a slowness or memory problem | `profile-performance` |
| the failing test is intermittent | `fix-flaky-tests` |
| write the regression test properly | `write-tests` |
| implement a larger fix | `build-feature` |
| the bug is a vulnerability | `security-audit` |
| understand the code path first | `trace-code` |
