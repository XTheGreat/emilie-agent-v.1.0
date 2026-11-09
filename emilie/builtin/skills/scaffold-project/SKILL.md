---
name: scaffold-project
phase: bangun
description: Start a new project or service properly - pin down what it is and which stack, check the official generator before hand-rolling, create a minimal skeleton that builds, tests and lints from the first commit (layout, config, CI, README, ignore rules), prove it works by running it, and leave a clean first commit point. Includes a generator for Python, Node, Go, Rust and static-web skeletons. Not for adding a feature to an existing codebase (build-feature) or choosing between technologies (evaluate-technology). Triggers - "new project", "start a project", "scaffold", "bootstrap", "boilerplate", "set up a repo", "create an app", "starter", "init a project", "project structure".
---

# Scaffold project

**Goal:** a new project where `install`, `test`, `lint` and `run` work from the first minute, the structure fits the stack's
conventions, and nothing is there that the project does not need yet.

## Ground rules

1. **Know what you are building first.** Name the kind (CLI, library, web app, API, static site), the language and runtime
   versions, where it will run, and who maintains it. If the stack is not decided, load `evaluate-technology`; if the needs are
   unclear, load `clarify-requirements`. Do not guess a stack silently.
2. **Never scaffold into existing work.** Check the target directory first. If it exists and has files, stop and ask. Never overwrite,
   never `git init` inside an existing repository, never delete.
3. **Official generator or minimal skeleton, not a framework museum.** For a framework (Next.js, Django, Rails, Vite, Spring), use its
   official generator at a pinned, current version; for plain stacks, use the bundled generator or write the minimal files by hand.
   Prefer boring, widely used tools.
4. **Minimal means minimal.** Include only what is needed now: source, one passing test, lint/format config, `.gitignore`, README, CI.
   No speculative layers, plugin systems, Docker, ORMs or "enterprise" folders until a requirement asks for them.
5. **Works from the first commit.** The skeleton must install, pass its test, pass the linter and run. Prove it by running those commands
   and show the output; "should work" is not enough.
6. **Pin and justify dependencies.** Each dependency has a reason. Check names against the real registry (look-alike packages exist),
   use current stable versions, commit the lockfile for applications.
7. **No secrets, ever.** Provide `.env.example` with placeholder values, ignore `.env`, and put real keys in the environment or a vault.
8. **Don't pick the license for the owner.** Ask; if undecided, say so in the README and leave `LICENSE` out.
9. **Commands need consent.** Installing packages, running generators that download code, and `git init` change the machine or the
   network. Say what you will run and run them only when the user has agreed or the request clearly includes them. Report any command
   that was blocked or not run.
10. **Report what exists.** End with the file tree, the commands you ran and their results, the decisions made, and what is still a TODO.

## Procedure

### Step 1 - Decide the shape

Write down: purpose in one sentence; type (CLI, library, web app, API, static site, worker); language and minimum runtime version;
deployment target; team conventions to follow (an existing sibling project is the best template); testing and lint preferences;
package/registry for publishing (if any). Ask the user only for the missing items that change the structure.

### Step 2 - Check the ground

1. Confirm the target path and that it is empty or absent (`ls`). Choose a name that is valid for the ecosystem and unlikely to clash
   (for a published package, search the registry).
2. Look for an organization template or sibling project to copy conventions from (CI, lint rules, folder names).
3. Check installed tool versions (`python --version`, `node -v`, `cargo -V`, `go version`) against what the skeleton needs.

### Step 3 - Generate

Pick one:

- **Bundled generator** (plain stacks):
  ```
  python "<this skill's directory>/scripts/scaffold.py" --list
  python "<this skill's directory>/scripts/scaffold.py" <stack> <name> [--dir PATH] --dry-run
  python "<this skill's directory>/scripts/scaffold.py" <stack> <name> [--dir PATH]
  ```
  Stacks: `python-cli`, `node-cli`, `go-cli`, `rust-cli`, `static-web`. It refuses to overwrite, runs nothing, writes no license, and prints
  the next commands. Always preview with `--dry-run` first.
- **Official generator** (frameworks): see `references/stack-notes.md` for the usual commands and what to check. Pin the version and read
  what it produced before building on it.
- **By hand**: for anything else, follow the checklist in `references/skeleton-checklist.md` and keep it to the same minimum.

### Step 4 - Fit it to the real project

Edit the placeholders (TODO description, name, author), set the language version, add only the dependencies you actually use, and configure the
linter and formatter. Add `.env.example` if configuration is needed. Replace the demo code with the first real, tiny vertical slice only if the
user asked for it; otherwise leave the demo so the first change is theirs.

### Step 5 - Prove it works

Run, in order, and show the results: install, test, lint/format check, build (if any), run. Fix what fails. Then run the same commands that the CI file
runs, so the first push is green. If a command cannot be run (no runtime, no approval, no network), say "not run" and why; do not report the
skeleton as working.

### Step 6 - Document and hand over

Make sure the README has: what it is, quick start (the exact commands you just ran), layout, how to test, how to contribute, and the license
status. Add the contribution basics only if there are collaborators. Leave version control to the user's decision: if asked, `git init`, check
`git status` for unwanted files, and make one clean initial commit with `commit-and-pr`.

### Step 7 - Report

List: the structure created (tree), commands run with results, versions chosen and why, anything deliberately left out (Docker, CI deploy, database)
with the trigger for adding it, open TODOs, and the next step (`build-feature` or `break-down-tasks`).

## Definition of done

- [ ] The kind of project, stack and versions were confirmed or stated as assumptions.
- [ ] The target directory was empty or new; nothing existing was overwritten.
- [ ] Install, test, lint and run were executed, and the output was shown (or "not run" with the reason).
- [ ] The structure follows the stack's conventions and contains nothing speculative.
- [ ] `.gitignore` covers build output, environments and secrets; `.env.example` exists if configuration is needed; no secrets are present.
- [ ] CI runs the same commands that pass locally.
- [ ] README quick start is accurate; the license status is stated.
- [ ] Every dependency is justified, from the real registry, and pinned or locked as the ecosystem expects.

## Pitfalls

- **Over-scaffolding.** Ten empty folders and five frameworks for a script. Start small; add structure when the code needs it.
- **Copying an outdated tutorial or template.** Old versions, deprecated tools. Check the official docs and the current version.
- **Scaffolding over existing files** or inside another repository.
- **Not running it.** A skeleton that never ran often fails on the first command.
- **Global installs and sudo.** Use a virtual environment, local node_modules, or project-local tool versions.
- **Committing generated junk**: `node_modules`, `.venv`, build output, IDE settings, lockfile from a different tool.
- **Silently choosing a license, a name or a registry scope** on the owner's behalf.
- **Typosquats.** `reqeusts` is not `requests`. Verify names and publishers before adding dependencies.
- **CI that differs from local.** The first push fails because the CI uses another command or version.
- **No test.** Even a skeleton needs one passing test so the harness is proven.

## Hand-offs

| Next | Load |
|---|---|
| choose the stack | `evaluate-technology` |
| decide the structure | `design-architecture` |
| plan the first slices | `break-down-tasks` |
| build the first feature | `build-feature` |
| set up CI/CD properly | `setup-ci-cd` |
| container and deployment | `containerize-deploy` |
| first commit and PR | `commit-and-pr` |
