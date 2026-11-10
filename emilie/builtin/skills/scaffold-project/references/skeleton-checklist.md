# Minimal skeleton checklist

Every new project should have these, scaled to its size. Items marked (opt) are added only when a requirement calls for them.

## Files

| File | Purpose | Notes |
|---|---|---|
| Source folder (`src/<pkg>/`, `src/`, `cmd/`, ...) | the code | follow the ecosystem's convention |
| One real test | proves the harness works | named after behavior; runs with one command |
| Manifest (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`) | name, version, dependencies, scripts | set the minimum runtime version |
| Lockfile | reproducible installs | commit for applications; follow the ecosystem for libraries |
| `.gitignore` | keep junk out | build output, environments, caches, `.env`, IDE folders |
| `.editorconfig` | consistent whitespace across editors | |
| `README.md` | what, quick start, test, layout, license status | commands must be exact |
| Lint/format config | one tool per job, in the manifest if possible | |
| CI workflow | runs install, lint, test (matrix over supported versions) | the same commands as local |
| `.env.example` | documents configuration (placeholders only) | when any configuration exists |
| `LICENSE` | the owner's choice | do not choose silently |
| (opt) `CONTRIBUTING.md`, `SECURITY.md`, `CODEOWNERS` | when there are collaborators or users | |
| (opt) `Dockerfile`, compose file | when deploying as a container | see `containerize-deploy` |
| (opt) `docs/` | architecture notes, ADRs | when decisions need recording (`write-adr`) |
| (opt) pre-commit hooks | run format/lint before commit | |
| (opt) `CHANGELOG.md` | when releasing to others | `write-changelog` |

## Layout principles

- Source and tests are separate, or tests sit next to the source in languages that expect it (Go, Rust).
- Entry point is thin: parse input, call the library code, print/return. Logic lives in importable modules.
- One responsibility per module; name modules after what they do, not "utils" or "common".
- Configuration comes from the environment or files read in one place; no scattered `os.environ` calls.
- Group by feature (`orders/`, `billing/`) once there are several, rather than by technical layer, unless the framework dictates otherwise.
- Keep the root clean: configs at the top, everything else in folders.

## First-run verification (all must pass before reporting done)

1. Fresh install in a clean environment succeeds.
2. The test command passes (and fails if you break the demo code: try it once).
3. The lint/format check passes.
4. The program runs and prints something sensible; `--help` works for CLIs; the page loads for web projects.
5. The CI file runs only commands that exist and that you just ran locally.
6. `git status` (after an init, if requested) shows no generated junk or secrets.

## Versions and dependencies

- State minimum supported runtime (for example Python 3.9, Node 18) and test on the oldest and newest you claim.
- Prefer the standard library when it is enough. Each dependency: why, license, maintained, size.
- Dev tools (test, lint) go in dev dependencies/extras, not runtime dependencies.
- Let the tool add dependencies (`npm install x`, `cargo add x`, `pip install x` then record it) so versions and locks stay consistent.

## Security defaults

- `.env` ignored; examples contain placeholders only.
- No default passwords; secrets from the environment.
- Dependency update automation (Dependabot or Renovate) is a good (opt) addition once the repo is on a host.
- Enable the host's secret scanning and branch protection after pushing.
