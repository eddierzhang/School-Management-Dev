# Halverson Ridge Registrar

A staff console for running a school's term: the stockroom, class registration,
and the demand signals that decide what gets promoted or given another section.

**Live page:** https://claude.ai/code/artifact/a9dc09a4-bc24-446a-bc7b-0206130573b5

This is a working prototype, not a deployed system. There is no server to run and
no build step — `console.html` is the whole application, published as a Claude
Artifact. Records live in the artifact's shared document store, so every person
with the link sees the same numbers and each other's edits as they happen.

## What it does

**Inventory.** 24 stockroom items with on-hand counts, reorder points and par
levels. Each row carries a level meter with a tick at its reorder point, and each
item is linked to the classes that consume it — so a spike in demand for Forensic
Science surfaces the fingerprint kits before the class runs short. Staff adjust
counts inline, record a physical count (which stamps the date), and roll flagged
items into a single requisition grouped by supplier.

**Registration.** 14 sections with rosters, caps and ordered waitlists. A full
class takes the next student onto the waitlist rather than refusing them. Seats
are handed out under a short lease on the class record, so two people registering
at the same moment cannot both claim the last one. From a roster you can drop a
student, move someone off the waitlist, change the cap, or open another section —
which mints a new section letter and moves waiting students across in order.

**Demand & promotion.** One published index per section, from three signals:

    demand = 100 × ( 0.40·seats_filled + 0.35·waitlist÷capacity + 0.25·signups_2wk÷(capacity×0.6) )

High scorers earn a section or a bulletin slot; low scorers get the promotion.
Separately, an initiatives board tracks things students are asking for that are
not classes yet (clubs, programs, extra sections) with their interest counts, and
moves them proposed → piloting → approved → a real course code that appears in
registration. Campaigns record what is being promoted, on which channel, and for
how long.

## Data

Six collections in the artifact's store, 50 documents:

| Path | What it holds |
|---|---|
| `courses/<CODE>` | section, with its roster and waitlist embedded |
| `inventory/<SKU>` | stockroom item, counts and thresholds |
| `initiatives/<ID>` | proposed club, program or section, with interest count |
| `campaigns/<ID>` | a promotion: headline, channel, run window |
| `catalog/students` | the 60-student directory, one document |
| `meta/school`, `meta/activity` | term settings; the last 40 record changes |

Rosters are embedded in the class document rather than split into their own
collection — it keeps a registration to a single leased write, and keeps the
document count far under the store's 5,000 cap.

## Working on it

Edit `console.html` and republish to the same URL. The file is published as
Artifact page content, so it deliberately has no `<!doctype>`, `<html>`, `<head>`
or `<body>` wrapper — those are supplied at publish time.

Seed data is generated, never hardcoded in the page: `node gen_seed.js` writes one
JSON document per record into `seed/` plus a `batch.json` manifest, which is
loaded into the store in a single 50-write batch. Re-running it is deterministic. The page renders an explicit "not connected" state rather than
falling back to sample data, so nothing on screen is ever mistaken for real
records.

## Limits worth knowing

- Anyone who can open the page can edit everything. There are no roles, and the
  console assumes office staff. Student-facing self-registration would need real
  accounts and permissions.
- A page that declares a shared store is organization-internal — it cannot be
  shared publicly by link.
- Interest signals on initiatives are logged by staff, not collected from
  students directly.
- Weekly signup history is seeded, not accumulated; live registrations increment
  the current week only.
