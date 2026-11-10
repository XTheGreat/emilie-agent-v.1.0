# Evaluation criteria

Pick the 5 to 8 that matter for *this* decision. Give each a weight: **must** (pass or fail), **important**, **nice**.
For each, write how you will judge it before you look at the candidates.

## Fit (usually the most important)
| Criterion | Question | How to check |
|---|---|---|
| Does the job | Does it do the main thing natively, or only with plugins or workarounds? | Docs page for your use case; a spike for the hard part |
| Fits the stack | Language, runtime version, framework, build tool, platform support (Windows, Linux, ARM, browsers) | Registry `requires`; CI badges; issues about your platform |
| Fits the scale | Works at your data size, request rate, concurrency | Docs on limits; real reports at similar scale; a spike |
| Fits the team | Learning curve, familiar concepts, quality of docs and examples | Time to first working example; community answers |

## Health and sustainability
| Criterion | Question | How to check |
|---|---|---|
| Maintenance | Recent releases and commits? Issues answered? | `package_health.py`; issue and PR response times |
| Bus factor | One maintainer, a company, a foundation? | Contributors page; registry maintainers; governance doc |
| Maturity | Stable API (1.0+)? Breaking-change history? | Changelog; migration guides between majors |
| Community | Active discussions, answers, plugins, hiring pool | Issue tracker, forum, Stack Overflow volume (as a signal only) |
| Longevity risk | Archived? Deprecated? Single-vendor roadmap? | Repo banner; registry deprecation notice; announcements |

## Safety and legal
| Criterion | Question | How to check |
|---|---|---|
| Licence | Compatible with your distribution (commercial, SaaS, GPL concerns)? | Licence file and SPDX id; the transitive licences |
| Security | Advisory history? Fixes fast? Safe defaults? | GitHub Security tab, OSV, registry audit |
| Supply chain | Few and healthy dependencies? Signed releases? Scope of install scripts? | Dependency count; lockfile review; provenance info |
| Data and compliance | Where does data go (hosted services)? Residency, GDPR, retention | Vendor docs and DPA |

## Cost and effort
| Criterion | Question | How to check |
|---|---|---|
| Adoption effort | Time to integrate and to get the team productive | Spike; size of the API surface |
| Running cost | Hosting, licences, paid tiers, usage-based pricing | Pricing page at your volume |
| Switching cost | How hard to leave: data export, standard formats, wrappers | Docs; how much of your code would touch it |
| Operational load | Monitoring, upgrades, backups, on-call burden | Docs; what other users complain about |

## Quality attributes (include only if they matter here)
Performance (latency, throughput, memory), reliability (failure behaviour), observability (logs, metrics, tracing),
testability (mocking, local development), accessibility, internationalisation, extensibility, bundle size (frontend),
cold-start time (serverless).

## Red flags (any of these deserves a stated mention)
- Deprecated, archived, or last release more than 18 months ago (unless the scope is tiny and stable by nature).
- No licence, or a licence that conflicts with your use.
- A single maintainer for something critical.
- Breaking changes in every minor version; no migration notes.
- Install scripts that run arbitrary code; many unmaintained transitive dependencies.
- Claims without evidence ("10x faster" with no workload).
- Name very close to a famous package (possible typosquat).
- Hard lock-in: proprietary data formats, no export path.

## Weights, quickly
- 1 or 2 **must-haves** (pass or fail). Examples: licence allows commercial use; runs on our Python version; supports offline.
- 3 or 4 **important** (weight 3): fit for the main task, maintenance, security, switching cost.
- 1 or 2 **nice** (weight 1): extra features, nicer docs.
If more than half your criteria are "must", you are probably describing a solution, not a need. Revisit the requirements.
