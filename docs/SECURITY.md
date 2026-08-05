# Security

What this application defends against, how, and — as importantly — what it does
not.

---

## Authentication

| Concern | Approach |
|---|---|
| Password storage | Argon2id (`argon2-cffi`). Memory-hard, no 72-byte truncation, reports when parameters need upgrading so hashes are re-hashed transparently on login. |
| Access token | 15-minute JWT, returned in the body, held **only in JavaScript memory**. |
| Refresh token | Opaque 384-bit random value in an httpOnly, `SameSite=Lax` cookie scoped to `/api/v1/auth`. Only its SHA-256 digest is stored. |
| Rotation | Every refresh mints a new token and revokes the old one. |
| Reuse detection | Tokens from one login share a `family_id`. Presenting an already-rotated token means a copy leaked, so the whole family is revoked. |
| Credential change | Advances `users.tokens_valid_from`, rejecting outstanding access tokens rather than waiting out their TTL. |

**Why the access token is not in `localStorage`:** anything there is readable by
any script that executes on the page, so one XSS bug yields a usable token —
and, if the refresh token were there too, an indefinitely usable one. In memory
plus an httpOnly cookie means the worst case of an XSS bug is a 15-minute
window, and the long-lived credential is never exposed to JavaScript at all.

The cost is that a reload starts with no access token; `AuthProvider` absorbs
that with one silent refresh on mount.

---

## Authorisation

`student < instructor < admin`, ranked in `api/deps.py`. `require_role` builds a
dependency asserting a minimum rank, so an admin satisfies every instructor
route without being listed.

**Ownership is checked before existence, everywhere.** A note, attempt, or
topology belonging to someone else returns **404, not 403** — a 403 confirms
the id exists, which is enough to enumerate them.

---

## What is deliberately withheld

Three payloads are built field by field rather than dumped from a model, so
that adding a field later cannot leak it by accident:

| Payload | Withholds | Why |
|---|---|---|
| `QuizForAttempt` | correct options, explanations, answer key | otherwise the answers are in the network tab |
| `LabDetail` | grading rules, fault injections | a lab whose faults are downloaded is a reading exercise |
| `CertificateVerification` | email, serial, everything but name/course/date | the code is designed to be pasted into a CV |

Fault injection happens **server-side** when a lab attempt starts. The intact
network never leaves the server.

---

## Transport and headers

The API sends a maximally strict CSP (`default-src 'none'`) because a JSON API
has nothing legitimate to load. The policy that protects the *application* is
the one nginx sends with `index.html`:

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; connect-src 'self'; object-src 'none';
base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

`style-src` needs `'unsafe-inline'` and this is not an oversight: React Flow
and Motion both set `element.style` directly for transforms, which that
directive governs, and nonces cannot cover style *attributes*. The honest
options are `'unsafe-inline'` or no animation. `script-src` has no such
exemption — there is no inline script anywhere in the bundle.

Also sent everywhere: `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Cross-Origin-Opener-Policy`, a `Permissions-Policy` denying
every feature the app never uses, and HSTS wherever TLS terminates.

Authenticated JSON is `Cache-Control: no-store` by default. Exactly one
endpoint opts out — the device catalogue, which is identical for every caller
and changes only on deploy.

---

## Input handling

- **Every request body is a Pydantic model.** Nothing reaches a query built
  from unvalidated input, and every query goes through SQLAlchemy's parameter
  binding — there is no string-interpolated SQL in the codebase.
- **Authored content is a discriminated union**, so no author-supplied HTML is
  ever stored. Lesson bodies are typed blocks; the renderer stays in control of
  presentation and there is nothing to sanitise on the way out.
- **Bodies are capped at 4 MB**, enforced before the payload is buffered.
- **Host headers are checked** against `ALLOWED_HOSTS` when it is set — a
  spoofed Host would poison the absolute URLs in password-reset mail.

---

## Rate limiting

Applied to the endpoints worth abusing — those that accept credentials or send
mail. Two layers: the application limiter (`app/core/rate_limit.py`) and an
nginx `limit_req` zone at the edge.

**The application limiter is per-process and in-memory.** With more than one
instance the effective limit is multiplied by the instance count, and it resets
on restart. That is a deliberate trade for now — the edge limiter covers the
tier — but move it to Redis before scaling out if the limit needs to be global.

---

## Account enumeration

"Forgot password" returns an identical response whether or not the address
exists. Verification and reset tokens share one table and one handling path,
and a wrong-purpose token is rejected with the *same* error as an unknown one —
so a reset token cannot be probed against the verification endpoint to learn
that it is valid.

---

## Secrets

Never in the repository, never in an image, never in a log.

| Target | Where secrets live |
|---|---|
| Azure | Key Vault, read via the app's managed identity |
| VPS | `/etc/nlp/api.env`, mode 0640 root:nlp |
| Docker | environment variables from the orchestrator |
| cPanel | the app's Environment Variables panel |

`.gitignore` excludes `.env` and every `.env.*` except `.env.example`.

---

## Known limitations

Stated plainly, because an undocumented gap is worse than a documented one:

1. **The rate limiter does not span instances** (above).
2. **No account lockout after repeated failures** — only rate limiting. Argon2id
   plus a 10-character minimum makes online guessing impractical, but a
   determined attacker with many source addresses is not locked out.
3. **No 2FA.** The schema does not preclude it; nothing implements it.
4. **No audit log of administrative actions.** Revoking a certificate or
   deleting a lab is not recorded beyond the application log.
5. **Source maps are built** (`sourcemap: 'hidden'`) and present in the image,
   though not served — nginx 404s `.map` and the `//# sourceMappingURL` comment
   is omitted. Anyone with filesystem access to the image can still read them.
6. **cPanel deployments run through a WSGI bridge**, which serialises requests
   per worker. A throughput limitation rather than a vulnerability.

---

## Reporting a vulnerability

Open a private security advisory on the repository, or email the maintainer.
Please do not open a public issue. Include a reproduction and the affected
version; expect an acknowledgement within a few days.
