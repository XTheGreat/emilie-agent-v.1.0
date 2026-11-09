# Specification template

One or two pages. Plain words. Numbered items, so the user can say "change 4, drop 7".

Mark anything not stated by the user as *(assumption)*. Mark things the code told you with `path:line`.

---

```markdown
# <Feature name> - specification

**Status:** draft | confirmed by <name> on <date>
**Requested by:** <who>, because <the problem in their words>

## 1. Goal
One or two sentences: what changes for whom, and how we will know it worked.

## 2. Users and scenarios
- **<Role>** wants to <action> so that <benefit>.
- Main scenario, step by step (the happy path).

## 3. Scope
**In scope**
1. ...
**Out of scope** (explicitly, so nobody assumes it)
1. ...
**Later / maybe**
1. ...

## 4. Acceptance criteria
Each one is something a person or an automated test can check.

| # | Given | When | Then |
|---|---|---|---|
| A1 | a logged-in user with a verified email | they request a password reset | an email with a one-time link arrives within 1 minute |
| A2 | a reset link older than 30 minutes | the user opens it | they see "link expired" and a button to request a new one |
| A3 | an email that has no account | someone requests a reset | the page looks identical to the success case (no account enumeration) |

## 5. Edge cases and errors
| Situation | Expected behaviour |
|---|---|
| The same link is used twice | second use fails with "link already used" |
| The user requests 6 resets in an hour | rate limited; message says to try later |
| Email service is down | request is queued and retried; user sees "we will email you shortly" *(assumption)* |

## 6. Constraints
- Technical: follows existing conventions (`app/auth/`, error format at `app/errors.py:12`).
- Security / privacy: ...
- Performance / scale: ...
- Compatibility: browsers, API versions, data already in production.
- Legal / policy: ...

## 7. Assumptions (riskiest first)
1. *(assumption)* Only password accounts are in scope; SSO accounts are not.
2. *(assumption)* Existing email templates can be reused.

## 8. Open questions
1. <question> - recommended default: <default> - who decides: <name>

## 9. Done means
- All acceptance criteria pass; tests exist for A1-A3 and the edge cases.
- No open questions marked "blocking".
- Documentation / changelog updated if user-visible.
```

---

## Quality bar

- **Observable:** no criterion says "works well", "is fast", "is secure". It says what you would see or measure.
- **Complete both ways:** every in-scope item has a criterion; every criterion traces to an in-scope item.
- **Consistent:** read the criteria against each other for contradictions (a limit in one place, none in another).
- **Behaviour only:** no table names, endpoints or libraries unless the user required them. Those belong in the design.
- **Short:** if it is more than two pages, split the feature or move detail to an appendix.

## Given / When / Then in one line each
- *Given* the starting state, *When* one event happens, *Then* the observable result.
- Use one *When* per criterion. Two events means two criteria.
- For non-functional needs use a measurable form: "Given 10,000 rows, when the report is generated, then it finishes in under 5 seconds on the staging hardware."
