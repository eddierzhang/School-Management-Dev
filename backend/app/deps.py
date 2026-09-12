"""Signals are recomputed per request and memoised for its duration.

The whole record is ~60 students and a few thousand scores, so a full pass costs
single-digit milliseconds — cheaper and far less error-prone than maintaining a
denormalised risk column that can drift from the grades it claims to summarise.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from .analytics import StudentSignal, build_signals
from .db import get_db


def signals(db: Session = Depends(get_db)) -> dict[str, StudentSignal]:
    return build_signals(db)
