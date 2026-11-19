# Four kinds of documentation

- **Tutorial** (learning): guided steps to a first success; safe, minimal choices.
- **How-to** (task): "How to configure X"; assumes basics, lists steps and expected results.
- **Reference** (facts): options, commands, API, config keys, exit codes, defaults; complete and dry.
- **Explanation** (understanding): architecture, trade-offs, why.
Do not mix them in one page. Docstrings: summary line, args, returns, raises, one example when non-obvious. Put commands the reader must copy in code blocks, expected output below.
Troubleshooting format: Symptom -> Cause -> Fix.
