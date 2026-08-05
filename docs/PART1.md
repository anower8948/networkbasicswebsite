# Part 1 — Project Architecture

Scope as specified: system architecture, folder structure, database design, UI
design system, authentication foundation.

## Delivered

### System architecture
Layered FastAPI backend (`api → services → repositories → models`) with a
feature-sliced React frontend. Documented in
[ARCHITECTURE.md](ARCHITECTURE.md).

### Folder structure
Monorepo: `backend/`, `frontend/`, `docs/`, plus Docker configuration. The
frontend is organised by feature rather than by file type, so the simulator's
eventual canvas renderer, device palette, cable router, packet animator and CLI
terminal stay together instead of scattering across five directories.

### Database design
23 tables covering identity, catalogue, progress, simulation and gamification.
The complete schema is defined now because the relationships between courses,
labs, progress and XP determine the shape of every later part; discovering them
incrementally would mean repeatedly migrating live data. Detailed in
[DATABASE.md](DATABASE.md).

Verified through a full `upgrade → downgrade → upgrade` cycle, and
`alembic check` confirms no drift between models and migrations.

### UI design system
The macOS-inspired Liquid Glass language: OKLCH colour, four glass materials,
light and dark themes, motion curves, and accessible primitives
(`GlassPanel`, `Button`, `Input`, `ThemeToggle`, `Spinner`, `ErrorBoundary`).
Detailed in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

### Authentication foundation
Registration, login, refresh with rotation, logout, logout-everywhere, session
listing, and password change. Argon2id hashing; 15-minute JWT access tokens in
memory; opaque refresh tokens in httpOnly cookies, stored only as digests, with
family-wide revocation on reuse detection. Role hierarchy with route guards on
both sides.

## Verified

| Check | Result |
|---|---|
| Backend tests | 53 passed |
| Frontend tests | 32 passed |
| `ruff check` | clean |
| `mypy app` | clean, 37 files |
| `tsc -b` | clean under `strict` + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` |
| `eslint` | clean |
| `vite build` | succeeds, route-level code splitting |
| `alembic check` | no drift |
| Migration round-trip | upgrade → downgrade → upgrade |

Exercised end-to-end against running servers: registration (first user promoted
to admin), login, refresh rotation, **reuse detection burning the token
family**, dashboard render with live data, light/dark themes, and session
restoration across a full page reload.

## Decisions worth flagging

**Access token in memory, refresh token in an httpOnly cookie.**
`localStorage` is readable by any injected script, so one XSS bug yields a
usable session. This design caps the damage at a 15-minute window and never
exposes the long-lived credential to JavaScript. Cost: a page reload starts
with no access token, absorbed by one silent refresh on mount.

**Refresh rotation with family revocation.** Every refresh mints a new token
and revokes the old one. Replaying an already-rotated token means a copy
leaked, so the entire family dies — both attacker and victim are logged out.
This is the OAuth 2.0 BCP reuse-detection pattern, and it is covered by tests.

**Topology stored as a versioned JSON document.** The editor loads and saves
whole topologies atomically and no query asks across users' devices, so
normalising into `devices`/`links`/`interfaces` would add joins without
benefit, while the document shape changes continuously through Parts 4–7.
Pydantic validates the document on the way in, so this is not unvalidated
storage.

**Enums as VARCHAR storing member values.** Native PostgreSQL enums need an
`ALTER TYPE` migration per added value and do not exist on SQLite. `values_callable`
persists `"student"` rather than SQLAlchemy's default `"STUDENT"`, so raw SQL
agrees with what the API emits.

**camelCase wire format.** `alias_generator=to_camel` on the schema base;
Python stays snake_case, TypeScript stays idiomatic, and `populate_by_name`
keeps snake_case valid on input.

**First account becomes administrator.** A fresh deployment is otherwise
unusable without a manual database edit. Controlled by
`BOOTSTRAP_FIRST_USER_AS_ADMIN`; turn it off once the real admin exists.

**Production config is enforced, not documented.** `Settings` refuses to start
when `ENVIRONMENT=production` without an explicit `SECRET_KEY`, with `DEBUG`
on, or with an insecure cookie flag. A generated key would silently invalidate
every session on restart — better to fail loudly at boot.

## Defined but not yet active

These tables carry no reader yet; they exist so the initial migration covers
the whole model rather than fragmenting it across ten migrations.

| Table | Activated in |
|---|---|
| `verification_tokens` | Part 2 (needs outbound email) |
| catalogue and progress tables | Part 3 |
| `topologies` | Part 4 |
| `labs`, `lab_attempts` | Part 8 |
| `achievements`, `xp_transactions`, `certificates` | Part 9 |

Sidebar entries for Courses, Simulator, Labs, Achievements and Settings are
rendered disabled, so the shell shows the full information architecture without
pretending those routes work.

## Not in this part

Deployment to Azure App Service and cPanel is Part 10 per the plan. Docker and
nginx configuration is included here because container parity is part of the
architecture foundation, but the Azure templates, CI pipeline and hardening
pass belong to Part 10 and have deliberately not been front-run.

API types in `frontend/src/types/api.ts` are hand-maintained and mirror the
Pydantic schemas. Part 10 replaces the file with types generated from the
OpenAPI document, removing drift risk entirely.

## Ready for Part 2

Part 2 (user system: email verification, profile management, session
management, progress tracking) builds directly on the `verification_tokens`
model, the `/auth/sessions` endpoint, and the `UserService` already in place.
