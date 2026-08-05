# Network Learning Platform

An interactive networking education platform — from OSI and subnetting through
CCNA-level routing and switching, and on to enterprise, cloud and automation
topics. Built around a topology simulator, a Cisco-style CLI, and hands-on labs.

**Current status: all 10 parts complete.** Architecture, database, design
system, authentication, user system, the learning platform with real CCNA
content, an interactive network designer, a fully configurable simulator with
device configuration windows and a working Cisco IOS command line, a packet
simulation engine that runs ARP, ICMP, DHCP, DNS, TCP and UDP over the topology
and explains step by step why traffic did or did not get through, graded
hands-on labs with fault injection and troubleshooting mode, and the full
recognition layer — achievements, leaderboards, verifiable certificates, notes
and instructor analytics. Production-hardened and deployable to Docker, Azure
App Service, a Linux VPS, or cPanel.

---

## Quick start

Requires Python 3.11+ and Node 20+.

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seeds     # load the Foundations course content
.venv/bin/uvicorn app.main:app --reload
```

API on `http://127.0.0.1:8000` · interactive docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App on `http://localhost:5173`. Vite proxies `/api` to the backend, so the
browser treats both as one origin and the refresh cookie stays first-party.

**The first account you register becomes the administrator.**

Email runs on the `console` backend in development: verification and password
reset links are printed to the backend log rather than sent, so both flows are
fully clickable with no SMTP server.

The seeder loads two complete courses — OSI/TCP-IP fundamentals and IPv4
addressing & subnetting — with four lessons, interactive widgets and two graded
quizzes, plus **four hands-on labs** (one per kind: guided, challenge,
troubleshooting, design) and **fifteen achievements**. It is idempotent: re-run
it after editing content and rows are updated in place, never duplicated. Labs
and badges are validated as they load, so a malformed grading rule or a badge
naming an unknown metric fails the seed rather than reaching a learner.

### Full stack on PostgreSQL

```bash
python3 deploy.py docker
```

One command: runs both test suites, generates a `SECRET_KEY` on first use,
builds the images, starts PostgreSQL + API + nginx, waits for health, seeds the
catalogue, and checks the security headers are being served. Serves on
`http://localhost:8080`. If the stack does not come up it prints the API logs
and stops it again rather than leaving a half-deployed mess.

`docker compose up --build` still works if you prefer to drive it yourself.

---

## Deploying

```bash
python3 deploy.py                      # pick a target interactively
python3 deploy.py docker               # containers on this machine
python3 deploy.py vps --host root@1.2.3.4
python3 deploy.py azure --resource-group nlp-prod --registry nlpregistry
python3 deploy.py --check              # preflight only, deploy nothing
python3 deploy.py docker --dry-run     # print every command, change nothing
```

Standard library only, so it runs before anything is installed. Docker is fully
automatic; VPS and Azure drive `ssh`/`az` and require the one-time setup in
[DEPLOYMENT.md](docs/DEPLOYMENT.md); cPanel creates its app through a web panel
with no API, so `deploy.py cpanel` builds the bundle and prints the checklist.

Anything touching a machine other than this one asks first, unless `--yes`.

---

## Verification

```bash
# backend
cd backend
.venv/bin/python -m pytest        # 444 tests
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/alembic check           # fails if models drift from migrations

# frontend
cd frontend
npm test                          # 99 tests
npm run typecheck
npm run lint
npm run build
```

All of the above pass. CI additionally runs the backend suite against
**PostgreSQL** as well as SQLite — SQLite ignores `VARCHAR` limits and
PostgreSQL enforces them, a difference that has already hidden one production
bug. To reproduce locally:

```bash
docker run -d --rm --name pg -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=nlp_ci -p 55432:5432 postgres:17-alpine
cd backend
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/nlp_ci" pytest -q
```

---

## Stack

| | |
|---|---|
| Frontend | React 19 · TypeScript · Vite 6 · Tailwind CSS v4 · Motion · TanStack Query · React Router 7 · React Flow |
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Alembic |
| Database | SQLite (development) · PostgreSQL (production) |
| Auth | Argon2id · JWT access tokens · rotating refresh tokens with reuse detection · email verification · password reset |
| Deployment | Docker · nginx · Azure App Service (Bicep) · Linux VPS (systemd) · cPanel (Passenger) |

React Flow powers the topology canvas. The Part 7 packet animation rides the
edges' own SVG paths rather than a second Konva canvas — a packet has to follow
the exact bend of the cable it is crossing, and an overlay canvas would have to
re-derive and re-sync every path on each pan and zoom. One less dependency and
one less thing to keep in step.

---

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System shape, layering, auth design, seams for later parts |
| [DATABASE.md](docs/DATABASE.md) | All 23 tables, JSON document formats, indexing, portability |
| [DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | Liquid Glass materials, tokens, theming, accessibility |
| [PART1.md](docs/PART1.md) | What shipped in Part 1 and why |
| [PART2.md](docs/PART2.md) | What shipped in Part 2 and why |
| [PART3.md](docs/PART3.md) | What shipped in Part 3 and why |
| [PART4.md](docs/PART4.md) | What shipped in Part 4 and why |
| [PART5-6.md](docs/PART5-6.md) | Device configuration and the Cisco CLI |
| [PART7.md](docs/PART7.md) | The packet simulation engine and its failure diagnostics |
| [PART8-9.md](docs/PART8-9.md) | Graded labs, fault injection, and the recognition layer |
| [PART10.md](docs/PART10.md) | Production hardening, and the three bugs it found |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, Azure, VPS and cPanel, step by step |
| [OPERATIONS.md](docs/OPERATIONS.md) | Health, logs, backups, common problems, scaling |
| [SECURITY.md](docs/SECURITY.md) | The security model — and its known limitations |

---

## Roadmap

| Part | Scope | Status |
|---|---|---|
| 1 | Architecture, database, design system, auth foundation | ✅ Complete |
| 2 | User system — verification, profiles, sessions, progress | ✅ Complete |
| 3 | Learning platform — course engine, lesson viewer, quizzes | ✅ Complete |
| 4 | Interactive network designer — drag-and-drop topology builder | ✅ Complete |
| 5 | Device configuration engine | ✅ Complete |
| 6 | Cisco CLI simulator | ✅ Complete |
| 7 | Packet simulation engine — ARP, DHCP, DNS, ICMP, TCP/UDP | ✅ Complete |
| 8 | Interactive labs, grading, troubleshooting mode | ✅ Complete |
| 9 | Certificates, achievements, leaderboards, instructor tools | ✅ Complete |
| 10 | Production release — performance, security, deployment | ✅ Complete |
