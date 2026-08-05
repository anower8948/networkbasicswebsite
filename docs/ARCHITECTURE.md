# System Architecture

> Status: **All 10 parts complete.** This document describes the system as
> built. For running it, see [DEPLOYMENT.md](DEPLOYMENT.md),
> [OPERATIONS.md](OPERATIONS.md) and [SECURITY.md](SECURITY.md).

## 1. Shape of the system

```
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                    │
│  React 19 · TypeScript · Vite · Tailwind v4 · Motion        │
│                                                             │
│  access token in memory ──────────┐                         │
│  refresh token in httpOnly cookie │                         │
└───────────────────────────────────┼─────────────────────────┘
                                    │ HTTPS  (same origin)
┌───────────────────────────────────▼─────────────────────────┐
│  nginx  —  static bundle + /api reverse proxy               │
└───────────────────────────────────┬─────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────┐
│  FastAPI                                                    │
│                                                             │
│   api/      routers, dependencies, HTTP concerns            │
│     ↓                                                       │
│   services/ business rules — no FastAPI, no SQL             │
│     ↓                                                       │
│   repositories/ every SQLAlchemy query lives here           │
│     ↓                                                       │
│   models/   ORM mappings                                    │
└───────────────────────────────────┬─────────────────────────┘
                                    │ SQLAlchemy 2.0 async
┌───────────────────────────────────▼─────────────────────────┐
│  SQLite (development)   ·   PostgreSQL (production)         │
└─────────────────────────────────────────────────────────────┘
```

## 2. Repository layout

```
networkbasicwebsite/
├── backend/
│   ├── app/
│   │   ├── core/          config, security, logging, exceptions, time helpers
│   │   ├── db/            engine, session, base model, portable column types
│   │   ├── models/        ORM entities, grouped by domain
│   │   ├── schemas/       Pydantic request/response contracts
│   │   ├── repositories/  query construction
│   │   ├── services/      use cases
│   │   ├── api/v1/        routers and endpoints
│   │   └── main.py        application factory
│   ├── alembic/           migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/           router
│       ├── components/
│       │   ├── ui/        design-system primitives
│       │   └── layout/    shells
│       ├── features/      vertical slices (auth today; courses, simulator…)
│       ├── lib/           api client, query client, utilities
│       ├── pages/         route components
│       ├── providers/     theme, auth
│       ├── styles/        the design system
│       └── types/         API contract types
├── docs/
└── docker-compose.yml
```

### Why features, not types

The frontend is organised by **feature** (`features/auth/…`) rather than by
technical role (`hooks/`, `components/`, `api/` at the top level). The
simulator alone will contribute a canvas renderer, a device palette, a cable
router, a packet animator and a CLI terminal. Grouped by type, those files
would be scattered across five directories; grouped by feature they stay
together and can be deleted or extracted as a unit.

`components/ui` is the deliberate exception: those primitives belong to no
feature and are shared by all of them.

## 3. Backend layering

Each layer may only call the one below it.

| Layer | Knows about | Never imports |
|---|---|---|
| `api/` | HTTP, cookies, status codes | SQLAlchemy queries |
| `services/` | business rules, domain exceptions | FastAPI, `Request`, `Response` |
| `repositories/` | SQLAlchemy, query construction | HTTP, business rules |
| `models/` | table shape, relationships | everything above |

The payoff is concrete: `AuthService` can be exercised with a bare
`AsyncSession` and no HTTP layer, and the grading engine in Part 8 can reuse
the same services from a background worker where no request exists at all.

### Errors

Services raise semantic exceptions (`EmailAlreadyRegistered`,
`InvalidToken`) from `app.core.exceptions`. A single handler in `main.py`
translates them into one consistent envelope:

```json
{ "error": { "code": "email_already_registered",
             "message": "An account with this email address already exists.",
             "details": { "fields": { "email": "…" } } } }
```

Because `code` is stable and machine-readable, the frontend branches on it
(`error.code === 'username_already_taken'`) instead of pattern-matching prose.

## 4. Authentication

Detailed rationale lives in `backend/app/core/security.py` and
`app/services/auth_service.py`. The essentials:

