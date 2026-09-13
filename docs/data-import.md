# Importing records

The demo seed is fictional. A real school's records come from its student
information system (SIS) as a **OneRoster 1.1 CSV** export, which PowerSchool,
Infinite Campus, Aeries, Skyward and Clever all produce.

## Files

| File | Required | Becomes |
|---|---|---|
| `users.csv` | yes | students (ID from `identifier`, else `username`), their first guardian, teachers |
| `classes.csv` | yes | sections: `classCode`, the first of `periods`, `location` as the room |
| `enrollments.csv` | yes | rosters; the `primary` teacher names the section's teacher |
| `courses.csv` | no | course titles and subjects (the department) |
| `academicSessions.csv` | no | term names |
| `categories.csv`, `lineItems.csv` | no | assessments; the kind (test, quiz, lab, project, homework) comes from the title, then the category |
| `results.csv` | no | scores: `not submitted` is missing work, `exempt` counts as neither missing nor graded |
| `attendance.csv` | no | not part of OneRoster: `userSourcedId,date,status` with status `present`, `absent`, `tardy` or `excused` |

Rows with `status` `tobedeleted` are skipped.

> **Add a `skill` column to `lineItems.csv`.** OneRoster has no skill tag on an
> assessment, and "what are they struggling on" needs one. Without it, the import
> warns and groups those pieces under `general`.

## Check, then import

From the Admin tab (**Import records**, administrators only), upload the export
as a zip. Or use the command line on the server:

```bash
python -m app.cli import-oneroster export.zip             # check only
python -m app.cli import-oneroster export.zip --apply     # import
python -m app.cli import-oneroster export/ --apply --create-teacher-accounts
```

**Nothing is written until everything checks out.** Every file is read and every
reference resolved before any change is made. A missing column, an unknown
student, a score above the maximum, a duplicate ID or an unreadable date refuses
the whole import. Each error names the file and line.

**A check is the real import, rolled back.** It runs inside a transaction,
reports exactly what would be created, updated and dropped, and then runs the
timetable checks on the result:

- rooms or teachers booked twice in one period
- students enrolled in two classes in one period
- classes with no teacher, or no assessments
- students with no enrollments
- assessments due in the future (they will not count until then)

## Rules

- **Re-importing is safe.** Students match on their ID, classes on their code,
  and assessments on their OneRoster `sourcedId`. Importing the same export twice
  changes nothing.
- **Each class in the file is a full roster.** A student no longer listed in a
  class is marked `dropped`, never deleted.
- **Nothing absent from the file is touched.** That covers students and classes
  not in it, and every plan, document, override and audit entry.
- **Teacher accounts** (`--create-teacher-accounts`, or the checkbox) are created
  from each teacher's email with no password, for sign-in through the school's
  identity provider. They are linked to their sections by name.
- **Limits.** Uploads are capped at 50 MB, and zips at 200 MB uncompressed.
  Import one school at a time.

Applied imports are recorded in the audit log with their counts.

## A minimal export

```csv
# users.csv
sourcedId,status,role,identifier,givenName,familyName,grades,email,agentSourcedIds
u1,active,student,S-1001,Ada,Lovelace,10,,g1
g1,active,parent,,Anne,Lovelace,,anne@example.org,
t1,active,teacher,,Grace,Hopper,,g.hopper@school.edu,

# classes.csv
sourcedId,title,classCode,periods,location
k1,Geometry,MAT-210,3,M-207

# enrollments.csv
sourcedId,classSourcedId,userSourcedId,role,primary
e1,k1,u1,student,false
e2,k1,t1,teacher,true

# lineItems.csv
sourcedId,title,classSourcedId,dueDate,resultValueMax,skill
li1,Proofs quiz,k1,2026-09-04,20,proofs

# results.csv
sourcedId,lineItemSourcedId,studentSourcedId,scoreStatus,score
r1,li1,u1,fully graded,17
```

`backend/tests/test_import.py` has a complete working example of every file.
