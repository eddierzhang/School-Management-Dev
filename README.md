# Halverson Ridge — student support

A student support and intervention dashboard for a school's support office. It
shows who is struggling, who is excelling, on which topics, and what to do about
it. Plans are opened, approved, tracked and closed, and local AI agents draft
plans for a person to adopt. It is a FastAPI backend with a React frontend, and
the AI runs on the school's own machine through Ollama.

**The product is the support workflow:** a student is flagged, you see why, a plan
is proposed, approved, tracked, then completed or retired. Everything else is an
optional module, off unless `HR_MODULES` lists it:

| Module | What it adds |
|---|---|
| `registrar` | Class demand, opening classes and sections, the registrar agent |
| `stockroom` | Inventory, requisitions, the stockroom agent, supplies on the class page |
| `finance` | The budget, transfers and revisions, the finance agent |
| `manager` | The general manager agent, which briefs on and dispatches the others |

A module that is off has no screens, no routes (404), no agents and no
proposals. Its permissions are removed from every role. `HR_MODULES=all` turns
them all on, which is how the demo and the tests run.

**`demo/`** holds what exists only for the demo: `gen_seed.js`, which generates
the fictional term (60 students in grades 9–12, 26 classes), and the registrar
console published as a Claude Artifact (`console.html`, with `dev-server.js` to
run it locally). The console keeps its own records in the Artifact store; the
backend is the source of truth for everything in the support app.

---

## Student support (backend + frontend)

### What it answers

**Who is struggling** — a struggle index per student, built from four named
factors rather than a single grade average.

**Who is excelling** — a separate index on its own axis. A student failing maths
and top of the class in science carries *both*; averaging the two into one
number is precisely how such a student gets missed.

**Every student, in one place** — the Students tab lists the whole school:
needs a plan, watch, steady and excelling, each with one **standing** score
(excelling index − struggle index, from −100 to +100), their lowest and strongest
class, absence and open plans. Netting the two indices is how a student failing
one class and top of another would vanish near zero, so anyone with struggle ≥ 35
*and* excelling ≥ 60 is marked **mixed**. Bands and plans still come from the
two indices underneath. Filter buttons narrow it to
struggling, one band, or anyone with a strength (including students who also
struggle), with live counts on each, so the steady middle is monitored too.

**What they are struggling *on*** — every graded piece is tagged with the strand
it tests, so mastery rolls up per topic. The system says *word problems, not
graphing*, which is the difference between "behind in maths" and a lesson plan.

**What the school should do** — rule-based recommendations that name an action,
a reason and an owner: homework recovery when the problem is submission,
tutoring on a named strand when it is comprehension, a counselor check-in when a
student is sliding across unrelated subjects, an attendance plan when grades are
following absence, and an enrichment placement when there is something to build
on. Opening a plan turns a computed recommendation into something a person owns.

**What a document says** — upload a teacher note, report card or piece of work
and the local model finds specific needs and strengths in it, each backed by a
verbatim quote and checked against the gradebook.

**What to reteach** — the same strand data aggregated per cohort. One student
below on a strand is a referral; half the class below on it is a lesson to run
again, and no amount of tutoring fixes that one student at a time.

### The indices

```
struggle = 0.55·low mastery + 0.20·decline + 0.15·unsubmitted work + 0.10·absence
excel    = 0.55·high mastery + 0.20·improvement + 0.15·completion + 0.10·consistency
```

Each is computed per class, then rolled up so the **worst (or best) class sets
the level** and the others add urgency into the remaining headroom:

```
student_index = worst + breadth × (100 − worst) × mean(others) ÷ 100
```

Averaging across classes was wrong twice over — it hid a student failing one
subject behind five they were fine in, and it quietly punished students who take
more classes, since the same failing grade diluted further with every extra
course on the timetable.

Nothing is cached. Every index is recomputed from the gradebook on read, so a
grade entered through the API moves the ranking on the next request with no
rebuild step. The weights, the normalisation scales and the band cut-offs all sit
together at the top of `backend/app/analytics.py`, deliberately separate from the
policy thresholds in `config.py` — **a real school would calibrate the bands
against its own grade distribution before trusting the counts.**

Missing past-due work counts as zero toward mastery *and* is tracked separately,
because "did not submit" and "submitted and scored badly" call for different
responses.

### First run

```bash
node demo/gen_seed.js                              # the demo roster, once

python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env               # pins the demo clock, among other things
backend/.venv/bin/python backend/seed.py           # migrates and seeds backend/halverson.db

cd frontend && npm install && cd ..
```

The demo term is built around 2026-09-12, so the seed refuses to run unless
`HR_TODAY=2026-09-12` is set, and the app should run with the same value. A real
deployment leaves `HR_TODAY` unset and uses the real date.

