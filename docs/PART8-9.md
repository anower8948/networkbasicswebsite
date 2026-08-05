# Parts 8 & 9 — Interactive Labs, and the Recognition Layer

Built together because they meet at one seam: a lab is the thing that gets
graded, and recognition is what a passing grade produces. Splitting them would
have meant building the grader in one part and wiring its only consumer in the
next.

---

## Part 8 — Interactive labs, grading, and troubleshooting

### A lab is data, not code

A lab is an authored document: requirements, objectives, a starting topology, a
list of **grading rules**, and — for troubleshooting labs — a list of **fault
injections**. Both rule and fault types are Pydantic discriminated unions
(`app/schemas/lab.py`), which means an instructor can author a lab through the
API and a malformed rule is rejected at write time rather than discovered by a
student mid-attempt.

Fourteen rule types ship. They divide cleanly in two:

| Graded by **simulating** | Graded by **inspecting** |
|---|---|
| `ping`, `no_ping`, `dns`, `port`, `dhcp_lease` | `interface_address`, `in_subnet`, `gateway`, `hostname`, `static_route`, `vlan`, `dhcp_pool`, `device_count`, `link` |

**Reachability is graded by actually running traffic.** A `ping` rule invokes
the Part 7 engine rather than inspecting addresses and inferring. Two things
follow, and both are the reason for the design:

* A lab cannot be passed with a network that merely *looks* right.
* When it fails, the simulator's own diagnosis becomes the feedback. There is
  one definition of "these two hosts can talk", and the simulator owns it.

`no_ping` is the rule that makes segmentation labs possible. Without an
assertion that traffic must **not** flow, a student can pass a VLAN or ACL lab
by cabling everything to everything — every reachability rule goes green and the
lesson is inverted.

### Every result explains itself

`CheckResult` carries a `summary` (what was asked) and a `detail` (what was
found). A grader that returns booleans teaches nothing:

```
✗ R1 GigabitEthernet0/0 must be configured with 192.168.1.1
  The interface is administratively down. It needs 'no shutdown'.

✗ GUEST1 must NOT be able to reach 192.168.5.11
  Guest traffic still reaches the staff network. Traffic got through:
  Reply from 192.168.5.11: 4/4 received, 2 hops.
```

Rules roll up onto the objectives the student reads. An objective passes only
when **every** rule tied to it passes — a half-configured VLAN is not half an
objective — and an objective with no rules attached is narrative only, so it
never fails anyone.

### Troubleshooting: authored working, broken on demand

A troubleshooting lab's `initial_topology` is the **finished, working** network.
The faults break it when an attempt starts. That order is what lets an author
prove the network passes its own rules before deciding how to break it, and
`tests/test_labs.py` asserts exactly that: the authored network scores 100, the
injected faults drop it below the pass mark, and fixing both restores it.

**Faults are applied server-side and never leave the server.** This is the same
discipline the quiz payload uses for answer keys — a lab whose fault list is in
the JSON the browser already downloaded is a reading exercise, not a
troubleshooting one. `tests/test_labs.py` asserts the briefing response contains
neither `gradingRules` nor `faultInjections`, and that the faulted address
`192.168.1.254` appears nowhere in it.

Each fault mutates the document **the way a real mistake would**: a shut
interface is `enabled: false` in the interface config, not a special "faulted"
flag. The learner fixes it with `no shutdown` like anything else, the Part 5
warning banner flags it, and nothing downstream — the CLI, the forms, the
simulator — needs to know a fault engine exists.

A fault that no longer matches (a device renamed since authoring) is logged and
skipped rather than raised. One stale fault should not make a lab unopenable.

### Check is free; submit is final

Two actions, deliberately different:

* **Check my work** — grades, updates the checklist, changes nothing else.
  Unlimited. Iterating on the feedback *is* the lab.
* **Submit** — closes the attempt, awards XP on a first pass, and reveals what a
  troubleshooting lab had broken.

A learner who can only find out how they did by ending the exercise will guess.
One who can check freely will read the feedback and iterate — which is the whole
point of grading by simulation.

