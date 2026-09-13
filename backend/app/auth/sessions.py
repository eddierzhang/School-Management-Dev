"""Server-side sessions behind an HttpOnly cookie.

The cookie holds a random token; the database holds its SHA-256. A session ends
when it expires, when the person signs out, or when an administrator deactivates
the account or changes its role (every session for that account is revoked).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, UserSession

settings = get_settings()
COOKIE = "hr_session"
# Refresh `last_seen_at` at most this often, so reads do not write on every request.
TOUCH_EVERY = timedelta(minutes=5)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request) -> str:
    # Behind the reverse proxy, uvicorn's --proxy-headers has already put the real
    # client address here; anything else in X-Forwarded-For is not trusted.
    return (request.client.host if request.client else "")[:64]


def start_session(db: Session, user: User, request: Request, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(UserSession(user_id=user.id, token_hash=_hash(token), created_at=now, last_seen_at=now,
                       expires_at=now + timedelta(hours=settings.session_hours),
                       ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:255]))
    user.last_login_at = now
    db.commit()
    response.set_cookie(COOKIE, token, max_age=int(settings.session_hours * 3600), httponly=True,
                        secure=settings.secure_cookies, samesite="lax", path="/")


def find_session(db: Session, token: str | None) -> tuple[UserSession, User] | None:
    if not token:
        return None
    row = db.execute(select(UserSession, User).join(User, User.id == UserSession.user_id)
                     .where(UserSession.token_hash == _hash(token))).first()
    if row is None:
        return None
    s, user = row
    now = datetime.utcnow()
    if s.revoked_at is not None or s.expires_at <= now or not user.active:
        return None
    if now - s.last_seen_at > TOUCH_EVERY:
        s.last_seen_at = now
        db.commit()
    return s, user


def end_session(db: Session, token: str | None, response: Response) -> None:
    if token:
        db.execute(update(UserSession).where(UserSession.token_hash == _hash(token))
                   .values(revoked_at=datetime.utcnow()))
        db.commit()
    response.delete_cookie(COOKIE, path="/")


def revoke_all(db: Session, user_id: int) -> None:
    db.execute(update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
               .values(revoked_at=datetime.utcnow()))
