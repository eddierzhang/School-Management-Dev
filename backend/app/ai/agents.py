"""The fleet.

Each agent owns one domain and sees only that domain's tools — four to six, never
twenty. That narrow surface is the main reason a 4B model can work here at all:
the hard part for a small model is choosing among many tools, not using one.

System prompts are deliberately short and concrete. Long, nuanced instructions
degrade small models; short imperative ones with an explicit stopping condition
work far better.
"""
from __future__ import annotations

from dataclasses import dataclass

from .toolkit import Tool
from . import tools as T

COMMON_RULES = (
    "Rules:\n"
    "- Use tools to get facts. Never invent a code, SKU, student ID or number.\n"
    "- Look before you propose. Propose only what the tool results support.\n"
    "- WRITING ABOUT A PROPOSAL DOES NOT RECORD IT. Only calling a propose_ tool records "
    "anything. If you describe an action in prose instead of calling the tool, nothing "
    "happens and your work is lost.\n"
    "- One propose_ call per action. Do not batch several actions into one sentence.\n"
    "- A proposal is a suggestion for a person to approve. Nothing you do changes records.\n"
    "- If a tool returns an error, read it and correct your call.\n"
    "- Make at most 3 proposals. Then write a two-sentence summary and stop calling tools."
)


@dataclass
class Agent:
    name: str
    title: str
    domain: str
    system: str
    tools: list[Tool]
    default_task: str
    # The runner performs this read before the model's first turn and feeds the
    # result in as an already-completed tool call. Observed: without it, the model
    # opens by inventing a SKU and a student count rather than looking. Starting it
    # on real data removes that entire failure class for the price of one query.
    opening: tuple[str, dict] | None = None

    def tool_specs(self) -> list[dict]:
        return [t.spec() for t in self.tools]

    def by_name(self) -> dict[str, Tool]:
        return {t.name: t for t in self.tools}


def _tool(fn, name, description, params, proposes=None) -> Tool:
    return Tool(name=name, description=description, parameters=params, handler=fn, proposes=proposes)


STOCKROOM = Agent(
    name="stockroom",
    title="Stockroom agent",
    domain="Inventory: what is running out, and what should be ordered.",
    system=(
        "You are the stockroom agent for Halverson Ridge High School. Your job is to keep "
        "supplies ahead of what classes need.\n\n"
        "Work in this order: find what is low, check which classes depend on it, then propose "
        "a requisition for the items that genuinely need ordering.\n\n" + COMMON_RULES
    ),
    default_task="Do a stockroom sweep. Find what is running out, check which classes it affects, "
                 "and propose what to order.",
    opening=("list_low_stock", {}),
    tools=[
        _tool(T.list_low_stock, "list_low_stock",
              "List stockroom items at or below their reorder point, worst first.",
              {"type": "object", "properties": {
                  "category": {"type": "string", "description": "Optional category filter, or omit for all."}},
               "required": []}),
        _tool(T.get_item, "get_item", "Full detail for one stockroom item by SKU.",
              {"type": "object", "properties": {
                  "sku": {"type": "string", "description": "Exact SKU, e.g. SCI-FPK-020."}},
               "required": ["sku"]}),
        _tool(T.list_items_for_course, "list_items_for_course",
              "Stockroom items a class consumes, with how many students are enrolled.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string", "description": "Exact course code, e.g. SCI-210."}},
               "required": ["course_code"]}),
        _tool(T.propose_requisition, "propose_requisition",
              "Propose ordering stock back up to par. Use exact SKUs from the other tools.",
              {"type": "object", "properties": {
                  "skus": {"type": "array", "items": {"type": "string"}, "description": "Exact SKUs to order."},
                  "reason": {"type": "string", "description": "One sentence on why, citing the numbers."}},
               "required": ["skus", "reason"]}, proposes="requisition"),
        _tool(T.propose_reorder_point, "propose_reorder_point",
              "Propose changing an item's reorder point when it trips too late or too often.",
              {"type": "object", "properties": {
                  "sku": {"type": "string"},
                  "new_reorder_point": {"type": "integer"},
                  "reason": {"type": "string"}},
               "required": ["sku", "new_reorder_point", "reason"]}, proposes="reorder_point"),
    ],
)

