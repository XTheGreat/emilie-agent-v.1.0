---
name: trace-code
phase: pahami
description: Follow one feature, function, request or value through the real code and return a verified trace - ordered hops with path:line, the data crossing each hop, branches, side effects, failure paths and the gaps text search cannot see. Read-only. Use for "how does X work / what happens when Y" questions about a single behaviour, or to prepare a change or a bug hunt. Not for a whole-project tour (project-overview), explaining one snippet (explain-code) or finding a defect's root cause (investigate-bug). Triggers - "trace", "how does this work", "what happens when", "walk me through", "where does this value come from", "who calls this", "follow the flow", "what does this endpoint do".
---

# Trace code

**Goal:** answer "how does this actually work?" for one behaviour by following the *real* execution path, and hand back
a trace the user can verify: ordered hops with `path:line`, what data crosses each hop, the important branches, the side
effects, how it fails, and honest gaps where a text search cannot see.

## Ground rules

1. **Follow the code, not the names.** A function called `validate` may save to the database. Read the body before you
   describe it.
2. **One scenario at a time.** A trace is a single path through the system. State the scenario up front (the input and the
   conditions). List the other paths as *branches*; do not try to narrate every path at once.
3. **Every hop has a `path:line` you actually read.** No hop from memory or from a name.
4. **Mark the gaps.** Decorators, registries, dependency injection, event buses, reflection, config-driven pipelines and
   generated code hide calls from text search. When you hit one, say "gap", show how you resolved it (the registration
   site) or say that you could not.
5. **Read-only.** No temporary prints, no edits, no instrumentation unless the user asks. Offer a runtime check instead.
6. **Stop at boundaries.** Framework internals, library code, the database driver, the network. Name the boundary and move
   on, unless the user wants to go through it.
7. **Never claim a command was denied unless you ran it and saw the refusal.** Read-only git (`log`, `show`, `blame`) works
   even when other commands need approval; try it before writing "history not checked".

## Procedure

### Step 0 - Pin the question

Turn the request into: **start** (the trigger) -> **end** (the observable outcome), under a **scenario**, for a **purpose**
(understand, change it, or debug it; the purpose decides how deep and what to record). If something essential is
ambiguous, ask one short question; otherwise state your assumption in one line and go.

### Step 1 - Find the anchor

Start from whatever you have. Preferred order of reliability (details and examples in `references/techniques.md`):

| You have | Search for |
|---|---|
| a message, label or error text the user sees | that exact string: `find_symbol.py --string "..."` |
| a URL, route, CLI command, event or topic name | the literal in route tables, decorators, subscribers |
| a function or class name | `find_symbol.py <name>` (definitions, calls, imports, tests, grouped) |
| a config key, flag or environment variable | the key name, then who reads it |
| a table, column or queue name | the name in models, migrations, queries |
| a stack trace | the file and line; walk *up* the frames |

```
python "<this skill's directory>/scripts/find_symbol.py" <symbol> [path]      # or:  --string "text"
```
(On Windows `python` or `py -3`.) If it cannot run, use `grep` and `glob`. Trace *forward* from the trigger to learn what
happens; trace *backward* from the outcome to learn where a value or effect comes from.

### Step 2 - Read the anchor properly

Open the whole function (`read_file` with `offset` and `limit`), not just the matching line. Note: its inputs, what it
calls, its branches, what it changes, what it returns or raises.

### Step 3 - Walk the path

Keep a short list of hops and a frontier of calls still to resolve (use `todo_write` if the trace is long). For each call
on your scenario's path, find its definition and decide:

- **Follow** it if it changes data, state or control flow on this path.
- **Summarize** it in a clause if it is a utility (formatting, logging, a getter).
- **Stop** at a boundary and name it.

Also check what the name *really* resolves to: an interface with several implementations, a subclass override, middleware
that wraps the call, a decorator that changes behaviour. When the path fans out into three or more independent branches,
use `tasks` to trace them in parallel with self-contained briefs, then merge the results.

### Step 4 - Resolve the dynamic gaps

When a call has no visible definition, look for the registration site rather than guessing: a decorator
(`@app.route`, `@Injectable`), a registry or table (`handlers[name] = fn`), a dependency-injection binding, an event
subscription, a middleware or plugin list, a config file naming a class, or a reflection call. `references/techniques.md` has
the patterns per ecosystem. If you cannot resolve it, record it under **Gaps** with your best lead.

### Step 5 - Collect side effects and failure paths

For the path you traced, list what it touches: database reads and writes (and transaction boundaries), network calls,
files, caches, global or shared state, emitted events, logs and metrics. Then failure: where errors are raised, caught,
translated or swallowed, what the caller finally sees, and what is retried or rolled back. Note concurrency: async hops,
threads, queues, and anything where order is not the order of the source code.

### Step 6 - Cross-check

Look at the **TESTS** group from the finder: which tests exercise this path, and what they assert. If git history matters
(why is it like this, when did it change), use `git log -S"<text>"` or `git log -L :<func>:<file>`. If the user allowed
commands, run the narrowest existing test for the path and read the real output. Otherwise suggest a runtime check
(debugger breakpoint, one log line) rather than adding it yourself.

### Step 7 - Write the trace

Use `references/trace-template.md`: question, a three-line short answer, the hop table, branches and failure paths, side
effects, gaps and assumptions, how to verify, and what to read next. Quote only the few lines that carry the point.
For five or more hops add a one-line arrow summary (`request -> route -> service -> repo -> response`).

### Step 8 - Offer the next step

Tie it to the purpose: change it (`break-down-tasks`, `build-feature`), it misbehaves (`investigate-bug`), the user wants the
bigger picture (`project-overview`).

## Definition of done

- [ ] The scenario, start and end are stated.
- [ ] Every hop has a `path:line` you read, and the data crossing it is named.
- [ ] The main branch points and failure paths are listed, with where errors are handled.
- [ ] Side effects are listed (or "none found" with what you checked).
- [ ] Every gap is marked with the reason and your lead.
- [ ] At least one cross-check (tests, history, or a run), or an explicit "not cross-checked".
- [ ] The answer is readable without opening the code, and points to the code for anyone who wants to.

## Pitfalls

- **Stopping at the first match.** The first hit is often a test, a comment, or a re-export.
- **Following the wrong overload or a same-named function** in another module. Check the import.
- **Trusting comments and names** over the body.
- **Missing the wrapper:** middleware, decorators, interceptors and base classes run before and after your function.
- **Treating source order as execution order** in async, event-driven or callback code.
- **Tracing everything.** A trace that follows every call is unreadable. Keep to the scenario, summarize utilities.
- **Presenting a dynamic call as resolved** when you only found a plausible name.
- **A wall of pasted code** instead of a path the user can follow.

## Hand-offs

| If the user then wants to... | Load |
|---|---|
| see the whole project first | `project-overview` |
| find why it fails | `investigate-bug` |
| understand one function line by line | `explain-code` |
| change this behaviour | `clarify-requirements`, then `break-down-tasks` |
| judge the quality of this path | `review-code` |