- **Passwords** — Argon2id (`argon2-cffi`). Memory-hard, no 72-byte truncation,
  and it reports when parameters need upgrading, so hashes are transparently
  re-hashed on login.
- **Access token** — a 15-minute JWT, returned in the response body and held
  only in JavaScript memory.
- **Refresh token** — an opaque 384-bit random string in an httpOnly,
  `SameSite=Lax` cookie scoped to `/api/v1/auth`. Only its SHA-256 digest is
  stored, so a database dump cannot be replayed.
- **Rotation with reuse detection** — every refresh mints a new token and
  revokes the old one. Tokens from one login share a `family_id`; presenting an
  already-rotated token means a copy leaked, so the whole family is revoked.
  Verified end-to-end in `tests/test_auth.py::TestRefreshRotation`.
- **Immediate invalidation** — changing a password advances
  `users.tokens_valid_from`, which rejects outstanding access tokens rather
  than letting them run out their TTL.

### Why not store the access token in localStorage

`localStorage` is readable by any script that executes on the page, so a single
XSS bug yields a token an attacker can use until it expires — and, if the
refresh token were there too, indefinitely. Keeping the access token in a
module-scoped variable and the refresh token in an httpOnly cookie means the
worst case of an XSS bug is a 15-minute window, and the long-lived credential
is never exposed to JavaScript at all.

The cost is that a page reload starts with no access token. `AuthProvider`
absorbs this with one silent refresh on mount.

### Roles

`student < instructor < admin`, ranked in `api/deps.py`. `require_role` builds a
dependency asserting a minimum rank, so an admin satisfies every instructor
route without being listed. The first account on an empty instance is promoted
to admin so a fresh deployment is administrable without a manual database edit
(`BOOTSTRAP_FIRST_USER_AS_ADMIN`).

### Single-use tokens

Email verification and password reset share the `verification_tokens` table and
the same handling as refresh tokens: an opaque random value goes to the user,
only its SHA-256 digest is stored. Issuing a new link retires any outstanding
one of the same purpose — otherwise every reset email ever sent stays usable
until expiry.

A wrong-purpose token is rejected with the *same* error as an unknown one, so a
reset token cannot be probed against the verification endpoint to learn it is
valid.

Both public endpoints are account-enumeration resistant: "forgot password"
returns an identical response whether or not the address exists.

## 4a. Email

`EmailService` renders messages; a backend delivers them.

| Backend | Use |
|---|---|
| `console` | development default — logs the message and its link, so verification and reset are clickable with no SMTP server |
| `smtp` | real delivery, run off the event loop via `asyncio.to_thread` |

Delivery failures are logged and swallowed, never raised. A registration must
not fail because a mail server was briefly unavailable — the account exists and
the user can request another message.

## 4b. Rate limiting

A sliding-window counter (`app/core/rate_limit.py`) guards the endpoints worth
abusing: password reset and resend (5/hour), login (10/15 min).

Login is keyed on the **email address**, not the client IP, so an attacker
rotating through proxies still shares a single budget against the account they
are targeting.

**Limitation:** the limiter is in-process. It resets on restart and each worker
keeps its own counters, so N workers permit N times the rate. That is acceptable
for bounding a mail flood but is not a global control. Part 10 swaps the backing
store for Redis; the `RateLimiter` interface is narrow so that change touches
one file.

## 4c. Progress engine

`ProgressService` owns every write to a learner's counters. Parts 3, 8 and 9
call it; nothing else may touch `user_stats.total_xp`.

Two invariants:

1. **The ledger is the truth.** `xp_transactions` is append-only and
   `user_stats` caches its aggregate. `recalculate_stats()` rebuilds the cache
   from the ledger — the repair path is what makes caching safe.
2. **XP is granted once per source.** Grants carry a reference
   (`("lesson", <uuid>)`) and deduplicate against it, so replaying a completion
   pays nothing.

**Levels** follow `100 × (n−1)^1.5`, capped at 100: closely spaced early for
fast feedback, stretching later. The curve exists in exactly one place and the
API ships precomputed values (`LevelProgressRead`) so the client never
reimplements it.

