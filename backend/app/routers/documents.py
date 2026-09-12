"""Uploading a document about a student.

Reading takes a minute or two on the local model, so an upload returns straight
away with the document in `processing` and the analysis runs in the background.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import ollama
from ..ai.documents import (EXTENSIONS, KINDS, MAX_BYTES, DocumentError, analyse_in_background,
                            chunk_text, extension_of, extract_text, sha256_of)
from ..config import get_settings
from ..db import get_db
from ..models import Student, StudentDocument

router = APIRouter(tags=["documents"])
settings = get_settings()


def _out(d: StudentDocument, full: bool = False) -> dict:
    out = {
        "id": d.id, "student_sid": d.student.sid, "student_name": d.student.name,
        "filename": d.filename, "kind": d.kind, "pages": d.pages, "chars": d.chars,
        "status": d.status, "summary": d.summary, "chunks": d.chunks, "model": d.model,
        "duration_ms": d.duration_ms, "error": d.error,
        "needs": sum(1 for f in d.findings or [] if f.get("type") == "need"),
        "strengths": sum(1 for f in d.findings or [] if f.get("type") == "strength"),
        "withheld": len(d.rejected or []),
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "analysed_at": d.analysed_at.isoformat() if d.analysed_at else None,
    }
    if full:
        out |= {"findings": d.findings or [], "rejected": d.rejected or [],
                "notices": d.notices or [], "text": d.text}
    return out


def _reap(db: Session) -> None:
    """A document whose analysis process died would otherwise say "processing" for ever."""
    cutoff = datetime.utcnow() - timedelta(minutes=20)
    stale = db.scalars(select(StudentDocument).where(
        StudentDocument.status == "processing", StudentDocument.uploaded_at < cutoff)).all()
    for d in stale:
        d.status = "failed"
        d.error = "The analysis stopped without finishing — the server restarted mid-read. Run it again."
    if stale:
        db.commit()


def _require_model() -> None:
    h = ollama.health()
    if not h["reachable"]:
        raise HTTPException(503, h["error"] or "Ollama is not reachable.")
    if not h.get("model_installed", True):
        raise HTTPException(503, f"{settings.ollama_model} is not installed. Run: ollama pull {settings.ollama_model}")


@router.post("/students/{sid}/documents", status_code=202)
async def upload(
    sid: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    db: Session = Depends(get_db),
) -> dict:
    student = db.scalar(select(Student).where(Student.sid == sid))
    if student is None:
        raise HTTPException(404, f"No student with SID {sid}")
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of: {', '.join(KINDS)}")
    if extension_of(file.filename or "") not in EXTENSIONS:
        raise HTTPException(415, "Upload a PDF, a Word document (.docx), or a text file.")

    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That file is over the 10 MB limit.")
    try:
        text, pages = extract_text(file.filename or "document", data)
    except DocumentError as e:
        raise HTTPException(422, str(e)) from e

    digest = sha256_of(data)
    existing = db.scalar(select(StudentDocument).where(
        StudentDocument.student_id == student.id, StudentDocument.sha256 == digest))
    if existing is not None:
        raise HTTPException(409, f"{student.name} already has this document (\"{existing.filename}\"). "
                                 "Open it, or re-run its analysis.")
    _require_model()

    doc = StudentDocument(
        student_id=student.id, filename=(file.filename or "document")[:255],
        content_type=EXTENSIONS[extension_of(file.filename or "")], kind=kind, sha256=digest,
        pages=pages, chars=len(text), text=text, status="processing",
        chunks=len(chunk_text(text)), model=settings.ollama_model,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    background.add_task(analyse_in_background, doc.id)
    return _out(doc)


@router.get("/students/{sid}/documents")
def list_documents(sid: str, db: Session = Depends(get_db)) -> list[dict]:
    student = db.scalar(select(Student).where(Student.sid == sid))
    if student is None:
        raise HTTPException(404, f"No student with SID {sid}")
    _reap(db)
    docs = db.scalars(select(StudentDocument).where(StudentDocument.student_id == student.id)
                      .order_by(StudentDocument.id.desc())).all()
    return [_out(d) for d in docs]


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)) -> dict:
    _reap(db)
    d = db.get(StudentDocument, doc_id)
    if d is None:
        raise HTTPException(404, f"No document {doc_id}")
    return _out(d, full=True)


@router.post("/documents/{doc_id}/analyze", status_code=202)
def reanalyse(doc_id: int, background: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    d = db.get(StudentDocument, doc_id)
    if d is None:
        raise HTTPException(404, f"No document {doc_id}")
    if d.status == "processing":
        raise HTTPException(409, "That document is already being read.")
    _require_model()
    d.status, d.error = "processing", None
    d.uploaded_at = datetime.utcnow()           # restarts the stale-read clock
    db.commit()
    background.add_task(analyse_in_background, d.id)
    return _out(d)


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db)):  # no return annotation: 204 carries no body
    d = db.get(StudentDocument, doc_id)
    if d is None:
        raise HTTPException(404, f"No document {doc_id}")
    db.delete(d)
    db.commit()
