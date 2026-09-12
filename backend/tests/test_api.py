import pytest


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_summary_bands_account_for_every_student(client):
    s = client.get("/api/summary").json()
    assert s["students"] == 60
    assert s["courses"] == 26
    assert s["needs_plan"] + s["watch"] + s["excelling"] + s["steady"] == s["students"]
    assert sum(b["count"] for b in s["bands"]) == s["students"]
    assert s["graded_assessments"] == 9 * s["courses"], "nine graded pieces per section so far"
    assert 0.7 < s["mean_attendance"] <= 1.0
    assert len(s["top_skill_gaps"]) > 0


def test_summary_has_all_four_bands_populated(client):
    """A dataset where nobody excels, or nobody struggles, cannot exercise the UI."""
    s = client.get("/api/summary").json()
    for band in ("needs_plan", "watch", "excelling", "steady"):
        assert s[band] > 0, f"no students in band {band}"


def test_students_list_and_filters(client):
    everyone = client.get("/api/students").json()
    assert len(everyone) == 60
    # One list covers every band, so the students tab can monitor the whole school.
    assert {s["band"] for s in everyone} == {"needs-plan", "watch", "steady", "excelling"}
    assert all(s["strongest_course"] for s in everyone if s["course_count"])
    assert all(s["standing"] == s["excel_index"] - s["struggle_index"] for s in everyone)
    # Netting the two hides a student who has both, so the flag has to catch them.
    assert any(s["mixed"] and s["band"] == "needs-plan" for s in everyone)

    by_standing = client.get("/api/students", params={"sort": "standing"}).json()
    assert by_standing[0]["standing"] <= by_standing[-1]["standing"]
    assert everyone[0]["struggle_index"] >= everyone[-1]["struggle_index"]

    watch = client.get("/api/students", params={"band": "needs-plan"}).json()
    assert watch and all(s["band"] == "needs-plan" for s in watch)

    g10 = client.get("/api/students", params={"grade": 10}).json()
    assert len(g10) == 15 and all(s["grade"] == 10 for s in g10)

    in_course = client.get("/api/students", params={"course": "MAT-150"}).json()
    assert 0 < len(in_course) < 60

    by_excel = client.get("/api/students", params={"sort": "excel"}).json()
    assert by_excel[0]["excel_index"] >= by_excel[-1]["excel_index"]

    hit = client.get("/api/students", params={"q": everyone[0]["name"].split()[0]}).json()
    assert any(s["sid"] == everyone[0]["sid"] for s in hit)


def test_students_list_rejects_bad_filters(client):
    assert client.get("/api/students", params={"band": "nonsense"}).status_code == 422
    assert client.get("/api/students", params={"grade": 8}).status_code == 422, "a high school: grades 9-12"


def test_student_detail_carries_reasons_and_recommendations(client):
    sid = client.get("/api/students", params={"band": "needs-plan"}).json()[0]["sid"]
    d = client.get(f"/api/students/{sid}").json()
    assert d["sid"] == sid
    assert d["courses"], "a student with no course signals cannot be banded"
    assert any(r["kind"] == "concern" for r in d["reasons"])
    assert d["recommendations"], "a struggling student must come with something to do"
    for r in d["recommendations"]:
        assert r["rationale"].strip(), "every recommendation states why"
        assert 1 <= r["priority"] <= 3
    assert 0 <= d["absence_rate"] <= 1


def test_student_detail_unknown_sid(client):
    assert client.get("/api/students/S-NOPE").status_code == 404


def test_courses_list_and_detail(client):
    courses = client.get("/api/courses").json()
    assert len(courses) == 26
    means = [c["class_mean"] for c in courses if c["class_mean"] is not None]
    assert means == sorted(means), "courses are ordered weakest-first"

    code = courses[0]["code"]
    d = client.get(f"/api/courses/{code}").json()
    assert d["course"]["code"] == code
    assert d["students"], "a course with a cohort reports its students"
    assert d["students"][0]["pct"] <= d["students"][-1]["pct"]
    assert d["skills"], "skill strands are what make 'struggling on what' answerable"
    assert sum(b["count"] for b in d["distribution"]) == len(d["students"])


