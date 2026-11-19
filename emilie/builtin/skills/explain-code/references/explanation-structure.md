# Explanation structure

1. **In one sentence:** what it does and why it exists.
2. **Where it fits:** who calls it, what it calls, what data it touches.
3. **Inputs and outputs:** types, shapes, units, errors raised, side effects.
4. **Walkthrough:** numbered steps with `file:line`, following one example (e.g. input `"2026-11-15"` -> parsed -> validated -> stored).
5. **Key concepts:** terms, patterns, invariants the code relies on.
6. **Gotchas:** surprising behavior, performance, concurrency, error paths, legacy workarounds.
7. **Change safely:** tests that cover it, what to run, what could break.
Levels - beginner: analogy + plain words, skip edge cases; peer: flow and design intent; expert: complexity, trade-offs, alternatives.
Diagrams: ASCII boxes and arrows for data flow or call order; keep to 6-8 nodes.
