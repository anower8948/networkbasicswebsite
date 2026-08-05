# Part 2 — User System

Scope as specified: login, registration, dashboard, profiles, progress tracking.

Login and registration shipped in Part 1 as the authentication foundation, so
Part 2 completes the account lifecycle around them: email verification, password
recovery, profile and session management, and the progress engine that every
later part writes through.

## Delivered

### Email verification
Sent automatically at registration, with a resend path from the account
settings and dashboard banners. Verification is **non-blocking** — an unverified
account can learn immediately; verification gates certificates only. Blocking
access on a mailbox round trip would abandon users at the point of highest
intent.

The landing page is reachable signed in *or* out, because an emailed link is
opened in whatever browser the mail client hands it to.

### Password reset
Request → emailed link → new password. The reset consumes the token, revokes
**every** session, and marks the address verified (receiving the link proves
mailbox control). A "your password was changed" notice follows, so a victim of
account takeover learns of it.

### Email delivery
`EmailService` with two backends behind one interface. `console` logs the
rendered message — the development default, so both flows are fully clickable
with no SMTP server anywhere. `smtp` delivers for real, off the event loop via
`asyncio.to_thread`. Delivery failures are logged and swallowed: a registration
must not fail because a mail server blinked.

### Rate limiting
Sliding-window limits on the endpoints worth abusing: password reset and resend
(5/hour) and login (10/15 min). Login is keyed on the **email address**, not the
IP, so an attacker rotating proxies still shares one budget against the account
they are targeting.

### Profile management
A settings screen with three sections — Profile, Security, Preferences — each
addressable by URL (`/settings?tab=security`), so a section can be linked to and
survives a reload.

Timezones are validated against the IANA database at the boundary. An invalid
value would silently fall back to UTC inside streak accounting and miscount that
learner's streaks indefinitely.

### Session management
Every device holding a live refresh token is listed with a parsed device label,
IP and sign-in time, with the current device marked so a user revoking others
does not sign themselves out by mistake. Revoking kills the whole token family:
a family shares one login, so leaving siblings alive would let that device
refresh straight back in.

### Progress engine
The foundation Parts 3, 8 and 9 write through. Two invariants:

1. **The ledger is the truth.** `xp_transactions` is append-only;
   `user_stats.total_xp` caches its sum and is rebuildable via
   `recalculate_stats()`. Caching is only safe because the repair path exists.
2. **XP is granted once per source.** Grants carry a reference
   (`lesson`, `<uuid>`) and deduplicate against it, so re-completing a lesson
   never pays twice.

Levels follow `100 × (n−1)^1.5`, capped at 100 — closely spaced early for fast
feedback, stretching later. The curve has exactly one implementation; the client
renders precomputed numbers and never recomputes them.

Streaks count **calendar days in the learner's own timezone**, not 24-hour
periods: studying at 23:00 and again at 08:00 is two days of practice and a
learner expects a streak of two. The stored counter only refreshes on activity,
so reads go through `current_streak()`, which reports zero after a missed day
rather than a stale number.

### Account deactivation
A soft flag, never a delete — certificates, lab attempts and the XP ledger must
survive, and a row delete would cascade them away. Sessions are revoked
immediately and login is refused.

## Verified

| Check | Result |
|---|---|
| Backend tests | 111 passed (53 → 111) |
| Frontend tests | 47 passed (32 → 47) |
| `ruff check` | clean |
| `mypy app` | clean, 45 files |
| `tsc -b` | clean |
| `eslint` | clean |
| `vite build` | succeeds |

Exercised end-to-end against running servers: registration issuing a real
verification link, clicking that link to confirm the address, token reuse
rejected, password reset through the browser form, old password refused and new
accepted, address auto-verified by the reset, identical responses for registered
and unregistered addresses on "forgot password", the study-time cap rejecting an
inflated ping, XP idempotency refusing a duplicate grant, a live level-up, and
the dashboard rendering all of it.

## Bugs found and fixed during verification

**Verification page spun forever.** The API returned 200 but the UI never left
its spinner. `useMutation` state lives on the component's observer; StrictMode's
simulated unmount detached it, so the in-flight result resolved into a dead
observer and the remounted one sat idle. Rebuilt as a **query keyed on the
token**: queries are cached by key, so the single-use token is spent exactly
once regardless of remounts, and the manual "already attempted" ref guard
disappeared with it.

**Reset link bounced signed-in users to the dashboard.** `/reset-password` sat
behind the public-only guard. The common case — signed in on a laptop, clicking
a reset link from email — silently swallowed the action. Emailed landing pages
now sit outside both guards. Completing a reset while signed in also clears the
local session, since the server has already revoked it.

**Rate limiter leaked between tests.** The limiter is a process-global
singleton, so login attempts in one test consumed another's budget and failures
would surface in whichever test ran eleventh. Reset moved into an autouse
fixture in `conftest.py`.

## Decisions worth flagging

**Study time is capped at one hour per ping.** `studySeconds` is client-supplied
and therefore untrusted; without a bound, a tampered client could inflate study
totals — and a future leaderboard — with one request.

**Account enumeration is closed on both public endpoints.** "Forgot password"
returns the same message whether or not the address exists, and verification
rejects a wrong-purpose token with the same error as an unknown one, so a reset
token cannot be probed against the verification endpoint to learn it is valid.

**Reissuing a link retires the previous one.** Otherwise every reset email ever
sent stays live until expiry, each an independent chance for an old message to
be replayed out of a mailbox.

**Timezone list in the UI is curated, not exhaustive.** The value only decides
which calendar day a session counts toward, so offset coverage matters more than
completeness — and the API accepts any valid IANA zone regardless. A stored
value outside the list is injected into the picker so it never misreports the
user's setting.

## Known limitation

The rate limiter is **in-process and per-worker**. It resets on restart, and N
uvicorn workers permit N times the configured rate. That is an acceptable trade
for turning an unbounded password-reset mail flood into a bounded one, but it is
not a global control. Part 10 swaps the backing store for Redis; the
`RateLimiter` interface is deliberately narrow so that change touches one file.

## Ready for Part 3

Part 3 (course engine, lesson viewer, quizzes, progress saving) builds on the
catalogue tables from Part 1 and calls `ProgressService.grant_xp` and
`record_activity` — both in place, tested, and exercised end-to-end.