Work is **autosaved** (4-second debounce). Unlike the free-form designer, where
saving over an abandoned experiment would be destructive, an attempt *is* the
learner's work in progress; losing half an hour of it to a closed tab is the
worse outcome. Reopening a lab resumes the open attempt rather than starting
fresh.

### The four seeded labs

One per `LabKind`, each demonstrating a different part of the grading model:

| Lab | Kind | Teaches |
|---|---|---|
| Build your first LAN | guided | Addressing and same-subnet reachability |
| Route between two subnets | challenge | The gateway decision, and `no shutdown` |
| The office cannot reach the server | troubleshooting | Reading a trace to find two injected faults |
| Separate guests from staff | design | VLAN segmentation, graded partly on what must *not* be reachable |

---

## Part 9 — Achievements, leaderboards, certificates, notes, instructor tools

### Achievements are data too

Each badge carries a declarative criteria document evaluated against **one**
snapshot of the learner's metrics:

```json
{"metric": "labs_completed", "operator": ">=", "value": 5}
{"allOf": [{"metric": "lessons_completed", ">=", 5},
           {"metric": "quizzes_passed",   ">=", 2},
           {"metric": "labs_completed",   ">=", 2}]}
```

Adding a badge is a seed row, not a deployment. More usefully: awarding fifteen
badges costs the same handful of queries as awarding one, because they all read
the same snapshot. A per-badge callback design would have run its own queries
fifteen times.

There is no `any_of`. A badge earned by either of two unrelated things is two
badges, and splitting them tells the learner more.

Details that matter:

* **Streaks use the live streak, not the stored counter.** A badge for seven
  days running must not go to someone whose streak lapsed weeks ago and whose
  counter was never refreshed.
* **Malformed criteria fail closed** — the badge is skipped and logged, never
  awarded, and never breaks the page for every other badge.
* **Secret badges are omitted from the response entirely** until earned. Showing
  one greyed out with its title defeats the point of it.
* **Unearned badges report progress**, gated by whichever requirement lags. "3
  of 10 labs" is an invitation; a padlock is not.

Evaluation runs **after** each completion commits, never inside `grant_xp` —
badges award XP themselves, so calling it from the grant path would recurse. The
newly-earned list comes back in the completion response, so the UI celebrates a
badge at the moment it is earned rather than on a later visit to the trophy case.

That introduced one subtlety worth recording: badge XP lands *after* the
completion has already computed its totals, so `totalXp` was briefly
inconsistent with the badge shown beside it. The three completion services now
re-read stats when a badge fired. `tests/test_learning.py` pins the arithmetic:
20 XP for a first lesson, +10 for the "First steps" badge it unlocks, and 30 in
total.

### Leaderboards need the ledger

Three scopes, and they are not the same query:

* **All time** reads `user_stats.total_xp` — a cached sum with a descending
  index behind it, so a top-50 is an index scan.
* **Weekly / monthly** can only be answered by summing `xp_transactions` in the
  window. This is why the ledger is append-only rather than a bare counter: "XP
  earned this week" is not derivable from a total.

Every board also carries **your own row**, even when you are outside the top 50.
A board that only shows the top 50 tells nothing to the 99% who most need the
encouragement. It shows display names, levels and XP — never an email address,
which `tests/test_gamification.py` asserts by checking the whole response body
for `@`.

### Certificates

Two identifiers, and the distinction is the design:

* **`serial`** (`NLP-2026-00001`) is internal and reads like a document number.
* **`verification_code`** is 32 hex characters of `secrets.token_hex`. It is the
  only thing a stranger needs, and being unguessable is what stops someone
  enumerating every certificate the platform has issued.

The recipient's name is **captured at issue time**, so a certificate does not
silently change the name on it when the holder edits their profile two years
later.

Verification is public, unauthenticated, and deliberately thin — it answers *is
this real, who holds it, for what*, and nothing else. An unknown code returns
`valid: false`, **not** a 404, so the status code cannot distinguish "wrong
code" from "revoked certificate". Revoking keeps the row: the code must keep
resolving, to `valid: false`.

