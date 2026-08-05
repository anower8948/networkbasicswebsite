# Operations

What to watch, what to do when it breaks, and how to get the data back.

---

## Health endpoints

Two, and the difference matters:

| Endpoint | Touches the database | Use for |
|---|---|---|
| `/api/v1/health` | No | Liveness — "is the process alive?" |
| `/api/v1/health/ready` | Yes | Readiness — "can it serve traffic?" |

Point the orchestrator's **liveness** probe at the first. A database blip
should take the instance out of the load balancer, not restart it — restarting
a healthy process because a database is slow turns a brief degradation into an
outage.

---

## Logs

Structured JSON, one object per request, with a `request_id` that is echoed in
the `X-Request-ID` response header. A user reporting "it failed at about
10:40" can be matched to an exact traceback if they can be persuaded to read
the id off the error.

```bash
# systemd
journalctl -u nlp-api -f
journalctl -u nlp-api --since '1 hour ago' | grep '"status_code":5'

# Docker
docker compose logs -f api

# Azure
az webapp log tail --name nlp-prod-api --resource-group nlp-prod
```

Every response also carries `X-Response-Time-ms`, so a slow endpoint can be
found without any additional instrumentation:

```bash
journalctl -u nlp-api --since today -o cat \
  | jq -r 'select(.duration_ms > 500) | "\(.duration_ms)  \(.method) \(.path)"' \
  | sort -rn | head -20
```

---

## What to watch

| Signal | Healthy | Investigate when |
|---|---|---|
| 5xx rate | ~0 | any sustained non-zero |
| p95 response time | < 300 ms | > 1 s for five minutes |
| `/simulation/run` p95 | < 500 ms | > 2 s — a large topology, or a routing loop |
| Database connections | < `DB_POOL_SIZE` | at the pool ceiling |
| Disk | < 70% | > 85% |
| 429 rate | low | a spike means abuse *or* a limit set too tight |

The simulation and grading endpoints are the only CPU-bound paths in the
application; everything else is IO-bound on the database.

---

## Backups

**Take them, and restore one.** An untested backup is a hypothesis.

```bash
# Nightly, retained 30 days
pg_dump -Fc network_learning > "/var/backups/nlp/$(date +%F).dump"
find /var/backups/nlp -name '*.dump' -mtime +30 -delete

# Restore — always into a scratch database first
createdb nlp_restore_test
pg_restore -d nlp_restore_test /var/backups/nlp/2026-08-05.dump
psql nlp_restore_test -c 'select count(*) from users;'
```

Azure Flexible Server takes automatic backups (14 days, geo-redundant in prod
per the Bicep). That does not remove the need to *restore* one on a schedule.

What is irreplaceable, in order: `users`, `xp_transactions` (the ledger every
counter is rebuildable from), `lab_attempts`, `topologies`, `certificates`.
Everything in the catalogue is re-seedable from the repository.

---

## Common problems

### Every login fails after a deploy

`SECRET_KEY` changed. Access tokens signed with the old key no longer verify.
Restore the previous value; if it is genuinely lost, everyone must sign in
again — and refresh cookies survive, so most people will not notice.

### "Refresh token reuse detected" in the logs

The reuse-detection path fired: a token was presented after it had already been
rotated. One-off, it is usually two tabs refreshing simultaneously. Repeatedly
for one user, treat it as a leaked token — the family is already revoked, which
is the designed response.

### XP totals look wrong

The ledger is the truth and the counters are a cache:

```python
from app.services.progress_service import ProgressService
await ProgressService(session).recalculate_stats(user)
```

### A lab nobody can pass

Check `/api/v1/admin/analytics`. A low pass rate beside a high average-hints
figure means the wording, not the difficulty. Fix the objective text or the
grading rule and re-seed — `python -m app.seeds` upserts by slug and never
touches learner progress.

### The simulator is slow on a large topology

Simulation is O(devices × links) per protocol run and holds no state between
requests. A topology large enough to be slow is usually a topology with an
accidental loop; the trace will show it as repeated hops until `MAX_HOPS`.

---

## Routine maintenance

**Weekly** — check the 5xx rate and the slowest endpoints; confirm backups ran.

**Monthly** — apply dependency updates:

```bash
cd backend && pip-audit --desc
cd frontend && npm audit
```

Both run in CI on every pull request (reported, not enforced — a fresh advisory
with no fix available should not block an unrelated change).

**Quarterly** — restore a backup into a scratch database; review admin and
instructor accounts; rotate SMTP credentials.

---

## Scaling

In the order the pressure actually arrives:

1. **Vertical first.** A single writer is not the bottleneck at this size; more
   CPU and RAM is cheaper and simpler than a second instance.
2. **More API instances.** The API is stateless — sessions are JWTs, the rate
   limiter is per-process, the simulator holds nothing between requests. Two
   caveats when you do: move migrations to a one-shot job so instances cannot
   race, and expect the rate limiter to become per-instance (move it to Redis
   if the limit needs to be global).
3. **A read replica.** The catalogue and leaderboard reads dominate and are the
   natural candidates.
4. **A CDN in front of `/assets/`.** They are content-hashed and served
   `immutable`, so this needs no invalidation strategy.
