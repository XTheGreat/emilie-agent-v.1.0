# Release checklist

Before: [ ] on release branch, up to date with remote [ ] clean tree [ ] tests, lint, types green [ ] no open blockers [ ] dependencies audited (`security-audit`) [ ] migrations reviewed and reversible [ ] docs and changelog updated [ ] version bumped everywhere.

Build: [ ] built from the release commit [ ] artifact contents inspected [ ] installed in a clean env [ ] smoke test passed [ ] checksums/signatures if the project uses them.

Ship (approval required): [ ] annotated tag pushed [ ] package published (PyPI/npm/crates/registry) [ ] release notes posted [ ] deploy started with a canary or staged rollout.

After: [ ] version visible in the running system [ ] error rate and latency watched for the agreed window [ ] announcement sent [ ] next dev version set if the project does that.

Abort triggers: error rate or latency above agreed threshold, failed smoke test, data-migration anomaly -> `emergency-rollback`.
