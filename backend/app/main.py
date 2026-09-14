import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .audit import AuditMiddleware
from .auth.deps import current_user
from .config import get_settings
from .db import schema_status
from .observability import configure
from .routers import (admin, agents, auth, courses, documents, finance, improvement, interventions, inventory,
                      manager, meta, schedule, scores, students, study_plans, support)

settings = get_settings()
log = logging.getLogger("halverson")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env != "test":
        configure("api")
    problems = settings.production_problems()
    if problems:
        raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(problems))
    # The schema is Alembic's job, run before the app starts. Starting against a
    # database that is behind would fail on the first query that touches a new
    # column, so say so plainly at startup; /api/ready reports it too.
    status = schema_status()
    if not status["up_to_date"]:
        log.error("Database schema is at %s but the code expects %s. Run `alembic upgrade head`.",
                  status["current"] or "nothing", status["head"])
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Student Support Platform API",
    version=__version__,
    description=(
        "Who is struggling, who is excelling, and on what. Every index is computed "
        "from the gradebook on read and reported with the named reasons behind it."
    ),
    # The schema is a map of every record the API exposes; it is for developers.
    docs_url=None if settings.public else "/docs",
    redoc_url=None,
    openapi_url=None if settings.public else "/openapi.json",
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        # Student records must not linger in shared browser or proxy caches.
        response.headers.setdefault("Cache-Control", "no-store")
    elif settings.static_dir:
        # The same headers Caddy sets in the production stack (frontend/Caddyfile).
        for k, v in STATIC_HEADERS.items():
            response.headers.setdefault(k, v)
    return response


STATIC_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}


app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Requested-With"],
)

# Public: sign-in, and the liveness and readiness checks (meta guards its own
# summary route).
app.include_router(auth.router, prefix="/api")
app.include_router(meta.router, prefix="/api")

# Everything else needs a signed-in person; each route then checks its permission.
signed_in = [Depends(current_user)]
for r in (students.router, courses.router, support.router, interventions.router, scores.router, agents.router,
          inventory.router, documents.router, finance.router, schedule.router, improvement.router, manager.router,
          study_plans.router, admin.router):
    app.include_router(r, prefix="/api", dependencies=signed_in)


if settings.static_dir:
    # One container for the public demo: the built interface beside the API. Any
    # path that is not a file is the single-page app's, except under /api.
    from pathlib import Path

    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = Path(settings.static_dir).resolve()
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def interface(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist):
            return FileResponse(file)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
