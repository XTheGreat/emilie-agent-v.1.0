---
name: design-api
phase: rencana
description: Design or review an API contract (HTTP/REST first, with notes for GraphQL, gRPC, webhooks and CLI/library interfaces) - consumers and use cases first, resources and operations, request and response shapes, errors, pagination, idempotency, auth, versioning and compatibility rules, delivered as a reviewable contract. Includes a linter for OpenAPI files and for routes found in source code. Not for the data model (design-database) or UI screens (design-ui-ux). Triggers - "design the API", "REST API", "endpoints for", "API contract", "OpenAPI", "swagger", "webhook design", "API versioning", "review this API", "breaking change".
---

# Design API

**Goal:** an interface that its consumers can use correctly on the first try, that fails in clear and recoverable ways,
and that can evolve without breaking the people who depend on it.

## Ground rules

1. **Consumers and tasks first.** Name who calls the API (your own front end, other teams, public developers, other
   services) and the tasks they must complete. Design around those tasks, not around the database tables.
2. **The contract is the product.** Anything observable is promised: field names, types, ordering, status codes, error
   shapes, timing. Decide on purpose what you promise.
3. **Read before you design.** If an API exists, run the linter (Step 2) and read three existing endpoints end to end. Match
   its conventions (naming, errors, pagination) unless you state why not. Consistency beats local perfection.
4. **Resources and standard verbs.** Nouns in paths, HTTP methods as verbs, standard status codes. A real command that is
   not a CRUD fit gets a clearly named action sub-resource (`POST /orders/{id}/cancel`), not a verb-in-path free-for-all.
5. **Errors are part of the design.** Every operation lists the failures that can happen, with a machine-readable code and a
   message a developer can act on. Never leak stack traces, SQL or internal ids in errors.
6. **Safe and idempotent on purpose.** GET never changes state. PUT and DELETE are idempotent. Retried POSTs that create
   or charge need an idempotency key.
7. **Every list is bounded.** No endpoint returns "all rows". Pagination, a maximum page size and a stable sort are part
   of the first version.
8. **Evolution rules before version 1.** Write down what counts as a breaking change and how consumers are told
   (`references/compatibility.md`). Adding is cheap; renaming and removing is expensive.
9. **Security is in the contract.** Authentication scheme, authorization per operation (including object-level checks),
   rate limits, input limits and what personal data crosses the wire.
10. **Mark each fact** as **Given**, **Checked** (read from the code or spec), **Assumed** or **Unknown**. No code is changed
    by this skill unless the user asks to implement.
    If a script could not be run (needs approval, missing runtime, no network), say "not run" and why; never describe a plan, schema or contract as validated or linted unless the tool actually ran.

## Procedure

### Step 1 - Pin down consumers and use cases

Write: who calls it, from where (browser, mobile, server, partner), what they need to accomplish (a short list of tasks, each
in a sentence), expected volume and latency, the style the consumers expect (REST/JSON, GraphQL, gRPC, webhooks) and
the constraints (existing auth, gateway, deadlines). Ask the user once for what is missing and matters. If the use cases are
vague, use `clarify-requirements` first.

### Step 2 - Learn what exists

1. Find the contract or the routes: `openapi.*`, `swagger.*`, route files, controllers, a `docs/` folder.
2. Run the linter:
   ```
   python "<this skill's directory>/scripts/api_lint.py" <openapi.json | openapi.yaml | source-dir>
   ```
   For OpenAPI it checks documented errors, success codes, pagination on lists, undeclared path parameters, request bodies on
   GET/DELETE, duplicate operation ids, security. For source it discovers routes (Flask, FastAPI, Express-style, Django,
   Spring, Gin-style) and checks path casing, verbs in paths, GET with side effects, duplicates, nesting depth, versioning.
   YAML specs need PyYAML; otherwise read them by hand. Route discovery is textual: mounted prefixes and dynamic routes can
   be missing, so confirm anything surprising in the code.
3. Note the conventions you must follow: casing, id format, envelope or bare objects, error shape, pagination style,
   timestamp format, auth header.

### Step 3 - Model resources and operations

