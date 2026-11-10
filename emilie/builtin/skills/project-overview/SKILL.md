---
name: project-overview
phase: pahami
description: Build an evidence-backed one-page map of an unfamiliar codebase - what it is, its stack, layout, how to run, build and test it, where execution starts, configuration, risks and unknowns. Read-only; installs and changes nothing. Not for tracing one feature (trace-code), explaining one file (explain-code) or diagnosing a failure (investigate-bug). Triggers - "what is this project", "give me an overview", "I just cloned this", "onboard me to this repo", "how does this repo work", "where do I start", "summarize the codebase", "map this project".
---

# Project overview

**Goal:** after about ten minutes of tool use, give the user a map they can act on: what this project is, how it is put
together, how to run it, and what to be careful about. A map, not a tour: short, structured, and every claim backed by
something you actually read or ran.

## Ground rules

1. **Evidence or silence.** Label each claim **Verified** (you read it, or ran it and saw the output), **Inferred**
   (reasoned from names or structure), or **Unknown**. Never present an inference as a fact. READMEs go stale, so check the
   important claims against the code or the CI config. **Numbers and facts about people or history** (how many commits,
   authors, tests, lines; "one maintainer"; "actively maintained") must come from a command or the inventory output. If you
   did not measure it, write "not checked" instead of guessing.
2. **Read-only.** Do not install dependencies, run migrations, start servers, build, or write files unless the user asked.
   Running the existing test suite or `--version`/`--help` is fine only if the user has allowed commands.
3. **Secrets stay shut.** Never open `.env`, key files, or credential files. Report that they exist; for `.env.example`
   list variable *names* only. If a secret appears anyway, do not repeat it in your answer.
4. **Breadth before depth.** Cover the whole project coarsely first, then go deeper only where the user's goal needs it.
5. **Do not dump.** No file trees pasted into the answer, no long quotes. Summarize and point to `path:line`.
6. **Be honest about size.** On a large repository say what you sampled and what you skipped.
7. **Never claim a command was denied unless you ran it and saw the refusal.** Read-only git (`log`, `shortlog`, `ls-files`)
   works even when other commands need approval; try it before writing "not checked".

## Procedure

Track the steps with `todo_write` when the repository is large. Start by saying in one line what you are about to do.

### Step 0 - Scope (one minute)

Confirm the folder you are mapping (`git rev-parse --show-toplevel`; in a sub-folder of a bigger repo, say so). Ask the user
only if the target is truly ambiguous, or if they have a goal that changes what matters ("I need to fix a bug in the
API" means go deep on the API, not wide on everything). Otherwise proceed.

### Step 1 - Run the inventory script

```
python "<this skill's directory>/scripts/inventory.py" <path>
```

On Windows use `python` or `py -3`; if neither exists, skip to the manual fallback below. The script is read-only and takes
about a second. It prints git facts, languages by lines, manifests and notable dependencies, CI workflows, README headings,
top-level layout, entry-point candidates, configuration (names only), test counts, and health signals (recent commits,
most-changed files, TODO counts, largest files).

Treat its output as **leads, not facts**. It cannot know what the code does.

*Manual fallback* (no Python): list the root with `glob`, then `read_file` the manifest, README, CI config, and any
`Makefile`/`justfile`. Use `git log --oneline -15` and `git ls-files | wc -l` (PowerShell: `(git ls-files).Count`).

### Step 2 - Read the few files that matter

Read these, in this order, skipping what does not exist: the README (headings and the "run" section), the main manifest
(`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`, ...), the CI workflow or Makefile (it holds the *real*
build and test commands), the agent-instruction files (`EMILIE.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`), and the
entry-point file the inventory suggested.

For a large or multi-package repository (more than about 2,000 files, or several manifests), do not read everything yourself:
use `tasks` to map up to four packages in parallel. Give each job a self-contained brief ("map the `api/` package: purpose,
entry point, key modules, how it is tested, external services; report in under 200 words with file paths").

`references/stack-signals.md` says what each file tells you and where to look for the entry point and the commands per
ecosystem.

### Step 3 - Follow one thread from entry to output

Pick the most central path (a web request, a CLI command, a job, the app's startup) and follow it for 3 to 6 hops,
noting `path:line` at each hop. This is the cheapest way to learn how the layers really connect, and it exposes
READMEs that no longer match the code. Stop at the first place the data leaves the project (database, network, disk).

### Step 4 - Establish how to run, test and build

Derive the commands from, in order of trust: the CI config, the Makefile/manifest scripts, the README. Where they disagree,
CI wins. Record each as *command, source, verified or not*.

Run nothing that installs or mutates. If the user has allowed commands and the test command is obviously safe, run it once
to learn the baseline (passes, fails, how long) and report the result exactly, including failures. Otherwise list what you
would run and offer to do it.

### Step 5 - Conventions and health

From the inventory and a few reads: code style tooling (formatter, linter, type checker), naming and layout patterns,
commit message style (`git log`), branching hints, test location and style. Then the honest part: the most-changed files
(the living core or a hotspot), test coverage by file count, TODO/FIXME density, very large files, missing CI, stale or
absent lockfiles, vendored or generated code that should be ignored.

### Step 6 - Write the overview

Use the structure in `references/overview-template.md`. Keep the main answer to roughly one screen of tables and bullets;
put detail the user may want later in an appendix section. Always include **Unknowns** and **Suggested next steps**.

### Step 7 - Offer the next step

End with two or three concrete options tied to what you found, for example: "trace how a request becomes a database write",
"get the tests running", "add the missing CI", "plan the feature you mentioned". Hand off to the matching skill
(see below) rather than starting another large task unasked.

## Definition of done

- [ ] The one-sentence description of the project is something the user could repeat to a teammate.
- [ ] Stack and versions come from manifests you read, not from guesses.
- [ ] Run, test and build commands are listed with their source, and you said which you actually ran.
- [ ] One end-to-end thread was followed with `path:line` references.
- [ ] Configuration is described by *names and purpose*, with no secret values.
- [ ] Risks and unknowns are explicit, and nothing inferred is passed off as verified.
- [ ] The answer fits roughly one screen, with an appendix for the rest.

## Pitfalls

- **Trusting the README.** It describes intent; CI and the code describe reality.
- **Counting vendored or generated code** as the project's own. Look at `.gitignore`, `vendor/`, `dist/`, lock files.
- **Missing the real entry point** in a monorepo: each package may have its own. Check workspace config.
- **Stopping at the file list.** Names mislead (`utils/` can hold the core); open a file in each important folder.
- **Running an install "just to see".** It changes the machine and can take minutes or fail. Ask first.
- **A confident tone over thin evidence.** If you read six files out of six hundred, say so.
- **Guessing at history.** "Single author", "abandoned", "well tested" are claims about people and coverage. Run
  `git shortlog -sn HEAD` or count test files before saying them, or write "not checked".
- **Hitting a blocked command and giving up.** If the inventory script cannot run (no Python, or commands are not
  allowed), use the manual fallback in Step 1 and say which facts you could not measure.

## Hand-offs

| If the user then wants to... | Load |
|---|---|
| follow one feature or function in depth | `trace-code` |
| turn a vague request into a spec | `clarify-requirements` |
| find out why something fails | `investigate-bug` |
| choose a library or approach | `evaluate-technology` |
| plan the work | `break-down-tasks` |
| understand one file or snippet | `explain-code` |
| write the onboarding guide | `onboard-teammate` |
