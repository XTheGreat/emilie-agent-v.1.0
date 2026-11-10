# Writing review feedback

## Severity levels

| Level | Meaning | Author must |
|---|---|---|
| **Blocker** | Bug, data loss, security hole, broken compatibility, crash, missing test for risky logic | fix before merge |
| **Major** | Likely problem or significant design/maintainability issue; wrong behavior in a realistic case | fix, or explain why not |
| **Minor** | Real but small improvement: naming, clarity, small inefficiency, missing edge-case test | fix if easy; otherwise follow-up |
| **Nit** | Taste or tiny style point | optional; prefix with `nit:` |
| **Question** | You do not understand; a clarification may reveal a bug or need a comment | answer |
| **Praise** | A specific thing done well | none (but say it) |

Say clearly which are blocking. Never block on a preference the project does not enforce.

## Evidence labels

- **Verified**: you ran it, reproduced it or traced it end to end.
- **Likely**: strong reading of the code, not run.
- **Question**: you cannot tell.

## Anatomy of a good comment

```
[Major] orders/service.py:88  (Verified)
`apply_coupon` is called after `total` is saved, so the discount is never persisted; a repeated checkout charges the full price.
Reproduced with test_checkout_twice (attached below).
Suggest: apply the coupon before `save_total(...)`, and add a test for the second checkout.
```

Parts: where (file:line), what is wrong, the consequence or failure scenario, how sure you are, and a suggestion or question. Keep it to what the author needs to act.

## Tone

- Ask rather than accuse: "What happens if `items` is empty here?" over "You forgot the empty case."
- Describe the code, not the person: "this function does two things" not "you wrote a messy function".
- Offer the reason, not only the rule.
- Acknowledge good work with specifics ("the parameterized fixtures make the edge cases easy to read").
- Prefer one clear suggestion to a vague "consider refactoring".

## Review summary template

```
Summary: <what the change does, in one sentence>. <Overall impression, one sentence.>
Verdict: Approve | Approve with minor comments | Request changes | Need more information

Blockers
1. [file:line] ...
Major
1. ...
Minor / nits
- ...
Questions
- ...
Good things
- ...
Checked: <tests, lint, types run - results>; <behaviors exercised>
Not reviewed / not verified: <what, and why>
Follow-ups (outside this change): <pre-existing issues noticed>
```

## Verdict rules

- **Approve**: you read it all, nothing blocks, residual risks are stated.
- **Approve with minor comments**: no blockers or majors; list small items.
- **Request changes**: at least one blocker or an unresolved major; list exactly what must change.
- **Need more information**: the intent, context or a result you need is missing; ask specific questions.

## When the change is too big

Say it is too large to review reliably, list the parts you did review and those you did not, and propose a split (for example refactor in one PR, behavior change in another, migration separately)
or a live walkthrough. Do not approve what you did not understand.

## Giving the review to the user

- Put the verdict and blockers first; keep the whole text readable in about five minutes.
- Offer to turn findings into inline comments (`gh pr review --comment`, `gh pr comment`) only if the user wants them posted.
- For suggested code changes, give a small diff or snippet as a suggestion; do not apply it to the author's branch unasked.
- After the author updates, re-run the brief on the new range and check each earlier finding off one by one.
