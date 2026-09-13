"""FastAPI dependencies: who is signed in, and whether they may do this.

Every router except sign-in and the health checks is mounted behind
`current_user` (app/main.py), so a route that forgets a permission check is still
closed to anyone not signed in. Routes then ask for the permission they need with
`require("students.read")`.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from .permissions import AGENT_PERMISSION, PROPOSAL_PERMISSION, permissions_for
from .sessions import COOKIE, find_session

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-requested-with"


@dataclass(frozen=True)
class Principal:
    id: int
    email: str
    name: str
    role: str
    teacher_name: str | None
    permissions: frozenset[str]

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def can_use_agent(self, agent: str) -> bool:
        perm = AGENT_PERMISSION.get(agent)
        return bool(perm and self.can(perm))

    def can_decide(self, proposal_kind: str) -> bool:
        perm = PROPOSAL_PERMISSION.get(proposal_kind)
        return bool(perm and self.can(perm))

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"


def check_csrf(request: Request) -> None:
    """A cross-site page cannot set a custom header without a CORS preflight, which
    this API does not grant, so its presence proves the request came from our own
    interface. SameSite=Lax cookies are the first line; this is the second."""
    if request.method in UNSAFE and not request.headers.get(CSRF_HEADER):
        raise HTTPException(403, "Missing the X-Requested-With header required on changes.")


def current_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    check_csrf(request)
    found = find_session(db, request.cookies.get(COOKIE))
    if found is None:
        raise HTTPException(401, "Sign in to continue.")
    _, user = found
    principal = Principal(id=user.id, email=user.email, name=user.name, role=user.role,
                          teacher_name=user.teacher_name, permissions=permissions_for(user.role))
    request.state.user = principal
    return principal


def require(permission: str):
    def check(user: Principal = Depends(current_user)) -> Principal:
        if not user.can(permission):
            raise HTTPException(403, f"Your role ({user.role}) cannot do this. It needs {permission}.")
        return user
    check.__name__ = f"require_{permission.replace('.', '_')}"
    return check


def require_by_method(read: str, write: str):
    """One permission to look and another to change, for routers that are all one domain."""
    def check(request: Request, user: Principal = Depends(current_user)) -> Principal:
        needed = write if request.method in UNSAFE else read
        if not user.can(needed):
            raise HTTPException(403, f"Your role ({user.role}) cannot do this. It needs {needed}.")
        return user
    return check
