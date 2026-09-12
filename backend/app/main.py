from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, SessionLocal, add_missing_columns, engine
from .demand import backfill_signups
from .routers import (agents, courses, documents, finance, improvement, interventions, inventory, meta,
                      schedule, scores, students, support)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    add_missing_columns()
    with SessionLocal() as db:
        backfill_signups(db)
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
          documents.router, finance.router, schedule.router, improvement.router):
    app.include_router(r, prefix="/api")