### Database and migrations

SQLite is the default for development. For Postgres, start it with
`docker compose up -d db` and set
`HR_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/educationhack`.

The schema is owned by Alembic (`backend/alembic/versions/`). The app never
creates or alters tables itself; it logs an error at startup if the database is
behind, and `/api/ready` returns 503 until it is migrated.

```bash
cd backend
.venv/bin/alembic upgrade head                              # bring a database up to date
.venv/bin/alembic revision --autogenerate -m "what changed"  # after changing app/models.py
```

A test fails if the models and the migrations disagree, so a model change
without a migration cannot be merged. A database created before migrations
existed can be brought under them with `alembic stamp 0001`, or reseeded.

`GET /api/health` is liveness (the process answers). `GET /api/ready` is
readiness: the database answers and is at the newest migration. The local model
is reported there but never makes the app unready.

### Running it

```bash
./dev.sh            # both, together
```

or separately:

```bash
cd backend  && .venv/bin/python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

- Interface — http://localhost:5174
- API — http://localhost:8000/api/health
- Interactive API docs — http://localhost:8000/docs

The Vite dev server proxies `/api` to port 8000, so the browser stays
same-origin and never needs CORS in development.

The URL is the view: `#/students`, `#/classes`, `#/skills`, and
`#/students/S-1507` with one student's record open (old `#/watchlist` and
`#/strengths` links open the Students tab pre-filtered) — so a support office can
bookmark a list or mail a colleague a link to one student.

### Tests

```bash
cd backend && .venv/bin/python -m pytest -q      # SQLite
HR_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/educationhack_test \
  .venv/bin/python -m pytest -q                  # the same suite on Postgres (drops that database's tables)
cd backend && .venv/bin/ruff check . && .venv/bin/pip-audit -r requirements.txt
cd frontend && npm run typecheck
```

Install the test tools with `pip install -r requirements-dev.txt`.
`requirements.txt` is what production installs.

CI (`.github/workflows/ci.yml`) runs on every pull request and on `main`:

- ruff and pip-audit on the backend
- the full test suite on both SQLite and Postgres 16
- a startup smoke test: migrate an empty Postgres, start uvicorn, wait for `/api/ready`
- the frontend typecheck, a production build, and `npm audit`

Dependabot opens weekly grouped updates for pip and npm.

`tests/test_analytics.py` builds a purpose-made record per test, so a failure
names a rule rather than a dataset. Two of those tests are regressions for real
calibration bugs: an `excel_index` scaled so that even a near-perfect record
could not reach its own band cut-off, and a weighting that capped mastery's
contribution below the "needs a plan" threshold, so a student at 48% with perfect
attendance read as "steady".

`tests/test_api.py` runs against its own freshly seeded database, never the dev
one.

### Importing the school's records

The demo seed is fictional. A real school's records come from its student
information system as a **OneRoster 1.1 CSV** export (PowerSchool, Infinite
Campus, Aeries, Skyward and Clever all produce one):

| File | Needed | Becomes |
|---|---|---|
| `users.csv` | yes | students (ID from `identifier`), their first guardian, teachers |
| `classes.csv` | yes | sections: `classCode`, first of `periods`, `location` as the room |
| `enrollments.csv` | yes | rosters; the `primary` teacher names the section's teacher |
| `courses.csv`, `academicSessions.csv` | no | course titles and subjects, term names |
| `categories.csv`, `lineItems.csv` | no | assessments; the kind comes from the title, then the category |
| `results.csv` | no | scores; `not submitted` is missing work, `exempt` counts as neither |
| `attendance.csv` | no | not OneRoster: `userSourcedId,date,status` |

OneRoster has no skill tag on an assessment, and "what are they struggling on"
needs one. Add a `skill` column to `lineItems.csv`. Without it the import warns
and groups those pieces under `general`.

```bash
python -m app.cli import-oneroster export.zip             # check only: reports, then rolls back
python -m app.cli import-oneroster export.zip --apply     # import
python -m app.cli import-oneroster export/ --apply --create-teacher-accounts
```

Administrators can do the same on the Admin tab (**Import records**). The flow
is always check first, then import.

- **Nothing is written until everything checks out.** Every file is read and
  every reference resolved first. A missing column, an unknown student, a score
  above the maximum or an unreadable date refuses the whole import and names
  the file and line.
- **A check is the real import, rolled back.** It reports exactly what would be
  created, updated and dropped, and runs the timetable checks on the result:
  rooms or teachers double-booked, students in two classes in one period,
  classes with no teacher or no assessments.
- **Re-importing is safe.** Students match on their ID, classes on their code,
  assessments on their OneRoster `sourcedId`. The same export twice changes
  nothing.
