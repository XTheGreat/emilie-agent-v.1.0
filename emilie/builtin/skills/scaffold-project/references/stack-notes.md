# Stack notes

Generators and versions change quickly. **Check the official documentation for the current command and flags before running
anything**, and pin the version you use. Commands below are the usual shapes, not guarantees.

## Python

- Layout: `src/<pkg>/`, `tests/`, `pyproject.toml` (PEP 621). Use a virtual environment (`python -m venv .venv`) or `uv`/`poetry` if the team does.
- Test: `pytest`. Lint/format: `ruff`. Types: `mypy` or `pyright` (opt).
- Packaging: `setuptools`, `hatchling`, or `poetry-core` as the build backend; define `[project.scripts]` for CLIs.
- Web: FastAPI (`pip install fastapi uvicorn`), Flask, Django (`django-admin startproject <name>`). Keep one command to run the dev server.
- Pitfalls: missing `__init__.py` confusion with `src/` layout; tests importing the package from the working directory instead of the installed one.

## Node / TypeScript

- Plain scripts and CLIs: ES modules (`"type": "module"`), `node --test` needs no dependencies (Node 18+).
- TypeScript: `typescript`, `tsx` or `ts-node` for running, `vitest` or `jest` for tests, `eslint` + `prettier` (or `biome`).
- Frameworks: Vite (`npm create vite@latest`), Next.js (`npx create-next-app@latest`), Express/Fastify (hand-rolled), NestJS CLI.
- Commit `package-lock.json` (or `pnpm-lock.yaml`, `yarn.lock`), set `engines.node`, and use one package manager.
- Pitfalls: mixing CommonJS and ESM; global installs; missing `files`/`exports` when publishing.

## Go

- `go mod init <module-path>`; module path is usually the repository URL for published code. `cmd/<name>/main.go` for multiple binaries, root `main.go` for one.
- Test: `go test ./...`. Lint: `go vet ./...` and `staticcheck` or `golangci-lint` (opt). Format: `gofmt`.
- Keep packages small; `internal/` for private code. Pitfall: wrong module path breaks imports later.

## Rust

- `cargo new <name>` (binary) or `cargo new --lib <name>`. Test: `cargo test`. Lint: `cargo clippy --all-targets -- -D warnings`. Format: `cargo fmt`.
- Commit `Cargo.lock` for binaries. Use workspaces when there are several crates.

## Java / Kotlin

- Spring Boot: start.spring.io (or `curl https://start.spring.io/starter.zip ...`); choose build tool (Maven or Gradle), Java version, minimal starters.
- Check the wrapper (`mvnw`/`gradlew`) is committed. Test with JUnit 5.

## .NET

- `dotnet new console|webapi|classlib -n <name>`; tests with `dotnet new xunit`; `dotnet test`.

## Ruby / PHP

- Rails: `rails new <name> --api` (or full stack) with a chosen database. Laravel: `composer create-project laravel/laravel <name>`.

## Static sites and front ends

- Hand-written HTML/CSS/JS is enough for small sites (use the bundled `static-web` stack): semantic HTML, `lang`, viewport, skip link, tokens, focus styles.
- Content sites: Astro, Eleventy, Hugo. Apps: Vite + a framework. Choose by need (`evaluate-technology`).
- Add a build only when you need one (bundling, TypeScript, content processing).

## Monorepos

- Only when several packages are released together. Use the ecosystem's workspace feature (npm/pnpm workspaces, Cargo workspace, Go workspaces, uv workspaces). One root CI, per-package tests.

## Containers and deploy (opt)

- Add a `Dockerfile` only when you deploy as a container: multi-stage build, non-root user, pinned base image, `.dockerignore`. See `containerize-deploy`.

## Checks after any official generator

1. Read the generated README and config; delete demo content you do not want.
2. Run install, test, lint, build, run.
3. Remove unneeded dependencies it added; update to the versions you need.
4. Check it did not create a git repository or commit unexpectedly (`git status`, `git log`).
5. Look for telemetry prompts or analytics it enabled by default.
