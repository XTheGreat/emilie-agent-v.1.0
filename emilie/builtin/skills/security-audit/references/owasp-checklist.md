# Security review checklist (OWASP Top 10 oriented)

Work through the items that apply. For each "no" or "unsure", trace the code and decide if it is a finding.

## A01 Broken access control

- [ ] Every route, RPC, GraphQL resolver and background action checks authorization on the **server**.
- [ ] Object-level checks: the code verifies that the *current user* may access *this id* (IDOR/BOLA). Changing an id in a request must not reveal another user's data.
- [ ] Function-level checks: admin and internal endpoints are protected, not just hidden in the UI.
- [ ] Multi-tenant isolation is enforced in queries (tenant id in every query or row-level security), not only by the application layer's good behavior.
- [ ] Mass assignment: request bodies are mapped to explicit allowed fields (no binding of `is_admin`, `role`, `price`).
- [ ] CORS lists specific origins; no wildcard with credentials. CSRF defenses on cookie-authenticated state-changing requests.
- [ ] Path handling cannot escape the intended directory (`..`, absolute paths, symlinks); file downloads authorize the user.
- [ ] Default deny: new routes are protected unless explicitly made public.

## A02 Cryptographic failures

- [ ] Data in transit uses TLS with verification enabled; HSTS on web apps; no mixed content.
- [ ] Passwords are hashed with a slow salted algorithm (argon2id, scrypt, bcrypt); never encrypted, never MD5/SHA-1/plain SHA-256.
- [ ] Sensitive data at rest is encrypted where required; keys are managed outside the code (KMS, vault) and rotated.
- [ ] Randomness for tokens, ids and secrets comes from a cryptographically secure source (`secrets`, `crypto.randomBytes`, `SecureRandom`).
- [ ] Modern algorithms and modes (AES-GCM, ChaCha20-Poly1305, Ed25519, RSA 2048+); no ECB, no static IV/nonce, no homemade crypto.
- [ ] Constant-time comparison for secrets and signatures; HMAC verification of webhooks.

## A03 Injection

- [ ] SQL/NoSQL: parameterized queries or ORM binding; no string-built queries; dynamic identifiers whitelisted.
- [ ] OS commands: no shell with user input; argument arrays; whitelist values.
- [ ] Template and expression injection (server-side templates, `eval`, expression languages); LDAP, XPath, header and log injection.
- [ ] XSS: output encoded for its context (HTML, attribute, JS, URL, CSS); no `innerHTML` with untrusted data; CSP in place; sanitizer for rich text.
- [ ] Deserialization of untrusted data uses data-only formats (JSON) with schema validation.
- [ ] XML parsers disable external entities and DTDs.

## A04 Insecure design

- [ ] Threat model exists for sensitive features (money, identity, files, admin).
- [ ] Business rules are enforced server-side (price, limits, state transitions); race conditions considered (double spend, concurrent updates, TOCTOU).
- [ ] Rate limiting and quotas on login, reset, search, signup, expensive operations; lockout or backoff on repeated failures.
- [ ] Abuse cases (enumeration, scraping, replay, spam) considered.

## A05 Security misconfiguration

- [ ] Debug mode, stack traces and verbose errors off in production; default accounts and sample apps removed.
- [ ] Security headers: CSP, X-Content-Type-Options, frame protection, Referrer-Policy, Permissions-Policy; cookies Secure, HttpOnly, SameSite.
- [ ] Least privilege for processes, containers (non-root, read-only filesystem, dropped capabilities), cloud roles and database users.
- [ ] Network exposure: only required ports; databases and admin panels not public; storage buckets private by default.
- [ ] Infrastructure as code reviewed (open security groups, public buckets, wildcard IAM).

## A06 Vulnerable and outdated components

- [ ] Dependencies pinned and locked; scanned (`sec_scan.py --osv`, `pip-audit`, `npm audit`, `cargo audit`, `govulncheck`); critical and exposed ones updated.
- [ ] Base images and OS packages updated; unsupported runtimes replaced.
- [ ] Install scripts and unusual sources reviewed; names checked for typosquatting; private package names protected against dependency confusion.

## A07 Identification and authentication failures

- [ ] Password policy sensible (length over complexity), breached-password check, no truncation; secure reset and email/phone verification flows (single-use, short-lived tokens).
- [ ] Brute-force and credential-stuffing defenses (rate limit, lockout/backoff, MFA).
- [ ] Sessions: random ids, rotated on login and privilege change, invalidated on logout and password change, sensible expiry; tokens not in URLs.
- [ ] JWT: signature and algorithm enforced (never `none`), expiry/audience/issuer checked, secrets strong, revocation strategy, no sensitive data in the payload.
- [ ] OAuth/OIDC: state and PKCE used, redirect URIs exact, tokens stored safely, scopes minimal.

## A08 Software and data integrity failures

- [ ] Updates, plugins and artifacts are verified (signatures, checksums); CI/CD pipelines protect secrets and require reviews for workflow changes.
- [ ] GitHub Actions/CI: no untrusted input in shell steps, `pull_request_target` not combined with PR code, pinned third-party actions, minimal token permissions.
- [ ] Insecure deserialization and auto-update mechanisms reviewed.

## A09 Logging and monitoring failures

- [ ] Security events are logged (logins, failures, permission denials, admin actions, data export) with who/when/where; logs are protected and tamper-evident.
- [ ] No secrets, tokens, passwords or personal data in logs or error messages; log injection prevented.
- [ ] Alerts for suspicious patterns; incident response contact and runbook exist.

## A10 Server-side request forgery

- [ ] Features that fetch URLs (webhooks, importers, previews, image proxies) restrict schemes and hosts, resolve and block private/link-local/metadata addresses (169.254.169.254), limit redirects, set timeouts and size limits, and do not return raw responses.

## Additional areas

- **Files and uploads**: validate type by content, limit size, randomize names, store outside the web root or in object storage with private ACL, scan if needed, serve with a safe content type and `Content-Disposition`.
- **Mobile and desktop clients**: no secrets in the binary or app bundle; certificate validation; secure storage (Keychain/Keystore); deep-link and intent validation.
- **APIs**: authentication on every endpoint, schema validation, pagination limits, no excessive data exposure in responses, versioned and inventoried (no forgotten old versions).
- **LLM and AI features**: untrusted text treated as data; tool and action permissions least-privilege; no secrets in prompts; outputs validated before use; injection and data exfiltration paths considered.
- **Privacy**: collection minimization, purpose limitation, consent where required, deletion and export paths, subprocessors, cross-border transfers.
- **Availability**: unbounded input sizes, regex backtracking, expensive queries, resource exhaustion, zip bombs, rate limits.
