---
name: write-changelog
phase: rilis
description: Write or update a changelog and release notes from the real history - collect commits and merged PRs since the last release, group them for users (Added, Changed, Fixed, Removed, Security, Breaking), rewrite developer jargon into user-facing sentences, and keep the file's existing format. Includes a script that drafts entries from git log. Not for choosing the version (prepare-release) or commit messages (commit-and-pr). Triggers - "write the changelog", "release notes", "what changed since", "update CHANGELOG", "summarize the commits", "what's new in this version".
---

# Write changelog

**Goal:** tell users what changed and what they must do about it, accurately, in their words.

## Ground rules
1. **Source from history, not memory.** Use `git log`, tags and PR titles; every entry must trace to a commit or PR.
2. **Write for users,** not maintainers: the effect, not the refactor. Drop noise (typos, CI tweaks, merges) unless users feel them.
3. **Breaking changes first,** with a migration instruction.
4. **Follow the existing format** of the project's CHANGELOG (Keep a Changelog is the default: `## [1.2.0] - 2026-11-15`).
5. **Do not invent.** If a commit is unclear, read its diff or ask; never guess impact.
6. **Credit and link** issues/PRs when the project does so; never include secrets or private ticket text.

## Procedure
1. Find the range: last tag to HEAD (`git describe --tags --abbrev=0`).
2. Draft: `python "<this skill's directory>/scripts/changelog_draft.py" [--since TAG] [--version X.Y.Z]` - groups conventional commits, flags breaking changes, lists unclassified commits for you to judge.
3. Edit: merge duplicates, rewrite each line as "what the user can now do / what was fixed / what behaves differently" (see `references/style.md`), classify the "other" bucket by reading diffs.
4. Insert under `## [Unreleased]` or a new version heading, update compare links at the bottom if the file uses them.
5. Show the user the diff; do not commit unless asked.

## Definition of done
- [ ] Every entry traces to history; breaking changes and migrations are explicit.
- [ ] Format matches the existing file; date and version correct.
- [ ] Internal-only noise removed; nothing invented.

## Pitfalls
Copying commit subjects verbatim. Missing a breaking change hidden in a "refactor". Wrong date or version. Dumping the whole log. Forgetting security fixes (give them their own heading).

## Hand-offs
| Next | Load |
|---|---|
| ship it | `prepare-release` |
| commit the file | `commit-and-pr` |
