"""Uploading a document about a student.

Reading takes a minute or two on the local model, so an upload returns straight
away with the document in `processing`, and the worker reads it (app/jobs.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import ollama
from ..ai.documents import (EXTENSIONS, KINDS, MAX_BYTES, DocumentError,
                            chunk_text, extension_of, extract_text, sha256_of)
from ..auth.deps import Principal, require
from ..auth.scope import ensure_student
from ..config import get_settings
from ..db import get_db
from ..jobs import enqueue
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


def _require_model() -> None:
    h = ollama.health()
    if not h["reachable"]:
        raise HTTPException(503, h["error"] or "Ollama is not reachable.")
    if not h.get("model_installed", True):
        raise HTTPException(503, f"{settings.ollama_model} is not installed. Run: ollama pull {settings.ollama_model}")


@router.post("/students/{sid}/documents", status_code=202)
async def upload(
    sid: str,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("documents.upload")),
) -> dict:
    ensure_student(db, user, sid)
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
    db.flush()
    # Read by the worker. If it dies mid-read the job is retried, and if it keeps
    # failing the document is marked failed rather than left "processing".
    enqueue(db, "document_analysis", {"doc_id": doc.id}, commit=False)
    db.commit()
    db.refresh(doc)
    return _out(doc)


@router.get("/students/{sid}/documents")
def list_documents(sid: str, db: Session = Depends(get_db),
                   user: Principal = Depends(require("students.read"))) -> list[dict]:
    ensure_student(db, user, sid)
    student = db.scalar(select(Student).where(Student.sid == sid))
    if student is None:
        raise HTTPException(404, f"No student with SID {sid}")
    docs = db.scalars(select(StudentDocument).where(StudentDocument.student_id == student.id)
                      .order_by(StudentDocument.id.desc())).all()
    return [_out(d) for d in docs]


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db),
                 user: Principal = Depends(require("students.read"))) -> dict:
    d = db.get(StudentDocument, doc_id)
    if d is None:
        raise HTTPException(404, f"No document {doc_id}")
    ensure_student(db, user, d.student.sid)
    return _out(d, full=True)


@router.post("/documents/{doc_id}/analyze", status_code=202)
def reanalyse(doc_id: int, db: Session = Depends(get_db),
              user: Principal = Depends(require("documents.upload"))) -> dict:
    d = db.get(StudentDocument, doc_id)
    if d is None:
        raise HTTPException(404, f"No document {doc_id}")
    ensure_student(db, user, d.student.sid)
    if d.status == "processing":
        raise HTTPException(409, "That document is already being read.")
    _require_model()
    d.status, d.error = "processing", None
    enqueue(db, "document_analysis", {"doc_id": d.id}, commit=False)
    db.commit()
    return _out(d)


@router.delete("/documents/{doc_id}", status_code=204, dependencies=[Depends(require("plans.write"))])
def delete_document(doc_id: int, db: Session = Depends(get_db)):  # no return annotation: 204 carries no body
    d = db.get(StudentDocument, doc_id)
    if d is None:
        raise HTTPException(404, f"No document {doc_id}")
    db.delete(d)
    db.commit()
