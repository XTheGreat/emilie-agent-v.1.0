# Changelog style

Headings (Keep a Changelog): Added, Changed, Deprecated, Removed, Fixed, Security. Add **Breaking** at the top when needed.

Rewrite pattern:
- commit `fix(auth): handle None in token refresh` -> "Fixed a crash when refreshing an expired session."
- commit `feat: add --json flag` -> "Added `--json` to print machine-readable output."
- commit `refactor!: rename config key` -> "**Breaking:** config key `old` is now `new`. Rename it in your config file."

Rules: start with a verb, present or past consistently; one change per line; mention the command, option or screen the user sees; no commit hashes in prose (link instead); keep each line under ~120 chars; most important first.

Skip: formatting, CI, dependency bumps without user effect, tests, internal renames. Include dependency bumps only for security fixes or changed requirements.
