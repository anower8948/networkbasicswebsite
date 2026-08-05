# Part 10 — Production Release

No new features. This part is about the difference between "it works on my
machine" and "it can be operated by someone else, on a Tuesday, at 3am".

The most valuable thing it produced was not a config file. It was **three real
bugs**, two of which would have shipped.

---

## The bugs

### 1. Seeding a production database failed outright

`tracks.accent_color` was `String(20)`. The seeded values are CSS custom-property
references — `var(--color-track-intermediate)`, 31 characters.

SQLite **ignores** `VARCHAR` length limits entirely. PostgreSQL enforces them.
Every part up to here was developed and tested on SQLite, so nothing noticed;
the first `python -m app.seeds` against PostgreSQL would have died with
`value too long for type character varying(20)`.

Found within a minute of running the existing suite against PostgreSQL. Fixed by
widening the column to 64 and adding migration `0d0bc11ed9a8`.

**The general lesson**, and the reason the CI matrix now exists: an abstraction
nobody exercises is an assumption. `app/db/types.py` was written to paper over
SQLite/PostgreSQL differences, and it does — but only for the differences it
knows about. The suite now runs on both dialects on every pull request.

### 2. The admin page crashed for every administrator

`TypeError: Cannot read properties of undefined (reading 'toLocaleString')`.

The schema field was `active_users_7d`. The camelCase alias generator
capitalises each underscore-separated segment, so `7d` became `7D` and the wire
field was `activeUsers7**D**`. The hand-written TypeScript interface said
`activeUsers7d`. TypeScript cannot see this — it is a runtime contract, and the
type only describes what the author *believed* the server sends.

This is the page I flagged in Part 9 as "verified by backend tests and
typecheck, not in the browser". It was the only unverified surface, and it was
broken. Verifying it required an admin session, which the containerised stack
provided by being freshly seeded — the first account registered becomes admin.

Fixed three ways, because one was not enough:

- Renamed to `active_users_week` / `new_users_week`, so no wire name depends on
  a capitalisation rule anyone has to know about.
- `Stat` renders `—` for a missing figure instead of throwing. A single absent
  number should not take down a page.
- A backend test asserts the **exact set** of `overview` keys, so a rename
  breaks CI rather than the client.

### 3. Assets carried two `Cache-Control` headers

nginx's `expires 1y;` emits its own `Cache-Control`, and the `add_header`
beside it added a second:

```
Cache-Control: max-age=31536000
Cache-Control: public, immutable
```

Which one a client honours is undefined, and the first is missing `immutable`.
Both nginx configurations now set the whole directive once.

---

## Security hardening

### Configuration that refuses to boot

`ENVIRONMENT=production` turns on a start-up check covering nine things that are
each *silently* wrong rather than obviously broken — a missing `Secure` flag, a
localhost CORS origin, `EMAIL_BACKEND=console` sending password resets to the
log, a SQLite `DATABASE_URL`. None of them break a deployment; all of them are
discovered during an incident.

Failing at start-up is the whole point: a container that will not boot gets
noticed, a missing cookie flag does not. All problems are collected and reported
together, so one failed boot reveals the entire list rather than the first item.

### Headers

The API sends `default-src 'none'` — a JSON API has nothing legitimate to load.
The policy that protects the *application* is nginx's, and it is written against
what the bundle actually does:

- `script-src 'self'` — no inline script anywhere in the bundle.
- `style-src 'self' 'unsafe-inline'` — **not** an oversight. React Flow and
  Motion set `element.style` directly for transforms, which that directive
  governs, and nonces cannot cover style *attributes*. The honest options are
  `'unsafe-inline'` or no animation.
- `connect-src 'self'` — the API is same-origin by design, so an exfiltration
  attempt has nowhere to send to.

Plus `Permissions-Policy` denying every feature the app never uses,
`Cross-Origin-Opener-Policy`, HSTS where TLS terminates, and
`Cache-Control: no-store` on all authenticated JSON — with exactly one opt-out,
the device catalogue, which is identical for everyone and changes only on
deploy.

Verified against the running stack, not asserted: `curl -I` on the served
pages, and zero CSP violations in the browser console across the lesson viewer,
the lab workspace (React Flow + Motion) and the admin page.

### Limits

- **4 MB body cap**, enforced in raw ASGI middleware *before* the payload is
  buffered — checking `Content-Length` in a handler is too late, because
  Starlette has already read it. Also counts streamed chunks, for clients that
  omit the header.