- **Each class in the file is a full roster.** A student no longer listed is
  marked dropped, never deleted. Students and classes absent from the file, and
  every plan, document and override, are left alone.
- **Teacher accounts** (`--create-teacher-accounts`) are created from each
  teacher's email, with no password, for sign-in through the school's identity
  provider, and linked to their sections by name.

Courses the catalog marks ungraded (P.E. in the demo) still show their scores on
the class page, but no longer move a student's indices, reasons or recommended
plans.

### History, overrides and rejection reasons

**A student's history.** The indices are recomputed on every read, which keeps
them honest but forgets yesterday. Snapshots record each student's struggle and
excelling index, band, attendance and open plans once a day (the worker does
this; `python -m app.cli snapshot` does it by hand). The student record charts
them over the term, with plans and overrides marked on the date they happened,
so you can see whether a plan moved anything. The seed backfills a reading each
Friday from week three, read from the gradebook as it stood then.
`GET /api/students/{sid}/history`.

**Overruling the index.** A counselor can record one of two things about a
student, always with a reason and an end date no more than 90 days out:

- *The concern is known and in hand.* The band stays, but the student stops
  counting as "needs a plan and has none". They leave the watchlist (unless
  `include_acknowledged=true`) and the support agent's sweep.
- *The index is wrong about this student.* The band is replaced everywhere:
  lists, counts, filters and agents.

The computed band is always shown beside the override. Overrides lapse on their
end date so they get looked at again, a new one replaces the old, and every
change is in the audit log. Snapshots record the computed band, not the
override. `POST /api/students/{sid}/overrides`,
`DELETE /api/students/{sid}/overrides/{id}`.

**Every rejection has a reason.** Rejecting an agent's proposal requires a note
(at least five characters). It is stored with the decider's email as
`decision_note`, and `GET /api/agents/proposals?status=rejected` lists them.
Read together, they show where the agents or the indices go wrong.

### Accounts, roles and the audit log

Everything except `/api/health`, `/api/ready` and sign-in needs a signed-in
person. The seed creates demo accounts, all with the password
`halverson-demo-2026`: `admin@`, `counselor@`, `registrar@` and `business@halverson.example.edu`,
plus one per teacher (`r.okonkwo@halverson.example.edu`, …).

| Role | Sees | Can do |
|---|---|---|
| Administrator | everything | everything, plus accounts, the audit log and the general manager |
| Counselor | every student | open and close plans, upload documents, request AI drafts, approve plan proposals |
| Teacher | only students in their own sections | record scores and upload documents for them, request drafts; approves nothing |
| Registrar | students, classes, timetable | open classes and sections; approve those proposals |
| Business office | stockroom and budget, no student records | change stock and budget; approve those proposals |

The full map is `backend/app/auth/permissions.py`. Every route checks its
permission on the server; the interface only hides what the API would refuse.
Approving an agent's proposal needs the same permission as making that change
by hand. Agent runs and transcripts are only visible to roles that may use that
agent, because a transcript quotes the records it read.

**Signing in.** Passwords are hashed with scrypt. Sessions are server-side rows
behind an HttpOnly, SameSite=Lax cookie (Secure in production). Changes also need
an `X-Requested-With` header, which a page on another site cannot send. Five
failed attempts lock an email for 15 minutes. Changing a role, deactivating an
account or resetting its password ends that person's sessions.

**The school's identity provider.** Set `HR_OIDC_ISSUER`, `HR_OIDC_CLIENT_ID`,
`HR_OIDC_CLIENT_SECRET` and `HR_OIDC_REDIRECT_URI` (Google Workspace, Microsoft
Entra, or any OpenID Connect provider) and the sign-in screen offers it. The
backend runs the authorization-code flow with PKCE and verifies the ID token's
signature, issuer, audience, expiry and nonce. The email must already have an
active account: signing in never creates one. Set `HR_PASSWORD_LOGIN=false` once
everyone uses it.

**The first administrator** of a new deployment is created on the server:

```bash
python -m app.cli create-user head@school.edu "Head of School" admin --password
```

After that, accounts are managed on the Admin tab. A teacher account needs the
teacher's name exactly as it appears on their sections.

**The audit log** (Admin tab, `GET /api/admin/audit`) records:

- every change made through the API, including refused attempts
- every time someone opens a student's record, documents, study plans, class
  work or timetable
- every sign-in, sign-out and failed sign-in

Rows are only ever inserted. Request bodies are never logged. Every response
carries an `X-Request-ID` that matches its audit entry.

**Production refuses to start** (`HR_APP_ENV=production`) with the development
secret key, a SQLite database, a pinned clock, or insecure cookies. It also
serves no `/docs`, and every API response is `Cache-Control: no-store`.

### Layout

