# Conventional Commits mapping

| Type | Section |
|---|---|
| feat | Added |
| fix | Fixed |
| perf | Changed (performance) |
| refactor, style, chore, build, ci, test, docs | usually omitted (docs: only if user docs changed) |
| revert | Fixed / Changed (say what was reverted) |
| `!` after type or `BREAKING CHANGE:` footer | Breaking |
| security, CVE in body | Security |

Scope `(auth)` becomes a prefix: "**auth:** ...". Commits that do not follow the convention go to "other" and need a human read.
