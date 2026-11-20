# Prioritizing debt

Score = (pain per occurrence x how often it bites) / effort to fix. Add risk (data loss, security, outages) as a multiplier.
High priority: hotspots (big AND frequently changed), code behind recurring bugs, missing tests on critical paths, build/test steps that slow everyone, undocumented tribal knowledge, EOL runtimes/dependencies.
Low priority: ugly but stable, rarely edited, isolated, scheduled for removal.
Quick wins: dead code removal, flaky test fixes, lint autofixes, renaming a confusing public name, deleting unused dependencies.
Categories: design, code, test, dependency, docs, build/tooling, knowledge.
Present as a table: item | evidence | impact | effort | recommendation (do now / schedule / accept).
