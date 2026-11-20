---
name: setup-ci-cd
phase: rilis
description: Set up or repair a CI/CD pipeline - detect the stack and existing workflows, define stages (install, lint, test, build, release, deploy), add caching, matrix, least-privilege permissions and pinned actions, keep secrets out of the repo, and verify the workflow locally or by reading a real run. Includes a script that detects the stack, commands and existing CI. Not for container images (containerize-deploy) or releases by hand (prepare-release). Triggers - "set up CI", "add GitHub Actions", "CI/CD pipeline", "fix the pipeline", "workflow is failing", "automate tests on push", "add GitLab CI", "continuous deployment".
---

# Set up CI/CD

**Goal:** every push is verified the same way the developer verifies it locally, fast, with minimal permissions, and releases are automated and reversible.

## Ground rules
1. **Mirror local commands.** CI runs the same install/lint/test/build commands the project documents; do not invent new ones.
2. **Least privilege.** `permissions: contents: read` by default; grant write only to the job that needs it. Never `pull_request_target` with untrusted checkout; never interpolate `${{ github.event.* }}` into `run:`.
3. **Secrets live in the platform's secret store,** never in files; do not echo them; scope deploy secrets to protected environments.
4. **Pin and cache.** Pin third-party actions to a version or SHA; cache dependencies keyed by lockfile; cancel superseded runs.
5. **Fast feedback first:** lint and unit tests before slow jobs; fail early.
6. **Deploys need a gate** (branch/tag rule, approval, environment) and a rollback path.
7. **Do not push or enable workflows** without the user's approval; show the file first.

## Procedure
1. Detect: `python "<this skill's directory>/scripts/ci_detect.py" [path]` - languages, package manager, test/lint/build commands, versions, existing CI files, risky patterns in them.
2. Choose the platform (existing one, else GitHub Actions) and stages from `references/pipeline-patterns.md`.
3. Write the workflow(s) with caching, a version matrix only where the project supports several versions, and concurrency control.
4. Validate: lint the YAML (`python -c "import yaml"` parse, `actionlint` if available), dry-run commands locally, read one real run's logs if possible.
5. Add status badge/docs only if asked. Report what runs when, the secrets the user must add, and what is not covered.

## Definition of done
- [ ] Workflow parses; commands match local ones; permissions minimal; actions pinned.
- [ ] Caching and concurrency set; secrets documented not committed.
- [ ] Deploy gated; failure modes and required secrets reported.

## Pitfalls
Tests passing locally but not in CI (missing services, env, timezone). Caches that never invalidate. Matrix explosion. Long-lived cloud credentials instead of OIDC. Deploying from every branch.

## Hand-offs
| Next | Load |
|---|---|
| image and deploy target | `containerize-deploy` |
| flaky CI tests | `fix-flaky-tests` |
| pipeline security | `security-audit` |
| release automation | `prepare-release` |
