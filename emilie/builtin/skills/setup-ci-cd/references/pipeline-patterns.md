# Pipeline patterns

Stages: checkout -> setup runtime (with cache) -> install (frozen lockfile) -> lint/format check -> type check -> unit tests (+coverage) -> build -> integration tests -> package -> (tag only) publish -> (protected env) deploy.

GitHub Actions skeleton:
```yaml
name: ci
on: { push: { branches: [main] }, pull_request: {} }
permissions: { contents: read }
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }
jobs:
  test:
    runs-on: ubuntu-latest
    strategy: { matrix: { python: ["3.11", "3.12"] } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}", cache: pip }
      - run: pip install -e ".[dev]"
      - run: ruff check . && pytest -q
```
Release job: `on: push: tags: ["v*"]`, `needs: test`, `permissions: id-token: write` for trusted publishing/OIDC.
GitLab: `stages:`, `cache: key: files: [lockfile]`, `rules:` instead of `only/except`, `environment:` with `when: manual` for prod.
Services (postgres, redis) via `services:`; wait for health before tests. Upload test reports and coverage as artifacts.