REGISTRAR = Agent(
    name="registrar",
    title="Registrar agent",
    domain="Scheduling: sections, rooms, periods, capacity and waitlists.",
    system=(
        "You are the registrar agent for Halverson Ridge High School. Your job is to keep the "
        "timetable workable: no clashes, no class with a waitlist longer than it needs, no "
        "half-empty room.\n\n"
        "Work in this order: check for clashes, check where waitlists are worst, find a free room, "
        "then propose a fix.\n\n" + COMMON_RULES
    ),
    default_task="Review the timetable. Find scheduling clashes and sections under waitlist "
                 "pressure, and propose fixes.",
    opening=("list_waitlist_pressure", {}),
    tools=[
        _tool(T.list_sections, "list_sections",
              "List class sections with enrolment, capacity and waitlist.",
              {"type": "object", "properties": {
                  "only_problems": {"type": "boolean",
                                    "description": "True to show only over- or under-subscribed sections."}},
               "required": []}),
        _tool(T.find_schedule_conflicts, "find_schedule_conflicts",
              "Find teachers or rooms double-booked in the same period. Computed exactly.",
              {"type": "object", "properties": {}, "required": []}),
        _tool(T.list_waitlist_pressure, "list_waitlist_pressure",
              "Sections with students waiting, worst first, and whether the waitlist fills a section.",
              {"type": "object", "properties": {}, "required": []}),
        _tool(T.find_open_rooms, "find_open_rooms", "Rooms with nothing scheduled in a given period.",
              {"type": "object", "properties": {
                  "period": {"type": "integer", "description": "Period number, 1-7."}},
               "required": ["period"]}),
        _tool(T.propose_new_section, "propose_new_section",
              "Propose opening a second section of an over-subscribed class in a free room.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string"},
                  "period": {"type": "integer"},
                  "room": {"type": "string", "description": "A room returned by find_open_rooms."},
                  "seats": {"type": "integer"},
                  "move_from_waitlist": {"type": "integer", "description": "How many waiting students to move in."},
                  "teacher": {"type": "string"},
                  "reason": {"type": "string"}},
               "required": ["course_code", "period", "room", "seats", "reason"]}, proposes="new_section"),
        _tool(T.propose_capacity_change, "propose_capacity_change",
              "Propose raising or lowering a section's seat cap.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string"},
                  "new_capacity": {"type": "integer"},
                  "reason": {"type": "string"}},
               "required": ["course_code", "new_capacity", "reason"]}, proposes="capacity_change"),
    ],
)

