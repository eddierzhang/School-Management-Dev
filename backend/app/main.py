from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .routers import agents, courses, interventions, meta, scores, students, support

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
          interventions.router, scores.router, agents.router):
    app.include_router(r, prefix="/api")
