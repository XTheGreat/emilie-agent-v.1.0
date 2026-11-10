# Refactoring safely

## Characterization tests (pin what the code does today)

1. Choose inputs that exercise each branch: typical, boundary, empty, invalid, large, and any case that once caused a bug.
2. Run the current code and record the outputs (return values, raised errors, files written, calls made to dependencies).
3. Assert those outputs exactly. Do not "correct" surprising results; add a comment (`# current behavior; suspected bug #123`).
4. Prefer testing through the public entry point, so internal restructuring does not break the tests.
5. For output that is large or structured, use snapshot/golden files, committed with the tests and reviewed by a person.
6. For pure functions with many possible inputs, compare old and new implementations on many generated inputs (property or differential test)
   while both exist.

## Seams for hard-to-test code

- Pass collaborators in (parameters or constructor) instead of creating them inside.
- Wrap calls to time, randomness, environment, filesystem, network in tiny functions that tests can replace.
- Extract the logic from the I/O: decide in a pure function, do the effect in a thin shell.
- Make the seam change on its own, with a test, before the real refactoring.

## Big moves

| Technique | Use when | Outline |
|---|---|---|
| **Parallel change (expand/contract)** | changing a signature, schema, API or format used by many callers | add the new alongside the old; migrate callers one by one; remove the old when unused; each step deployable |
| **Strangler** | replacing a large module or subsystem | route one slice of behavior to the new code at a time behind a switch; delete the old part when empty |
| **Branch by abstraction** | swapping an implementation deep in the system | introduce an interface; make the old code implement it; build the new implementation behind it; switch; delete the old |
| **Feature flag the switch** | risky replacement in production | flag between old and new; compare results in shadow mode; roll out gradually |
| **Shadow comparison** | proving equivalence on real traffic | run both, return the old result, log differences |

## Reviewable commits

1. Pure moves and renames (a diff tool that detects moves will show them as such).
2. Mechanical extractions with no logic edits.
3. Structural changes to logic (the interesting commit).
4. Cleanup (dead code removal, formatting) separately.

Never mix a behavior change into these. Explain the sequence in the pull request so the reviewer can read it commit by commit.

## Rename checklist

- Search for the old name in: source, tests, docs, comments, config files, scripts, CI, SQL, templates, JSON/YAML keys, environment variables,
  log messages, dashboards and alerts that match on text.
- Search dynamic uses: `getattr`, reflection, string-built names, decorators, serialization field names, ORM column names.
- Public names: consider consumers outside the repository; deprecate with an alias first.
- Case variants: `userId`, `user_id`, `UserID`, `USER_ID`.
- Run the full test suite and the build; compile or type-check the whole project.

## Delete safely

1. Search for references (including dynamic) and for the name in non-code files.
2. Check coverage or runtime logs when the code could be reached by configuration or plugins.
3. Remove in its own commit with a message that says what and why, so it is easy to restore.
4. Public API: deprecate, wait a release, then remove.

## Warning signs mid-refactoring

- Tests are failing for reasons you do not understand: revert the last step.
- You are editing tests to match new behavior: you changed behavior. Stop and decide whether that is intended.
- The diff keeps growing and you cannot explain it in one sentence: split it.
- You are fixing unrelated problems: write them down and continue the plan.
- The branch has lived more than a few days without merging: ship what is green.

## Measuring the result

Re-run `hotspots.py` on the same path and compare: function length, parameters, nesting, cyclomatic complexity, duplicate blocks, file size.
Also record qualitative gains (a new feature that used to take N files now takes 1). Report when a metric got worse, and why that is acceptable.
