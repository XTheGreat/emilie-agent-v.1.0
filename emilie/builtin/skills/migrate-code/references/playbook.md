# Migration playbook

## Kinds of migration and their usual risks

| Kind | Examples | Main risks |
|---|---|---|
| Language/runtime version | Python 3.9 to 3.12, Node 18 to 22, Java 11 to 21 | removed APIs, changed defaults, native extensions, dependency support |
| Framework major version | Django 3 to 5, React 17 to 18, Spring Boot 2 to 3 | behavior changes with no compile error, plugin ecosystem, config format |
| Library swap | moment to date-fns, requests to httpx, jest to vitest | semantic differences (time zones, rounding, errors), missing features |
| API/protocol change | REST v1 to v2, SOAP to REST, callbacks to promises/async | consumers outside your repo, error handling, ordering and timing |
| Language port | JavaScript to TypeScript, Python 2 to 3, Java to Kotlin | idioms, performance, hidden dynamic behavior |
| Architecture/pattern | monolith to services, ORM change, state-management change | data ownership, consistency, operations |
| Data/schema/storage | database engine, ID type, file format | irreversible data loss, downtime, dual writes |
| Build/tooling | webpack to Vite, Maven to Gradle, CI provider change | hidden build steps, environment differences |

## Strategy selection

| Strategy | Choose when | How |
|---|---|---|
| **In place, mechanical** | small codebase, strong tests, the change is a pure rename/signature change | run the official codemod or a scripted transform; fix errors; one commit or a few |
| **Incremental with adapter / compatibility layer** | many call sites, several teams, cannot stop feature work | introduce an adapter that exposes the old interface over the new implementation (or the reverse), migrate callers gradually, then delete the adapter |
| **Strangler (module by module)** | large subsystem, new framework side by side | route features one at a time to the new code; both run in production; remove old parts as they empty |
| **Parallel run / shadow** | behavior parity is critical (billing, pricing, search ranking) | run old and new on the same input, serve old, log differences, fix until diffs are zero, then switch |
| **Feature flag switch** | risky runtime behavior | flag the new path; ramp gradually; keep the old path until stable |
| **Rewrite** | last resort: the old design cannot reach the goals, and the scope is small enough | specify the behavior with tests first, build to the tests, run in parallel; expect longer than planned |

## Reading upgrade guides

1. Identify your current and target versions exactly (`lockfile`, `--version`), and every version between.
2. Read the *breaking changes* and *deprecations* sections, plus "upgrading" notes, for each major in between.
3. Make a table: Change | Where in our code | Fix | Tool.
4. Look for: removed functions, renamed options, changed defaults, stricter validation, changed return types, changed error types,
   changed ordering/time/locale behavior, dropped platform or runtime support, changed configuration file formats, new required
   permissions or flags, changed packaging/entry points, security-related defaults.
5. Run the existing tests with deprecation warnings turned into errors (where the tool supports it) to find usage of deprecated APIs *before* upgrading.
6. Search the vendor's issue tracker for "upgrade to X" problems and for your key plugins' compatibility.
7. Check the compatibility of every dependency with the target (peer ranges, supported runtimes).

## Writing a useful adapter

- The adapter lives in one module with the *old* interface and *new* implementation (or vice versa). All code goes through it.
- Add a lint rule or test that forbids importing the old library directly outside the adapter; that makes the inventory trend to zero.
- Keep it thin and temporary. Put a removal note and an owner at the top of the file.
- Record which calls use which path (a counter or log) so you know when the old path is idle.

## Codemods and scripted rewrites

1. Prefer the vendor's codemod (read its source or docs for what it changes). Run it on a clean branch.
2. If you write your own: operate on the syntax tree when you can (`libcst`, `jscodeshift`, `ts-morph`, `gofmt -r`, `comby`), otherwise a
   precisely anchored regex; test it on fixtures that include tricky cases (comments, strings, multi-line calls, aliases).
3. Review the diff by category: sample from each distinct form, not only the first screen.
4. Format the output with the project's formatter in a separate commit to keep the semantic diff reviewable.

## Verification layers

1. Compile/type-check/lint clean.
2. Existing test suite green, compared with the baseline.
3. Characterization tests for behavior that could differ (dates, numbers, ordering, text encoding, error messages and types, default values).
4. Integration or end-to-end run of the main flows.
5. Differential run: same inputs through old and new, compare outputs.
6. Performance and memory check on a realistic workload when the library is on a hot path.
7. Staged rollout with monitoring; error rates and latency compared before and after.

## Finishing checklist

- [ ] Inventory (old pattern) = 0 in source, tests, docs, config, scripts, CI.
- [ ] Old dependency removed from manifests and lockfiles; old config and flags removed.
- [ ] Adapters/shims deleted; temporary tests and comments removed.
- [ ] Docs, README, onboarding notes and examples updated.
- [ ] A guard (lint rule, test, or CI grep) prevents regressions.
- [ ] Rollback no longer needed and the old path was deleted deliberately, not forgotten.
- [ ] Lessons and decisions recorded (`write-adr`).