def test_course_detail_unknown_code(client):
    assert client.get("/api/courses/XXX-999").status_code == 404


def test_watchlist_is_ranked_and_only_concern_bands(client):
    wl = client.get("/api/watchlist", params={"limit": 30}).json()
    assert wl
    assert all(s["band"] in ("needs-plan", "watch") for s in wl)
    idx = [s["struggle_index"] for s in wl]
    assert idx == sorted(idx, reverse=True)

    only_plan = client.get("/api/watchlist", params={"include_watch": False}).json()
    assert all(s["band"] == "needs-plan" for s in only_plan)


def test_strengths_can_include_students_who_also_struggle(client):
    st = client.get("/api/strengths", params={"limit": 40}).json()
    assert st
    assert all(s["excel_index"] >= 60 for s in st)
    idx = [s["excel_index"] for s in st]
    assert idx == sorted(idx, reverse=True)


def test_skill_gaps_surface_the_reteach_list(client):
    gaps = client.get("/api/skill-gaps", params={"limit": 60}).json()
    assert gaps
    means = [g["class_mean"] for g in gaps]
    assert means == sorted(means), "weakest strand first"
    for g in gaps:
        assert 0 <= g["share_below"] <= 1
        assert g["students_below"] <= g["cohort"]


def test_seeded_cohort_gap_is_detected(client):
    """The seeder makes 'word problems' hard for all of MAT-150; the engine
    should independently rediscover that from the scores alone."""
    gaps = client.get("/api/skill-gaps", params={"limit": 200}).json()
    mat = [g for g in gaps if g["course_code"] == "MAT-150"]
    assert mat
    weakest = min(mat, key=lambda g: g["class_mean"])
    assert weakest["skill"] == "word problems", [g["skill"] for g in mat]
    assert weakest["share_below"] > 0.4


def test_recommendations_endpoint_filters_by_priority(client):
    top = client.get("/api/recommendations", params={"priority": 1}).json()
    assert top and all(r["priority"] == 1 for r in top)


# --- interventions ---------------------------------------------------------
def test_intervention_lifecycle(client):
    sid = client.get("/api/students", params={"band": "needs-plan"}).json()[-1]["sid"]
    body = {"student_sid": sid, "kind": "tutoring", "title": "Small-group tutoring, Tuesdays",
            "rationale": "Below the support line with work submitted.", "course_code": "MAT-150"}

    created = client.post("/api/interventions", json=body)
    assert created.status_code == 201, created.text
    iv = created.json()
    assert iv["status"] == "active" and iv["student_sid"] == sid

    dupe = client.post("/api/interventions", json=body)
    assert dupe.status_code == 409, "the same active plan should not be openable twice"

    listed = client.get("/api/interventions", params={"status": "active"}).json()
    assert any(x["id"] == iv["id"] for x in listed)

    patched = client.patch(f"/api/interventions/{iv['id']}",
                           json={"status": "completed", "outcome": "Back above 75%."})
    assert patched.status_code == 200
    assert patched.json()["status"] == "completed"

    detail = client.get(f"/api/students/{sid}").json()
    assert any(x["id"] == iv["id"] for x in detail["interventions"])

    assert client.delete(f"/api/interventions/{iv['id']}").status_code == 204
    assert client.patch(f"/api/interventions/{iv['id']}", json={"status": "active"}).status_code == 404


def test_intervention_validation(client):
    assert client.post("/api/interventions", json={
        "student_sid": "S-NOPE", "kind": "tutoring", "title": "Nope"}).status_code == 404
    sid = client.get("/api/students").json()[0]["sid"]
    assert client.post("/api/interventions", json={
        "student_sid": sid, "kind": "astrology", "title": "Not a real kind"}).status_code == 422
    assert client.post("/api/interventions", json={
        "student_sid": sid, "kind": "tutoring", "title": "x"}).status_code == 422
    assert client.post("/api/interventions", json={
        "student_sid": sid, "kind": "tutoring", "title": "Valid title here",
        "course_code": "XXX-999"}).status_code == 404