```
backend/
  app/
    analytics.py     the signal engine — indices, reasons, recommendations, cohort gaps
    models.py        students, courses, enrollments, assessments, scores, attendance, plans
    schemas.py       wire shapes, mirrored by frontend/src/types.ts
    routers/         students · courses · support · interventions · scores · inventory ·
                     agents · meta
    stock.py         the one definition of "low", shared by the API and the agent
  seed.py            generates the gradebook from the shared roster
  tests/
frontend/
  src/
    views/           overview · students · classes · strands · plans ·
                     stockroom · agents
    components/      charts, student drawer, plan dialog, UI primitives
    api.ts           typed client, one function per endpoint
```

---

## Finance

The Finance tab tracks the FY2027 budget line by line: allocation, transfers,
spending, and **committed** money — the stockroom's open requisition, costed to
par and charged to the department that buys it, so an approved order shows up as
soon as it is approved. Each line is judged against how much of the year has gone
(`app/finance.py`, shared by the API, the screen and the agent):

```
over budget      spent + committed exceed the budget
at risk          the year-end projection exceeds the budget
under-spending   under 35% of the expected pace, after the first six weeks
on track         everything else
```

One-time purchases are kept out of the projection's monthly pace; otherwise a
front-loaded line — an August laptop refresh — reads as a runaway. Two rules raise
charges for review: the same vendor and amount twice within ten days, and one
charge over a quarter of its line. Transfers never edit an allocation; they are
recorded beside it.

The **finance agent** proposes transfers into lines that are over or at risk, from
lines that stay on track afterwards, and proposes holding suspicious charges. On its
first live run it found both planted problems — an HVAC invoice paid twice under the
same reference, and forty climbing harnesses bought for a course that no longer
exists — but tried four transfers from lines that were themselves at risk, because
it had only been shown the problem lines. Every one was refused; its opening read
now also lists the lines that can give, and how much.

The seeded ledger is fictional (`app/finance_seed.py`).

### Opening lines and revising the budget

**Moving money to where it is needed**, on the Finance tab, lists the lines that
need money, and how much, beside the lines that can give. "Needs money" means
overspending, projected overspending by June, or low stock nobody has ordered
that the line can't absorb. "Can give" is the most a line can lose and stay on
track. From there:

- **A budget revision** moves money across several lines at once and is approved
  as one package. It's judged on its combined effect: a line giving to two others
  must stay on track after both, no line receives more than 125% of its need, and
  no line both gives and receives. If the budget changed before approval, none of
  it is applied.
- **Opening a line** creates a line for a purpose no existing line covers. It
  opens at zero allocation and is funded by a transfer from a line with room, so
  no approved allocation is ever edited.

A person can do either on the page (`POST /api/finance/revisions`,
`POST /api/finance/lines`). The finance agent proposes them with
`propose_budget_revision` and `propose_new_budget_line`, and both wait for
approval on the Finance tab and in the fleet inbox. Any dollar figure the agent
cites must match the budget data.

**Observed live, and why the agent no longer has a single-transfer tool.** Given
both tools, with five lines short, qwen3:4b funded one of them with a transfer and
stopped. With only the revision tool, the same sweep proposed one revision
covering all five ($15,563 from four lines with room), and the narrower task
"address PE-EQP, MAT-INS and CSC-ROB" got a revision covering exactly those
three. Both runs had no tool errors. Asked for a maths workshop line, it opened
`MAT-WKS` with $1,500 from tutoring.

```
GET  /api/finance/needs       lines needing money, and lines that can give
POST /api/finance/lines       open a line, funded by a transfer
POST /api/finance/revisions   several transfers, validated and applied together
```

---

## The course catalog

Every section is a real course from the *2026-27 Upper School Course of Study*
(`backend/app/catalog.py`). The first 14 were mapped onto it. Codes, teachers, rooms and periods
are unchanged; each section now carries the catalog title, department, length,
credits, prerequisite, UC-approval flag and page number, shown on the class page.

Nine map directly. Five had no counterpart and use the nearest real course:
Esports & Game Design → Digital World, Model UN → Introduction to Speech and
Debate, Rock Climbing → Personal Fitness, Culinary Basics → Biotechnology, Life
Science → Biology. Skill strands were renamed position by position, so existing
scores carry over. Three stockroom items (climbing harness, kitchen apron, chef
knife) no longer belong to any class and are unlinked.

Twelve more sections come straight from the same document, filling departments
the first fourteen missed: English 1 and English 3, World History 1, United
States History, Algebra 2 & Trigonometry, AP Calculus AB, Physics, Chemistry,
Programming, French 1, Economics and Psychology. `demo/gen_seed.js` builds their
rosters period by period, so a student is only enrolled where they have no class
that period and only in the grades a course is meant for (English 1 and Physics
for grade 9, U.S. History for grade 11, AP Calculus for 11–12). No teacher or room
is double-booked, and no student gains a clash. Their gradebooks are generated on
a separate random stream, so the original fourteen sections' scores, attendance
and plans are exactly what they were.

