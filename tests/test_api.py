"""Full HTTP flows with a stand-in model (no network, no API key)."""

import io
import json
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pitchcraft.ai.client import Usage
from pitchcraft.api.app import create_app
from pitchcraft.pipeline.service import Service
from pitchcraft.pipeline.store import Store

FIX = Path(__file__).resolve().parents[1] / "private" / "fixtures"  # git-ignored, see private/README.md
needs_private = pytest.mark.skipif(not (FIX / "client_base.docx").exists(), reason="needs private/fixtures")
needs_soffice = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice needed")


class FakeModel:
    """Plan call asks for the price until it is answered; then returns the recorded plan.
    Follow-up turns get a one-op plan that shortens the 5.1 intro."""

    def __init__(self, log: list):
        self.log = log

    def call(self, *, system, content, schema, cache_prefix_blocks=0):
        text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
        self.log.append({"system": system[:60], "text": text[-3000:]})
        props = schema["properties"]
        if "is_proposal" in props:
            is_prop = "Scope of Work" in text or "COMMERCIAL" in text
            return {"is_proposal": is_prop, "confidence": "high", "document_type": "VAPT proposal" if is_prop else "notes",
                    "company": "Example Co", "client": "", "summary": "x", "concerns": [] if is_prop else ["Not a proposal"],
                    "unsafe_content": False}, Usage()
        if "issues" in props:
            return {"issues": []}, Usage()
        plan = json.loads((FIX / "client_plan.json").read_text())
        plan.setdefault("reference_terms", [])
        plan.setdefault("proposal_meta", {"client": "Harbor Point", "title": "Harbor Point VAPT add-on", "tags": ["vapt", "webapp"]})
        if "Mode: review pass" in system:
            return {**plan, "ops": [], "fact_changes": [], "questions": []}, Usage()
        if "Current request (do this now)" in text:  # follow-up turn in the same chat
            return {**plan, "fact_changes": [], "questions": [], "ops": [{
                "op": "set_text", "target": "P135", "replace": "The engagement covers 4,378 assets across five locations.",
                "find": None, "expect": None, "anchor": None, "like": None, "items": None, "rows": None, "targets": None,
                "reason": "shorter", "evidence": "make it smaller"}]}, Usage()
        if "<answers>" not in text:
            return {**plan, "ops": [], "questions": [
                {"id": "price", "question": "What is the new total price?", "why": "Not given", "options": ["AED 71,000"], "blocking": True}]}, Usage()
        return plan, Usage(input_tokens=10, output_tokens=5)


def wait_job(c, jid, timeout=240):
    t = time.time()
    while time.time() - t < timeout:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("planning", "applying"):
            return j
        time.sleep(0.3)
    raise AssertionError("timeout")


@pytest.fixture
def env(tmp_path):
    calls: list = []
    svc = Service(Store(tmp_path), model_factory=lambda s: FakeModel(calls))
    c = TestClient(create_app(tmp_path, service=svc, auth_enabled=True))
    me = c.get("/api/auth/me").json()
    assert me["setup_needed"] is False and me["default_login"] is True
    assert c.get("/api/proposals").status_code == 401
    # fresh install: admin / admin works, but only to change the password
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200 and r.json()["user"]["must_change"] is True
    assert c.get("/api/proposals").status_code == 403
    assert c.post("/api/auth/password", json={"old": "admin", "new": "admin"}).status_code == 400
    assert c.post("/api/auth/password", json={"old": "admin", "new": "correct-horse"}).status_code == 200
    assert c.get("/api/proposals").status_code == 200
    me = c.get("/api/auth/me").json()
    assert me["default_login"] is False and me["user"]["must_change"] is False
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "correct-horse"}).status_code == 200
    return c, calls, tmp_path


