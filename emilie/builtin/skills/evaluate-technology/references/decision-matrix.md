# Decision matrix and recommendation template

Show facts in the cells, then a score. Someone who disagrees with a score should see exactly which fact to argue with.

Mark facts **C** (checked), **R** (reported by a source), **?** (unknown). Scores run 0 to 5 (0 = fails, 5 = excellent).

---

## 1. The decision
**Decision:** choose <what> for <purpose>.
**Constraints:** <runtime, licence, hosting, team, budget, timeline>.
**Out of scope:** <what this evaluation does not decide>.

## 2. Criteria
| # | Criterion | Weight | How it is judged |
|---|---|---|---|
| 1 | Licence compatible with commercial distribution | **must** | SPDX id on the registry and in the repo |
| 2 | Runs on Python 3.10 and Windows | **must** | `requires_python`, CI matrix, issues |
| 3 | Does the main job natively | 3 | docs page + 20-minute spike |
| 4 | Maintenance and health | 3 | `package_health.py`, issue response time |
| 5 | Switching cost | 2 | how many files would import it |
| 6 | Learning curve and docs | 1 | time to first working example |

## 3. Candidates
| Option | Why it is on the list |
|---|---|
| A: <name> | the incumbent / the most common in this ecosystem |
| B: <name> | newer, simpler API |
| C: do not add a library | the standard library may be enough for this small part |
*Left out:* <name> (archived), <name> (needs a hosted service we cannot use).

## 4. Comparison (facts, then score)
| Criterion | A | B | C |
|---|---|---|---|
| 1 Licence (must) | MIT (C) pass | Apache-2.0 (C) pass | n/a pass |
| 2 Python 3.10 + Windows (must) | yes; CI covers Windows (C) pass | yes (C) pass | yes pass |
| 3 Main job | native, 12 lines in spike (C) **5** | needs a plugin for X (R) **3** | 40 lines, hand-rolled (C) **2** |
| 4 Health | 6 releases/yr, last 2 months ago, 5 maintainers (C) **4** | 34 releases/yr, 3 maintainers (C) **5** | stdlib: stable, no new features **4** |
| 5 Switching cost | 38 call sites would depend on it **2** | wrapper possible, ~10 sites **3** | none **5** |
| 6 Learning curve | docs good; team knows it **5** | new concepts **3** | known **5** |
| **Weighted total** (weights 3,3,2,1) | **4.0** | **3.7** | **3.7** |

If the totals disagree with your judgement, say so and explain: "B scores lower mainly because of the plugin, which I could
not verify (marked R). If the plugin works as documented, B and A are close."

## 5. Recommendation
**Use A**, confidence **medium-high**.
- It does the main job natively and the spike confirmed it (C).
- It is maintained and the team already knows it.
- The switching cost is the weak point: limit it by wrapping A in one module.

**Trade-offs accepted:** a heavier dependency tree (28 direct dependencies) and a slower release rhythm than B.

**Risks and mitigations:** pin the version; keep the wrapper thin; re-check health before each major upgrade.

**What would change this:** if the requirement for X becomes must-have, B wins; if the project stays under 200 lines of this
logic, C is simpler and has no dependency at all.

**Not verified:** B's plugin behaviour under load; A's memory use above 1M rows.

## 6. Sources
- A docs, getting-started and migration notes: <url> (accessed <date>)
- Registry and repository data: output of `package_health.py` on <date>
- Spike: folder `scratch/spike-a/`, output pasted above
