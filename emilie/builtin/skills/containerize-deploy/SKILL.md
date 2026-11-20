---
name: containerize-deploy
phase: rilis
description: Containerize an application and plan its deployment - write a small, reproducible, non-root Dockerfile with layer caching and a .dockerignore, add health checks and config through environment variables, compose a local stack, build and run it to verify, and describe the rollout (staging, canary, rollback). Includes a Dockerfile linter script. Not for pipeline YAML (setup-ci-cd) or incident rollback (emergency-rollback). Triggers - "dockerize", "write a Dockerfile", "containerize this", "docker compose", "deploy this app", "make a container image", "deploy to kubernetes", "production image".
---

# Containerize and deploy

**Goal:** an image that builds the same everywhere, runs as a non-root user with config from the environment, proves it is healthy, and can be rolled out and rolled back safely.

## Ground rules
1. **Read how the app starts first** (entrypoint, port, env vars, writable paths, external services) before writing anything.
2. **Small and reproducible:** pinned base tag (not `latest`), multi-stage build when a toolchain is needed, lockfile install, `.dockerignore` for `.git`, env files, caches.
3. **Non-root, minimal:** `USER` set, no secrets baked into layers or `ARG`, no `ADD` from URLs, no privileged mode.
4. **12-factor config:** settings from env vars, logs to stdout/stderr, graceful SIGTERM, state in volumes or external services.
5. **Health:** a cheap `HEALTHCHECK`/readiness endpoint that checks real dependencies lightly.
6. **Verify by running:** build, start, hit the health endpoint, check size and `docker history`; say if Docker is unavailable.
7. **No production deploy without approval;** staging first, with a stated rollback.

## Procedure
1. Inspect the project (`ci_detect.py` of `setup-ci-cd` finds stack and commands).
2. Write `Dockerfile` and `.dockerignore` from `references/dockerfile-patterns.md`; add `compose.yaml` for local dependencies when needed.
3. Lint: `python "<this skill's directory>/scripts/docker_lint.py" [Dockerfile]` and fix findings.
4. Build and run; test the health endpoint; confirm it runs as non-root and stops quickly on SIGTERM.
5. Deployment plan using `references/deploy-checklist.md`: target (compose, Kubernetes, PaaS), config and secrets, resources, replicas, probes, migration order, rollout strategy, rollback.
6. Report image size, run command, env vars required, and what you could not verify.

## Definition of done
- [ ] Image builds, runs, passes health check, non-root, no secrets inside.
- [ ] `.dockerignore`, pinned base, cache-friendly layer order.
- [ ] Config via env; deployment and rollback steps written.

## Pitfalls
`COPY . .` before dependency install (kills cache). Baking `.env` into the image. Running as root. Using `latest`. No signal handling (slow stop). Healthcheck that always passes. Migrations run by every replica at once.

## Hand-offs
| Next | Load |
|---|---|
| pipeline to build and push | `setup-ci-cd` |
| observe it in production | `setup-monitoring` |
| rollback | `emergency-rollback` |
| hardening | `security-audit` |