SUPPORT = Agent(
    name="support",
    title="Student support agent",
    domain="Children: who is struggling, on what, and what support to open.",
    system=(
        "You are the student support agent for Halverson Ridge High School. Your job is to turn "
        "the flagged list into specific, defensible support plans.\n\n"
        "Work in this order: see who is flagged, open the worst one or two records to find out what "
        "is actually wrong, then propose support that matches the cause. Missing work needs homework "
        "recovery; a low grade with work submitted needs tutoring on the named weak strand; absence "
        "needs an attendance plan; sliding across several classes needs a check-in.\n\n"
        "You are not diagnosing a child. You are routing them to a person.\n\n" + COMMON_RULES
    ),
    default_task="Review the flagged students. Look at the worst cases and propose support that "
                 "matches what is actually wrong.",
    opening=("list_flagged_students", {}),
    tools=[
        _tool(T.list_flagged_students, "list_flagged_students",
              "Students flagged as needing a plan or worth watching, worst first.",
              {"type": "object", "properties": {
                  "band": {"type": "string", "enum": ["needs-plan", "watch", "all"],
                           "description": "Which band to list. Omit for all flagged."}},
               "required": []}),
        _tool(T.get_student, "get_student",
              "One student's full picture: grades per class, weakest strands, absence, reasons.",
              {"type": "object", "properties": {
                  "sid": {"type": "string", "description": "Exact student ID, e.g. S-1507."}},
               "required": ["sid"]}),
        _tool(T.list_skill_gaps, "list_skill_gaps",
              "Topic strands where a whole class is below the line — a reteach signal, not a referral.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string", "description": "Optional class filter."}},
               "required": []}),
        _tool(T.propose_support_plan, "propose_support_plan",
              "Propose opening a support plan for one student. Match the kind to the cause.",
              {"type": "object", "properties": {
                  "student_sid": {"type": "string"},
                  "kind": {"type": "string", "enum": T.PLAN_KINDS},
                  "title": {"type": "string", "description": "What will actually happen, in a few words."},
                  "rationale": {"type": "string", "description": "The evidence, citing numbers."},
                  "course_code": {"type": "string", "description": "The class it concerns, if any."}},
               "required": ["student_sid", "kind", "title", "rationale"]}, proposes="support_plan"),
    ],
)

FINANCE = Agent(
    name="finance",
    title="Finance agent",
    domain="Budget: what is overspending, where money is needed, what looks wrong, and where money can move.",
    system=(
        "You are the finance agent for Halverson Ridge High School's business office. Your job "
        "is to keep every budget line solvent through June and catch charges that need a person's eye.\n\n"
        "Work in this order: read lines_needing_money and lines_with_room. Propose ONE budget "
        "revision with a move into each line that needs money, from lines with room, each amount no "
        "more than that line needs. Open a new line only for a purpose no existing line covers, "
        "funded from a line with room. Then check spending anomalies and propose a review for any that look like real "
        "mistakes, such as a duplicated invoice. Amounts are dollars.\n\n" + COMMON_RULES
    ),
    default_task="Review the budget. Find where money is needed, propose a revision that moves it from "
                 "lines with room, and flag any charges that look like mistakes.",
    opening=("list_budget_status", {"only_problems": True}),
    tools=[
        _tool(T.list_budget_status, "list_budget_status",
              "Budget lines with their status, budget, spending, commitments and year-end projection.",
              {"type": "object", "properties": {
                  "only_problems": {"type": "boolean",
                                    "description": "True for lines not on track; false for every line."}},
               "required": []}),
        _tool(T.get_budget_line, "get_budget_line",
              "One budget line in detail, with its commitments and recent transactions.",
              {"type": "object", "properties": {
                  "code": {"type": "string", "description": "Exact line code, e.g. SPD-TRV."}},
               "required": ["code"]}),
        _tool(T.find_spending_anomalies, "find_spending_anomalies",
              "Unreviewed transactions caught by a rule: possible duplicates and unusually large charges.",
              {"type": "object", "properties": {}, "required": []}),
        _tool(T.propose_transaction_review, "propose_transaction_review",
              "Propose holding one transaction for a person to review.",
              {"type": "object", "properties": {
                  "transaction_id": {"type": "integer", "description": "Id from find_spending_anomalies."},
                  "concern": {"type": "string", "description": "What looks wrong, in one sentence."},
                  "reason": {"type": "string", "description": "The evidence, citing the rule and amounts."}},
               "required": ["transaction_id", "concern", "reason"]}, proposes="transaction_review"),
        _tool(T.propose_budget_revision, "propose_budget_revision",
              "Propose moving money across several lines at once, from lines with room to lines that need it.",
              {"type": "object", "properties": {
                  "moves": {"type": "array", "description": "One to six moves, one into each line that needs money.",
                            "items": {"type": "object", "properties": {
                                "from_line": {"type": "string", "description": "A line from lines_with_room."},
                                "to_line": {"type": "string", "description": "A line from lines_needing_money."},
                                "amount": {"type": "number", "description": "Dollars."}},
                                "required": ["from_line", "to_line", "amount"]}},
                  "reason": {"type": "string", "description": "Why, citing the needs and amounts from the tools."}},
               "required": ["moves", "reason"]}, proposes="budget_revision"),
        _tool(T.propose_new_budget_line, "propose_new_budget_line",
              "Propose opening a new budget line for a purpose no existing line covers, funded from a line with room.",
              {"type": "object", "properties": {
                  "code": {"type": "string", "description": "New code: department letters, dash, three letters, e.g. MAT-TUT."},
                  "name": {"type": "string", "description": "What the money is for."},
                  "department": {"type": "string", "description": "An existing department name."},
                  "category": {"type": "string", "description": "An existing category, e.g. Supplies or Programs."},
                  "from_line": {"type": "string", "description": "A line from lines_with_room to fund it."},
                  "amount": {"type": "number", "description": "Dollars to move into the new line."},
                  "reason": {"type": "string", "description": "What it pays for and why no existing line fits."}},
               "required": ["code", "name", "department", "category", "from_line", "amount", "reason"]},
              proposes="budget_line"),
    ],
)

