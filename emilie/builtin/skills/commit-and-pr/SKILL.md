---
name: commit-and-pr
phase: rilis
description: Turn finished work into clean commits and a pull request - review what is staged, split unrelated changes, write Conventional Commit messages that explain why, check for secrets and leftovers, push the branch and write a PR description with summary, testing and risk. Includes a script that summarizes the working tree and flags problems before committing. Commits and pushes only when asked. Not for reviewing someone else's change (review-code) or cutting a release (prepare-release). Triggers - "commit this", "make a commit", "write a commit message", "open a PR", "create a pull request", "push my changes", "split this into commits", "PR description".
---

# Commit and PR

**Goal:** history a reviewer can read and revert: small logical commits, honest messages, and a PR that says what, why, how tested and what is risky.

## Ground rules
1. **Only commit or push when the user asks.** Show the plan first; never `--force`, `--no-verify`, or amend published commits without explicit approval.
2. **Stage deliberately** (`git add -p` or named files), never `git add -A` blindly; check the diff of what is staged.
3. **One logical change per commit;** tests with the code they cover; unrelated formatting separate.
4. **Message explains why.** Subject <= 72 chars, imperative, Conventional type (`references/commit-messages.md`); body for motivation and trade-offs.
5. **Nothing secret or accidental:** run the script, never commit `.env`, keys, large binaries or debug leftovers.
6. **Match the repo's conventions** (look at `git log`), and the project's attribution rules.

## Procedure
1. Brief: `python "<this skill's directory>/scripts/commit_prep.py"` - branch, staged/unstaged/untracked, size, secret-like lines (masked), debug leftovers, suggested commit type and scope, and whether to split.
2. Run the project's tests/lint on the change (`build-feature`).
3. Propose the commit plan (which files per commit, message each) and get a yes.
4. Commit; on hook failure fix the cause and create a NEW commit, do not bypass.
5. For a PR: confirm the base branch, push with upstream, then `gh pr create` (if allowed) with the template in `references/pr-template.md`; link the issue.
6. Report the commit hashes, the PR URL, and anything not verified.

## Definition of done
- [ ] Only intended files committed; no secrets or leftovers.
- [ ] Messages follow the convention and explain why.
- [ ] Checks run or "not run" stated; PR has summary, testing, risk, linked issue.
- [ ] No force-push, hook bypass, or history rewrite without approval.

## Pitfalls
Giant "misc fixes" commits. Messages that restate the diff. Committing generated files or lockfile churn by accident. Pushing to the default branch. Forgetting to rebase/merge the base and rerun tests.

## Hand-offs
| Next | Load |
|---|---|
| self-review before PR | `review-code` |
| release | `prepare-release` |
| CI failing on the PR | `setup-ci-cd` |
