"""Document reader tests.

None of these call Ollama. The checks that make a small model's reading safe to
show — verbatim quotes, no diagnoses, independent corroboration, severity that the
gradebook can raise — are pure functions, so they are tested directly. Upload
tests stub the model with output shaped like what qwen3:4b actually returned.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from app.ai import documents as D
from app.ai import ollama

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
sys.path.insert(0, str(SAMPLES))
import make_samples  # noqa: E402

NOTE = SAMPLES / "talia-barnard-teacher-note.txt"


@pytest.fixture(scope="module")
def note_text() -> str:
    return D.extract_text(NOTE.name, NOTE.read_bytes())[0]


@pytest.fixture
def talia(db):
    from app.analytics import build_signals
    return build_signals(db)["S-1507"]


# --- extraction ------------------------------------------------------------
def test_all_three_formats_extract_the_same_sentence():
    key = "loses track of what the question is asking partway through multi-step word problems"
    for ext in ("txt", "docx", "pdf"):
        p = SAMPLES / f"talia-barnard-teacher-note.{ext}"
        text, pages = D.extract_text(p.name, p.read_bytes())
        assert key in D.normalise(text), f"{ext} lost the key sentence"
        if ext == "pdf":
            assert pages == 1


def test_a_pdf_that_is_really_something_else_is_refused():
    with pytest.raises(D.DocumentError, match="not a PDF"):
        D.extract_text("report.pdf", b"just some text pretending")


def test_a_docx_that_is_really_something_else_is_refused():
    with pytest.raises(D.DocumentError, match="not a Word document"):
        D.extract_text("note.docx", b"%PDF-1.4 not a zip")


def test_unsupported_type_is_refused():
    with pytest.raises(D.DocumentError, match="not a supported type"):
        D.extract_text("photo.jpg", b"\xff\xd8\xff")


def test_a_pdf_with_no_text_explains_the_scan_limitation():
    blank = make_samples.make_pdf([])
    with pytest.raises(D.DocumentError, match="no vision model"):
        D.extract_text("scan.pdf", blank)


def test_oversize_is_refused():
    with pytest.raises(D.DocumentError, match="limit is 10 MB"):
        D.extract_text("big.txt", b"a" * (D.MAX_BYTES + 1))


def test_chunks_respect_paragraphs_and_size():
    paras = [("Sentence about the student. " * 30).strip() for _ in range(12)]
    text = "\n\n".join(paras)
    chunks = D.chunk_text(text, size=2000)
    assert len(chunks) > 1
    assert all(len(c) <= 2000 for c in chunks)
    assert D.normalise(" ".join(chunks)) == D.normalise(text), "chunking must not lose or duplicate text"


def test_one_enormous_paragraph_is_still_split():
    text = "The student worked hard today. " * 1200
    chunks = D.chunk_text(text, size=3000)
    assert all(len(c) <= 3000 for c in chunks)


# --- check 1: quotes must really be in the document ------------------------
def test_a_real_quote_is_accepted(note_text):
    assert D.quote_in_document(
        "she loses track of what the question is asking partway through multi-step word problems",
        D.normalise(note_text))


def test_case_curly_quotes_and_line_breaks_are_forgiven(note_text):
    assert D.quote_in_document(
        "HER ABSENCES ARE\nclustered on Mondays", D.normalise(note_text))


def test_an_ellipsis_may_join_two_real_fragments_in_order(note_text):
    n = D.normalise(note_text)
    assert D.quote_in_document("Her absences are clustered on Mondays ... lunchtime review sessions", n)
    assert not D.quote_in_document("lunchtime review sessions ... Her absences are clustered", n), \
        "fragments joined out of order are not a quotation"


def test_a_paraphrase_is_not_a_quotation(note_text):
    assert not D.quote_in_document(
        "she struggles to understand what word problems are asking", D.normalise(note_text))


def test_an_invented_quote_is_rejected(note_text):
    assert not D.quote_in_document(
        "Talia is frequently disruptive and refuses to work with others", D.normalise(note_text))


def test_a_tiny_quote_proves_nothing(note_text):
    assert not D.quote_in_document("Mondays", D.normalise(note_text))


# --- check 2: no diagnoses -------------------------------------------------
@pytest.mark.parametrize("area", ["possible ADHD", "signs of dyslexia", "anxiety disorder",
                                  "may be on the spectrum", "undiagnosed learning disability"])
def test_findings_that_name_a_condition_are_withheld(area, note_text, talia):
    out = D.review([{"area": area, "type": "need", "severity": "high",
                     "quote": "finds it hard to settle into written work at home",
                     "explanation": "", "suggested_support": "check-in"}], note_text, talia)
    assert out.findings == []
    assert "condition" in out.rejected[0]["reason"]
    assert any("diagnostic" in n for n in out.notices)


def test_describing_behaviour_is_fine(note_text, talia):
    out = D.review([{"area": "settling into written work", "type": "need", "severity": "medium",
                     "quote": "finds it hard to settle into written work at home",
                     "explanation": "Takes a long time to start writing.", "suggested_support": "check-in"}],
                   note_text, talia)
    assert len(out.findings) == 1 and not out.rejected


# --- check 3: independent corroboration ------------------------------------
def test_a_strand_named_in_the_finding_is_matched(talia):
    g = D.corroborate({"area": "multi-step word problems", "type": "need",
                       "quote": "loses track partway through multi-step word problems"}, talia)
    assert g["verdict"] == "agrees"
    assert any(e["source"].startswith("word problems") for e in g["evidence"])


def test_a_word_is_not_stretched_to_a_whole_department(talia):
    """Regression: "writing" matched all of Humanities and cited Model UN's grade
    as evidence about short stories."""
    g = D.corroborate({"area": "narrative structure", "type": "strength",
                       "quote": "Her short stories in Creative Writing have a clear narrative structure"}, talia)
    sources = " ".join(e["source"] for e in g["evidence"])
    assert "Model UN" not in sources
    assert "ENG-201" in sources


def test_missing_work_is_scoped_to_the_class_named(talia):
    """Regression: an algebra homework finding cited every graded piece in the school."""
    g = D.corroborate({"area": "algebra homework", "type": "need",
                       "quote": "has not turned in three of the last five algebra assignments"}, talia)
    missing = next(e for e in g["evidence"] if e["kind"] == "missing")
    assert "MAT-150" in missing["source"]
    assert missing["detail"].endswith("of 9 graded pieces missing")


def test_disagreement_is_reported_not_hidden(talia):
    strong = max((s for c in talia.courses for s in c.skills), key=lambda s: s.pct)
    g = D.corroborate({"area": strong.skill, "type": "need",
                       "quote": f"struggles badly with {strong.skill}"}, talia)
    if strong.pct >= 85:
        assert g["verdict"] == "disagrees"


def test_no_evidence_is_its_own_verdict(talia):
    assert D.corroborate({"area": "tying shoelaces", "type": "need",
                          "quote": "cannot tie shoelaces quickly"}, talia)["verdict"] == "no-evidence"


# --- severity ---------------------------------------------------------------
def test_severity_is_raised_by_a_failing_strand(talia):
    """Regression: the model rated word problems "low" for a student at 13% on them."""
    f = {"area": "multi-step word problems", "type": "need", "severity": "low",
         "quote": "loses track partway through multi-step word problems"}
    f["gradebook"] = D.corroborate(f, talia)
    sev, note = D.calibrate_severity(f)
    assert sev == "high" and "Raised from low" in note


def test_severity_is_never_lowered(talia):
    f = {"area": "tying shoelaces", "type": "need", "severity": "high", "quote": "x"}
    f["gradebook"] = D.corroborate(f, talia)
    assert D.calibrate_severity(f) == ("high", None)


def test_strengths_are_left_alone(talia):
    f = {"area": "exposure", "type": "strength", "severity": "low", "quote": "x"}
    f["gradebook"] = D.corroborate(f, talia)
    assert D.calibrate_severity(f)[0] == "low"


# --- review end to end ------------------------------------------------------
def test_review_keeps_real_findings_and_withholds_the_rest(note_text, talia):
    raw = [
        {"area": "multi-step word problems", "type": "need", "severity": "low",
         "quote": "loses track of what the question is asking partway through multi-step word problems",
         "explanation": "", "suggested_support": "tutoring"},
        {"area": "disruptive behaviour", "type": "need", "severity": "high",
         "quote": "Talia is frequently disruptive in class", "explanation": "", "suggested_support": "check-in"},
        {"area": "possible ADHD", "type": "need", "severity": "high",
         "quote": "finds it hard to settle into written work at home", "explanation": "", "suggested_support": "check-in"},
        {"area": "composition and exposure", "type": "strength", "severity": "medium",
         "quote": "her photographs show a real eye for composition and exposure",
         "explanation": "", "suggested_support": "tutoring"},
    ]
    out = D.review(raw, note_text, talia)
    kept = {f["area"] for f in out.findings}
    assert kept == {"multi-step word problems", "composition and exposure"}
    assert len(out.rejected) == 2
    word = next(f for f in out.findings if f["area"] == "multi-step word problems")
    assert word["severity"] == "high"
    photo = next(f for f in out.findings if f["type"] == "strength")
    assert photo["suggested_support"] == "enrichment", "a strength is never routed to tutoring"
    assert out.findings[0]["type"] == "need", "needs are listed before strengths"
    assert "multi-step word problems" in out.summary and "2 claims withheld" in out.summary


def test_duplicates_are_collapsed(note_text, talia):
    f = {"area": "attendance", "type": "need", "severity": "medium",
         "quote": "Her absences are clustered on Mondays", "explanation": "", "suggested_support": "attendance-plan"}
    assert len(D.review([f, dict(f)], note_text, talia).findings) == 1


# --- the transport: no silent truncation -----------------------------------
def test_every_request_sets_the_context_window(monkeypatch):
    captured = {}

    def fake_post(path, body, timeout):
        captured.update(body)
        return {"message": {"content": "{}"}, "prompt_eval_count": 50}

    monkeypatch.setattr(ollama, "_post", fake_post)
    ollama.chat([{"role": "user", "content": "hi"}])
    assert captured["options"]["num_ctx"] == ollama.settings.ollama_num_ctx


def test_oversize_input_is_refused_before_sending(monkeypatch):
    monkeypatch.setattr(ollama, "_post", lambda *a, **k: pytest.fail("should not have been sent"))
    too_big = "x" * (ollama.settings.ollama_num_ctx * ollama.CHARS_PER_TOKEN_FLOOR + 10)
    with pytest.raises(ollama.OllamaError, match="silently cut"):
        ollama.chat([{"role": "user", "content": too_big}])


def test_truncation_is_detected_from_the_reported_token_count():
    # Measured: a 49,825-character prompt came back as 2,050 tokens at the default window.
    assert ollama.looks_truncated(49825, 2050)
    assert not ollama.looks_truncated(49825, 8442)


# --- the upload API ----------------------------------------------------------
FAKE_FINDINGS = {"findings": [
    {"area": "multi-step word problems", "type": "need", "severity": "low",
     "quote": "loses track of what the question is asking partway through multi-step word problems",
     "explanation": "Sets up steps then answers a different question.", "suggested_support": "tutoring"},
    {"area": "attendance", "type": "need", "severity": "medium",
     "quote": "Her absences are clustered on Mondays", "explanation": "", "suggested_support": "attendance-plan"},
    {"area": "invented", "type": "need", "severity": "high",
     "quote": "Talia refuses to do any group work", "explanation": "", "suggested_support": "check-in"},
]}


@pytest.fixture
def model_up(monkeypatch):
    import json as _json

    monkeypatch.setattr(ollama, "health", lambda: {
        "reachable": True, "error": None, "model": "qwen3:4b", "models": ["qwen3:4b"],
        "model_installed": True, "capabilities": ["tools"], "can_run_agents": True})
    monkeypatch.setattr(D, "chat", lambda messages, **k: ollama.ChatReply(
        content=_json.dumps(FAKE_FINDINGS), thinking="", prompt_tokens=900))


def _upload(client, sid, path: Path, kind="teacher-note", name=None, data=None):
    return client.post(f"/api/students/{sid}/documents",
                       files={"file": (name or path.name, io.BytesIO(data if data is not None else path.read_bytes()))},
                       data={"kind": kind})


def test_upload_reads_and_stores_verified_findings(client, model_up):
    r = _upload(client, "S-1507", SAMPLES / "talia-barnard-teacher-note.pdf")
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    try:
        d = client.get(f"/api/documents/{doc_id}").json()
        assert d["status"] == "done", d.get("error")
        assert d["needs"] == 2 and d["withheld"] == 1
        word = next(f for f in d["findings"] if f["area"] == "multi-step word problems")
        assert word["severity"] == "high" and word["gradebook"]["verdict"] == "agrees"
        assert d["rejected"][0]["area"] == "invented"
        listed = client.get("/api/students/S-1507/documents").json()
        assert any(x["id"] == doc_id for x in listed)
        assert "text" not in listed[0], "the list view does not ship document text"
    finally:
        assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_the_same_document_twice_is_refused(client, model_up):
    path = SAMPLES / "talia-barnard-teacher-note.txt"
    first = _upload(client, "S-1507", path).json()["id"]
    try:
        again = _upload(client, "S-1507", path)
        assert again.status_code == 409
        assert "already has this document" in again.json()["detail"]
    finally:
        client.delete(f"/api/documents/{first}")


def test_upload_validation(client, model_up):
    note = SAMPLES / "talia-barnard-teacher-note.txt"
    assert _upload(client, "S-NOPE", note).status_code == 404
    assert _upload(client, "S-1507", note, kind="horoscope").status_code == 422
    assert _upload(client, "S-1507", note, name="photo.jpg").status_code == 415
    fake_pdf = _upload(client, "S-1507", note, name="note.pdf")
    assert fake_pdf.status_code == 422 and "not a PDF" in fake_pdf.json()["detail"]
    blank = _upload(client, "S-1507", note, name="scan.pdf", data=make_samples.make_pdf([]))
    assert blank.status_code == 422 and "vision model" in blank.json()["detail"]


def test_upload_is_refused_when_the_model_is_missing(client, monkeypatch):
    monkeypatch.setattr(ollama, "health", lambda: {
        "reachable": False, "error": "Cannot reach Ollama at http://localhost:11434",
        "models": [], "model": "qwen3:4b", "can_run_agents": False})
    r = _upload(client, "S-1507", SAMPLES / "talia-barnard-teacher-note.docx")
    assert r.status_code == 503


def test_a_failed_read_is_recorded_not_stuck(client, monkeypatch, model_up):
    def boom(*a, **k):
        raise ollama.OllamaError("Cannot reach Ollama")
    monkeypatch.setattr(D, "chat", boom)
    r = _upload(client, "S-1507", SAMPLES / "talia-barnard-teacher-note.docx")
    doc_id = r.json()["id"]
    try:
        d = client.get(f"/api/documents/{doc_id}").json()
        assert d["status"] == "failed" and "Cannot reach Ollama" in d["error"]
    finally:
        client.delete(f"/api/documents/{doc_id}")
