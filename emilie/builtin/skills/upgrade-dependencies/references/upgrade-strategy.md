# Upgrade strategy

Order: 1) security fixes 2) patch bumps 3) minor bumps 4) majors one by one, most foundational (language runtime, framework) last and alone.
Risk signals: 0.x versions (any bump may break), peer-dependency ranges, packages with native extensions, packages you import widely, big version jumps (2+ majors: step through each).
Read: CHANGELOG / GitHub releases / migration guide; search the code for removed or renamed APIs (`grep`).
Commands: Python `pip list --outdated`, `pip-audit`; Node `npm outdated`, `npm audit`; Go `go list -u -m all`; Rust `cargo outdated`, `cargo audit`; Ruby `bundle outdated`.
Pin with a reason: `# pinned <2: library X 2.0 drops Python 3.9`. Add a reminder to revisit.
Rollback: each group is a commit; `git revert` it. Keep the lockfile in the same commit.
