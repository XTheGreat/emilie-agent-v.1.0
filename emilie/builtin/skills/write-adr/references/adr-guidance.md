# When to write an ADR

Write one for decisions that are costly to reverse or affect many parts: data store, framework, auth approach, API style, deployment model, module boundaries, major dependency, deprecation policy, security trade-off.
Skip for local choices easily changed in a PR. Review ADRs in the PR that implements them. Keep a `README`/index listing number, title and status. Number sequentially, never reuse numbers. Lightweight formats: MADR, Nygard. Match what the repo already uses.
