# Optional modules

The product is the student support workflow. These modules sit beside it and are
**off unless `HR_MODULES` lists them** (comma-separated, or `all`). A module that
is off has no screens, no routes (they return `404`), no agents and no
proposals, and its permissions are removed from every role.

| Module | Adds | Used by |
|---|---|---|
| `registrar` | class demand, opening classes and sections, the registrar agent | registrar |
| `stockroom` | inventory, requisitions, the stockroom agent, supplies on the class page | business office |
| `finance` | the budget, transfers and revisions, the finance agent | business office |
| `manager` | the general manager agent | administrators |

The demo (`dev.sh`) and the test suite run with `HR_MODULES=all`.

- [Registrar: class demand and opening classes](#registrar-class-demand-and-opening-classes)
- [Stockroom](#stockroom)
- [Finance](#finance)
- [General manager](#general-manager)
- [The course catalog](#the-course-catalog)
- [The registrar console prototype](#the-registrar-console-prototype)

## Registrar: class demand and opening classes

The **Class demand** tab ranks every class by a published demand index:

```
demand = 100 × (0.40·seats filled + 0.35·waitlist÷capacity + 0.25·signups in 2 wk÷(capacity×0.6))
over-subscribed 70+ · high demand 52+ · healthy 32+ · seats to fill below 32
```

Demand is pooled across a class's sections (`MAT-150`, `MAT-150.B`, …), so opening
a section that absorbs the waitlist makes the class read as relieved. Each class
gets a suggested action: open a section, add seats, promote it, or review it for
next term.

**New class** and **Open a section** refuse a room or teacher already booked in
that period. `app/timetable.py` holds that rule, and the registrar agent's
approved proposals go through the same code. A new section copies the catalog
entry and takes students from the class's waitlist in the order they joined.

```
GET  /api/courses/demand             ranked classes, with the formula and bands
GET  /api/courses/openings?period=3  rooms and teachers free that period
POST /api/courses                    open a new class
POST /api/courses/{code}/sections    open another section, optionally moving the waitlist
```

## Stockroom

On-hand counts, reorder points, par levels, suppliers, and the open requisition
grouped the way it is sent: one list per supplier.

- Every item is linked to the classes that consume it, so a shortage is ranked by
  **how many students depend on it** rather than by how empty the shelf is.
- A **physical count** (`POST /api/inventory/{sku}/count`) replaces the running
  total and stamps the date. Editing a number (`PATCH`) does not. That is the
  difference between "we think there are six" and "I counted six this morning".
- `app/stock.py` holds the one definition of "low", shared by the API, the
  interface and the agent. A test asserts they agree.

```
critical       at or below 55% of the reorder point
below reorder  at or below the reorder point
watch          within 25% above the reorder point
stocked        everything else
```

## Finance

The budget, line by line: allocation, transfers, spending, and **committed**
money (the stockroom's open requisition, costed to par and charged to the
department that buys it). Each line is judged against how much of the year has
passed (`app/finance.py`):

```
over budget      spent + committed exceed the budget
at risk          the year-end projection exceeds the budget
under-spending   under 35% of the expected pace, after the first six weeks
on track         everything else
```

One-time purchases are kept out of the projected pace, so a front-loaded line (an
August laptop refresh) does not read as a runaway. Two rules flag charges for
review: the same vendor and amount twice within ten days, and one charge over a
quarter of its line.

**Allocations are never edited.**

- A **budget revision** moves money across several lines and is approved as one
  package. It is judged on its combined effect: a line giving to two others
  must stay on track after both, no line receives more than 125% of its need,
  and no line both gives and receives.
- **Opening a line** creates it at zero and funds it with a transfer from a line
  with room.

Every transfer records who approved it. The finance agent proposes revisions,
new lines and holds on suspicious charges, and any dollar figure it cites must
match the budget data.

```
GET  /api/finance/needs       lines needing money, and lines that can give
POST /api/finance/lines       open a line, funded by a transfer
POST /api/finance/revisions   several transfers, validated and applied together
```

The demo ledger is fictional (`app/finance_seed.py`).

## General manager

See [AI agents](ai-agents.md#the-general-manager).

## The course catalog

Every demo section is a course from a real *2026–27 Upper School Course of
Study* (`backend/app/catalog.py`). Each section carries the catalog title,
department, length, credits, prerequisite, UC-approval flag and page number,
shown on the class page. Courses the catalog marks ungraded do not count toward
students' indices.

## The registrar console prototype

`demo/console.html` is an earlier, standalone registrar console published as a
Claude Artifact, with inventory, registration with waitlists and seat leases, and
a demand and promotion board. It keeps its own records in the Artifact store and
has no accounts. It is a prototype; the application's backend is the source of
truth.

```bash
node demo/gen_seed.js
node demo/dev-server.js     # http://localhost:5173
```

`dev-server.js` supplies a `localStorage`-backed stand-in for the Artifact store.
Run `resetRegistrarData()` in the browser console to reload the seed.
