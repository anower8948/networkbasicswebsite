# Database Design

23 tables across five domains. The full schema is defined now — rather than
grown table by table — because the relationships between courses, labs,
progress and gamification determine the shape of every later part, and
discovering them incrementally would mean repeatedly migrating live data.

Tables not exercised until a later part are marked. They carry no code that
reads them yet; they exist so the initial migration covers the whole model.

## Domains

```
identity          users · user_stats · refresh_tokens · verification_tokens
catalogue         tracks · courses · modules · lessons · quizzes ·
                  quiz_questions · quiz_options
progress          enrollments · lesson_progress · quiz_attempts · notes · bookmarks
simulation        labs · lab_attempts · topologies
gamification      achievements · user_achievements · xp_transactions · certificates
```

## Identity

### `users`
Identity and authorisation only. Learning counters live in `user_stats` so the
authentication path — hit on every request — never loads gamification data.

| Column | Notes |
|---|---|
| `id` | UUID |
| `email` | unique, stored lowercase |
| `username` | unique, compared case-insensitively |
| `hashed_password` | Argon2id |
| `role` | `student` \| `instructor` \| `admin` |
| `is_active` | soft deactivation; blocks login and rejects live tokens |
| `tokens_valid_from` | access tokens issued before this instant are rejected |

### `user_stats` (1:1 with `users`)
Denormalised counters: XP, level, completion counts, streaks. Every value is
rebuildable from `xp_transactions`, `lesson_progress` and `lab_attempts`; they
are cached because rendering a dashboard or leaderboard from those source
tables would need several aggregate scans per request.

### `refresh_tokens`
One row per issued refresh token, storing only a SHA-256 digest.

`family_id` groups every token descending from a single login. Rotation revokes
the presented row and links it to its successor via `replaced_by_id`.
Presenting an already-revoked token means a copy leaked, so the entire family
is revoked — this column is what makes that possible.

### `verification_tokens` — *Part 2*
Single-use tokens for email verification and password reset.

## Catalogue

`tracks → courses → modules → lessons`, a strict tree. Ordering at each level
is an explicit `order_index` so instructors can reorder content without
touching timestamps.

### `lessons.content_blocks`

Lesson bodies are a JSON array of typed blocks, not HTML:

```jsonc
[
  { "type": "heading", "level": 2, "text": "What a subnet mask does" },
  { "type": "paragraph", "text": "A mask splits an address into…" },
  { "type": "diagram",  "diagramId": "ipv4-anatomy" },
  { "type": "callout",  "variant": "tip", "text": "/24 leaves 254 hosts." },
  { "type": "simulator","topologyTemplate": "two-hosts-one-switch" },
  { "type": "exercise", "kind": "subnet-calc", "prompt": "Split 192.168.1.0/24…" }
]
```

This keeps presentation under the renderer's control, lets interactive blocks
(simulator embeds, subnet calculators) sit inline with prose, and avoids
storing author-supplied HTML that would need sanitising on every render.

### Quizzes
`quizzes → quiz_questions → quiz_options`. Choice-style questions mark
correctness on the option; types without discrete options (fill-blank,
subnet-calc, CLI command) carry expected values and matching rules in
`quiz_questions.answer_key`.

## Progress

| Table | Grain |
|---|---|
| `enrollments` | one per (user, course); caches `progress_percent` |
| `lesson_progress` | one per (user, lesson); resume position and time spent |
| `quiz_attempts` | one per submission; keeps raw `responses` |
| `notes` | anchored to a lesson, optionally to a content block |
| `bookmarks` | one per (user, lesson) |

`quiz_attempts.responses` retains the learner's raw answers so an attempt can
be reviewed, and re-graded if a question's answer key is later corrected.

## Simulation

### `topologies.document`

A saved network is **one JSON document**, not normalised into
`devices` / `links` / `interfaces` tables:

