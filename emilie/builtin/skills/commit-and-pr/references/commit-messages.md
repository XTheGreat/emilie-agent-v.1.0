# Commit messages

Format: `type(scope): subject` + blank line + body + footers.
Types: feat, fix, perf, refactor, docs, test, build, ci, chore, revert. `!` or a `BREAKING CHANGE:` footer marks a breaking change.

Subject: imperative ("add", not "added"), no trailing period, <= 72 chars.
Body (wrap ~72): why the change, what alternatives were rejected, side effects. Not a line-by-line diff narration.
Footers: `Fixes #123`, `Refs #45`, `Co-Authored-By: ...` (when the project or tool requires attribution).

Bad: "fix stuff", "update", "WIP". Good: "fix(auth): refresh token before expiry to stop 401 loops".
