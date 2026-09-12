"""FY2027 budget and the first ten weeks of spending — FICTIONAL.

Built with specific situations in it, so the finance screen and agent have real
things to find rather than a uniformly healthy ledger:

    PE-EQP   over budget — forty climbing harnesses bought in August for a
             climbing course that is now Personal Fitness
    SPD-TRV  at risk — early tournament travel on pace to overrun by June
    FAC-MNT  at risk, because of a duplicated HVAC invoice (same reference, twice)
    PFA-MUS  one charge over a quarter of the line (a piano rebuild)
    ART-STU  under-spending — studio supplies barely touched ten weeks in
    CSC-TEC  front-loaded but on track: the laptop refresh is marked one-time

    python -m app.finance_seed      # adds finance tables to an existing database
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

LINES = [
    # code,     name,                                   department,                      category,     allocated, owner
    ("SCI-LAB", "Science lab supplies",                 "Science",                       "Supplies",     18000, "R. Okonkwo"),
    ("SCI-EQP", "Science equipment",                    "Science",                       "Equipment",    12000, "R. Okonkwo"),
    ("MAT-INS", "Mathematics instructional materials",  "Mathematics",                   "Supplies",      4500, "S. Frankel"),
    ("CSC-TEC", "Computer lab technology and software", "Computer Science",              "Technology",   22000, "J. Whitfield"),
    ("CSC-ROB", "Robotics equipment",                   "Computer Science",              "Equipment",     9000, "M. Delacroix"),
    ("ENG-INS", "English instructional materials",      "English",                       "Supplies",      3500, "T. Ellery"),
    ("MCL-INS", "Language materials",                   "Modern and Classical Languages", "Supplies",     3000, "C. Quintero"),
    ("ART-STU", "Visual arts studio supplies",          "Visual Arts",                   "Supplies",      8500, "L. Moreau"),
    ("PFA-MUS", "Music and ensembles",                  "Performing Arts",               "Programs",      7000, "P. Sandoval"),
    ("PE-EQP",  "Physical education equipment",         "Physical Education",            "Equipment",     5000, "D. Boone"),
    ("SPD-TRV", "Speech and debate tournaments",        "Speech and Debate",             "Travel",       14000, "T. Ellery"),
    ("SUP-TUT", "Tutoring and intervention",            "Student Support",               "Programs",     20000, "Support office"),
    ("FAC-MNT", "Facilities maintenance",               "Facilities and Operations",     "Maintenance",  30000, "Facilities office"),
    ("PRO-DEV", "Professional development",             "Administration",                "Staff",        15000, "Principal's office"),
]

T = date
TRANSACTIONS = [
    # line,     posted,          vendor,                        description,                                  amount,  reference,   one_time
    ("SCI-LAB", T(2026, 8, 14), "Carolina Biological",          "Biology lab consumables, fall",               1380.00, "CB-44102", False),
    ("SCI-LAB", T(2026, 9, 2),  "Flinn Scientific",             "Reagents and indicator solutions",             940.50, "FS-8813",  False),
    ("SCI-LAB", T(2026, 9, 9),  "Sirchie",                      "Forensic hair and fiber sample kits",          629.00, "SR-2207",  False),
    ("SCI-EQP", T(2026, 8, 20), "Precision Microscope Service", "Annual microscope service",                   1200.00, "PMS-310",  True),
    ("MAT-INS", T(2026, 8, 18), "Texas Instruments",            "Replacement graphing calculators (4)",         498.00, "TI-5530",  False),
    ("MAT-INS", T(2026, 9, 4),  "Desmos Classroom",             "Printed activity packets",                     282.00, "DC-1190",  False),
    ("CSC-TEC", T(2026, 8, 6),  "CDW Education",                "Chromebook cart refresh (30 units)",         11480.00, "CDW-77120", True),
    ("CSC-TEC", T(2026, 8, 25), "JetBrains",                    "Educational licence renewals",                 620.00, "JB-0921",  False),
    ("CSC-TEC", T(2026, 9, 8),  "Logitech for Education",       "Headset replacements",                         620.00, "LG-4410",  False),
    ("CSC-ROB", T(2026, 8, 27), "VEX Robotics",                 "Motor and sensor kits",                       1480.00, "VX-66019", False),
    ("ENG-INS", T(2026, 8, 22), "Penguin Random House",         "Poetry anthology class set",                   410.00, "PRH-2231", False),
    ("MCL-INS", T(2026, 8, 19), "Vista Higher Learning",        "Spanish 1 workbook set",                       520.00, "VHL-7781", False),
    ("ART-STU", T(2026, 9, 5),  "Blick Art Materials",          "Glaze sample set",                             180.00, "BL-30912", False),
    ("PFA-MUS", T(2026, 7, 28), "Bay Area Piano Service",       "Rehearsal room piano rebuild",                2300.00, "BAP-118",  True),
    ("PFA-MUS", T(2026, 9, 3),  "J.W. Pepper",                  "Jazz band charts, fall concert",               420.00, "JWP-55210", False),
    ("PE-EQP",  T(2026, 7, 15), "Vertical Solutions",           "Climbing wall annual inspection",             1850.00, "VS-2026-07", True),
    ("PE-EQP",  T(2026, 8, 12), "Petzl Education",              "Youth climbing harnesses (40)",               2320.00, "PZ-99102", True),
    ("PE-EQP",  T(2026, 9, 1),  "Perform Better",               "Resistance bands and mats",                   1190.00, "PB-40117", False),
    ("SPD-TRV", T(2026, 8, 30), "National Speech & Debate Assn","Chapter membership, annual",                   610.00, "NSDA-26",  True),
    ("SPD-TRV", T(2026, 9, 6),  "Golden Gate Charter",          "Bus, Berkeley invitational",                  1640.00, "GGC-8841", False),
    ("SPD-TRV", T(2026, 9, 10), "Tabroom.com",                  "Tournament entry fees, September",            1150.00, "TAB-1520", False),
    ("SUP-TUT", T(2026, 8, 31), "Bright Path Tutoring",         "Tutoring contract, August hours",             1260.00, "BPT-0831", False),
    ("SUP-TUT", T(2026, 9, 11), "Bright Path Tutoring",         "Tutoring contract, early September hours",    1440.00, "BPT-0911", False),
    ("FAC-MNT", T(2026, 8, 5),  "Allied Plumbing",              "Restroom valve repairs, B wing",               640.00, "AP-3308",  False),
    ("FAC-MNT", T(2026, 8, 28), "Bayside HVAC Services",        "Quarterly HVAC maintenance",                  2480.00, "HV-2291",  False),
    ("FAC-MNT", T(2026, 9, 3),  "Bayside HVAC Services",        "Quarterly HVAC maintenance",                  2480.00, "HV-2291",  False),
    ("FAC-MNT", T(2026, 9, 9),  "Pacific Janitorial Supply",    "Custodial supplies",                          1120.00, "PJS-7710", False),
    ("PRO-DEV", T(2026, 8, 3),  "NCTM",                         "Annual conference registrations (3)",         3900.00, "NCTM-26",  True),
]


# Planned purchases a person has already reviewed. Without this, the large-charge
# rule flags every budgeted one-off alongside the charges that actually need a look.
CLEARED = {
    "CDW-77120": "Approved in the FY2027 technology plan.",
    "NCTM-26": "Approved in the FY2027 professional development plan.",
    "VS-2026-07": "Required annual safety inspection.",
}


def seed_finance(db: Session) -> tuple[int, int]:
    from .models import BudgetLine, Transaction

    if db.query(BudgetLine).count():
        return 0, 0
    lines = {}
    for code, name, dept, cat, allocated, owner in LINES:
        ln = BudgetLine(code=code, name=name, department=dept, category=cat,
                        fiscal_year="FY2027", allocated=float(allocated), owner=owner)
        db.add(ln)
        lines[code] = ln
    db.flush()
    for code, posted, vendor, desc, amount, ref, one_time in TRANSACTIONS:
        db.add(Transaction(line_id=lines[code].id, posted_on=posted, vendor=vendor, description=desc,
                           amount=amount, reference=ref, one_time=one_time,
                           review_status="cleared" if ref in CLEARED else "clear",
                           review_note=CLEARED.get(ref, "")))
    db.commit()
    return len(LINES), len(TRANSACTIONS)


if __name__ == "__main__":
    from .db import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        n_lines, n_txn = seed_finance(s)
        print(f"budget lines {n_lines}  transactions {n_txn}" if n_lines else "Finance records already present.")
    finally:
        s.close()