To bring an existing database up to date without losing plans, proposals or
documents, run `node demo/gen_seed.js` and then `python seed.py --upgrade` in
`backend/`: it adds any section missing from the database with its roster and
gradebook, and takes each student's grade and homeroom from the seed.

The school is a high school, grades 9–12, fifteen students per grade. The
catalog says P.E. is ungraded. The gradebook still scores Personal Fitness, and
those scores show on its class page, but they do not count toward any student's
indices.

---

## Class demand, and opening classes

The **Class demand** tab ranks every class by the registrar console's published
demand index, so both halves agree on what is popular:

```
demand = 100 × (0.40·seats filled + 0.35·waitlist÷capacity + 0.25·signups in 2 wk÷(capacity×0.6))
over-subscribed 70+ · high demand 52+ · healthy 32+ · seats to fill below 32
```

Demand is pooled across a class's sections (`MAT-150`, `MAT-150.B`, …), so opening
a section that absorbs the waitlist makes the class read as relieved. Each class
gets a suggested action: open a section (waitlist ≥ half a section), add seats,
promote, or review for next term (under-filled with signups cooling).

**New class** and **Open a section** both refuse a room or teacher already booked
in that period. `app/timetable.py` holds that rule, and the registrar agent's
approved proposals go through the same code. A new section copies the catalog
entry and takes students from the class's waitlist in the order they joined.

```
GET  /api/courses/demand             ranked classes, with the formula and bands
GET  /api/courses/openings?period=3  rooms and teachers free that period
POST /api/courses                    open a new class
POST /api/courses/{code}/sections    open another section, optionally moving the waitlist
```

Weekly signups are stored on each course (`courses.signups`). An existing
database gets the column at startup and is backfilled from `seed/`, with no
reseed needed.

---

## Schedules

The **Schedule** tab is the master timetable: every running section laid out by
period, with rows by room or by teacher, filterable by department. Select a class
to open its page. Below it, pick any student to see their day period by period:
the classes they're enrolled in, free periods, and classes they're waitlisted
for. The same timetable appears in every student's record.

Conflicts are shown, never quietly resolved (`app/schedule.py`):

- **Timetable clashes** — a room or teacher booked into two sections in the same period.
- **Student clashes** — a student enrolled in two classes in the same period.

The seeded term has no timetable clashes but **41 of 60 students have a student
clash**: `demo/gen_seed.js` fills rosters by balancing class load and never looks at
periods. The screen lists every one, so the registrar can see the scale of it.

```
GET /api/schedule                  sections by period, rooms, teachers, both kinds of clash
GET /api/students/{sid}/schedule   one student's day, with free periods and clashes
```

---

## Class improvement plans

Every class page has an **Improvement plan** section. A support plan is for one
child; a class plan is for the course, for when half the room is below the line
on one strand or a sixth of the work never comes in.

**What the numbers say** is deterministic (`app/class_plans.py`): class average,
work handed in, trend, every strand, and each kind of work, with a status
(*needs a plan*, *worth watching*, *doing well*) and named issues. On the seeded
term, Speech and Debate, Algebra 1 and English 4 need a plan.

**Draft a plan with the AI agent** starts the **class improvement agent** on that
one class. It opens on the class's performance and can only propose for that
class. A run takes about 40–140 seconds on qwen3:4b. The draft has a diagnosis,
one or two focus strands, two to five actions and a measurable four-week goal.
Adopting it records today's numbers as the baseline, so the plan shows
**at adoption / now / change** for the class average, work handed in and each
focus strand until it is completed or retired. The same agent is in the fleet,
where a blank run drafts plans for the neediest classes.

A draft is sent back to the model, with the reason, when it:

- **cites a percentage the data doesn't contain.** Targets ("to 75%") are exempt.
  Observed live: an invented "20%", fixed on the next call.
- **miscounts.** Observed live: "15 of 28 students below the 72% line" for Algebra 1.
  Every percentage in that sentence was real, but 15 of 28 is the word-problems
  strand; the class is 13 of 28. A count is checked against the measure its
  sentence names, not just against any number in the data.
- **ignores missing work.** Observed live: Speech and Debate, with 16% of work not
  handed in, got a plan of two reteach lessons. Reteaching doesn't fix work that
  never arrives, so a plan must address it; on its third call the model added one.
- names a strand the course doesn't teach, has vague actions or an unmeasurable
  goal, or duplicates an active plan or a draft already waiting.