CLASSES = Agent(
    name="classes",
    title="Class improvement agent",
    domain="Teaching: classes whose results call for a change in how the course is taught.",
    system=(
        "You are the class improvement agent for Halverson Ridge High School. You draft "
        "improvement plans for whole classes. A class plan changes the teaching; it does not "
        "refer one child.\n\n"
        "Work in this order: read the class's performance, find the cause, then propose one plan "
        "whose actions match that cause:\n"
        "- A strand with many students below the line: reteach that named strand a different way, "
        "then check it with a short quiz.\n"
        "- Work not handed in: class time to start it, smaller pieces, a weekly missing-work check.\n"
        "- Tests lower than labs or projects: practice under test conditions before the next test.\n"
        "- Recent work sliding: slow the pacing and review before moving on.\n"
        "Each action says what happens, who does it (usually the class teacher) and when. The goal is "
        "a number from the class data to reach within four weeks. Cite only numbers the tools "
        "returned.\n\n" + COMMON_RULES
    ),
    default_task="Find the classes that most need an improvement plan and draft one for each of the "
                 "worst, matching the plan to what is actually wrong.",
    opening=("list_classes_by_need", {}),
    tools=[
        _tool(T.list_classes_by_need, "list_classes_by_need",
              "Every class with its status, average, work handed in, trend, weakest strands and issues, "
              "neediest first.",
              {"type": "object", "properties": {}, "required": []}),
        _tool(T.get_class_performance, "get_class_performance",
              "One class in detail: every strand, each kind of work, trend, and whether it has a plan.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string", "description": "Exact course code, e.g. MAT-150."}},
               "required": ["course_code"]}),
        _tool(T.list_skill_gaps, "list_skill_gaps",
              "Strands where a whole class is below the line, across the school.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string", "description": "Optional class filter."}},
               "required": []}),
        _tool(T.propose_class_plan, "propose_class_plan",
              "Propose an improvement plan for one class. Actions must match the cause in the data.",
              {"type": "object", "properties": {
                  "course_code": {"type": "string", "description": "Exact course code."},
                  "title": {"type": "string", "description": "The plan in a few words, e.g. 'Reteach word problems'."},
                  "diagnosis": {"type": "string",
                                "description": "What is wrong and why, in two sentences, citing numbers from the tools."},
                  "focus_strands": {"type": "array", "items": {"type": "string"},
                                    "description": "One or two strand names exactly as get_class_performance lists them."},
                  "actions": {"type": "array", "items": {"type": "string"},
                              "description": "Two to five concrete steps: what happens, who does it, when."},
                  "goal": {"type": "string",
                           "description": "A measurable target within four weeks, e.g. 'word problems average to 72%'."}},
               "required": ["course_code", "title", "diagnosis", "focus_strands", "actions", "goal"]},
              proposes="class_plan"),
    ],
)

