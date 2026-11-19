---
name: upgrade-dependencies
phase: rawat
description: Upgrade project dependencies safely - inventory what is outdated or vulnerable, classify updates by risk (patch, minor, major), upgrade in small groups with a green baseline, read changelogs for breaking changes, run tests after each step, and record what changed. Includes a script that lists outdated and unpinned dependencies per ecosystem. Not for a language or framework migration (migrate-code) or a full vulnerability audit (security-audit). Triggers - "update dependencies", "upgrade packages", "outdated packages", "bump the libraries", "npm audit fix", "dependabot", "upgrade python version", "update requirements".
---

# Upgrade dependencies

**Goal:** stay current and patched without breaking the project: small, tested, reversible steps.

## Ground rules
1. **Green baseline first.** Run tests/lint/types before touching anything; record failures that already exist.
2. **Group by risk,** one group per commit: security patches, patch/minor, then each major alone (`references/upgrade-strategy.md`).
3. **Read the changelog** of every major (and risky minor) before upgrading; list the breaking changes that apply to this code.
4. **Lockfile discipline:** change the manifest and lockfile together; no hand-edited lockfiles; no unrelated churn.
5. **Test after each group;** if it breaks, bisect the group, pin the offender with a comment explaining why.
6. **Never `--force` resolutions or silence audit findings** without stating the reason; do not downgrade security.
7. **Network/package installs need approval** if the environment restricts them; say what you could not run.

## Procedure
1. Inventory: `python "<this skill's directory>/scripts/outdated.py" [path]` - detects ecosystems, shows outdated (when the tool is available), unpinned/URL/git dependencies, EOL runtime hints.
2. Plan the groups and order; get a yes for the plan if it includes majors.
3. For each group: upgrade, install, run tests, fix code for breaking changes (with `refactor-code` discipline), commit.
4. Re-run the audit command of the ecosystem; compare before/after.
5. Report: upgraded, skipped (and why), pinned, vulnerabilities remaining, follow-ups.

## Definition of done
- [ ] Baseline known; each group tested; lockfile consistent.
- [ ] Breaking changes handled or deferred with reason; audit before/after reported.

## Pitfalls
Upgrading everything at once. Ignoring transitive vulnerabilities. Trusting a green test suite with poor coverage (smoke-test manually). Mixed lockfile managers. Bumping the runtime and libraries together.

## Hand-offs
| Next | Load |
|---|---|
| big framework jump | `migrate-code` |
| vulnerabilities | `security-audit` |
| tests lacking | `write-tests` |
| commit | `commit-and-pr` |