```
GET   /api/improvement                        every class, neediest first, with plans and drafts
GET   /api/courses/{code}/improvement         snapshot, plans with progress, drafts, latest run
POST  /api/courses/{code}/improvement/draft   start the agent on one class (202)
PATCH /api/improvement-plans/{id}             complete or retire, with an outcome
```

---

## Study plans for one student

A support plan routes a student to a person. A study plan says what that
student actually does, session by session, in one class. The **study plan
agent** drafts it from every past-due assignment, and a person adopts it from
the student's record under **Study plans**.

**What exactly they struggle on** (`app/study_plans.py`). The reading sets each
strand and each kind of work against the class average, and keeps *missing*
separate from *wrong*. Its findings:

| Finding | Means | The plan should |
|---|---|---|
| `strand-gap` | weak on a strand the class is fine on | redo that strand with worked examples |
| `strand-missing` | strand is low only because pieces were never handed in | hand them in, not reteach |
| `class-gap` | the whole class is weak there too | keep it short, ask the teacher for a reteach |
| `tests-below-practice` | tests and quizzes 10+ points under homework, labs, projects | timed practice |
| `missing-work` | assignments not handed in, by id | list them to catch up |
| `sliding` / `declining` | a strand's latest piece, or the class overall, dropping | review before new work |

**Checks on a draft.** The same pattern as class plans. A draft goes back to the
model with what to fix if:
- a percentage isn't in the reading
- an "N of M" count belongs to a different strand or kind of work
- a strand isn't one the class assesses
- a session lacks a duration or never names a focus strand
- a catch-up id isn't really missing
- missing work or a test gap has no matching session

Adopting keeps the reading as a baseline. Progress then shows the class grade,
each focus strand and the missing count against it.

Measured on qwen3:4b, for S-1507 in MAT-150: one scoped run, 164 s, zero tool
errors. The first draft passed every check: all three missing assignments by id,
real figures, four timed sessions. Its weak points: it put every session in
week 1, and it still scheduled relearning on a strand marked `strand-missing`.
Read the draft before adopting it.

API: `GET /api/students/{sid}/study`, `GET /api/students/{sid}/classes/{code}/work`,
`POST /api/students/{sid}/classes/{code}/study-plan/draft`, `PATCH /api/study-plans/{id}`.

## Reading documents about a student

Open any student's record and upload a teacher note, report card, assessment or
piece of work (PDF, Word or text). The local model reads it in the background —
about two minutes for a page — and returns specific needs and strengths, each
with a support plan one click away.

```bash
.venv/bin/python backend/samples/make_samples.py   # a fictional note about Talia Barnard, in .txt/.docx/.pdf
```

A 4B model reading prose will invent things, so nothing it finds is shown until it
has passed three deterministic checks:

1. **It must quote the document.** Every finding carries a verbatim quotation, and
   the quotation must actually occur in the extracted text. Case, curly quotes and
   line breaks are forgiven; paraphrase is not. An invented need has nothing to quote.
2. **It may not diagnose.** "Finds it hard to settle into written work" is something
   a support office can act on. "Has ADHD" is not this tool's to say; a finding that
   names a condition is withheld with a notice to route it to the right staff.
3. **The gradebook check is independent.** The model never sees the student's grades,
   so it can't parrot them back. Corroboration is computed afterwards and shown as
   *agrees*, *disagrees* or *mixed* — disagreement is worth a look too. Severity is
   raised when the gradebook shows a need is worse than the model rated it
   (observed: "low" for a strand the student scores 13% on), and never lowered.

Withheld claims stay visible with the reason, alongside the full text that was read.

On the sample note the model found five things — word problems, missing algebra
work, Monday absences, photography, narrative writing — every quote verified and
every one matched by the gradebook. It did not turn the parent's question about
ADHD into a finding, and did not attribute another student's habits to Talia.

**Limits.** Scans and photos can't be read: no vision model is installed, and a PDF
with no text layer is refused with that explanation. Only extracted text is stored,
never the file; deleting a document removes everything that was read. Documents
longer than about 100,000 characters are refused — upload the relevant section.

### The context window, and a correction to how agents are run

Ollama runs qwen3:4b at a **4,096-token** window unless told otherwise — not the
262k the model supports — and input past the window is cut to about half of it
**with no error**. Measured: a 50,000-character document arrived as 2,050 tokens.
Every request now sets `num_ctx` (16,384 by default, `HR_OLLAMA_NUM_CTX`), refuses
input that cannot fit before sending it, and flags replies whose reported token
count shows they were cut. Documents are split on paragraph boundaries into parts
well inside the window. This applies to the agent fleet too; its runs had not yet
been observed overflowing, but longer ones could have, silently.

---

## The stockroom

The Stockroom tab covers what the school holds: on-hand counts, reorder points,
par levels, suppliers, and the open requisition grouped the way it gets sent —
one list per supplier.