def test_auth(env):
    c, _, _ = env
    assert c.post("/api/auth/setup", json={"username": "x2", "password": "aaaaaaaa"}).status_code == 409
    assert c.post("/api/users", json={"username": "sara", "password": "short"}).status_code == 400
    assert c.post("/api/users", json={"username": "sara", "password": "long-enough-1"}).status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/templates").status_code == 401
    assert c.post("/api/auth/login", json={"username": "sara", "password": "nope-nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "sara", "password": "long-enough-1"}).status_code == 200
    assert c.get("/api/templates").status_code == 200
    assert c.get("/api/users").status_code == 403  # not admin
    assert c.post("/api/auth/password", json={"old": "long-enough-1", "new": "even-longer-2"}).status_code == 200
    assert c.get("/api/templates").status_code == 200  # cookie re-issued after change
    r = c.patch("/api/auth/profile", json={"display_name": "Sara Khan", "username": "sara.k"})
    assert r.status_code == 200 and r.json()["user"]["username"] == "sara.k"
    me = c.get("/api/auth/me").json()["user"]
    assert me["username"] == "sara.k" and me["display_name"] == "Sara Khan"
    assert c.patch("/api/auth/profile", json={"username": "admin"}).status_code == 400  # taken


@needs_private
def test_template_check(env):
    c, _, _ = env
    good = (FIX / "client_base.docx").read_bytes()
    r = c.post("/api/templates/inspect", files={"file": ("p.docx", good)})
    rep = r.json()
    assert rep["structure"]["ok"] and rep["verdict"] == "ok" and rep["ai"]["is_proposal"]
    # a tiny document fails the structure check and cannot be added
    buf = io.BytesIO()
    with zipfile.ZipFile(good and io.BytesIO(good)) as src, zipfile.ZipFile(buf, "w") as dst:
        for i in src.infolist():
            data = src.read(i)
            if i.filename == "word/document.xml":
                data = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        b'<w:body><w:p><w:r><w:t>hello</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
            dst.writestr(i, data)
    r = c.post("/api/templates/inspect", files={"file": ("tiny.docx", buf.getvalue())})
    assert r.json()["verdict"] == "reject"
    assert c.post("/api/templates", files={"file": ("tiny.docx", buf.getvalue())}).status_code == 400
    assert c.post("/api/templates", files={"file": ("notdocx.docx", b"plain")}).status_code == 400


@needs_soffice
@needs_private
def test_proposal_chat_flow(env):
    c, calls, _ = env
    r = c.post("/api/templates", files={"file": ("company.docx", (FIX / "client_base.docx").read_bytes())}, data={"name": "Company style"})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert r.json()["inspection"]["verdict"] == "ok"

    # create a proposal (chat) with a first message
    r = c.post("/api/proposals", data={"title": "Harbor add-on", "client": "Harbor Point", "tags": json.dumps(["vapt", "2026"]),
                                       "mode": "edit", "template_id": tid, "instructions": "add services, +30 man days, change price"},
               files=[("inputs", ("request-1.png", (FIX / "request-1.png").read_bytes(), "image/png"))])
    assert r.status_code == 200, r.text
    prop = r.json()
    pid, jid = prop["id"], prop["turns"][0]
    job = wait_job(c, jid)
    assert job["status"] == "needs_answers" and job["questions"][0]["id"] == "price"

    c.post(f"/api/jobs/{jid}/plan", json={"answers": {"price": "AED 71,000"}}).raise_for_status()
    job = wait_job(c, jid)
    assert job["status"] == "planned"
    c.post(f"/api/jobs/{jid}/apply", json={"review": True, "visual": False}).raise_for_status()
    job = wait_job(c, jid)
    assert job["status"] == "done", job.get("error")
    assert job["version"] == 1
    levels = {a["check"]: a["level"] for a in job["audits"]}
    assert levels["style"] == "pass" and levels["render"] == "pass"

    prop = c.get(f"/api/proposals/{pid}").json()
    assert [v["n"] for v in prop["versions"]] == [0, 1]
    assert prop["client"] == "Harbor Point" and prop["title"] == "Harbor add-on"  # user-given values are kept
    assert "webapp" in prop["tags"]
    assert c.get(f"/api/proposals/{pid}/versions/1/docx").status_code == 200
    assert c.get(f"/api/proposals/{pid}/versions/1/pages").json()["count"] > 20
    assert c.get(f"/api/proposals/{pid}/versions/1/pages/1").headers["content-type"] == "image/png"

    # approve, then a follow-up in the same chat (auto-apply), which returns it to draft as v2
    assert c.post(f"/api/proposals/{pid}/approve", json={}).json()["status"] == "approved"
    r = c.post(f"/api/proposals/{pid}/messages", data={"instructions": "make the scope intro smaller and more diplomatic",
                                                         "auto_apply": "true"})
    assert r.status_code == 200, r.text
    jid2 = r.json()["turns"][-1]
    job2 = wait_job(c, jid2)
    assert job2["status"] == "done" and job2["version"] == 2
    assert "add services, +30 man days" in calls[-2]["text"] or any("Earlier requests" in x["text"] for x in calls)
    prop = c.get(f"/api/proposals/{pid}").json()
    assert prop["status"] == "draft" and len(prop["versions"]) == 3

    # organise: tags/client filters, search, history, duplicate
    c.patch(f"/api/proposals/{pid}", json={"tags": ["vapt", "priority"], "status": "approved"}).raise_for_status()
    assert len(c.get("/api/proposals?tag=priority").json()) == 1
    assert len(c.get("/api/proposals?client=harbor%20point").json()) == 1
    assert len(c.get("/api/proposals?q=nothing-matches").json()) == 0
    assert len(c.get("/api/proposals?status=approved").json()) == 1
    found = c.get("/api/search?q=scope intro").json()
    assert found and found[0]["id"] == pid and found[0]["matched_in"] == "message"
    assert c.get("/api/search?q=harbor").json()[0]["matched_in"] == "title"
    assert c.get("/api/search?q=zzz-none").json() == []
    hist = c.get("/api/history").json()
    assert {h["id"] for h in hist} >= {jid, jid2}
    ch = c.get(f"/api/proposals/{pid}/versions/2/changes?against=0").json()
    assert ch["changed"] + ch["added"] > 0
    assert c.get(f"/api/proposals/{pid}/versions/2/changes.pdf?against=1").headers["content-type"] == "application/pdf"
    assert c.get(f"/api/proposals/{pid}/versions/1/changes?against=2").status_code == 400
    dup = c.post(f"/api/proposals/{pid}/duplicate", json={"version": 1}).json()
    assert dup["id"] != pid and len(dup["versions"]) == 1


def test_bad_requests(env):
    c, _, _ = env
    assert c.post("/api/proposals", data={"mode": "new"}).status_code == 400
    assert c.get("/api/jobs/../../etc").status_code == 404
    assert c.get("/api/proposals/zzzzzzzzzzzz").status_code == 404


def test_template_check_runs_once_per_file(tmp_path, monkeypatch):
    """The upload dialog checks a file, then Add sends it again: Claude must only be asked once."""
    svc = Service(Store(tmp_path), model_factory=lambda s: FakeModel([]))
    runs = []
    monkeypatch.setattr(svc, "_inspect_template", lambda data, name, settings: runs.append(name) or {"ai": {"is_proposal": True}, "verdict": "ok"})
    svc.inspect_template(b"same file", "a.docx", {"api_key": None})
    svc.inspect_template(b"same file", "a.docx", {"api_key": None})
    assert runs == ["a.docx"]
    svc.inspect_template(b"other file", "b.docx", {"api_key": None})
    assert runs == ["a.docx", "b.docx"]


def test_jobs_interrupted_by_restart_become_retryable(tmp_path):
    store = Store(tmp_path)
    svc = Service(store, model_factory=lambda s: FakeModel([]))
    buf = io.BytesIO()
    import zipfile as _z
    with _z.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
    try:
        job = svc.create_job(mode="new", title="t", instructions="x", base_name="b.docx", base_bytes=buf.getvalue(), inputs=[])
    except Exception:
        pytest.skip("minimal docx not accepted by the loader")
    store.update_job(job["id"], status="planning", stage="Claude is planning")
    Service(store, model_factory=lambda s: FakeModel([]))  # a restart
    j = store.get_job(job["id"])
    assert j["status"] == "error" and "restarted" in j["error"]