The verification page renders standalone — no app shell, no navigation, no
sign-in prompt — because it is reached from a link on a CV by someone who has no
account and never will.

### Notes, bookmarks, instructor tools

Notes are written where the thought occurs (a panel in the lesson) and reviewed
in one place (the notes page). Each note comes back with its lesson and course
slug from a single join, so the notes page is not the classic N+1. Ownership is
checked **before** existence everywhere, so another learner's note 404s rather
than 403s and the endpoint cannot be used to discover which note ids exist.

Instructor analytics are **aggregate only**. Instructor tooling on a learning
platform slides easily into surveillance, so the line drawn is: an instructor
may see how the *content* is performing, and a roster of standing — level, XP,
counts, last active — because they need to know who is falling behind. They may
not see a per-learner activity trail.

The two columns that earn their place are a lab's **pass rate** beside its
**average hints**. A lab with a low pass rate and a high hint average is not a
hard lab; it is a badly worded one, and putting those side by side is what makes
that visible.

---

## Architecture notes

`TopologyWorkspace` was extracted from the simulator page when the lab needed
the same surface. The two screens differ in their *chrome* — one has save and
export, the other objectives and submit — but the editing surface is identical,
and two copies would have drifted within a part or two. The lab passes its
briefing and checklist in as leading tabs.

New endpoint groups: `/labs`, `/achievements`, `/leaderboard`, `/certificates`,
`/notes`, `/bookmarks`, `/admin`. No new tables — Parts 8 and 9 are what the
Part 1 schema was designed around, and `alembic check` reports no drift.

## Verification

Backend: **417 tests**, `ruff` clean, `mypy` clean across 99 files, `alembic
check` no drift. Frontend: **99 tests**, `tsc` clean, `eslint` clean, `vite
build` succeeds.

Verified end to end in a browser:

* The troubleshooting lab opens with faults applied, checks at 20% with the
  simulator's diagnosis (*"PC1 could not resolve 192.168.1.254 to a MAC
  address"*) rendered against the failing objective, and — after fixing the
  gateway in the form and clearing the shut interface — **passes at 100%,
  awards +80 XP, and reveals both fault explanations**.
* Starting a second attempt re-applies the faults from the intact original.
* Passing the lab unlocked **Hands on** and **Flawless**, which appear earned on
  the achievements page with the rest showing progress.
* The leaderboard ranks correctly, medals the top three, and highlights your own
  row.
* A certificate issued for a completed course renders with its verification link;
  the public page verifies it signed-out with no shell and no email, and answers
  *"No matching certificate"* for an unknown code.
* Notes and bookmarks save from inside a lesson and appear on the notes page.

The admin page was verified by its backend tests (analytics figures, roster, role
gating, lab authoring) and by typecheck — not in the browser, because the seeded
session was a student account.

## Bugs found and fixed during these parts

* **A device's configuration could be written onto another device.**
  `DeviceConfigWindow` seeds its working `DeviceConfig` from the device on
  mount. Opening a second device without the instance unmounting in between
  reused the first device's state, and the next edit wiped the second device's
  interfaces. Found in browser verification — R1 came back with every interface
  unassigned. Fixed with a `key` on the device id, and pinned by
  `device-config-window.test.tsx`, which reproduces the bug in the un-keyed case
  so the reason for the key is on the record.
* **`totalXp` disagreed with the badge in the same response**, described above.
* **A route collision**: `/lessons/{lesson_id}/notes` shadowed the lesson
  viewer's `/lessons/{course_slug}/{lesson_slug}`, and whichever router was
  registered first silently won. Notes moved to `/notes/lesson/{lesson_id}`
  rather than depending on registration order.
* **Five identically-named checkboxes.** Every interface's "no shutdown" control
  had the same accessible name; the address fields beside them were already
  qualified per interface. Both checkboxes now match that convention.

## What Part 10 builds on this

Performance, security review, deployment (Azure App Service, Docker, cPanel),
and final documentation. The application surface is now complete: everything
from Part 10 is hardening and shipping rather than new capability.