# --- scores feed straight back into the signals ----------------------------
def test_recording_a_zero_moves_the_signal(client):
    """No cached risk column: a grade entered now changes the index on next read."""
    code = "MAT-150"
    roster = client.get(f"/api/courses/{code}").json()["students"]
    target = max(roster, key=lambda r: r["pct"])          # a strong student
    sid = target["sid"]
    items = [a for a in client.get(f"/api/courses/{code}/assessments").json() if a["graded"]]
    assert items

    before = next(c for c in client.get(f"/api/students/{sid}").json()["courses"]
                  if c["course_code"] == code)
    heaviest = max(items, key=lambda a: a["weight"] * a["max_points"])
    original = client.put("/api/scores", json={
        "assessment_id": heaviest["id"], "student_sid": sid, "points": 0.0})
    assert original.status_code == 200

    after = next(c for c in client.get(f"/api/students/{sid}").json()["courses"]
                 if c["course_code"] == code)
    assert after["pct"] < before["pct"], (before["pct"], after["pct"])
    assert after["struggle_index"] >= before["struggle_index"]

    # put it back so later tests see the seeded record
    restored = client.put("/api/scores", json={
        "assessment_id": heaviest["id"], "student_sid": sid,
        "points": heaviest["max_points"] * before["pct"] / 100})
    assert restored.status_code == 200


def test_score_validation(client):
    sid = client.get("/api/students").json()[0]["sid"]
    items = client.get("/api/courses/MAT-150/assessments").json()
    aid = items[0]["id"]
    assert client.put("/api/scores", json={
        "assessment_id": aid, "student_sid": sid, "points": 9999}).status_code == 422
    assert client.put("/api/scores", json={
        "assessment_id": aid, "student_sid": sid, "points": -1}).status_code == 422
    assert client.put("/api/scores", json={
        "assessment_id": 999999, "student_sid": sid, "points": 1}).status_code == 404


def test_marking_work_missing_is_recordable(client):
    """points=None is meaningful: not submitted, not 'no data'."""
    sid = client.get("/api/students").json()[0]["sid"]
    aid = client.get("/api/courses/MAT-150/assessments").json()[0]["id"]
    r = client.put("/api/scores", json={"assessment_id": aid, "student_sid": sid, "points": None})
    assert r.status_code == 200
    assert r.json()["points"] is None and r.json()["pct"] is None


def test_class_page_has_description_teacher_and_performance(client):
    d = client.get("/api/courses/MAT-150").json()
    c = d["course"]
    assert c["description"] and c["teacher"] == "S. Frankel"

    s = d["stats"]
    assert s["students"] == len(d["students"])
    assert 0 <= s["completion_rate"] <= 1 and 0 <= s["late_rate"] <= 1 and 0 <= s["absence_rate"] <= 1
    assert s["improving"] + s["declining"] <= s["students"]

    # graded work only, in due order, and every enrolled student accounted for on each piece
    dues = [a["due_on"] for a in d["assessments"]]
    assert dues == sorted(dues) and dues
    assert all(a["submitted"] + a["missing"] <= s["students"] for a in d["assessments"])

    # the teacher block lists this section among the teacher's sections
    assert "MAT-150" in {t["code"] for t in d["teacher"]["sections"]}
    assert d["teacher"]["students_taught"] >= s["students"]

    assert {i["sku"] for i in d["supplies"]} >= {"MAT-CAL-GRA"}
    assert all(p["sid"] for p in d["plans"])


def test_class_page_completion_matches_the_students_missing_work(client):
    d = client.get("/api/courses/SCI-210").json()
    graded = sum(r["graded_items"] for r in d["students"])
    missing = sum(r["missing"] for r in d["students"])
    assert d["stats"]["completion_rate"] == pytest.approx(1 - missing / graded, abs=0.001)