**Streaks** count calendar days in the learner's own timezone, not 24-hour
periods — studying at 23:00 and again at 08:00 is two days of practice. The
stored counter only refreshes on activity, so reads go through
`current_streak()`, which reports zero after a missed day rather than a stale
value. An unparseable stored timezone degrades to UTC instead of raising.

Client-reported `studySeconds` is capped at one hour per ping: it is untrusted
input, and an unbounded value would let a tampered client inflate study totals
and any leaderboard built on them.

## 4d. Learning content

Lesson bodies are an ordered list of **typed content blocks**, not HTML or
Markdown. The union is defined once in `app/schemas/content.py` as a Pydantic
discriminated union and mirrored in `frontend/src/types/content.ts`.

Both sides use exhaustive dispatch (`assertNever`), so adding a block type on
the server without adding a renderer is a compile error rather than silently
dropped content. Validation happens on write, so a malformed block — a table
whose rows do not match its headers, an image without alt text — cannot be
stored.

The interactive widget catalogue is a closed `Literal` on both sides: a lesson
can never reference a widget that does not exist.

## 4e. Quiz grading

Grading is entirely server-side, and the security property is enforced by
**type separation** rather than by discipline:

| Type | Contains | Sent |
|---|---|---|
| `QuizForAttempt` | prompts, options (`id`, `text`, `orderIndex`) | before submission |
| `QuizResult` | correctness, explanations, correct answers | after submission only |

Because they are different models, an answer key cannot leak into the delivered
payload by accident.

Eight question types are graded. Choice questions use **set equality** — no
partial credit, because a half-right answer to "select every true statement" is
wrong. Free-text answers are normalised (whitespace/case, IP spacing, Cisco
command form) and matched against an author-supplied `accepted` list;
normalisation is deliberately not fuzzy matching, since accepting a misspelt
protocol name would teach the wrong term.

Shuffling is seeded on the attempt id so a refresh does not reorder questions,
and an unsubmitted attempt is resumed rather than replaced, so refreshing does
not consume a limited attempt.

## 4f. The topology model

The device catalogue (`app/services/device_catalog.py`) is the single definition
of what equipment exists and what its ports are called. It uses **real Cisco
naming** (`GigabitEthernet0/0`, `FastEthernet0/24`, `Serial0/0/0`) and realistic
port counts, because Part 5 configures these interfaces, Part 6's CLI addresses
them by name and Part 7 forwards frames across them — all three must agree, so
the catalogue is served from the backend rather than duplicated per feature.

Cable selection follows the MDI/MDI-X rules CCNA examines: same-pinout devices
need a crossover, opposite-pinout devices a straight-through, and port type
(serial, wireless, fibre) overrides device type. A wrong cable produces a
**warning with an explanation, never a rejection** — a teaching simulator should
let the classic mistake happen and then explain it.

Documents are validated structurally on save, not just per field: link endpoints
must resolve, interfaces must exist on that device kind, and **an interface can
carry at most one cable**. That last rule is what keeps a saved topology
physically buildable.

Two editor invariants worth preserving in later parts:

* The document is the single source of truth; React Flow nodes and edges are
  derived from it every render, never held in parallel.
* `device_count` is derived from the document on write, never trusted from the
  client.

## 4g. Device configuration and the CLI

One `DeviceConfig` model fills `TopologyDevice.config`. Three things read and
write it: the configuration forms, the CLI engine, and the running-config
renderer. There is no synchronisation between them because there is nothing to
synchronise — `show running-config` is the proof they agree.

The CLI is a mode-dispatched command engine (`app/services/cli/`) with IOS
abbreviation matching, authentic error messages (`% Invalid input detected at
'^' marker.` with the caret positioned), and eight configuration modes.

**CLI sessions are stateless server-side.** The terminal holds the mode and
selected interface and sends them with each command, so no per-connection state
exists to expire, leak, or require sticky routing.

Configuration validation is genuine — contiguous masks, in-range VLAN ids,
addresses that parse — but *warnings* about incomplete configuration are
advisory. A half-finished configuration is a normal state while learning; Part 7
turns those warnings into observable failures when traffic does not flow.

