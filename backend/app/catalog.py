"""Every running section, mapped to a real course in the course of study.

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

Twelve more sections were added later straight from the same document, filling
departments the first fourteen missed: English 1 and 3, World History 1, U.S.
History, Algebra 2 & Trigonometry, AP Calculus AB, Physics, Chemistry,
Programming, French 1, Economics and Psychology. Those map directly.
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
    # --- Added sections (from the same course of study) ---------------------------
    "ENG-101": {
        "legacy_title": "English 1: The Study of Literary Genres", "mapping": "direct",
        "title": "English 1: The Study of Literary Genres", "dept": "English", "page": 16,
        "length": "year", "credits": 1.0, "prerequisite": "None", "uc_approved": True,
        "description": "Grade 9 literature across genres: long and short fiction, memoir, drama and lyric "
                       "poetry, with analytical essays, a personal narrative and researched writing.",
        "skills": ["literary analysis", "analytical essay writing", "poetry", "revision"],
        "cohort_gap": "analytical essay writing",
    },
    "ENG-301": {
        "legacy_title": "English 3: A Survey of American Literature", "mapping": "direct",
        "title": "English 3: A Survey of American Literature", "dept": "English", "page": 16,
        "length": "year", "credits": 1.0, "prerequisite": "English 2 or Honors English 2", "uc_approved": True,
        "description": "Major American authors in chronological order, making thematic connections across "
                       "literary periods and honing critical reading and argumentation.",
        "skills": ["close reading", "thematic connections", "literary terms", "argumentation"],
        "cohort_gap": "argumentation",
    },
    "HIS-101": {
        "legacy_title": "World History 1: Early Civilizations through the Renaissance", "mapping": "direct",
        "title": "World History 1: Early Civilizations through the Renaissance",
        "dept": "History and Social Science", "page": 24,
        "length": "year", "credits": 1.0, "prerequisite": "None", "uc_approved": True,
        "description": "World history from early river valley civilizations to 1600 C.E. across Europe, "
                       "Africa, Asia and the Americas, with document evaluation, thesis construction and research.",
        "skills": ["world religions", "document evaluation", "thesis construction", "political and economic systems"],
        "cohort_gap": "thesis construction",
    },
    "HIS-301": {
        "legacy_title": "United States History", "mapping": "direct",
        "title": "United States History", "dept": "History and Social Science", "page": 25,
        "length": "year", "credits": 1.0, "prerequisite": "Completion of grade 10 history requirement",
        "uc_approved": True,
        "description": "The history and culture of the United States from the colonial era to the present, "
                       "with analytical essay writing and the evaluation of primary source documents.",
        "skills": ["the Constitution and Bill of Rights", "industrialization", "civil rights movement",
                   "primary source analysis"],
        "cohort_gap": "primary source analysis",
    },
    "MAT-310": {
        "legacy_title": "Algebra 2 & Trigonometry", "mapping": "direct",
        "title": "Algebra 2 & Trigonometry", "dept": "Mathematics", "page": 33,
        "length": "year", "credits": 1.0, "prerequisite": "Geometry", "uc_approved": True,
        "description": "Functions studied algebraically, numerically and graphically: polynomial, rational, "
                       "exponential and logarithmic, then radicals, complex numbers and trigonometric functions.",
        "skills": ["polynomial functions", "exponential and logarithmic functions", "complex numbers",
                   "trigonometric functions"],
        "cohort_gap": "exponential and logarithmic functions",
    },
    "MAT-410": {
        "legacy_title": "AP Calculus AB", "mapping": "direct",
        "title": "AP Calculus AB", "dept": "Mathematics", "page": 34,
        "length": "year", "credits": 1.0,
        "prerequisite": "A- or better in Precalculus or Honors Precalculus, and departmental approval",
        "uc_approved": True,
        "description": "College-level calculus of one variable: limits, continuity, derivatives, integration, "
                       "the fundamental theorem of calculus, and slope fields.",
        "skills": ["limits and continuity", "derivatives", "applications of differentiation", "integration"],
        "cohort_gap": "applications of differentiation",
    },
    "SCI-101": {
        "legacy_title": "Physics", "mapping": "direct",
        "title": "Physics", "dept": "Science", "page": 52,
        "length": "year", "credits": 1.0, "prerequisite": "None", "uc_approved": True,
        "description": "Conceptual introduction to motion, forces, momentum, energy, electric charge, circuits, "
                       "magnetism and waves, built around lab activities and demonstrations.",
        "skills": ["motion and forces", "energy and momentum", "circuits", "waves"],
        "cohort_gap": "circuits",
    },
    "SCI-201": {
        "legacy_title": "Chemistry", "mapping": "direct",
        "title": "Chemistry", "dept": "Science", "page": 52,
        "length": "year", "credits": 1.0, "prerequisite": "Physics or Honors Physics", "uc_approved": True,
        "description": "Conceptual and quantitative chemistry: atomic theory, chemical bonding, acid-base "
                       "behavior and oxidation-reduction, with many laboratory experiments.",
        "skills": ["atomic theory", "chemical bonding", "acid-base behavior", "oxidation-reduction"],
        "cohort_gap": "oxidation-reduction",
    },
    "TEC-140": {
        "legacy_title": "Programming", "mapping": "direct",
        "title": "Programming", "dept": "Computer Science", "page": 11,
        "length": "semester", "credits": 0.5, "prerequisite": "Geometry or Honors Geometry", "uc_approved": True,
        "description": "Algorithmic problem-solving and abstraction through object-oriented programming: "
                       "classes, methods, inheritance, arrays and strings.",
        "skills": ["decomposition", "classes and methods", "arrays", "inheritance"],
        "cohort_gap": "inheritance",
    },
    "WLD-110": {
        "legacy_title": "French 1", "mapping": "direct",
        "title": "French 1", "dept": "Modern and Classical Languages", "page": 40,
        "length": "year", "credits": 1.0, "prerequisite": "None", "uc_approved": True,
        "description": "Basic elements of French and the cultures of the French-speaking world, through "
                       "active communication, authentic materials and pair and group projects.",
        "skills": ["listening", "speaking", "reading", "writing"],
        "cohort_gap": "writing",
    },
    "BUS-110": {
        "legacy_title": "Economics", "mapping": "direct",
        "title": "Economics", "dept": "Business and Entrepreneurship", "page": 8,
        "length": "semester", "credits": 0.5, "prerequisite": "Open to students in grades 10, 11 and 12",
        "uc_approved": True,
        "description": "Survey of micro- and macroeconomics: supply and demand, elasticity, market structures, "
                       "the business cycle, monetary and fiscal policy, and personal finance.",
        "skills": ["supply and demand", "elasticity", "market structures", "monetary and fiscal policy"],
        "cohort_gap": "elasticity",
    },
    "SOC-210": {
        "legacy_title": "Psychology", "mapping": "direct",
        "title": "Psychology", "dept": "History and Social Science", "page": 29,
        "length": "semester", "credits": 0.5, "prerequisite": "Completion of grade 9 history requirement",
        "uc_approved": True,
        "description": "Introductory psychology: personality and development theory, states of consciousness, "
                       "abnormal psychology and therapy, learning and memory.",
        "skills": ["personality theory", "states of consciousness", "learning and memory", "abnormal psychology"],
        "cohort_gap": "abnormal psychology",
    },
}

# Sections added after the original fourteen. The seed grades them on their own
# random stream (seed.py), so the original sections' generated records don't move.
ADDED_SECTIONS = frozenset({"ENG-101", "ENG-301", "HIS-101", "HIS-301", "MAT-310", "MAT-410",
                            "SCI-101", "SCI-201", "TEC-140", "WLD-110", "BUS-110", "SOC-210"})

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
