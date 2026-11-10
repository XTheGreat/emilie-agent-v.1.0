---
name: migrate-code
phase: bangun
description: Move code from one framework, library, language version or API to another without breaking it - research the official migration path and breaking changes, size the work by counting real usages, pick a strategy (big bang, incremental with a compatibility layer, or strangler), migrate in verified batches, and finish by removing the old path. Includes a usage-inventory script. Not for plain dependency bumps (upgrade-dependencies) or structure-only cleanup (refactor-code). Triggers - "migrate", "migration", "port to", "convert to", "move from", "switch from", "replace library", "upgrade the framework", "deprecated API", "rewrite in", "port this".
---

# Migrate code

**Goal:** move to the new framework, version, library or pattern in steps that each leave the system working, with the old way
gone at the end, and evidence at every step that behavior is preserved.

## Ground rules

1. **Know why and what "done" is.** State the reason (end of support, security, performance, hiring), the target (exact version or
   library), and the exit criterion: the old thing is removed from code, config, docs and build. A migration that stalls at 80% leaves two
   systems to maintain.
2. **Read the official migration guide and changelog first.** List every breaking change between your current and target version, one
   major version at a time. Do not rely on memory: APIs, defaults and flags change between releases. Check the exact versions you have
   (lockfile) and the target's release notes.
3. **Size it with data.** Count the real usages with the inventory script (Step 3). The distinct forms of use decide the strategy and the
   effort; guesses do not.
4. **Safety net before changes.** Record a green baseline of tests, lint, types and build. Add characterization tests around behavior that the
   migration might alter (formatting, rounding, defaults, error types, ordering). No net, no big moves.
5. **Incremental beats big bang.** Prefer a path where old and new coexist (adapter, compatibility layer, feature flag, strangler) and each
   batch is shippable. Choose big bang only for small codebases, mechanical changes with full tests, or when coexistence is impossible.
6. **One kind of change per step.** Separate the migration from refactoring, features and unrelated upgrades. Upgrade one major version at a
   time when the guide recommends it.
7. **Prefer mechanical transforms.** Use the official codemod or compiler/migration tool when it exists; otherwise write a precise
   search-and-replace or script and review its diff. Never hand-edit hundreds of call sites without a rule.
8. **Behavior parity is the bar.** Compare before and after on real inputs (tests, snapshot outputs, shadow runs). Differences must be
   understood and either fixed or explicitly accepted.
9. **Data migrations are different.** Schemas and stored data follow expand and contract with backups, batches and rollback
   (`design-database`, its `migration-safety.md`). Never run data-changing commands on real data without the user's yes.
10. **Plan the exit and the rollback.** Each step says how to go back. Keep the old path until the new one has proved itself, then delete it.
11. **Say what was not verified.** If a command cannot be run (needs network, install approval, a runtime), report "not run" and why.

## Procedure

### Step 1 - Define the migration

