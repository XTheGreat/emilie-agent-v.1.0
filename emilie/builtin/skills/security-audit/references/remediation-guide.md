# Remediation patterns

Fix the class of bug, not the single instance, and add a test that fails without the fix.

## SQL injection

```python
# bad
cur.execute(f"SELECT * FROM users WHERE name = '{name}'")
# good
cur.execute("SELECT * FROM users WHERE name = %s", (name,))        # driver placeholders
```
```js
// bad: db.query("SELECT * FROM t WHERE id = " + id)
db.query("SELECT * FROM t WHERE id = $1", [id]);                   // pg; use ? for mysql
```
Dynamic column or table names: map user choices to a fixed whitelist. ORMs: avoid raw SQL fragments with interpolation.

## Command injection

```python
# bad: os.system("ping " + host); subprocess.run("ls " + d, shell=True)
subprocess.run(["ping", "-c", "1", host], check=True)              # argument list, no shell
```
Validate against an allowlist (hostname regex, known directories). Prefer a library over spawning a process.

## Cross-site scripting

- Render with the framework's auto-escaping; do not bypass it (`|safe`, `mark_safe`, `dangerouslySetInnerHTML`, `v-html`) for untrusted data.
- Use `textContent` instead of `innerHTML`; sanitize necessary HTML with DOMPurify (client) or bleach/nh3 (server) with an allowlist.
- Add a Content-Security-Policy that forbids inline scripts; set `HttpOnly` cookies.

## Authentication and sessions

- Password hashing: `argon2-cffi`, `bcrypt`, or `scrypt` with per-user salt, tuned cost; rehash on login if parameters change.
- Session ids random (128+ bits), regenerate on login, expire idle and absolute, invalidate on logout and password change; cookies `Secure; HttpOnly; SameSite=Lax|Strict`.
- Reset tokens: random, single use, short expiry, stored hashed; do not reveal whether an account exists.
- Throttle logins (per account and per IP) and require MFA for sensitive accounts.

## Authorization (IDOR / broken access control)

```python
# bad: order = Order.get(order_id)
order = Order.get(order_id, owner_id=current_user.id)              # scope the query to the caller
if order is None:
    raise NotFound()                                                # 404, do not reveal existence
```
Centralize checks (decorator/middleware/policy objects), default deny, test each role with a matrix (user A cannot read user B's object, non-admin cannot call admin routes). Enforce tenant filters in the data layer (row-level security).

## Secrets

1. Rotate the exposed secret first (revoke at the provider).
2. Load from the environment or a secret manager; keep `.env` out of git (`.gitignore`), commit `.env.example` with placeholders.
3. Remove from history if needed (`git filter-repo`/BFG) after rotation; assume the old value is compromised regardless.
4. Add secret scanning (gitleaks/trufflehog or the host's native feature) as a pre-commit hook and in CI.

## Deserialization

Use JSON with schema validation (pydantic, JSON Schema, zod). For YAML use `safe_load`. Never `pickle`/`marshal` untrusted bytes; if inter-service Python objects are needed, sign and authenticate the channel and still prefer JSON.

## SSRF

Allowlist schemes (https) and hosts; resolve DNS and reject private, loopback, link-local and cloud metadata ranges after resolution (and again on redirects); disable redirects or re-validate each; set timeouts and size limits; use a dedicated egress proxy for user-supplied URLs.

## Path traversal and file handling

```python
base = Path("/srv/uploads").resolve()
target = (base / user_name).resolve()
if base not in target.parents and target != base:
    raise Forbidden()
```
Generate server-side filenames; check content type by content; limit size; store outside the web root; never execute uploads.

## Cryptography

- Hashing for integrity: SHA-256+. Passwords: see above. HMAC for message authentication with constant-time compare (`hmac.compare_digest`, `crypto.timingSafeEqual`).
- Encryption: AES-256-GCM or ChaCha20-Poly1305 via a vetted library (`cryptography`, libsodium, Tink); unique random nonce per message; keys from KMS.
- Random: `secrets.token_urlsafe(32)`, `crypto.randomBytes(32)`, `SecureRandom`.
- TLS: never disable verification; fix certificates or trust stores. Minimum TLS 1.2.

## JWT

Verify signature with a fixed algorithm allowlist, check `exp`, `nbf`, `aud`, `iss`; use strong secrets or asymmetric keys; keep access tokens short-lived; store refresh tokens safely and rotate them; no sensitive data in claims.

## CORS and CSRF

Allow specific origins; do not reflect arbitrary `Origin`; credentials only with exact origins. CSRF: SameSite cookies plus anti-CSRF tokens for state-changing requests; require custom headers for APIs using cookies.

## Configuration and headers

```
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
```
Production: debug off, generic error pages, no stack traces, remove sample apps and default credentials, least-privilege service accounts.

## Containers and CI

- Dockerfile: pinned base image (digest), minimal image, non-root `USER`, no secrets in layers or build args, multi-stage builds, `HEALTHCHECK`.
- Compose/Kubernetes: no `privileged`, drop capabilities, read-only root filesystem, resource limits, network policies, secrets via the platform.
- GitHub Actions: `permissions:` minimal per job; pin actions by SHA; never use `pull_request_target` with untrusted checkout; pass event data through `env:` and quote it; protect environments with required reviewers.

## Dependencies

Lockfiles committed; `pip-audit`, `npm audit`, `cargo audit`, `govulncheck`, or `sec_scan.py --osv` in CI; update critical and exposed packages first; check changelogs and run tests after upgrades; remove unused packages; verify package names and publishers.

## Logging

Log security events (authn, authz failures, admin actions); never log secrets or personal data; sanitize newlines in logged user input; ship logs to a protected store; alert on anomalies.

## Test the fix

- A regression test with the exploit input (for example `"' OR '1'='1"`, `"../../etc/passwd"`, `<script>`), asserting the safe outcome.
- An authorization matrix test for access control fixes.
- Run the scanner again; the finding must disappear for the right reason (not because the pattern was reworded).