Two details do the work. Every item is linked to the classes that consume it, so
each row carries **how many students depend on it**, and a shortage is ranked by
who it affects rather than by how empty the shelf is. And a **physical count** is
a different operation from nudging a number: `POST /inventory/{sku}/count`
replaces the running total and stamps the date, `PATCH` does not — the difference
between "we think there are six" and "I counted six this morning".

`app/stock.py` holds the one definition of what "low" means. The API, the
interface and the stockroom agent all read it, because three copies would drift,
and an agent proposing an order for something the screen calls healthy is worse
than either being wrong on its own. A test asserts the agent's view and the API's
view agree.

```
critical       at or below 55% of the reorder point — nearly out
below reorder  at or below the reorder point — the flag that triggers ordering
watch          within 25% above the reorder point — heading that way
stocked        everything else
```

---

## The agent fleet (local, via Ollama)

Three agents, one domain each, running entirely on the machine through Ollama.
Local inference is the point rather than a cost saving: **student records never
leave the building**, so the question of whether a school may send a child's
grades to a third-party API does not arise.

| Agent | Owns | Can propose |
|---|---|---|
| **Registrar** | Sections, rooms, periods, capacity, waitlists | Open a section · change capacity |
| **Stockroom** | Inventory, reorder points, what classes consume | Order stock · change a reorder point |
| **Student support** | Who is struggling, on what | Open a support plan |

### Agents propose; they never write

An agent has read tools for its own corner of the school and `propose_*` tools
that record an intent. Nothing reaches the database until a person approves it,
and approval runs deterministic code in `app/ai/executor.py` that **re-validates
against current state** — a seat that filled or a plan opened since the proposal
was made is refused, not forced through.

This boundary is what makes a 4B model safe to point at a school's records. In
testing the model hallucinated a SKU (`MAT-ALG-101`) and invented an enrolment
count. Neither reached the database: the proposal tool rejected the unknown SKU
with a message telling it how to recover, and it corrected itself on the next
step.

### What the model can and cannot do, measured

`ollama show` is the gate: an agent needs the `tools` capability.

| Model | Capabilities | Usable as an agent |
|---|---|---|
| `gemma3:1b` | `completion` | **No** — cannot call tools at any prompt |
| `qwen3:4b` | `completion`, `tools`, `thinking` | Yes |

Four behaviours were measured against qwen3:4b rather than assumed, and each one
is load-bearing in the code:

1. **`think: true` is required, not an optimisation.** With thinking disabled the
   model writes its reasoning into `content` and emits *no tool call at all*.
   With it enabled, reasoning goes to a separate field, `content` comes back
   clean, and the call fires — and it is *faster* (3.0s vs 4.5s).
2. **It gets arguments wrong.** Observed: `list_items_for_course({"category":
   "All"})` — the wrong parameter entirely. Every call is schema-checked and a
   failure is returned as a `tool` message naming what was wrong and what the
   tool expects, so the model repairs it instead of the run dying.
3. **It describes actions instead of taking them.** Left alone it writes "I
   propose ordering X and Y" and stops, having recorded nothing. Two defences: a
   **seeded opening read** (the runner performs the first query itself and feeds
   the result in, so the model cannot open by inventing data) and a **nudge** when
   a turn ends with prose and no proposals.
4. **It sometimes writes the tool call as prose JSON**, occasionally with a stray
   `</think>`. Recovered by a fallback parser and flagged in the transcript.

As a backstop, a run that still ends with no proposals gets a **harvest** step:
one more call with Ollama's constrained JSON decoding (`format` = a schema), so
the last question is "fill in this shape", not "remember to call a tool". Every
harvested entry is replayed through the same tool handlers, so all the guardrails
still apply.

### Runs are slow, and that is fine

A run is 90–180 seconds on this hardware. Agent runs are therefore background
jobs with a run record and polling, never a blocking request, and they are capped
by steps (`HR_AGENT_MAX_STEPS`) and wall clock (`HR_AGENT_MAX_SECONDS`). The
natural framing is a sweep you kick off, not a chat you wait on.

### Every run keeps its whole transcript

Because the model is unreliable, the only basis for trusting a proposal is being
able to read exactly what happened: each step, each tool call and its arguments,
each rejection and why, and what the agent concluded. The Agents tab shows all of
it, including which calls were repaired and whether a nudge or the harvest step
was needed.

### Where the fleet appears

The home page carries the three agents and anything they are waiting on you to
approve. Each card has a prompt box: type a task in your own words, or leave it
blank to run the sweep shown as the placeholder. ⌘/Ctrl+Enter runs it. The
**Agents** tab is the same fleet plus the run history and full transcripts.