STUDY = Agent(
    name="study",
    title="Study plan agent",
    domain="One student in one class: what exactly they struggle on, and a week-by-week study plan.",
    system=(
        "You are the study plan agent for Halverson Ridge High School. You write a detailed study plan "
        "for one student in one class, from their actual assignments.\n\n"
        "Work in this order: read the student's class work, decide what exactly is wrong from the "
        "findings, then call propose_study_plan once. Match the sessions to the cause:\n"
        "- strand-gap: the student, not the class, is weak on a strand. Sessions redo that strand's "
        "assignments with worked examples, then a short self-check.\n"
        "- strand-missing: the strand is low only because work is missing. Hand that work in first; "
        "do not reteach what they already understand.\n"
        "- class-gap: the whole class is weak too. Keep sessions short and ask the teacher for a reteach.\n"
        "- tests-below-practice: practice quizzes under timed test conditions.\n"
        "- missing-work: list the missing assignment ids in catch_up_assignments and give a session to hand them in.\n"
        "- sliding or declining: review the earlier material before new work.\n"
        "Write three to eight sessions. Each says when (e.g. 'Mon week 1'), what exactly the student does, "
        "who helps if anyone, and for how many minutes. Name the focus strand in its sessions. The goal "
        "is a number to reach within three weeks. Cite only numbers the tools returned.\n\n" + COMMON_RULES
    ),
    default_task="Find the students whose class work most needs a study plan and draft a detailed plan "
                 "for the worst one or two, matched to what exactly they are struggling on.",
    opening=("list_students_for_study_plans", {}),
    tools=[
        _tool(T.list_students_for_study_plans, "list_students_for_study_plans",
              "Students in a class whose work calls for a study plan and who have none, lowest grade first.",
              {"type": "object", "properties": {}, "required": []}),
        _tool(T.get_student_class_work, "get_student_class_work",
              "One student's work in one class: findings, every strand against the class, each kind of work, "
              "missing and recent assignments.",
              {"type": "object", "properties": {
                  "sid": {"type": "string", "description": "Exact student ID, e.g. S-1507."},
                  "course_code": {"type": "string", "description": "Exact course code, e.g. MAT-150."}},
               "required": ["sid", "course_code"]}),
        _tool(T.propose_study_plan, "propose_study_plan",
              "Propose a detailed study plan for one student in one class. Sessions must match the findings.",
              {"type": "object", "properties": {
                  "student_sid": {"type": "string"},
                  "course_code": {"type": "string"},
                  "title": {"type": "string", "description": "The plan in a few words, e.g. 'Catch up and relearn word problems'."},
                  "diagnosis": {"type": "string",
                                "description": "What exactly the student struggles on and why, in two or three "
                                               "sentences, citing numbers from get_student_class_work."},
                  "focus_strands": {"type": "array", "items": {"type": "string"},
                                    "description": "One to three strand names exactly as get_student_class_work lists them."},
                  "sessions": {"type": "array", "items": {"type": "string"},
                               "description": "Three to eight study sessions: when, what exactly, who helps, how many minutes."},
                  "catch_up_assignments": {"type": "array", "items": {"type": "integer"},
                                           "description": "Ids from missing_assignments to hand in. Empty if none are missing."},
                  "goal": {"type": "string", "description": "A number to reach in three weeks, e.g. 'word problems to 72%'."}},
               "required": ["student_sid", "course_code", "title", "diagnosis", "focus_strands", "sessions", "goal"]},
              proposes="study_plan"),
    ],
)

FLEET: dict[str, Agent] = {a.name: a for a in (SUPPORT, CLASSES, STUDY, REGISTRAR, STOCKROOM, FINANCE)}

# The general manager sits over the fleet and reads FLEET itself, so it registers
# after the specialists exist.
from .manager import MANAGER  # noqa: E402

FLEET[MANAGER.name] = MANAGER
