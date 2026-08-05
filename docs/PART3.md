# Part 3 — Learning Platform

Scope as specified: course engine, lesson viewer, quizzes, progress saving.

## Delivered

### Course engine
`tracks → courses → modules → lessons`, served through three projection depths
so a request never carries more than it needs: card-sized summaries for
listings, a syllabus without lesson bodies for the course page, and the full
body only when a lesson is opened. Loading prose to render a table of contents
would ship hundreds of kilobytes to draw a list.

The catalogue is **public**. Browsing and reading a lesson need no account —
progress fields simply come back empty. Every per-learner annotation
(enrolment, percentage, lesson status) is batched into set-based lookups, so
the catalogue page issues a fixed number of queries regardless of how many
courses exist.

### Lesson viewer
Lesson bodies are an ordered list of **typed content blocks**, validated as a
Pydantic discriminated union on write and rendered by an exhaustive TypeScript
switch on read. Ten block types: heading, paragraph, list, callout, code,
table, image, definitions, divider, interactive.

Two properties fall out of that design:

* A malformed block cannot be stored. A table whose rows do not match its
  headers, an image without alt text, or an unknown widget name fails the
  seed rather than reaching a reader.
* No author-supplied HTML is ever persisted, so there is nothing to sanitise
  and the renderer keeps full control of presentation.

`assertNever` in both the block renderer and the widget dispatcher makes adding
a type server-side without adding a renderer a **compile error** — the two
files cannot drift silently.

### Interactive widgets
Four, each doing real work rather than decoration:

* **Subnet calculator** — live network/broadcast/host maths with the binary
  split colour-coded and the magic-number working spelled out, mirroring what
  the lesson teaches so a learner can check their hand calculation.
* **OSI stack** — a clickable seven-layer explorer with per-layer
  troubleshooting prompts.
* **IPv4 anatomy** — octet breakdown showing how the bits add up to each value.
* **TCP handshake** — an animated SYN / SYN-ACK / ACK exchange.

### Quizzes
Eight question types, all graded server-side: single choice, multiple choice,
true/false, fill-blank, ordering, matching, subnet calculation, and CLI command.

The security property is enforced by **type separation**: `QuizForAttempt`
(pre-submission) and `QuizResult` (post-submission) are different models, so an
answer key cannot leak into the delivered payload by accident. Verified both in
tests and against the running server — the delivered JSON contains no
`isCorrect`, no `explanation`, and no `answerKey`, and each option carries
exactly `{id, text, orderIndex}`.

Other grading decisions:

* **Multiple choice is set equality, not partial credit.** "TCP and UDP are
  both connection-oriented" is wrong even though half of it is right.
* **Free text is normalised** — whitespace and case for fill-blank, IP-aware
  spacing for subnet answers, and Cisco-command normalisation for CLI answers,
  with an author-controlled `accepted` list for legitimate alternatives.
* **Shuffling is seeded on the attempt id**, so a refresh shows the same order
  instead of reshuffling mid-attempt.
* **An unsubmitted attempt is resumed**, so refreshing the page does not burn
  one of a limited number of attempts.

### Progress saving
Completing a lesson records progress, awards XP through the Part 2 engine
(idempotent by reference, so re-completing pays nothing), recomputes the course
percentage from lesson state, and — on the final lesson — completes the course
and pays a 100 XP bonus once.

The percentage is **derived on every completion, not incremented**, so
publishing or unpublishing a lesson cannot leave it permanently wrong.

Reading position autosaves, and the study timer pauses when the tab is hidden —
without that, a lesson left open overnight would report eight hours of study.

### Seeded content
Two complete CCNA-level courses with four lessons and two quizzes, authored as
plain data in `app/seeds/foundation_content.py` and loaded by an **idempotent**
seeder that upserts by slug, so re-running after an edit updates rows in place
and never touches learner progress.

```bash
python -m app.seeds
```

The content is treated as a shipped artefact: tests assert every block
validates, every lesson declares objectives, every single-choice question has
exactly one correct option, and every free-text question carries an answer key.

## Verified

| Check | Result |
|---|---|
| Backend tests | 160 passed (111 → 160) |
| Frontend tests | 64 passed (47 → 64) |
| `ruff check` | clean |
| `mypy app` | clean, 60 files |
| `tsc -b` | clean |
| `eslint` | clean |
| `vite build` | succeeds |
| `alembic check` | no drift |

Driven end to end against running servers: browsed the catalogue, enrolled,
read a lesson with every block type rendering, started a quiz, confirmed the
delivered payload leaked no answers, submitted, saw the recorded score, and
finished both courses — ending at level 4 with 555 XP, 4 lessons and 2 courses
completed, all through the real UI.

## Bugs found and fixed during verification

**Lazy relationship load in async context.** `EnrollmentRead` declared an
optional `course`, and `from_attributes` reads every declared field off the ORM
object — triggering a lazy load that raises `MissingGreenlet` under asyncio.
Split into `EnrollmentRead` (no relationship) and `EnrollmentWithCourse`
(loaded explicitly), which makes the eager-loading requirement visible in the
type rather than a runtime surprise.

**Multi-select could drop a selection.** Two clicks in the same tick both
computed the next selection from the same render's props, so the first was
lost. Found by scripting the quiz in the browser and scoring lower than the
answers deserved. Fixed by giving `onChange` a functional updater form that
resolves against live state; a regression test now clicks two options in
succession and asserts both stay checked.

**Test paired results positionally.** Questions are delivered shuffled while
results come back in stored order — the API is right to key on `questionId`,
and the test was wrong to zip them. Fixed with a `result_for` helper, and the
constraint is now documented where it matters.

## Decisions worth flagging

**Content blocks over HTML or Markdown.** Structured blocks keep presentation
under the renderer's control, let interactive widgets sit inline with prose,
make the content queryable, and eliminate sanitisation entirely. The cost is an
authoring format that needs a schema — which is also what makes malformed
content impossible to store.

**The widget catalogue is a closed `Literal`.** A lesson can never reference a
widget that does not exist, on either side of the wire.

**Free-text answers normalise but do not fuzzy-match.** Accepting "packet" for
"a packet" is correct; accepting "pakcet" would teach the wrong spelling of a
term the learner needs in an exam. Legitimate alternatives are listed
explicitly by the author.

**Study time is capped twice.** The client clamps to an hour before sending and
the server rejects anything larger — a machine waking from sleep should not
produce a 422, and a tampered client should not be able to inflate totals.

## Not in this part

Notes and bookmarks have tables from Part 1 but belong to Part 9's platform
features, so no endpoints were added for them. Certificates
(`grants_certificate` is set on the subnetting course) are also Part 9.

The admin content API — creating and editing courses through the UI rather than
the seeder — is Part 9's instructor tooling.

## Ready for Part 4

Part 4 (interactive network designer) is the first part that does not build on
the catalogue: it uses the `topologies` table and the document schema sketched
in Part 1, plus React Flow and Konva, which are not yet installed.