A typed prompt genuinely steers the run. Told *"only look at Science Lab items,
ignore every other category"*, the stockroom agent saw all ten low items in its
opening read — graphing calculators among them, the worst shortage in the school —
and proposed only the two Science Lab ones.

Both render the same components over one shared state hook (`components/fleet.tsx`),
so they cannot drift or poll twice. Approving anywhere refreshes the counts that
depend on it — approving a support plan moves the Support plans badge on the spot,
rather than leaving it stale until you navigate.

### Running the fleet

```bash
ollama serve                 # if it is not already running
ollama pull qwen3:4b         # the tool-capable model
./dev.sh                     # → http://localhost:5174/#/agents
```

Point it at a different model with `HR_OLLAMA_MODEL` (and `HR_OLLAMA_URL` for a
remote Ollama). If the model cannot call tools, the fleet page says so and
disables the run buttons rather than failing at run time.

A bigger tool-capable model is the single highest-leverage upgrade here — the
guardrails stay the same, the proposals just get better. Nothing in the
architecture assumes a small model; it only assumes an unreliable one.

### Tests

The agent layer is covered without ever calling Ollama: argument validation and
its repair messages, the refusal of hallucinated identifiers, the proposal
boundary (a test asserts no tool mutates the database), the executor's staleness
checks, and the routes' behaviour when the model cannot call tools. The model is
the one part that cannot be asserted on, so everything around it is.

---

## The general manager

The **General manager** panel sits at the top of the home page and the Agents tab.
It does two things, and deliberately has no propose_ tools for either.

**It answers questions about the school.** Its read tool is a briefing computed
in `app/school_briefing.py` from the same modules every screen uses — student
bands, class averages and skill gaps, class demand, the stockroom, the budget,
and proposals waiting. A 4B model asked to summarise raw tables drops and invents
figures; handed a correct digest, it quotes it. The panel also shows the
briefing's "needs attention now" lines directly, with no model involved.

**It puts the other agents to work.** `dispatch_agent` starts a specialist with a
task the manager writes, naming the students, classes, items or budget lines to
look at. That needs no approval, because a specialist can itself only propose:
the manager changes what gets looked at, never what gets done. Dispatched runs
queue and start one at a time after current work, since Ollama serves one model;
the queue is rebuilt from `queued` rows if the server restarts. At most three
dispatches per run, never itself, never an agent that is already busy.

On its first live runs it answered "how is the school doing?" from the briefing
with every figure correct, and asked to get the team working, dispatched
support, classes and finance — each with a task naming the actual students,
classes and budget lines behind it.

---

## Registrar console (the Artifact)

**Live page:** https://claude.ai/code/artifact/a9dc09a4-bc24-446a-bc7b-0206130573b5

`demo/console.html` is a complete application published as a Claude Artifact. Records
live in the artifact's shared document store, so everyone with the link sees the
same numbers and each other's edits as they happen.

**Inventory** — 24 stockroom items with counts, reorder points and par levels,
each linked to the classes that consume it, so a surge in demand for Forensic
Science surfaces the fingerprint kits before the class runs short.

**Registration** — 14 sections with rosters, caps and ordered waitlists. A full
class waitlists the next student rather than refusing them, and seats are handed
out under a short lease so two staff registering at once cannot both claim the
last one.

**Demand & promotion** — a published demand index driving what earns another
section or a bulletin slot, plus an initiatives board that moves student requests
from proposed to piloting to a real course code.

### Running the console on localhost

```bash
node demo/gen_seed.js
node demo/dev-server.js     # → http://localhost:5173
```

A plain static server would render the layout with no data: the page reaches its
records through `window.claude`, which exists only inside the Claude viewer.
`dev-server.js` composes the viewer's head/body skeleton, a `localStorage`-backed
stand-in for that store, and `console.html` unmodified. Run
`resetRegistrarData()` in the devtools console to reload the seed.

---

## Limits worth knowing

- **The agents are advisory.** They cannot change a record. Every proposal is
  applied by deterministic code after a person approves it, and a small local
  model will sometimes propose something silly — which is why the transcript and
  the evidence sit next to every proposal.
- **The registrar console has no accounts.** The support app requires sign-in,
  roles and an audit log (see *Accounts, roles and the audit log*). The Artifact
  console does not, and is a demo.
- **The indices are heuristics, not assessments.** They rank attention; they do
  not diagnose. Every number is reported with the reasons behind it precisely so
  a person can overrule it.
- **The data is invented.** Halverson Ridge, its students and its staff are
  fictional, generated deterministically by `demo/gen_seed.js` and `backend/seed.py`.
- **The clock is pinned** to 2026-09-12 (`HR_TODAY`) so "missing work", trends and
  attendance rates stay stable whenever the app is run.
- An artifact that declares a shared store is organization-internal and cannot be
  shared by public link.
