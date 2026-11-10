---
name: evaluate-technology
phase: pahami
description: Compare libraries, frameworks, services or approaches for a concrete need and recommend one with evidence - criteria and constraints first, two to four real candidates (including "do not add anything"), facts from primary sources and live registry data, an honest scored comparison, and what would change the recommendation. Not for requirements gathering (clarify-requirements) or for recording the final decision (write-adr). Triggers - "which library", "which framework", "should I use", "compare", "pros and cons", "alternatives to", "best tool for", "evaluate", "is it worth switching to".
---

# Evaluate technology

**Goal:** help the user choose with their eyes open. Not "the most popular one", but the option that best fits *their*
needs and constraints, backed by facts you checked, with the trade-offs and the risks stated plainly.

## Ground rules

1. **Criteria before candidates.** Decide what matters (and how much) *before* looking at options, or the first option you
   like will quietly define the criteria.
2. **Fit beats fame.** Stars, downloads and blog posts measure attention, not suitability. Use them as signals only.
3. **Primary sources.** Prefer official docs, the project's repository and changelog, the registry, and the project's own
   issue tracker over articles and listicles. Blog posts age fast: note the date and the version they describe.
4. **Check the version you would actually use.** An API or limitation described for v2 may not hold in v4.
5. **Include the null option.** "Use the standard library", "keep what we have" and "build the small part ourselves" are
   candidates, and are often the right answer.
6. **Say what you verified.** Mark each fact **Checked** (you read or ran it), **Reported** (a source says so), or
   **Unknown**. Never present a vendor claim as measured fact.
7. **Recommend.** A comparison with no recommendation pushes the work back to the user. Give one, with a confidence level
   and the conditions that would change it.
8. **No installs in the user's project.** A trial run goes in a scratch folder, only if the user allows commands and the
   package comes from the real registry (check the spelling: look-alike names exist).

## Procedure

### Step 1 - Frame the decision

State in one or two sentences what is being decided and why now. Then collect the constraints that rule options in or out:
language and runtime versions, the existing stack (read the manifests), licence rules, hosting and budget, team skills,
performance or scale needs, security or compliance needs, and how long it must be maintained. If a constraint is unknown and it
matters, ask once (see `clarify-requirements`); otherwise state the assumption.

### Step 2 - Set the criteria and the weights

Choose 5 to 8 criteria from `references/criteria.md`, give each a weight (must-have, important, nice-to-have), and write one
line on how you will judge it. **Must-haves are pass or fail**; an option that fails one is out, however good the rest.

### Step 3 - Choose the candidates

Two to four, including the null option and the incumbent if there is one. How to find them: the ecosystem's own "awesome" or
official lists, the registry search sorted by relevance and by recent activity, what similar open-source projects use, and
what the framework's docs recommend. Explain in one line why each is on the list and why notable ones were left out.

### Step 4 - Collect facts

For each candidate, in this order:

1. **Registry and repository health.** Run
   ```
   python "<this skill's directory>/scripts/package_health.py" <pypi|npm|crates|go> <name> [<name> ...]
   ```
   It prints the latest version, release age and cadence, licence, runtime requirement, dependency count, downloads,
   GitHub activity, and warnings (deprecated, archived, stale, no licence, single maintainer, pre-1.0). Needs network access.
   Without it, use `web_fetch` on the registry page and the repository.
2. **Documentation and fit.** Read the getting-started page and the section on *your* use case. Does it do the thing you need
   natively, or via a plugin or workaround? Check the changelog for breaking changes and the migration notes between major
   versions.
3. **Issues and security.** Search the issue tracker for your use case and for open bugs that would hurt; check the security
   advisories (GitHub Security tab, the registry's audit, OSV). Note the response time on issues.
4. **Cost and lock-in.** Licence terms, paid tiers, hosting costs, data export, and how hard it is to leave.
5. **Evidence of real use.** Who runs it at your scale? Prefer concrete reports (case studies, issue threads) to marketing.

Use `web_search` and `web_fetch` for steps 2 to 5, and `tasks` to research several candidates in parallel with the same
brief. Record each fact with its source.

### Step 5 - Try it, if it is cheap and allowed

If the choice is close or risky and the user allows commands, run a **small spike** in a scratch folder (never in the
project): implement the one hard thing from the must-haves, time it, and note what was awkward. Report what you ran
and its output. A twenty-minute spike beats an hour of reading about the hard part.

### Step 6 - Score and decide

Fill the matrix from `references/decision-matrix.md`. Show raw facts in the cells, not just numbers, so the user can disagree
with a score. Apply the must-have filter first. Then weigh the rest, but do not hide behind arithmetic: if the numbers and
your judgement disagree, say so and explain.

### Step 7 - Write the recommendation

Lead with the answer: **"Use X"** (or "X unless Y"), your confidence (high, medium, low) and why in three bullets. Then the
trade-offs you are accepting, the risks and how to reduce them (pin versions, wrap it behind an interface, keep an exit
path), the migration or adoption cost, and **what would change the recommendation** (a requirement, a scale threshold,
a licence change). Keep the detailed matrix as an appendix.

### Step 8 - Offer the next step

Record the decision with `write-adr`, plan the adoption with `break-down-tasks`, or start building with `build-feature` or
`scaffold-project`.

## Definition of done

- [ ] The decision, constraints and weighted criteria are written down before the comparison.
- [ ] Candidates include the null option, and each is there for a stated reason.
- [ ] Every important fact has a source or a "checked" mark; unknowns are listed.
- [ ] Health data came from the registry or repository, not from an article.
- [ ] There is a clear recommendation with a confidence level and the conditions that would change it.
- [ ] Risks, lock-in and the cost of switching later are stated.
- [ ] No dependency was added to the user's project.

## Pitfalls

- **Popularity as proof.** A framework with 100k stars may be wrong for a 3-page site.
- **Stale sources.** Check the date and the version of every article and benchmark.
- **Vendor benchmarks and "10x faster" claims.** Look for the workload, the hardware and who ran it. Prefer your own spike.
- **Hidden requirements.** The option that wins on features may fail on licence, hosting or team skills.
- **Evaluating the wrong thing.** Compare the options on the user's task, not on a generic feature list.
- **Look-alike packages and typosquats.** Confirm the exact name, publisher and repository link.
- **Analysis paralysis.** If two options are close and the choice is reversible, pick the simpler one and say so.
- **Ignoring the cost of change.** Replacing the incumbent has a price. Include it.

## Hand-offs

| Next | Load |
|---|---|
| unclear needs first | `clarify-requirements` |
| record the choice | `write-adr` |
| design around it | `design-architecture` |
| set it up | `scaffold-project`, `integrate-third-party` |
| move off the old one | `migrate-code` |
