---
name: onboard-teammate
phase: rawat
description: Prepare a new contributor to be productive - gather real facts about the project (stack, layout, how to run, test and lint, conventions, entry points, key docs, first-task candidates), verify the setup steps work, and produce a concise onboarding guide with a first-day path and a good-first-issue list. Includes a script that collects the facts. Not for writing the full README (write-documentation) or explaining one module (explain-code). Triggers - "onboard a new developer", "onboarding guide", "getting started for new contributors", "new teammate", "how do I get set up", "CONTRIBUTING", "first issue", "ramp up on this repo".
---

# Onboard teammate

**Goal:** a newcomer goes from clone to a merged first change in a day, knowing where things live and how the team works.

## Ground rules
1. **Facts from the repo,** not assumptions: read config, scripts, CI and recent history; say what you could not confirm.
2. **Test the path:** run the setup, test and lint commands (with approval for installs); fix or flag steps that fail - that is the most valuable finding.
3. **Layered:** one-page overview first, details linked; the first hour must be doable without asking anyone.
4. **No secrets or private access details;** describe where to request them, not their values.
5. **Reflect real conventions** (branching, commit style, review rules, test expectations) visible in history and CI.
6. **Keep it maintained:** put the guide where it will be updated (`CONTRIBUTING.md` or `docs/onboarding.md`).

## Procedure
1. Collect: `python "<this skill's directory>/scripts/onboarding_facts.py" [path]` - languages, layout, entry points, commands (install/test/lint/build/run), env example, CI, docs, conventions from `git log`, active areas and top contributors by area, TODO/"good first issue" hints.
2. Verify the setup path by running it; record snags and the fixes.
3. Write the guide with `references/onboarding-template.md`: overview, setup, daily workflow, layout map, conventions, where to ask, first tasks, glossary.
4. Pick 3-5 first tasks (small, well-scoped, tested areas) with the file to start in.
5. Report what is verified and what the user must still supply (access, contacts, team norms).

## Definition of done
- [ ] Setup steps verified or marked unverified; commands copy-pasteable.
- [ ] Layout map, conventions, workflow and first tasks included.
- [ ] No secrets; owner and update location named.

## Pitfalls
Stale setup instructions. Assuming tribal knowledge. Dumping every doc link with no order. First tasks that touch the riskiest code. Forgetting accounts/permissions lead time.

## Hand-offs
| Next | Load |
|---|---|
| deeper project map | `project-overview` |
| explain a module | `explain-code` |
| README and reference | `write-documentation` |
