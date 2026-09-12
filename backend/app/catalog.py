"""The 14 running sections, mapped to real courses in the course of study.

Source: *2026-27 Upper School Course of Study* (The Harker School, June 2026).
Page numbers are the printed ones. Section codes, teachers, rooms and periods
are this school's own and did not change; only what each section *is* did.

Five sections had no exact counterpart and were mapped to the nearest real
course — noted in `mapping`:

    Esports & Game Design   → Digital World       (lists "gaming as a learning platform")
    Model UN                → Intro to Speech and Debate (research and argumentation)
    Rock Climbing           → Personal Fitness    (no climbing course in the catalog)
    Culinary Basics         → Biotechnology       (no food course; nearest hands-on lab elective)
    Life Science            → Biology

Skill strands are renamed position by position, so the gradebook's existing
scores carry over to the strand that replaces each one.
"""
from __future__ import annotations

SOURCE = "2026-27 Upper School Course of Study"

CATALOG: dict[str, dict] = {
    "MAT-150": {
        "legacy_title": "Algebra Foundations", "mapping": "direct",
        "title": "Algebra 1", "dept": "Mathematics", "page": 32,
        "length": "year", "credits": 1.0, "prerequisite": "None", "uc_approved": True,
        "description": "Expressions, equations and inequalities, factoring polynomials and systems "
                       "of equations, concluding with the quadratic formula.",
        "skills": ["linear equations", "factoring polynomials", "systems of equations", "word problems"],
        "cohort_gap": "word problems",
    },
    "MAT-210": {
        "legacy_title": "Geometry", "mapping": "direct",
        "title": "Geometry", "dept": "Mathematics", "page": 32,
        "length": "year", "credits": 1.0, "prerequisite": "Algebra 1", "uc_approved": True,
        "description": "Euclidean geometry built on inductive and deductive reasoning: congruence, "
                       "similarity, transformations and written proof.",
        "skills": ["proof writing", "transformations", "congruence and similarity", "constructions"],
        "cohort_gap": "proof writing",
    },
    "SCI-118": {
        "legacy_title": "Life Science", "mapping": "nearest: Life Science has no counterpart; Biology is the grade 11 life-science course",
        "title": "Biology", "dept": "Science", "page": 53,
        "length": "year", "credits": 1.0,
        "prerequisite": "Chemistry, Honors Chemistry or AP Chemistry", "uc_approved": True,
        "description": "Introductory lab science: biochemistry, ecology, cell structure and function, "
                       "and classical genetics.",
        "skills": ["cell structure and function", "ecology", "classical genetics", "biochemistry"],
        "cohort_gap": "biochemistry",
    },
    "SCI-210": {
        "legacy_title": "Forensic Science", "mapping": "direct",
        "title": "Forensic Science", "dept": "Science", "page": 56,
        "length": "semester", "credits": 0.5,
        "prerequisite": "Completion of grade 9 science requirement", "uc_approved": True,
        "description": "Techniques of a forensic laboratory: hair and fiber analysis, blood spatter, "
                       "fingerprinting and forensic DNA analysis.",
        "skills": ["hair and fiber analysis", "fingerprinting", "blood spatter analysis", "DNA analysis"],
        "cohort_gap": "blood spatter analysis",
    },
    "CTE-122": {
        "legacy_title": "Culinary Basics", "mapping": "nearest: the catalog has no culinary course",
        "title": "Biotechnology", "dept": "Science", "page": 55,
        "length": "semester", "credits": 0.5,
        "prerequisite": "First semester of Biology, Honors Biology or AP Biology; preference to grade 12",
        "uc_approved": True,
        "description": "Lab-based introduction to biotechnology techniques, with novel research on "
                       "the local environment and the ethics of the field.",
        "skills": ["lab techniques", "experimental design", "field research", "bioethics"],
        "cohort_gap": "experimental design",
    },
    "TEC-130": {
        "legacy_title": "Esports & Game Design", "mapping": "nearest: Digital World lists gaming as a learning platform",
        "title": "Digital World", "dept": "Computer Science", "page": 11,
        "length": "semester", "credits": 0.5, "prerequisite": "Algebra 1", "uc_approved": True,
        "description": "Current topics in computer science: digital representation, architecture and "
                       "networking, programming, and ethics and privacy.",
        "skills": ["digital representation", "programming", "networking", "computing ethics"],
        "cohort_gap": "networking",
    },
    "CTE-118": {
        "legacy_title": "Intro to Robotics", "mapping": "direct",
        "title": "Robotics Principles: Hardware", "dept": "Computer Science", "page": 12,
        "length": "semester", "credits": 0.5, "prerequisite": "Completion of Algebra 2", "uc_approved": True,
        "description": "Drive trains, electrical systems, sensors and manipulators, designed in CAD "
                       "and built onto small ground robots.",
        "skills": ["drive trains", "sensors and wiring", "CAD", "manipulator design"],
        "cohort_gap": "CAD",
    },
    "ENG-201": {
        "legacy_title": "Creative Writing Workshop", "mapping": "direct: the catalog notes this course was previously titled Creative Writing",
        "title": "English 4: Art of Poetry and Fiction", "dept": "English", "page": 23,
        "length": "semester", "credits": 0.5,
        "prerequisite": "English 3, Honors English 3 or departmental approval", "uc_approved": True,
        "description": "Study of poetry and fiction craft, then original writing discussed in workshop, "
                       "with constant revision.",
        "skills": ["narrative structure", "revision", "workshop critique", "figurative language"],
        "cohort_gap": "figurative language",
    },
    "WLD-101": {
        "legacy_title": "Spanish I", "mapping": "direct",
        "title": "Spanish 1", "dept": "Modern and Classical Languages", "page": 38,
        "length": "year", "credits": 1.0, "prerequisite": "None", "uc_approved": True,
        "description": "Basic elements of Spanish and the cultures of the Spanish-speaking world, "
                       "across listening, speaking, reading and writing.",
        "skills": ["speaking", "reading", "listening", "writing"],
        "cohort_gap": "listening",
    },
    "SOC-130": {
        "legacy_title": "Model UN", "mapping": "nearest: no Model UN course; Speech and Debate covers research and argumentation",
        "title": "Introduction to Speech and Debate", "dept": "Speech and Debate", "page": 59,
        "length": "year", "credits": 0.5, "prerequisite": "None", "uc_approved": False,
        "extra_period": True,
        "description": "Public speaking and argumentation through public forum, Lincoln-Douglas and "
                       "congressional debate.",
        "skills": ["critical writing", "research", "argumentation", "presentation"],
        "cohort_gap": "research",
    },
    "ART-140": {
        "legacy_title": "Ceramics & Wheel Throwing", "mapping": "direct",
        "title": "Foundations: Ceramics", "dept": "Visual Arts", "page": 68,
        "length": "semester", "credits": 0.5, "prerequisite": "None", "uc_approved": False,
        "description": "Clay as idea, material and process: pinch, coil, slab and throwing on the "
                       "potter's wheel.",
        "skills": ["pinch and coil", "wheel throwing", "slab construction", "critique"],
        "cohort_gap": "slab construction",
    },
    "ART-112": {
        "legacy_title": "Digital Photography", "mapping": "direct",
        "title": "Foundations: Photography", "dept": "Visual Arts", "page": 68,
        "length": "semester", "credits": 0.5, "prerequisite": "None", "uc_approved": False,
        "description": "Photographic concepts, image capture and camera functions on digital "
                       "cameras, each paired with contemporary theory.",
        "skills": ["exposure", "composition", "digital imaging", "photographic theory"],
        "cohort_gap": "digital imaging",
    },
    "MUS-105": {
        "legacy_title": "Jazz Band", "mapping": "direct",
        "title": "Jazz Band", "dept": "Performing Arts", "page": 65,
        "length": "year", "credits": 0.5, "prerequisite": "Some auditions may be required",
        "uc_approved": False, "extra_period": True,
        "description": "The primary jazz ensemble, also the pep band; CMEA festivals, homecoming and "
                       "two annual concerts.",
        "skills": ["sight reading", "improvisation", "ensemble timing", "tone"],
        "cohort_gap": "sight reading",
    },
    "PE-160": {
        "legacy_title": "Rock Climbing", "mapping": "nearest: the catalog has no climbing course",
        "title": "Personal Fitness", "dept": "Physical Education", "page": 51,
        "length": "semester", "credits": 0.5, "prerequisite": "None", "uc_approved": False,
        # The catalog says P.E. is ungraded and off the transcript. This app still
        # records scores for it and the support engine still counts them.
        "graded": False,
        "description": "Cardio-respiratory and muscular endurance, strength and flexibility, and "
                       "designing a well-rounded workout routine.",
        "skills": ["resistance training", "cardiovascular endurance", "flexibility", "workout design"],
        "cohort_gap": "flexibility",
    },
}

SKILLS = {code: c["skills"] for code, c in CATALOG.items()}


def catalog_fields(code: str) -> dict:
    """Column values for a Course row. Title and department are included, so the
    catalog wins over whatever the seed JSON still says."""
    c = CATALOG.get(code)
    if c is None:
        return {}
    return {
        "title": c["title"], "dept": c["dept"], "description": c["description"],
        "length": c["length"], "credits": c["credits"], "prerequisite": c["prerequisite"],
        "uc_approved": c["uc_approved"], "extra_period": c.get("extra_period", False),
        "graded": c.get("graded", True), "catalog_page": c["page"],
        "legacy_title": c["legacy_title"],
    }
COHORT_GAP = {code: c["cohort_gap"] for code, c in CATALOG.items()}

# Stockroom items that only made sense for the old sections.
UNLINKED_ITEMS = {
    "PE-HRN-CLB": "PE-160",   # climbing harness — Personal Fitness has no wall
    "CUL-APR-STD": "CTE-122", # kitchen apron — Biotechnology is a lab, not a kitchen
    "CUL-KNF-CHF": "CTE-122", # chef knife
}
