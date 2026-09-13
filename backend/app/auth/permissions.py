"""Roles, and what each one may see and do.

Permissions are coarse on purpose: one per kind of work, not one per endpoint, so
a school can read this file and recognise its own staff.

    admin      everything, including accounts, the audit log and data import
    counselor  every student, support plans, documents, and approving plans
    teacher    only the students in their own sections; can record scores,
               upload documents and ask for draft plans, but approves nothing
    registrar  classes, sections and the timetable, and approving those changes
    business   the stockroom and the budget; no student records at all

A teacher's `students.read` is narrowed to their own sections by app/auth/scope.py.
"""
from __future__ import annotations

ROLES = ("admin", "counselor", "teacher", "registrar", "business")

ROLE_LABELS = {
    "admin": "Administrator",
    "counselor": "Counselor / support staff",
    "teacher": "Teacher",
    "registrar": "Registrar",
    "business": "Business office",
}

PERMISSIONS = {
    "students.read": "See students' records (teachers: only their own sections)",
    "plans.write": "Open, change and close support and study plans; approve plan proposals",
    "documents.upload": "Upload documents about a student",
    "drafts.request": "Ask the AI agent to draft a study or class plan",
    "scores.write": "Record scores (teachers: only in their own sections)",
    "courses.read": "See classes, the catalog and class demand",
    "courses.write": "Open classes and sections, change capacity; approve those proposals",
    "schedule.read": "See the master timetable",
    "agents.read": "See the agents, their runs and their proposals",
    "inventory.read": "See the stockroom",
    "inventory.write": "Change the stockroom; approve stockroom proposals",
    "finance.read": "See the budget",
    "finance.write": "Change the budget; approve budget proposals",
    "manager.run": "Run the general manager agent",
    "users.manage": "Create accounts and change roles",
    "audit.read": "Read the audit log",
    "data.import": "Import records from the student information system",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(PERMISSIONS),
    "counselor": frozenset({"students.read", "plans.write", "documents.upload", "drafts.request",
                            "courses.read", "schedule.read", "agents.read"}),
    "teacher": frozenset({"students.read", "documents.upload", "drafts.request", "scores.write",
                          "courses.read", "schedule.read"}),
    "registrar": frozenset({"students.read", "courses.read", "courses.write", "schedule.read", "agents.read"}),
    "business": frozenset({"courses.read", "inventory.read", "inventory.write", "finance.read",
                           "finance.write", "agents.read"}),
}

# Running an agent, reading its transcripts, and seeing its proposals all need the
# permission for the records it works on: a transcript quotes those records.
AGENT_PERMISSION = {
    "support": "plans.write",
    "study": "plans.write",
    "classes": "plans.write",
    "registrar": "courses.write",
    "stockroom": "inventory.write",
    "finance": "finance.write",
    "manager": "manager.run",
}

# Approving a proposal needs the same permission as making the change by hand.
PROPOSAL_PERMISSION = {
    "support_plan": "plans.write",
    "study_plan": "plans.write",
    "class_plan": "plans.write",
    "new_section": "courses.write",
    "capacity_change": "courses.write",
    "requisition": "inventory.write",
    "reorder_point": "inventory.write",
    "new_item": "inventory.write",
    "budget_transfer": "finance.write",
    "transaction_review": "finance.write",
    "budget_line": "finance.write",
    "budget_revision": "finance.write",
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())