Write: from -> to (names and exact versions), the reason and deadline, the scope (which apps, packages, folders), what must not change
(public API, data formats, user-visible behavior), and the constraints (no downtime, can't freeze features, supported platforms). If
the target is not chosen, load `evaluate-technology`.

### Step 2 - Research the path

Read the official upgrade/migration guide, the changelog or release notes for each version in between, deprecation warnings produced
by the current code (run the tests and the app with warnings enabled and capture them), and the list of removed or changed APIs.
Use `web_search` and `web_fetch` on primary sources; note the date and version of anything you read. Produce a table:
**change -> affects us? -> how to adapt -> automated tool?**. Look for an official codemod or migration CLI (read what it does before running it).

### Step 3 - Size it from the code

```
python "<this skill's directory>/scripts/usage_inventory.py" --old "<regex of the old API>" [--new "<regex of the new API>"] [path] [--ext .py,.js] [--top 15]
```

Use specific patterns (import lines, call forms like `moment\([^)]*\)\.\w+`) so the "distinct forms" table separates the cases that need
different replacements. It reports hits and files (split into source, tests, docs, config), the forms found, the heaviest files, sample
lines, and, with `--new`, the percentage already migrated. Also search by hand for what text search misses: dynamic access, generated code,
configuration and build files, documentation, scripts, and other repositories that depend on this one.

### Step 4 - Pick the strategy

Use `references/playbook.md` to choose among: **in-place mechanical** (codemod then fix), **incremental with adapter or compatibility shim**,
**strangler / module by module**, **parallel run (shadow) then switch**, and **rewrite** (last resort). Write the choice with its reason, the
batch order (leaf modules and low-risk first, shared core when the pattern is proven), and the rollback for each batch. For large work, write the
plan with `break-down-tasks`.

### Step 5 - Prepare the ground

1. Baseline: run tests, lint, types and build; record failures that already exist.
2. Add characterization tests for risky behavior; fix flaky tests that would hide regressions (`fix-flaky-tests`).
3. Create the adapter, shim or wrapper that lets old and new coexist, and a way to see which path is used (a metric, a log line, a lint rule that
   forbids new uses of the old API).
4. Pin versions; upgrade the toolchain pieces the target needs (runtime, compiler, build plugins) as their own steps.

### Step 6 - Migrate in batches

For each batch: apply the transform (tool or scripted), review the diff, fix compile and type errors, run tests, run the app on the main paths,
re-run the inventory to show progress, and commit separately when asked (`commit-and-pr`). Keep each batch small enough to review. Stop when
a surprise appears (a behavior difference, a missing equivalent): record it in the plan, decide with the user, then continue.

### Step 7 - Finish and clean up

When OLD usage is 0 in source, tests, docs and config: remove the shims and compatibility code, the old dependency and its configuration, deprecated
flags and temporary tests; update docs, README, CI and build files; run the full verification once more on a clean checkout. Add a guard (a lint
rule or a test) that fails if the old API reappears.

### Step 8 - Report

Provide: from/to and versions, the strategy, what changed (counts, files), the behavior differences found and their disposition, the commands run
and results (and baseline comparison), anything not verified, rollback instructions, and remaining follow-ups. Offer `review-code` and
`write-changelog` (for users) if the change is visible.

## Definition of done

- [ ] The target, reason, scope and exit criterion were written down; versions are exact.
- [ ] The official guide and each breaking change were read and tabulated with how they affect this code.
- [ ] Usage was measured by script (old, and new when applicable), with distinct forms; manual searches covered what text search misses.
- [ ] A baseline existed and each batch ended with tests, lint, types and build passing.
- [ ] Behavior parity was checked on real inputs; every difference is fixed or explicitly accepted.
- [ ] The inventory shows zero old usage in source, tests, docs and config; shims, old dependencies and flags are removed.
- [ ] A guard prevents the old API from returning.
- [ ] Rollback steps and unverified items are documented.

## Pitfalls

- **Skipping the guide.** Changed defaults and silent semantic changes are not compile errors.
- **Jumping several majors at once.** Do them one at a time when the vendor says so; you can bisect failures.
- **Big-bang branch that lives for months.** It rots against main. Ship in batches behind a shim.
- **Trusting automated codemods blindly.** Review their diffs and run tests; they miss dynamic and unusual usage.
- **Mixing refactors and features into the migration diff.** Reviews become guesswork.
- **Half-migrated forever.** Two ways of doing everything. Set the exit criterion and a guard.
- **Counting only source files.** Tests, docs, config, scripts and CI also use the old API.
- **Ignoring data and operations.** Stored formats, serialized objects, caches, queues in flight and deployment tooling also change.
- **No rollback.** Keep the old path deployable until the new one is proven.
- **Declaring victory from compile success.** Compiles and passes tests is not behavior parity; compare outputs.

## Hand-offs

| Next | Load |
|---|---|
| choose the target | `evaluate-technology` |
| plan the batches | `break-down-tasks` |
| version bumps only | `upgrade-dependencies` |
| restructure first | `refactor-code` |
| schema or data move | `design-database` |
| tests are weak or flaky | `write-tests`, `fix-flaky-tests` |
| verify the result | `review-code` |
| announce to users | `write-changelog` |
| commit or PR | `commit-and-pr` |
