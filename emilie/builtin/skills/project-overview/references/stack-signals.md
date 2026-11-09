# Stack signals: what a file tells you, and where to look next

Use this after the inventory script. Each row is a *lead*: confirm it by reading the file.

## Manifests and what they reveal

| File | Tells you | Look at |
|---|---|---|
| `package.json` | Node project: name, scripts, dependencies, `type` (ESM or CommonJS), `main`, `bin`, `workspaces` (monorepo) | `scripts` (the real commands), `engines` (Node version) |
| `pyproject.toml` | Python project: dependencies, Python version, console scripts, build backend, tool config (ruff, pytest, mypy, black) | `[project.scripts]`, `[tool.*]` |
| `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile` | Older or simpler Python packaging | extras, pinned versions |
| `go.mod` | Go module path and Go version | `cmd/*` folders hold executables |
| `Cargo.toml` | Rust crate or workspace; `[[bin]]` entries | `src/main.rs` (binary), `src/lib.rs` (library) |
| `pom.xml`, `build.gradle(.kts)` | JVM project; modules; Java/Kotlin version; plugins (Spring Boot?) | `<modules>`, `application.yml` |
| `*.csproj`, `*.sln`, `global.json` | .NET projects and SDK version | `Program.cs` |
| `composer.json` | PHP dependencies (Laravel? Symfony?) | `artisan`, `public/index.php` |
| `Gemfile` | Ruby (Rails? `config/routes.rb`) | `bin/rails` |
| `mix.exs`, `pubspec.yaml`, `CMakeLists.txt` | Elixir, Dart/Flutter, C/C++ | `lib/main.dart`, `main.cpp` |
| `Dockerfile`, `docker-compose.yml` | Runtime base image, exposed ports, backing services (db, cache, queue) | `FROM`, `EXPOSE`, `services:` |
| `Makefile`, `justfile`, `Taskfile.yml` | The project's own command vocabulary | targets named `test`, `lint`, `run`, `build` |
| `.github/workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile` | **The real build and test commands**, Node/Python versions, deploy steps | `run:` steps |
| `.nvmrc`, `.python-version`, `.tool-versions` | Exact runtime versions | |
| `.pre-commit-config.yaml`, `.editorconfig`, `.eslintrc*`, `.prettierrc`, `ruff.toml` | Code style tooling | |
| `tsconfig.json` | TypeScript settings; `paths` aliases explain odd imports | `include`, `paths` |
| `renovate.json`, `dependabot.yml` | Dependencies are maintained automatically | |
| `CODEOWNERS` | Who owns which part of the code | |

## Frameworks: how to recognize them and where execution starts

| Signal | Framework | Entry / structure to read |
|---|---|---|
| `react`, `vite.config.*`, `src/main.tsx` | React + Vite | `src/main.tsx` -> `App.tsx` -> routes |
| `next` in deps, `app/` or `pages/` | Next.js | the folder *is* the routing table; `next.config.js` |
| `vue`, `nuxt` | Vue / Nuxt | `src/main.ts`, `pages/` |
| `express`, `fastify`, `koa`, `@nestjs/core` | Node servers | server file named in `main` or `scripts.start`; routes folder; Nest: `main.ts` + modules |
| `django`, `manage.py`, `settings.py` | Django | `urls.py` -> `views.py` -> `models.py`; `INSTALLED_APPS` |
| `fastapi`, `flask` | Python web | the file with `FastAPI()` / `Flask(__name__)`; routers |
| `celery`, `rq`, `dramatiq` | Background jobs | task modules; broker URL in config |
| `rails` | Rails | `config/routes.rb` -> controllers -> models |
| `spring-boot-starter` | Spring Boot | `@SpringBootApplication` class; controllers; `application.yml` |
| `cmd/<name>/main.go` | Go service or CLI | each `cmd/*` is one executable |
| `[[bin]]` or `src/main.rs` | Rust CLI/service | `main()` and the `clap` or `axum` setup |
| `argparse`, `click`, `typer`, `cobra`, `clap` | CLI | the command definitions are the "routes" |
| `electron`, `react-native`, `expo`, Flutter | Desktop / mobile | main process / app entry plus platform folders |
| `terraform`, `*.tf`, `helm/`, `k8s/` | Infrastructure as code | modules, variables, environments |
| `dbt_project.yml`, `airflow`, notebooks | Data pipelines | DAG or model folders, config |

## Typical commands per ecosystem (verify against CI or the manifest before trusting)

| Ecosystem | Install | Run | Test | Lint / format |
|---|---|---|---|---|
| Node | `npm ci` (or `pnpm i`, `yarn`) | `npm run dev` / `npm start` | `npm test` | `npm run lint` |
| Python | `pip install -e .[dev]` / `uv sync` / `poetry install` | per README or console script | `pytest` | `ruff check .`, `black --check .` |
| Go | `go mod download` | `go run ./cmd/<name>` | `go test ./...` | `go vet ./...`, `golangci-lint run` |
| Rust | (cargo fetches) | `cargo run` | `cargo test` | `cargo clippy`, `cargo fmt --check` |
| Java (Maven) | `mvn -q dependency:resolve` | `mvn spring-boot:run` | `mvn test` | per plugins |
| Java (Gradle) | `./gradlew build -x test` | `./gradlew bootRun` | `./gradlew test` | per plugins |
| .NET | `dotnet restore` | `dotnet run` | `dotnet test` | `dotnet format --verify-no-changes` |
| Ruby | `bundle install` | `bin/rails s` | `bundle exec rspec` / `rails test` | `rubocop` |
| PHP | `composer install` | `php artisan serve` | `vendor/bin/phpunit` | `phpcs` |

Anything with `install`, `migrate`, `deploy`, `up`, `docker compose up`, or `terraform apply` **changes state**: describe it,
do not run it unasked.

## Layout conventions worth recognizing

- `src/` + `tests/` (library or app); `lib/` (Ruby, Elixir, Dart); `cmd/` + `internal/` + `pkg/` (Go); `app/` (Rails, Next, Laravel).
- Layered: `controllers|routes` -> `services` -> `repositories|models` -> database. The middle layer is usually where the rules live.
- Hexagonal / clean: `domain/`, `application/`, `infrastructure/`, `adapters/`.
- Monorepo: `packages/*`, `apps/*`, `services/*`, plus a workspace file (`pnpm-workspace.yaml`, `lerna.json`, `nx.json`,
  `turbo.json`, Cargo `[workspace]`). Map each package separately.
- Generated or vendored (do not count as the project's own): `dist/`, `build/`, `target/`, `node_modules/`, `vendor/`,
  `*.min.js`, `*_pb2.py`, `*.generated.*`, migrations (generated but worth skimming for the schema).

## Reading history for orientation (read-only git)

```
git log --oneline -15                                  # recent direction and message style
git shortlog -sn HEAD | head                           # how many people, how concentrated
git log --since=90.days --name-only --format= | sort | uniq -c | sort -rn | head -15   # hotspots
git log --diff-filter=A --format=%cs -1 -- <file>      # when a file was added
git blame -L <a>,<b> <file>                            # who and when for a specific region
```
(PowerShell: pipe to `Group-Object | Sort-Object Count -Descending | Select-Object -First 15` instead of `sort | uniq -c`.)
