# Smell -> refactoring catalog

Pick the smallest transformation that removes the pain. Each entry: the symptom, the move, and how to do it safely.

## Functions and methods

| Smell | Refactoring | How |
|---|---|---|
| Long function (over ~50 lines, many comment-separated sections) | **Extract function** | Pick a block that does one thing; move it to a function named for its intent; pass what it reads, return what it produces; run tests; repeat |
| Deep nesting (over 3 or 4 levels) | **Guard clauses / early return**; extract the inner block | Invert conditions that exit early (`if not x: return`); flatten `else` branches; extract loop bodies |
| Many parameters (over 5) | **Introduce parameter object** / make a config dataclass | Group parameters that travel together; add the object as an overload first, migrate callers, then drop the old |
| Boolean flag parameters (`do(x, True, False)`) | **Split function** or use named arguments / enum | Create two named functions; keep the old one delegating until callers move |
| Temporary variable chains, unclear expressions | **Inline** or **extract variable** with a meaningful name | Name the intermediate result; inline trivial ones |
| Duplicated code | **Extract function**, then call from both places | Make copies identical first (parameterize the differences), extract, replace |
| Comment explaining a block | **Extract function** named after the comment | Delete the comment when the name says it |
| Magic numbers and strings | **Replace with named constant** or enum | Search for other occurrences before naming |
| Function does a query and a command (returns and mutates) | **Separate query from modifier** | Split; update callers |
| Output parameters / mutation of arguments | **Return a value** | Return the changed data; assign at the call site |

## Data and conditionals

| Smell | Refactoring | How |
|---|---|---|
| Long if/elif chains on a type or code | **Lookup table** (dict of handlers) or **polymorphism** | Table first if each branch is small; classes when branches share state |
| Repeated `if x is None` checks | **Null object** / default values / early validation at the boundary | Normalize once at the edge |
| Primitive obsession (strings for money, ids, emails) | **Introduce value type** | Wrap with validation; migrate usage gradually |
| Data clumps (same 3 fields everywhere) | **Introduce class / record** | |
| Complex boolean expressions | **Extract predicate** with a name (`is_eligible(user)`) | Keep the expression identical; name only |
| Switch duplicated in many places | **Polymorphism** or a single function that owns the decision | |

## Classes and modules

| Smell | Refactoring | How |
|---|---|---|
| God class (does many unrelated things) | **Extract class** by responsibility | Move fields and methods that change together; keep a delegating facade until callers move |
| Feature envy (method uses another object's data more than its own) | **Move method** | Move, leave a delegate, then update callers |
| Shotgun surgery (one change touches many files) | **Move/Inline** to gather the concept in one place | |
| Divergent change (one file changes for unrelated reasons) | **Split module** | Separate by reason to change |
| Inappropriate intimacy / circular imports | **Extract shared interface** or reverse a dependency | Use `design-architecture`'s import graph to see cycles |
| Large module of utilities | **Move functions to where they are used** or to cohesive modules | Avoid new `utils` dumping grounds |
| Dead code | **Remove** | Prove it is unused: search, coverage, logs; delete in its own commit |
| Speculative generality (hooks and options nobody uses) | **Inline / collapse hierarchy** | Remove one layer at a time |
| Inheritance used for reuse | **Replace inheritance with composition** | Add a field of the old parent type and delegate |

## Names and layout

- Rename to reveal intent (`d` -> `days_until_due`). Rename one symbol at a time, with a repository-wide search for strings, docs, config, reflection and JSON keys.
- Move files to match the structure the team uses; update imports, build configs and docs in the same step.
- Make the main flow readable top-down: public functions first, helpers below, or the project's convention.

## Order of operations for a messy function

1. Pin behavior with tests.
2. Rename variables and functions for clarity.
3. Extract obvious blocks and constants.
4. Flatten nesting with guard clauses.
5. Remove duplication by extracting shared pieces.
6. Reconsider boundaries (move to the right module/class).
7. Re-run tests and metrics; stop when the pain is gone.

## When not to refactor

- No tests and no way to add them safely: propose tests first.
- Code is about to be deleted or replaced.
- A deadline fix is in flight in the same code (do it after, or coordinate).
- You do not yet understand the behavior: read and trace first (`trace-code`).
- The benefit is purely aesthetic and the code is stable and untouched.
