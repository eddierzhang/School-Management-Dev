"""The engine and session factory.

The schema is owned by Alembic (`backend/alembic/versions/`): the app never
creates or alters tables at startup. Run `alembic upgrade head` before starting
it, which is what the deploy's `migrate` step and `seed.py` both do.
"""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _sqlite else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True,
                       pool_pre_ping=not _sqlite)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Named constraints, so a later migration can drop or alter one by name on any
# database (SQLite's batch mode needs names to rebuild a table).
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def alembic_config():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    cfg.attributes["configure_logger"] = False
    return cfg


def migrate() -> None:
    """Bring the database to the newest migration."""
    from alembic import command

    command.upgrade(alembic_config(), "head")


def schema_status() -> dict:
    """Which migration the database is at, and whether that is the newest one."""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    try:
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        current = None
    return {"current": current, "head": head, "up_to_date": current == head}


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
