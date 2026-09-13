"""The audit log: who changed what, who looked at which student, who signed in.

Most events are written by `AuditMiddleware`, so no route can forget to log:

* every POST, PUT, PATCH and DELETE under /api — including refused ones (a 403 is
  as worth knowing about as a 200)
* every GET of one student's record, documents, plans, class work or timetable

Sign-in, sign-out and failed sign-in are written by the auth routes themselves,
with the email that was tried. Request bodies are never logged: they hold the
very records the log exists to protect.

Writing an event uses its own session. If that fails, the failure is logged and
the response still goes out; the change it describes has already been committed.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from .db import SessionLocal
from .models import AuditEvent

log = logging.getLogger("halverson.audit")

# GET routes whose response is one person's record. Route templates, as FastAPI
# matched them, so a change to a path here is a change to what is logged.
SENSITIVE_READS = {
    "/api/students/{sid}": "student.view",
    "/api/students/{sid}/documents": "student.documents.list",
    "/api/documents/{doc_id}": "document.view",
    "/api/students/{sid}/study": "student.study.view",
    "/api/students/{sid}/classes/{code}/work": "student.classwork.view",
    "/api/students/{sid}/schedule": "student.schedule.view",
    "/api/students/{sid}/history": "student.history.view",
}

ENTITY_PARAMS = [("sid", "student"), ("doc_id", "document"), ("pid", "proposal"), ("iv_id", "intervention"),
                 ("plan_id", "plan"), ("txn_id", "transaction"), ("sku", "item"), ("run_id", "run"),
                 ("user_id", "user"), ("override_id", "override"), ("code", "course"), ("name", "agent")]


def record(action: str, *, request: Request | None = None, actor=None, status: int | None = None,
           entity_type: str | None = None, entity_id: str | None = None, detail: dict | None = None,
           actor_email: str | None = None) -> None:
    actor = actor or (getattr(request.state, "user", None) if request is not None else None)
    event = AuditEvent(
        at=datetime.utcnow(), action=action[:80],
        actor_id=getattr(actor, "id", None), actor_email=(getattr(actor, "email", None) or actor_email or "")[:160],
        actor_role=getattr(actor, "role", "") or "",
        method=request.method if request is not None else "",
        path=str(request.url.path)[:300] if request is not None else "",
        status=status, entity_type=entity_type, entity_id=(str(entity_id)[:80] if entity_id is not None else None),
        detail=detail or {}, ip=(request.client.host if request is not None and request.client else "")[:64],
        request_id=(getattr(request.state, "request_id", "") if request is not None else "")[:36])
    try:
        with SessionLocal() as db:
            db.add(event)
            db.commit()
    except Exception:
        log.exception("Could not write audit event %s", action)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", "")[:36] or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id

        path = request.url.path
        if not path.startswith("/api/") or path.startswith("/api/auth/"):
            return response
        # FastAPI reports the route's own path, without the /api prefix it is mounted under.
        route_path = getattr(request.scope.get("route"), "path", None)
        template = ("/api" + route_path if route_path and not route_path.startswith("/api/") else route_path) or path
        if response.status_code == 401:
            # Nobody signed in: nothing was done and nothing was seen, and logging
            # anonymous requests would let anyone fill the table.
            return response
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            action = f"{request.method} {template}"
        elif request.method == "GET" and template in SENSITIVE_READS and response.status_code < 400:
            action = SENSITIVE_READS[template]
        else:
            return response

        params = request.scope.get("path_params") or {}
        entity_type, entity_id = next(((kind, params[p]) for p, kind in ENTITY_PARAMS if p in params), (None, None))
        await run_in_threadpool(record, action, request=request, status=response.status_code,
                                entity_type=entity_type, entity_id=entity_id,
                                detail={k: str(v) for k, v in params.items()})
        return response