## 4h. Packet simulation

Four modules under `app/services/simulation/`, layered so that each has one job
and `trace.py` — pure data, no dependencies — sits at the bottom where the
layers above it cannot become circular:

| Module | Responsibility |
|---|---|
| `network.py` | Resolves a document plus its configs into MACs, broadcast domains and routing tables |
| `forwarding.py` | ARP, egress selection, hop-by-hop delivery, and failure diagnosis |
| `protocols.py` | ICMP, ARP, DHCP, DNS, TCP and UDP exchanges |
| `trace.py` | The event vocabulary everything above writes into |

**The trace is the return value, not a side effect.** A simulator that answers
only "worked" or "failed" teaches nothing; `SimulationResult` carries the list
of decisions, each naming the device, the interface, the choice and its
grounds. Failure diagnosis is correspondingly a first-class feature — a shut
interface must not be reported as a missing route, and a wrong cable must not be
reported as a VLAN mismatch, so the engine inspects the segment before it
explains itself.

**Simulation is stateless and reads no tables.** `POST /simulation/run` takes
the document the client is *currently editing*, so experiments never become
saved topologies. Because those documents carry device configs as free-form
JSON, an unparseable config returns 422 naming the device rather than a 500.

Two simplifications, both documented at the point where they bite: MAC
addresses are derived deterministically (`sha256(device_id:interface)` behind a
locally-administered `02:` prefix) so two runs produce identical, followable
traces; and dynamic routing floods advertised networks between routers sharing a
protocol and a working link rather than running OSPF/EIGRP/RIP for real, because
reachability — not convergence or DR/BDR election — is what the lesson needs.

## 4i. Labs and grading

A lab is an **authored document**, not code: requirements, objectives, a
starting topology, a list of grading rules, and — for troubleshooting labs — a
list of fault injections. Rules and faults are Pydantic discriminated unions, so
a malformed rule is rejected at write time rather than found by a student
mid-attempt, and the same validation guards the seeder and the authoring API.

**Reachability is graded by simulating it.** A `ping` rule runs the Part 7
engine rather than inspecting addresses and inferring, which means a lab cannot
be passed by a network that merely looks right — and the simulator's own
diagnosis becomes the feedback the student reads. `no_ping` is what makes
segmentation labs gradeable: without an assertion that traffic must *not* flow,
cabling everything together passes every reachability rule.

**Faults never leave the server.** They are applied when an attempt starts, to a
copy, and no learner-facing payload carries the fault list — the same discipline
that withholds quiz answer keys. Each fault mutates the document the way a real
mistake would (a shut interface is `enabled: false`, not a "faulted" flag), so
the CLI, the config forms and the simulator need no knowledge of a fault engine.

Checking work is free and unlimited; only submitting closes the attempt and pays
XP. Iterating on the feedback is the exercise.

## 4j. Recognition

Achievements are **data**: a declarative criteria document evaluated against one
shared metric snapshot, so awarding fifteen badges costs what awarding one does.
Evaluation runs after a completion commits — never inside `grant_xp`, which
would recurse, since badges award XP themselves.

Leaderboards are why `xp_transactions` is append-only rather than a counter: the
all-time board reads the cached `user_stats.total_xp` behind its descending
index, but "XP earned this week" can only be summed from the ledger.

Certificates carry two identifiers on purpose — a readable `serial` for the
document, and a high-entropy `verification_code` that is the only thing needed
to verify one. Verification is public and thin, answers `valid: false` rather
than 404 for an unknown code (so the status cannot separate "wrong" from
"revoked"), and revoking keeps the row so the code still resolves.

Instructor analytics are **aggregate only**. The roster shows standing, not a
per-learner activity trail; the line is drawn where instructor tooling would
otherwise become surveillance.

## 4k. Production posture

Middleware order is the reverse of registration, so the body-size limit runs
outermost and rejects an over-sized payload before anything else touches it; the
security-header middleware runs innermost, where it can see whether an endpoint
set its own `Cache-Control`. The limit is raw ASGI rather than
`BaseHTTPMiddleware` because the latter only sees a request once the body has
already been buffered — which is the cost it exists to avoid.

