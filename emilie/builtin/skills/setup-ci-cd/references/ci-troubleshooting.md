# CI troubleshooting

- Passes locally, fails in CI: differing versions, missing env var/service, case-sensitive paths, timezone/locale, unpinned deps, tests depending on order or network.
- "Permission denied" pushing/tagging: job lacks `contents: write`.
- Cache not restored: key changes every run or path wrong; use lockfile hash.
- Timeouts: parallelize, split slow tests, cache build outputs, set `timeout-minutes`.
- Secrets empty on forks: by design; do not work around with `pull_request_target`.
- Flaky: rerun to confirm, then `fix-flaky-tests`; never just add retries blindly.
- Read the first failing step, not the last error; download raw logs and artifacts.
