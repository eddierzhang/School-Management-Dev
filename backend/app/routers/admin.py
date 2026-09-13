"""Accounts and the audit log. Administrators only."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import audit, importer
from ..auth.deps import Principal, require
from ..auth.passwords import hash_password, password_problem
from ..auth.permissions import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS, ROLES
from ..auth.sessions import revoke_all
from ..db import get_db
from ..models import AuditEvent, Course, User

router = APIRouter(prefix="/admin", tags=["admin"])

ROLE_PATTERN = "^(" + "|".join(ROLES) + ")$"


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=160, pattern=r"^[^@\s]+@[^@\s]+$")
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern=ROLE_PATTERN)
    teacher_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=1024)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    teacher_name: str | None = Field(default=None, max_length=120)
    active: bool | None = None
    password: str | None = Field(default=None, max_length=1024)


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role), "teacher_name": u.teacher_name,
            "active": u.active, "has_password": bool(u.password_hash),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


def _check_teacher(db: Session, role: str, teacher_name: str | None) -> str | None:
    name = (teacher_name or "").strip() or None
    if role != "teacher":
        return None
    if name is None:
        raise HTTPException(422, "A teacher account needs the teacher name used on their sections.")
    if db.scalar(select(Course.id).where(Course.teacher == name).limit(1)) is None:
        raise HTTPException(422, f"No section is taught by {name!r}. Use the name exactly as it appears on the timetable.")
    return name


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True))) or 0


@router.get("/roles")
def roles(_: Principal = Depends(require("users.manage"))) -> dict:
    return {"roles": [{"role": r, "label": ROLE_LABELS[r], "permissions": sorted(ROLE_PERMISSIONS[r])} for r in ROLES],
            "permissions": PERMISSIONS}


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: Principal = Depends(require("users.manage"))) -> list[dict]:
    return [_user_out(u) for u in db.scalars(select(User).order_by(User.active.desc(), User.name)).all()]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _: Principal = Depends(require("users.manage"))) -> dict:
    email = body.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, f"There is already an account for {email}.")
    if body.password and (problem := password_problem(body.password)):
        raise HTTPException(422, problem)
    u = User(email=email, name=body.name.strip(), role=body.role,
             teacher_name=_check_teacher(db, body.role, body.teacher_name),
             password_hash=hash_password(body.password) if body.password else None, active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return _user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db),
                me: Principal = Depends(require("users.manage"))) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, f"No account {user_id}")
    changes = body.model_dump(exclude_unset=True)
    losing_admin = u.role == "admin" and u.active and (
        changes.get("active") is False or changes.get("role", "admin") != "admin")
    if losing_admin and u.id == me.id:
        raise HTTPException(409, "You cannot remove your own administrator access. Ask another administrator.")
    if losing_admin and _active_admins(db) <= 1:
        raise HTTPException(409, "This is the last active administrator.")

    if "password" in changes:
        if changes["password"] and (problem := password_problem(changes["password"])):
            raise HTTPException(422, problem)
        u.password_hash = hash_password(changes["password"]) if changes["password"] else None
    if "name" in changes and changes["name"]:
        u.name = changes["name"].strip()
    role = changes.get("role") or u.role
    if "role" in changes or "teacher_name" in changes:
        u.teacher_name = _check_teacher(db, role, changes.get("teacher_name", u.teacher_name))
    # Anything that narrows what the account may do ends its sessions at once.
    if (changes.get("role") and changes["role"] != u.role) or changes.get("active") is False or "password" in changes:
        revoke_all(db, u.id)
    u.role = role
    if "active" in changes and changes["active"] is not None:
        u.active = changes["active"]
    db.commit()
    return _user_out(u)


MAX_IMPORT_UPLOAD = 50 * 1024 * 1024


@router.post("/import/oneroster")
async def import_oneroster(
    request: Request,
    file: UploadFile = File(...),
    apply: bool = Form(False),
    create_teacher_accounts: bool = Form(False),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("data.import")),
) -> dict:
    """Check (and with apply=true, import) a OneRoster CSV zip from the student information system.

    Without `apply` nothing is kept: the import runs in a transaction, reports what
    it would do, and rolls back. Any error refuses the whole import.
    """
    data = await file.read(MAX_IMPORT_UPLOAD + 1)
    if len(data) > MAX_IMPORT_UPLOAD:
        raise HTTPException(413, "That file is over the 50 MB limit. Import one school at a time.")
    try:
        files = importer.read_zip(data)
    except importer.ImportFileError as e:
        raise HTTPException(422, str(e)) from e
    report = await run_in_threadpool(importer.run_import, db, files, apply=apply,
                                     create_teacher_accounts=create_teacher_accounts)
    out = report.as_dict()
    if report.applied:
        audit.record("import.oneroster", request=request, actor=user, status=200,
                     detail={"file": (file.filename or "")[:120], "created": out["created"], "updated": out["updated"],
                             "dropped_enrollments": out["dropped_enrollments"]})
    return out


@router.get("/audit")
def audit_log(
    actor: str | None = None, action: str | None = None,
    entity_type: str | None = None, entity_id: str | None = None,
    since: datetime | None = None, before_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), _: Principal = Depends(require("audit.read")),
) -> dict:
    """Newest first. Page with `before_id` set to the last id of the previous page."""
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if actor:
        stmt = stmt.where(AuditEvent.actor_email == actor.strip().lower())
    if action:
        stmt = stmt.where(AuditEvent.action.like(f"{action}%"))
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if since:
        stmt = stmt.where(AuditEvent.at >= since)
    if before_id:
        stmt = stmt.where(AuditEvent.id < before_id)
    rows = db.scalars(stmt).all()
    return {"events": [{"id": e.id, "at": e.at.isoformat(), "actor_email": e.actor_email, "actor_role": e.actor_role,
                        "action": e.action, "status": e.status, "entity_type": e.entity_type,
                        "entity_id": e.entity_id, "path": e.path, "ip": e.ip, "request_id": e.request_id,
                        "detail": e.detail or {}} for e in rows],
            "next_before_id": rows[-1].id if len(rows) == limit else None}