```jsonc
{
  "schemaVersion": 1,
  "devices": [
    { "id": "r1", "type": "router", "model": "2911",
      "position": { "x": 240, "y": 160 }, "name": "R1",
      "interfaces": [
        { "id": "g0/0", "ip": "192.168.1.1", "mask": "255.255.255.0",
          "enabled": true, "speed": "auto", "duplex": "auto" }
      ],
      "config": { "hostname": "R1", "routes": [], "acls": [] } }
  ],
  "links": [
    { "id": "l1", "from": { "device": "r1", "interface": "g0/0" },
      "to": { "device": "sw1", "interface": "fa0/1" },
      "cable": "straight-through" }
  ],
  "groups": [],
  "viewport": { "x": 0, "y": 0, "zoom": 1 }
}
```

Three reasons:

1. **The access pattern is whole-document.** The editor loads and saves an
   entire topology atomically. No query asks for "all routers across all
   users", so normalisation would buy nothing and cost a multi-table join on
   every canvas load.
2. **The shape changes fast.** Parts 4–7 add device types and per-interface
   configuration keys continuously. A versioned document migrates in
   application code instead of one DDL migration per change.
3. **`schema_version` makes migration explicit** rather than implicit.

This is not unvalidated storage: the document is validated by Pydantic models
in `app/schemas/topology.py` (Part 4) on the way in.

### `labs` — *Part 8*
`requirements` (narrative), `objectives` (checkpoints), `initial_topology`,
`grading_rules` and `fault_injections`. Grading rules are declarative
assertions the grader evaluates:

```jsonc
{ "type": "ping", "from": "PC1", "to": "8.8.8.8", "points": 10 }
{ "type": "interface-up", "device": "R1", "interface": "g0/0", "points": 5 }
{ "type": "config-contains", "device": "R1", "pattern": "router ospf 1", "points": 10 }
```

Fault injections drive troubleshooting mode:
`{ "type": "wrong_gateway", "target": "PC2" }`.

## Gamification — *Part 9*

`xp_transactions` is an **append-only ledger**: every grant records amount,
reason and a soft reference to the originating entity. `user_stats.total_xp` is
its running sum.

The reference is deliberately *not* a foreign key — the ledger must survive
deletion of the lesson or lab it refers to, and a cascade would silently erase
a learner's history.

Keeping the ledger means a corrupted counter is always rebuildable, and it
answers questions a single total cannot, such as "XP earned this week" for a
rolling leaderboard.

`certificates` carries both an internal `serial` and a public
`verification_code`, so a certificate can be verified by a third party without
exposing the internal identifier.

## Portability decisions

| Concern | Decision | Why |
|---|---|---|
| Primary keys | UUID via `GUID` decorator | client-side generation for offline editing; IDs leak no row counts |
| Enums | VARCHAR (`enum_column`) | native PG enums need `ALTER TYPE` per value and do not exist on SQLite |
| Enum storage | member *value*, not *name* | `"student"`, not `"STUDENT"` — matches what the API emits |
| JSON | `JSON` + `JSONB` variant | JSONB is indexable on PostgreSQL |
| Constraint names | explicit naming convention | Alembic cannot emit reliable `DROP CONSTRAINT` on SQLite otherwise |
| Foreign keys | `PRAGMA foreign_keys=ON` on connect | SQLite ignores FKs by default, silently breaking every one |

## Indexing

Beyond primary and unique keys, composite indexes match the actual read paths:

| Index | Serves |
|---|---|
| `ix_user_stats_total_xp_desc` | leaderboard top-N |
| `ix_enrollments_user_status` | "my active courses" |
| `ix_lesson_progress_user_status` | dashboard progress rollup |
| `ix_courses_track_order`, `ix_modules_course_order`, `ix_lessons_module_order` | ordered catalogue rendering |
| `ix_refresh_tokens_user_family` | family revocation on reuse detection |
| `ix_topologies_owner_updated` | "my recent designs" |
| `ix_xp_transactions_user_created` | time-windowed XP queries |

## Migrations

```bash
alembic revision --autogenerate -m "description"   # generate
alembic upgrade head                               # apply
alembic downgrade -1                               # roll back one
alembic check                                      # fail if models drift
```

`alembic check` belongs in CI: it fails when models and migrations disagree,
which is the failure mode that otherwise surfaces as a production deploy error.

The initial migration has been verified through a full
`upgrade → downgrade → upgrade` cycle on SQLite.
