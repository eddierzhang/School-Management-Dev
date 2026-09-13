"""Signing in and out, and who is signed in."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import oidc
from ..auth.deps import Principal, check_csrf, current_user
from ..auth.passwords import hash_password, password_problem, verify_password
from ..auth.permissions import ROLE_LABELS
from ..auth.sessions import COOKIE, end_session, start_session
from ..config import get_settings
from ..db import get_db
from ..models import AuditEvent, User

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
log = logging.getLogger("halverson.auth")


class LoginIn(BaseModel):
    email: str = Field(max_length=160)
    password: str = Field(max_length=1024)


def me_out(user: Principal) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "role_label": ROLE_LABELS.get(user.role, user.role), "teacher_name": user.teacher_name,
            "permissions": sorted(user.permissions), "modules": sorted(settings.enabled_modules)}


@router.get("/config")
def auth_config() -> dict:
    """What the sign-in screen should offer. Public."""
    return {"password_login": settings.password_login, "oidc": settings.oidc_enabled,
            "oidc_label": settings.oidc_button_label, "school": settings.school_name,
            "signup": _signup_open(), "signup_domains": settings.signup_domains,
            "signup_roles": [{"role": r, "label": ROLE_LABELS[r]} for r in REQUESTABLE_ROLES]}


# ---- asking for an account ------------------------------------------------------------
# Anyone can ask; only an administrator can say yes. Administrator is never requestable.
REQUESTABLE_ROLES = ("teacher", "counselor", "registrar", "business")
SIGNUP_RECEIVED = ("Thanks — your request has been sent. An administrator will review it, and you can sign "
                   "in once it is approved.")


def _signup_open() -> bool:
    # Requests set a password, so they need password sign-in to be on.
    return settings.signup_enabled and settings.password_login


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(max_length=1024)
    requested_role: str = Field(pattern="^(" + "|".join(REQUESTABLE_ROLES) + ")$")
    note: str | None = Field(default=None, max_length=1000)


@router.post("/signup", status_code=202)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Ask for an account. It is created inactive and pending an administrator's approval.

    The response is the same whether or not the email already has an account, so the
    form cannot be used to find out who has one.
    """
    check_csrf(request)
    if not _signup_open():
        raise HTTPException(404, "Accounts are created by an administrator here.")
    email = body.email.strip().lower()
    domains = settings.signup_domains
    if domains and email.rsplit("@", 1)[-1] not in domains:
        raise HTTPException(422, f"Use your school email address ({', '.join('@' + d for d in domains)}).")
    if problem := password_problem(body.password):
        raise HTTPException(422, problem)

    ip = (request.client.host if request.client else "")[:64]
    since = datetime.utcnow() - timedelta(hours=1)
    recent = db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.action == "auth.signup_requested", AuditEvent.ip == ip, AuditEvent.at >= since)) or 0
    if recent >= settings.signup_max_per_hour:
        raise HTTPException(429, "Too many account requests from this address. Try again later.")

    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is None:
        db.add(User(email=email, name=body.name.strip(), role=body.requested_role,
                    requested_role=body.requested_role, request_note=(body.note or "").strip() or None,
                    password_hash=hash_password(body.password), active=False, pending=True))
        db.commit()
        created = True
    else:
        created = False
    audit.record("auth.signup_requested", request=request, actor_email=email, status=202,
                 detail={"requested_role": body.requested_role, "new": created})
    return {"requested": True, "message": SIGNUP_RECEIVED}


def _recent_failures(db: Session, email: str) -> int:
    since = datetime.utcnow() - timedelta(minutes=settings.login_lockout_minutes)
    return db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.action == "auth.login_failed", AuditEvent.actor_email == email, AuditEvent.at >= since)) or 0


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    if not settings.password_login:
        raise HTTPException(403, "Password sign-in is turned off. Use your school account.")
    email = body.email.strip().lower()
    if _recent_failures(db, email) >= settings.login_max_failures:
        audit.record("auth.login_locked", request=request, actor_email=email, status=429)
        raise HTTPException(429, f"Too many failed attempts. Try again in {settings.login_lockout_minutes} minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is not None and password_ok and user.pending:
        # Only someone who knows the password learns the request is still waiting.
        audit.record("auth.login_pending", request=request, actor_email=email, status=403)
        raise HTTPException(403, "Your account request is waiting for an administrator to approve it.")
    if user is None or not user.active or not password_ok:
        audit.record("auth.login_failed", request=request, actor_email=email, status=401)
        raise HTTPException(401, "That email and password do not match an active account.")
    start_session(db, user, request, response)
    principal = Principal(id=user.id, email=user.email, name=user.name, role=user.role,
                          teacher_name=user.teacher_name, permissions=frozenset())
    audit.record("auth.login", request=request, actor=principal, status=200, detail={"method": "password"})
    return {"signed_in": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: Principal = Depends(current_user)) -> dict:
    end_session(db, request.cookies.get(COOKIE), response)
    audit.record("auth.logout", request=request, actor=user, status=200)
    return {"signed_out": True}


@router.get("/me")
def me(user: Principal = Depends(current_user)) -> dict:
    return me_out(user)


@router.get("/oidc/login")
def oidc_login() -> RedirectResponse:
    if not settings.oidc_enabled:
        raise HTTPException(404, "Sign-in through an identity provider is not configured.")
    try:
        url, cookie = oidc.begin()
    except (oidc.OIDCError, Exception) as e:
        log.error("OIDC sign-in could not start: %s", e)
        return RedirectResponse("/#/login?error=provider-unavailable", status_code=302)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(oidc.STATE_COOKIE, cookie, max_age=oidc.STATE_TTL, httponly=True,
                    secure=settings.secure_cookies, samesite="lax", path="/api/auth/oidc")
    return resp


@router.get("/oidc/callback")
def oidc_callback(request: Request, code: str | None = None, state: str | None = None,
                  error: str | None = None, db: Session = Depends(get_db)) -> RedirectResponse:
    if not settings.oidc_enabled:
        raise HTTPException(404, "Sign-in through an identity provider is not configured.")
    fail = RedirectResponse("/#/login?error=sign-in-failed", status_code=302)
    fail.delete_cookie(oidc.STATE_COOKIE, path="/api/auth/oidc")
    if error:
        audit.record("auth.login_failed", request=request, status=401, detail={"method": "oidc", "error": error[:80]})
        return fail
    try:
        claims = oidc.finish(code, state, request.cookies.get(oidc.STATE_COOKIE))
    except oidc.OIDCError as e:
        log.warning("OIDC sign-in failed: %s", e)
        audit.record("auth.login_failed", request=request, status=401, detail={"method": "oidc", "reason": str(e)[:200]})
        return fail

    email = str(claims["email"]).strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.active:
        audit.record("auth.login_failed", request=request, actor_email=email, status=403,
                     detail={"method": "oidc", "reason": "no active account"})
        resp = RedirectResponse("/#/login?error=not-registered", status_code=302)
        resp.delete_cookie(oidc.STATE_COOKIE, path="/api/auth/oidc")
        return resp

    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(oidc.STATE_COOKIE, path="/api/auth/oidc")
    start_session(db, user, request, resp)
    audit.record("auth.login", request=request, status=200, actor_email=user.email,
                 detail={"method": "oidc", "sub": str(claims.get("sub"))[:80]},
                 actor=Principal(id=user.id, email=user.email, name=user.name, role=user.role,
                                 teacher_name=user.teacher_name, permissions=frozenset()))
    return resp
