import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import schema_status
from .routers import (agents, courses, documents, finance, improvement, interventions, inventory, manager,
                      meta, schedule, scores, students, study_plans, support)

settings = get_settings()
log = logging.getLogger("halverson")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    title="Halverson Ridge — Academic Support API",
    version="0.1.0",
    description=(
        "Who is struggling, who is excelling, and on what. Every index is computed "
        "from the gradebook on read and reported with the named reasons behind it."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (meta.router, students.router, courses.router, support.router,
          interventions.router, scores.router, agents.router, inventory.router,
          documents.router, finance.router, schedule.router, improvement.router, manager.router,
          study_plans.router):
    app.include_router(r, prefix="/api")
