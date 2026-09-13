# The support engine

How the platform decides who needs attention, on what, and what to do about
it. Every figure described here is computed from the gradebook when a page
loads. Nothing is cached, so a grade entered through the API moves the rankings
on the next request.

- [What it answers](#what-it-answers)
- [The indices](#the-indices)
- [Recommendations](#recommendations)
- [History](#history)
- [Overruling the index](#overruling-the-index)
- [Class improvement plans](#class-improvement-plans)
- [Study plans](#study-plans)
- [Reading documents](#reading-documents)
- [Schedules](#schedules)

## What it answers

**Who is struggling.** A struggle index per student, built from four named
factors rather than a single grade average.

**Who is excelling.** A separate index on its own axis. A student failing maths
and top of the class in science carries both; averaging the two into one number
is precisely how such a student gets missed.

**Every student in one place.** The Students tab lists the whole school by band
(*needs a plan*, *watch*, *steady*, *excelling*), each student with a single
**standing** score (excelling index − struggle index, −100 to +100), their
lowest and strongest class, absence and open plans. Netting the two indices can
hide a student with a real concern and a real strength near zero. So anyone with
struggle ≥ 35 *and* excelling ≥ 60 is marked **mixed**, and bands still come
from the two indices underneath.

**What they struggle on.** Every graded piece is tagged with the skill strand it
tests, so mastery rolls up per topic. The system says *word problems, not
graphing*: the difference between "behind in maths" and a lesson plan.

**What to reteach.** The same strand data aggregated per class. One student below
on a strand is a referral; half the class below on it is a lesson to run again.

## The indices

```
struggle = 0.55·low mastery + 0.20·decline + 0.15·unsubmitted work + 0.10·absence
excel    = 0.55·high mastery + 0.20·improvement + 0.15·completion + 0.10·consistency
```

Each is computed per class. The student's indices then take the worst (or best)
class as the level, and the other classes add urgency into the remaining
headroom:

```
student_index = worst + breadth × (100 − worst) × mean(others) ÷ 100
```

Averaging across classes was wrong twice over. It hid a student failing one
subject behind five they were fine in, and it penalized students who take more
classes, since the same failing grade diluted further with every extra course.

| Band | Rule |
|---|---|
| Needs a plan | struggle ≥ 55 |
| Watch | struggle ≥ 35 |
| Excelling | excel ≥ 70 (and not flagged) |
| Steady | everything else |

The weights, normalization scales and band cut-offs sit together at the top of
`backend/app/analytics.py`, separate from the policy thresholds in configuration
(`HR_SUPPORT_THRESHOLD`, `HR_CONCERN_FLOOR`). **A real school should calibrate
the bands against its own grade distribution before trusting the counts.**

Details that matter:

- **Missing work** that is past due counts as zero toward mastery *and* is
  tracked separately. "Did not submit" and "submitted and scored badly" need
  different responses.
- **Exempt work** (excused) counts as neither missing nor graded.
- **Ungraded courses** (P.E. in the demo catalog) still show their scores on the
  class page, but do not move a student's indices, reasons or recommended plans.
- **Teachers** see these figures only for students in their own sections,
  including the summary counts.

Two regression tests guard real calibration bugs. One was an excelling index
scaled so a near-perfect record could not reach its own cut-off. The other was
a weighting that capped mastery below the "needs a plan" threshold, so a student
at 48% with perfect attendance read as "steady".

## Recommendations

Rules, in priority order, each naming an action, a reason and a suggested owner:

| Situation | Recommendation |
|---|---|
| Absent 12%+ of days | Attendance plan with a family call |
| Slipping in two or more unrelated classes | Counselor check-in this week |
| 25%+ of work missing in a class | Homework recovery block for that class |
| Failing a class with work handed in | Tutoring on the weakest strand |
| Just under the support line | Two-week progress check |
| Excelling in a class | A seat in a related course with room, or extension work |

Opening a plan turns a computed recommendation into something a person owns.

## History

The indices are recomputed on every read, which keeps them honest but forgets
yesterday. **Snapshots** record each student's indices, computed band, attendance
and open plans once a day. The worker takes them after `HR_SNAPSHOT_HOUR`, or
you can run `python -m app.cli snapshot` by hand.

The student record charts the struggle and excelling indices over the term, with
plans and overrides marked on the date they happened, so you can see whether a
plan moved anything. The demo seed backfills a reading each Friday from week
three, read from the gradebook as it stood then.

`GET /api/students/{sid}/history`

## Overruling the index

A counselor can record one of two things about a student, always with a reason
and an end date no more than 90 days away:

- **The concern is known and in hand.** The band stays, but the student stops
  counting as "needs a plan and has none". They leave the to-do watchlist
  (`include_acknowledged=true` brings them back) and the support agent's sweep.
- **The index is wrong about this student.** The band is replaced everywhere:
  lists, counts, filters and agents.

The computed band is always shown beside the override. Overrides lapse on their
end date so someone looks again, a new one replaces the old, and every change is
in the audit log. Snapshots record the computed band, not the override.

`POST /api/students/{sid}/overrides` · `DELETE /api/students/{sid}/overrides/{id}`

## Class improvement plans

A support plan is for one student; a class plan is for the course. Use one when
half the room is below the line on one strand, or a sixth of the work never
comes in.

**What the numbers say** is deterministic (`app/class_plans.py`). It covers class
average, work handed in, trend, every strand, and each kind of work, and gives
the class a status (*needs a plan*, *worth watching*, *doing well*) with named
issues.

**Drafting a plan** starts the class improvement agent on that one class. The
draft has a diagnosis, one or two focus strands, two to five actions and a
measurable four-week goal. Adopting it records today's numbers as the baseline,
and the plan then shows **at adoption / now / change** until it is completed or
retired.

A draft goes back to the model, with the reason, when it:

- cites a percentage the data does not contain (targets such as "to 75%" are allowed)
- miscounts. For example, "15 of 28 below the line" was the word-problems strand, not the class.
- ignores missing work: reteaching does not fix work that never arrives
- names a strand the course does not teach, has vague actions or an unmeasurable
  goal, or duplicates an active plan or waiting draft

```
GET   /api/improvement                        every class, neediest first
GET   /api/courses/{code}/improvement         snapshot, plans with progress, drafts, latest run
POST  /api/courses/{code}/improvement/draft   start the agent on one class (202)
PATCH /api/improvement-plans/{id}             complete or retire, with an outcome
```

## Study plans

A support plan routes a student to a person. A study plan says what the student
actually does, session by session, in one class. The study plan agent drafts it
from every past-due assignment, and a counselor adopts it from the student's
record.

The reading (`app/study_plans.py`) sets each strand and each kind of work
against the class average, and keeps *missing* separate from *wrong*:

| Finding | Means | The plan should |
|---|---|---|
| `strand-gap` | weak on a strand the class is fine on | redo that strand with worked examples |
| `strand-missing` | low only because pieces were never handed in | hand them in, not reteach |
| `class-gap` | the whole class is weak there too | keep it short; ask the teacher for a reteach |
| `tests-below-practice` | tests 10+ points under homework and labs | timed practice |
| `missing-work` | assignments not handed in, by id | list them to catch up |
| `sliding` / `declining` | a strand or the class trending down | review before new work |

A draft is sent back if a percentage is not in the reading, if a count belongs to
a different strand, if a strand is not assessed, if a session lacks a duration
or focus, if a catch-up item is not really missing, or if missing work or a test
gap has no matching session. Adopting keeps the reading as a baseline.

Teachers can request a draft for students in their own class; adopting it needs
a counselor.

## Reading documents

Upload a teacher note, report card, assessment or piece of work (PDF, Word or
text) to a student's record. The worker reads it with the local model, about
two minutes for a page, and returns specific needs and strengths, each with a
support plan one click away.

A small model reading prose will invent things, so nothing it finds is shown
until it passes three deterministic checks:

1. **It must quote the document.** Every finding carries a verbatim quotation
   that must occur in the extracted text. Case, curly quotes and line breaks are
   forgiven; paraphrase is not.
2. **It may not diagnose.** "Finds it hard to settle into written work" is
   actionable. "Has ADHD" is not this tool's to say, so a finding that names a
   condition is withheld with a notice to route it to the right staff.
3. **The gradebook check is independent.** The model never sees the student's
   grades. Corroboration is computed afterwards as *agrees*, *disagrees* or
   *mixed*. Severity can be raised when the gradebook shows a need is worse,
   and is never lowered.

Withheld claims stay visible with the reason. Only the extracted text is stored,
never the file, and deleting a document removes everything that was read. Scans
without a text layer are refused, as are documents over about 100,000
characters.

**The context window.** Ollama runs models at a 4,096-token window unless told
otherwise, and silently cuts input past it: a 50,000-character document arrived
as 2,050 tokens. Every request therefore sets `num_ctx` (`HR_OLLAMA_NUM_CTX`,
16,384 by default), refuses input that cannot fit, and flags replies whose token
count shows they were cut. Documents are split on paragraph boundaries into
parts well inside the window.

A fictional sample note lives in `backend/samples/`
(`python backend/samples/make_samples.py` regenerates it).

## Schedules

The Schedule tab is the master timetable: every running section by period, with
rows by room or by teacher. Pick a student to see their day: enrolled classes,
free periods, and waitlisted classes. The same timetable appears in every
student's record.

Conflicts are shown, never quietly resolved (`app/schedule.py`):

- **Timetable clashes:** a room or teacher booked into two sections in one period.
- **Student clashes:** a student enrolled in two classes in the same period.

The demo term deliberately contains student clashes, and the import runs the
same checks on real data.

```
GET /api/schedule                  sections by period, rooms, teachers, both kinds of clash
GET /api/students/{sid}/schedule   one student's day
```
