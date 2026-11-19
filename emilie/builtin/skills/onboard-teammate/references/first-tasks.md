# Choosing first tasks

Good: well-covered by tests, local blast radius, clear acceptance, touches one module, teaches the workflow (fix a documented bug, improve an error message, add a missing test, small CLI option, doc fix, remove dead code).
Avoid: security, data migrations, concurrency, public API changes, performance tuning, anything needing production access.
Give each: goal, files to start in, how to test, who reviews, expected size (under ~100 lines).
Sources: TODO/FIXME with context, issues labeled good-first-issue, undocumented flags, low-coverage modules.