- **`ALLOWED_HOSTS`** rejects a spoofed `Host`, which would otherwise poison
  the absolute URLs in password-reset mail.
- **nginx `limit_req`** at the edge, because the application limiter is
  per-process and resets on restart.

---

## Performance

| Change | Effect |
|---|---|
| GZip middleware on the API | JSON responses compress ~3× |
| `query` split into its own chunk | Entry bundle 321 kB → 295 kB |
| `sourcemap: 'hidden'` + nginx 404 on `.map` | Maps exist for debugging, are not served |
| `Cache-Control: immutable` on hashed assets | Repeat visits fetch only `index.html` |
| Device catalogue cacheable for an hour | The one endpoint where that is safe |

React Flow — the largest dependency — is already isolated behind the lazy route
imports, so it is downloaded only by someone who opens the simulator or a lab.

---

## Deployment

Four targets, all in `infra/`, all documented in
[DEPLOYMENT.md](DEPLOYMENT.md):

| Target | What is provided |
|---|---|
| **Docker Compose** | Already existed; now serves the hardened nginx config |
| **Azure App Service** | Bicep for two App Services, PostgreSQL Flexible Server, Key Vault read via managed identity; OIDC deploy workflow |
| **Linux VPS** | Sandboxed systemd unit, nginx site, and a deploy script that **rolls back automatically** if the health check fails |
| **cPanel** | Passenger WSGI bridge, `.htaccess`, and an honest warning |

Three decisions worth stating:

**Images are tagged with the commit SHA, never `latest`.** A mutable tag makes
"which build is running?" unanswerable during an incident and turns a rollback
into a rebuild.

**Migrations do not run on application start-up** in the multi-instance targets.
Two containers booting together would race to run the same migration.

**The cPanel target is documented with its cost.** It runs the ASGI app through
a WSGI bridge, so every request occupies a worker for its whole duration and the
async driver's concurrency advantage is lost. It works — verified with a real
WSGI call returning 200 with headers intact — but expect several times less
throughput. The documentation says to choose it when shared hosting is the
constraint, not by preference.

---

## Verification

Everything below was run, not assumed.

| Check | Result |
|---|---|
| Backend suite (SQLite) | **444 passed** |
| Backend suite (PostgreSQL 17) | **444 passed** |
| `ruff`, `ruff format`, `mypy` | clean, 100 files |
| `alembic check` | no drift, both dialects |
| Frontend suite | **99 passed** |
| `tsc`, `eslint`, `vite build` | clean |
| Both Docker images | build |
| `nginx -t` on both configs | valid |
| Full stack on PostgreSQL | all three containers healthy |
| Security headers as served | verified with `curl -I` |
| CSP violations in the browser | **zero**, across lessons, labs, admin |
| Oversized POST | 413 |
| Source map request | 404 |
| SPA deep link | 200 |
| gzip negotiated | yes |
| Seed on PostgreSQL, twice | idempotent |
| cPanel WSGI bridge | 200, headers intact |

Also added: `.github/workflows/ci.yml` (lint, types, both dialects, both images,
`nginx -t`, dependency audit) and `deploy-azure.yml` (OIDC, SHA-tagged images,
migration job, smoke test with retry).

---

## Documentation

| Document | Contents |
|---|---|
| [DEPLOYMENT.md](DEPLOYMENT.md) | All four targets, the production guard, the post-deploy checklist |
| [OPERATIONS.md](OPERATIONS.md) | Health probes, log queries, what to watch, backups, common problems, scaling order |
| [SECURITY.md](SECURITY.md) | The security model, what is deliberately withheld, and **six known limitations** stated plainly |

The limitations section is deliberate. The rate limiter does not span instances;
there is no account lockout, no 2FA, and no audit log of administrative actions.
An undocumented gap is worse than a documented one — the next person needs to
know what they are inheriting.

---

## What is genuinely not done

Being straight about the boundary of this work:

- **The Azure Bicep has never been deployed to a real subscription.** It is
  written against the current resource schemas and reviewed, but "the template
  is correct" and "the deployment succeeded" are different claims and only the
  first is supported here.
- The same applies to the **cPanel** instructions beyond the WSGI bridge itself,
  which was tested locally.
- **No load testing.** The performance changes are sound in principle and
  measurable in the bundle sizes, but no figure here comes from a load
  generator.
- **No error tracking or metrics backend** is wired up. The structured logs and
  request ids make one easy to add; none is configured.