`ENVIRONMENT=production` turns on a start-up check that **refuses to boot** on
any of nine misconfigurations, reporting all of them at once. Every item on that
list is silently wrong rather than obviously broken; a container that will not
start gets noticed, and a missing cookie flag does not.

The API's Content-Security-Policy is `default-src 'none'` — a JSON API has
nothing legitimate to load. The policy protecting the application is nginx's,
and `style-src` there needs `'unsafe-inline'` because React Flow and Motion set
`element.style` directly and nonces cannot cover style attributes. `script-src`
has no such exemption.

**CI runs the backend suite against both SQLite and PostgreSQL.** The portable
column types in `app/db/types.py` exist to hide the differences between them,
and an abstraction nobody exercises is an assumption — the matrix immediately
found a column too narrow for its own seed data, which SQLite had been silently
ignoring.

## 5. Database portability

SQLite in development, PostgreSQL in production — one schema, no dialect forks.

| Concern | Approach |
|---|---|
| UUID keys | `GUID` decorator: native `UUID` on PostgreSQL, `CHAR(36)` elsewhere |
| JSON | `JSON` with a `JSONB` variant on PostgreSQL |
| Enums | VARCHAR via `enum_column`, never native PG `ENUM` |
| Timestamps | `DateTime(timezone=True)`; reads normalised by `core.datetime_utils.as_utc` |
| Migrations | Alembic with `render_as_batch` on SQLite for table rebuilds |

Two of these deserve their reasoning stated:

**Enums as VARCHAR.** A native PostgreSQL `ENUM` needs an `ALTER TYPE`
migration to add one value and does not exist on SQLite at all. Adding a device
category in Part 4 should not require dialect-specific DDL. `enum_column` also
sets `values_callable` so the *value* (`"student"`) is stored rather than
SQLAlchemy's default of the member *name* (`"STUDENT"`) — otherwise raw SQL
would disagree with every value the API emits.

**Naive datetimes from SQLite.** SQLite has no timestamp type, so SQLAlchemy
returns naive datetimes from it and aware ones from PostgreSQL. Comparing the
two raises `TypeError` — a bug that appears in exactly one environment. Every
value read back passes through `as_utc()`.

## 6. Wire format

Requests and responses are **camelCase**. `APIModel` sets
`alias_generator=to_camel`, and FastAPI serialises with `by_alias=True`, so the
Python code stays snake_case while the TypeScript client stays idiomatic.
`populate_by_name` keeps snake_case valid on input, so both spellings are
accepted from a request body.

## 7. Frontend data flow

- **Server state** — TanStack Query. 4xx responses are never retried; they will
  not succeed on a second attempt and retrying only delays the error.
- **Session state** — `AuthProvider`, because it must be readable synchronously
  during render by the route guards.
- **Theme** — `ThemeProvider` plus an inline script in `index.html` that applies
  the stored theme *before first paint*, avoiding a white flash for dark-mode
  users.
- **Routing** — React Router 7 with lazy route components. Parts 4–7 bring
  React Flow and Konva; splitting at the route boundary keeps them out of the
  login page's bundle.

## 8. Seams for later parts

| Part | Plugs into |
|---|---|
| ~~2 — User system~~ | ✅ complete |
| ~~3 — Learning platform~~ | ✅ complete |
| ~~4 — Topology designer~~ | ✅ complete |
| ~~5 — Device configuration~~ | ✅ complete |
| ~~6 — Cisco CLI~~ | ✅ complete |
| ~~7 — Packet simulation~~ | ✅ complete — pure functions over the document and `DeviceConfig`; no new tables |
| ~~8 — Labs~~ | ✅ complete — `labs.grading_rules`, `lab_attempts.check_results`; `SimulationResult.success` is the gradeable assertion and the trace is its evidence |
| ~~9 — Platform features~~ | ✅ complete — `achievements`, `xp_transactions`, `certificates`, `notes`, `bookmarks`; no new tables were needed |
| ~~10 — Production~~ | ✅ complete — hardening, CI on both dialects, and four deployment targets |
