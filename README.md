# Halverson Ridge — school management

Software for running a school term, in two halves that share one fictional
school, one roster, and one visual identity.

| | What it does | How it runs |
|---|---|---|
| **Registrar console** | Stockroom inventory, class registration with waitlists, and the demand signals behind what gets promoted | A published Claude Artifact — no server |
| **Student support** | Who is struggling, who is excelling, on which topics, and what to do about it | FastAPI backend + React frontend |

Both describe the same term at Halverson Ridge Middle School: the same 60
students, the same 14 classes, generated once by `gen_seed.js` and loaded into
both halves.

---

## Student support (backend + frontend)

### What it answers

**Who is struggling** — a struggle index per student, built from four named
factors rather than a single grade average.

**Who is excelling** — a separate index on its own axis. A student failing maths
and top of the class in science appears on *both* lists; averaging the two into
one number is precisely how such a student gets missed.

**What they are struggling *on*** — every graded piece is tagged with the strand
it tests, so mastery rolls up per topic. The system says *word problems, not
graphing*, which is the difference between "behind in maths" and a lesson plan.

**What the school should do** — rule-based recommendations that name an action,
a reason and an owner: homework recovery when the problem is submission,
tutoring on a named strand when it is comprehension, a counselor check-in when a
student is sliding across unrelated subjects, an attendance plan when grades are
following absence, and an enrichment placement when there is something to build
on. Opening a plan turns a computed recommendation into something a person owns.

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
node gen_seed.js                                   # the shared roster, once

python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python backend/seed.py           # builds backend/halverson.db

cd frontend && npm install && cd ..
```

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

The URL is the view: `#/watchlist`, `#/classes`, `#/skills`, and
`#/watchlist/S-1507` with one student's record open — so a support office can
bookmark a list or mail a colleague a link to one student.

### Tests

```bash
cd backend && .venv/bin/python -m pytest -q      # 33 tests
cd frontend && npm run typecheck
```

`tests/test_analytics.py` builds a purpose-made record per test, so a failure
names a rule rather than a dataset. Two of those tests are regressions for real
calibration bugs: an `excel_index` scaled so that even a near-perfect record
could not reach its own band cut-off, and a weighting that capped mastery's
contribution below the "needs a plan" threshold, so a student at 48% with perfect
attendance read as "steady".

`tests/test_api.py` runs against its own freshly seeded database, never the dev
one.

### Layout

```
backend/
  app/
    analytics.py     the signal engine — indices, reasons, recommendations, cohort gaps
    models.py        students, courses, enrollments, assessments, scores, attendance, plans
    schemas.py       wire shapes, mirrored by frontend/src/types.ts
    routers/         students · courses · support · interventions · scores · meta
  seed.py            generates the gradebook from the shared roster
  tests/
frontend/
  src/
    views/           overview · struggling · excelling · classes · strands · plans
    components/      charts, student drawer, plan dialog, UI primitives
    api.ts           typed client, one function per endpoint
```

---

## Registrar console (the Artifact)

**Live page:** https://claude.ai/code/artifact/a9dc09a4-bc24-446a-bc7b-0206130573b5

`console.html` is a complete application published as a Claude Artifact. Records
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
node gen_seed.js
node dev-server.js     # → http://localhost:5173
```

A plain static server would render the layout with no data: the page reaches its
records through `window.claude`, which exists only inside the Claude viewer.
`dev-server.js` composes the viewer's head/body skeleton, a `localStorage`-backed
stand-in for that store, and `console.html` unmodified. Run
`resetRegistrarData()` in the devtools console to reload the seed.

---

## Limits worth knowing

- **No authentication anywhere.** Both halves assume office staff on a trusted
  network. The support side handles real student records; putting it in front of
  anyone would need accounts, roles and an audit trail first.
- **The indices are heuristics, not assessments.** They rank attention; they do
  not diagnose. Every number is reported with the reasons behind it precisely so
  a person can overrule it.
- **The data is invented.** Halverson Ridge, its students and its staff are
  fictional, generated deterministically by `gen_seed.js` and `backend/seed.py`.
- **The clock is pinned** to 2026-09-12 (`HR_TODAY`) so "missing work", trends and
  attendance rates stay stable whenever the app is run.
- An artifact that declares a shared store is organization-internal and cannot be
  shared by public link.
