---
name: prepare-release
phase: rilis
description: Prepare a release safely - verify the tree is clean and green, decide the version bump from the changes, update version files and changelog, build the artifacts, tag, and write a go/no-go summary with a rollback plan. Includes a script that checks git state, version files, tags and unreleased commits. Does not publish or push unless the user says so. Not for the changelog text alone (write-changelog) or CI setup (setup-ci-cd). Triggers - "prepare a release", "cut a release", "bump the version", "ship it", "release checklist", "tag a release", "ready to release", "publish a new version".
---

# Prepare release

**Goal:** a release that is reproducible, versioned correctly, verified, and reversible - with an honest go/no-go.

## Ground rules

1. **Nothing irreversible without approval.** Tagging locally is fine; pushing tags, publishing packages, deploying and creating GitHub releases need the user's explicit yes.
2. **Release from a clean, green tree** on the intended branch. Uncommitted changes, failing tests or a stale branch mean no-go until resolved.
3. **Version by evidence.** Derive the bump (major/minor/patch) from what changed since the last tag, using `references/versioning.md`.
4. **One source of truth** for the version; update every place that repeats it, then grep for the old number.
5. **Build from the tag's commit,** not from a dirty directory, and verify the artifact (install it, run it).
6. **Write the rollback plan before you ship** (`emergency-rollback`).

## Procedure

### Step 1 - Brief
```
python "<this skill's directory>/scripts/release_check.py" [path]
```
Reports branch, cleanliness, upstream sync, last tag, commits since it (grouped by type, breaking changes), version files and whether they agree, changelog status, and CI config found.

### Step 2 - Gate
Run the project's tests, linter and type checker (commands: `build-feature/scripts/detect_commands.py`). Any failure is no-go; report it, do not hide it.

### Step 3 - Decide the version
Breaking change -> major (or minor while 0.x per project policy), new feature -> minor, fixes only -> patch. State the reasoning and the commits that drive it.

### Step 4 - Update files
Bump version files, finalize the changelog (`write-changelog`), update docs and migration notes. Commit as `chore(release): vX.Y.Z`.

### Step 5 - Build and verify
Build with the project's command, inspect the artifact contents (no secrets, no tests-only files, correct version), install it in a fresh environment and smoke-test the main command.

### Step 6 - Tag and (with approval) publish
`git tag -a vX.Y.Z -m "..."` then, only if approved, push, publish, create the release notes. Follow `references/release-checklist.md`.

### Step 7 - Report
Go/no-go, version, what ships, what was verified and not, rollback steps, post-release checks (monitoring, smoke test).

## Definition of done
- [ ] Tree clean, branch correct, tests/lint/types green or the failure reported.
- [ ] Version bump justified; all version references agree.
- [ ] Changelog updated; artifact built and smoke-tested.
- [ ] Tag created; publishing done only with approval.
- [ ] Rollback plan written.

## Pitfalls
- Releasing from a feature branch or dirty tree. Forgetting a second version file. Moving a tag after publishing. Publishing before verifying the artifact. Skipping migration notes for breaking changes.

## Hand-offs
| Next | Load |
|---|---|
| changelog text | `write-changelog` |
| commit and PR | `commit-and-pr` |
| automate the pipeline | `setup-ci-cd` |
| deploy | `containerize-deploy` |
| it went wrong | `emergency-rollback` |