List the resources (nouns the consumers care about), their identifiers, and relationships. For each task from Step 1 write the
call sequence and check it needs few round trips. Then fill an operations table: method, path, purpose, auth, success code,
error codes. Rules and idioms for paths, methods, status codes, filtering and long-running work are in
`references/rest-guide.md`. Use a sub-resource for ownership (`/orders/{id}/lines`) only one level deep; use filters for the rest.

### Step 4 - Design shapes and errors

For each operation: request (path, query, headers, body) and response bodies with field names, types, required or optional,
nullability, formats (ISO-8601 UTC timestamps, decimal money as strings or integer minor units with currency), enumerations
as documented sets, and an example. Define one **error format** for the whole API (a stable `code`, a human `message`, field
details for validation, a request id; RFC 9457 problem details is a good base) and the mapping from failures to status codes.

### Step 5 - Decide the cross-cutting behavior

State each, once, for the whole API: authentication and token lifetime, authorization checks (object level, not only route
level), pagination (cursor preferred for changing data; maximum page size), filtering and sorting syntax, idempotency keys,
concurrency control (`ETag`/`If-Match` or a version field for updates), rate limiting and the headers that report it, caching
headers, request size limits, time zones and locales, CORS if browsers call it, and deprecation signals (`Deprecation` and
`Sunset` headers plus changelog).

### Step 6 - Plan evolution

Choose the versioning approach (path `/v1`, header, or additive-only with no versions for small internal APIs), define breaking
vs non-breaking changes with `references/compatibility.md`, and state the deprecation window. If you are changing an existing API,
list every change and classify it. Plan contract tests so the spec and the implementation cannot drift apart.

### Step 7 - Write the contract and review it

Use `references/contract-template.md`; when the project uses OpenAPI, write it as OpenAPI (JSON or YAML) so tools can check it.
Run `api_lint.py` on the new contract and fix or explain every warning. Walk each task from Step 1 through it as the consumer
would, with a real example request and response, and check the unhappy paths: invalid input, missing auth, someone else's
object, duplicate submit, timeout then retry, a page boundary. Save it where the project keeps API docs, or offer a path.

### Step 8 - Hand off

Offer `design-database` if the model must change, `build-feature` to implement, `write-tests` for contract tests,
`write-documentation` for the guide, `security-audit` for sensitive APIs, and `write-adr` for decisions such as the versioning
or pagination style.

## Definition of done

- [ ] Consumers and tasks are listed, and each task has a worked call sequence.
- [ ] Each operation has method, path, auth, request, success response, and the errors it can return.
- [ ] One error format and one pagination style are defined and used everywhere; every list is bounded.
- [ ] Idempotency, concurrency control, rate limits and auth are decided for every write operation.
- [ ] Breaking-change rules, versioning and deprecation process are written down.
- [ ] The linter ran on the contract; each warning is fixed or explained.
- [ ] Examples exist for success and for at least one failure per operation.
- [ ] Facts about the existing API come from the spec or code (Checked), not memory.

## Pitfalls

- **API mirrors the tables.** Consumers end up joining the data themselves. Shape responses around tasks.
- **200 for everything, with `{ "error": ... }` inside.** Clients, caches and monitors rely on status codes.
- **Verbs in URLs** (`/getUser`, `/createOrder`), and GET endpoints that change data.
- **Unbounded lists, or offset pagination over data that changes** (skipped and duplicated rows). Prefer cursors.
- **Leaking internals:** auto-increment ids in public URLs where enumeration matters, database column names, stack traces.
- **Missing object-level authorization.** "Logged in" is not "allowed to read order 17".
- **Floating-point money; timestamps without zones; booleans as strings.**
- **Silent breaking changes:** renaming a field, tightening validation, changing a default, adding a required request field.
- **Chatty or mega-endpoints.** Either many round trips per task or one call returning everything. Count calls per task.
- **Inventing a new convention per endpoint.** Follow the existing ones.
- **Documented but untested.** A contract with no contract tests drifts within weeks.

## Hand-offs

| Next | Load |
|---|---|
| overall structure | `design-architecture` |
| data model | `design-database` |
| the screens that call it | `design-ui-ux` |
| implement | `build-feature` |
| contract tests | `write-tests` |
| docs for users | `write-documentation` |
| sensitive data or auth | `security-audit` |
| record a decision | `write-adr` |
