# Halverson Ridge — school management

Software for running a school term, in two halves that share one fictional
school, one roster, and one visual identity.

| | What it does | How it runs |
|---|---|---|
| **Registrar console** | Stockroom inventory, class registration with waitlists, and the demand signals behind what gets promoted | A published Claude Artifact — no server |
| **Student support** | Who is struggling, who is excelling, on which topics, and what to do about it | FastAPI backend + React frontend |
| **Agent fleet** | Three local AI agents — registrar, stockroom, student support — that review their domain and propose changes for approval | Ollama, on this machine |

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

**What the stockroom holds** — 24 items with counts, reorder points and par
levels, each tied to the classes that consume it. A class filling up shows here
before it runs short, and the number of students depending on an item is what
ranks a shortage against the others.

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
    routers/         students · courses · support · interventions · scores · inventory ·
                     agents · meta
    stock.py         the one definition of "low", shared by the API and the agent
  seed.py            generates the gradebook from the shared roster
  tests/
frontend/
  src/
    views/           overview · struggling · excelling · classes · strands · plans ·
                     stockroom · agents
    components/      charts, student drawer, plan dialog, UI primitives
    api.ts           typed client, one function per endpoint
```

---

## The course catalog

The 14 running sections are mapped to real courses in the *2026-27 Upper School
Course of Study* (`backend/app/catalog.py`). Codes, teachers, rooms and periods
are unchanged; each section now carries the catalog title, department, length,
credits, prerequisite, UC-approval flag and page number, shown on the class page.

Nine map directly. Five had no counterpart and use the nearest real course:
Esports & Game Design → Digital World, Model UN → Introduction to Speech and
Debate, Rock Climbing → Personal Fitness, Culinary Basics → Biotechnology, Life
Science → Biology. Skill strands were renamed position by position, so existing
scores carry over. Three stockroom items (climbing harness, kitchen apron, chef
knife) no longer belong to any class and are unlinked.

Known mismatches: the catalog is for grades 9–12 and this school's students are
6–8, so several prerequisites (Biology needs Chemistry) would not be met; and the
catalog says P.E. is ungraded, while the gradebook still scores Personal Fitness.

---

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

- **The agents are advisory.** They cannot change a record. Every proposal is
  applied by deterministic code after a person approves it, and a small local
  model will sometimes propose something silly — which is why the transcript and
  the evidence sit next to every proposal.
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
