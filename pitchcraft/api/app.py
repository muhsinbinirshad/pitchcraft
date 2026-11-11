"""HTTP API and static web UI."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..ai import MODELS
from ..engine import DocxPackage, PackageError
from ..engine.render import page_files, render, render_lock, renderer_status
from ..pipeline.service import Service, _clean_tags
from ..pipeline.store import Store
from .auth import COOKIE, SESSION_TTL, Auth, AuthError

WEB_DIR = Path(os.environ.get("PITCHCRAFT_WEB", Path(__file__).resolve().parents[2] / "frontend" / "out"))
MAX_UPLOAD = 50 * 1024 * 1024
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class PlanRequest(BaseModel):
    answers: dict[str, str] = {}
    instructions: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    auto_apply: bool = False
    review: bool = True
    visual: bool = False


class ApplyRequest(BaseModel):
    selected: Optional[list[int]] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    review: bool = True
    visual: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRequest(BaseModel):
    username: str
    password: str
    admin: bool = False


class PasswordRequest(BaseModel):
    old: str
    new: str


class ProposalPatch(BaseModel):
    title: Optional[str] = None
    client: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[str] = None


class VersionRequest(BaseModel):
    version: Optional[int] = None


class ProfileRequest(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None


class TemplatePatch(BaseModel):
    name: str


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"{upload.filename} is larger than 50 MB")
    return data


def _settings(req, api_key: str | None) -> dict:
    out = {"api_key": api_key or None, "model": req.model, "effort": req.effort,
           "review": getattr(req, "review", True), "visual": getattr(req, "visual", False)}
    if isinstance(req, PlanRequest):
        out["auto_apply"] = req.auto_apply
    return out


def _truthy(v: str) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


def _form_settings(model: str, effort: str, auto_apply: str, review: str, visual: str, key: str | None) -> dict:
    return {"api_key": key or None, "model": model or None, "effort": effort or None,
            "auto_apply": _truthy(auto_apply), "review": _truthy(review or "true"), "visual": _truthy(visual)}


_render_lock = render_lock
log = logging.getLogger("pitchcraft")


def create_app(data_dir: Path | None = None, service: Service | None = None, auth_enabled: bool | None = None) -> FastAPI:
    data_dir = data_dir or Path(os.environ.get("PITCHCRAFT_DATA", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    svc = service or Service(Store(data_dir))
    store = svc.store
    auth = Auth(data_dir)
    if auth_enabled is None:
        auth_enabled = os.environ.get("PITCHCRAFT_AUTH", "on").lower() not in ("off", "0", "false")
    if auth_enabled and auth.ensure_default_admin():
        log.warning("Created the default login admin / admin. It must be changed at first sign-in.")
    secure_cookie = _truthy(os.environ.get("PITCHCRAFT_SECURE_COOKIE", ""))
    svc.migrate_orphan_jobs()
    app = FastAPI(title="Pitchcraft", version="0.2.0")

    def not_found(_: Exception = None):
        raise HTTPException(404, "Not found")

    def job_or_none(jid: str) -> dict | None:
        try:
            return store.get_job(jid)
        except KeyError:
            return None

    # ---------- auth ----------
    def current_user(request: Request) -> dict:
        if not auth_enabled:
            return {"username": "local", "admin": True}
        user = auth.verify(request.cookies.get(COOKIE))
        if user is None:
            raise HTTPException(401, "Sign in required")
        # the default password unlocks nothing but changing it
        if user.get("must_change") and not request.url.path.startswith("/api/auth/"):
            raise HTTPException(403, "Change the default password first")
        return user

    def admin_user(user: dict = Depends(current_user)) -> dict:
        if not user["admin"]:
            raise HTTPException(403, "Admins only")
        return user

    def set_cookie(resp: Response, username: str) -> None:
        resp.set_cookie(COOKIE, auth.issue(username), max_age=SESSION_TTL, httponly=True, samesite="lax",
                        secure=secure_cookie, path="/")

    @app.get("/api/auth/me")
    def me(request: Request):
        if not auth_enabled:
            return {"user": {"username": "local", "admin": True}, "setup_needed": False, "auth": False}
        return {"user": auth.verify(request.cookies.get(COOKIE)), "setup_needed": not auth.has_users(), "auth": True,
                "default_login": auth.default_login_active()}

    @app.post("/api/auth/setup")
    def setup(req: LoginRequest, resp: Response):
        if auth.has_users():
            raise HTTPException(409, "Setup is already done")
        try:
            u = auth.add_user(req.username, req.password, admin=True)
        except AuthError as e:
            raise HTTPException(400, str(e))
        set_cookie(resp, u["username"])
        return {"user": u}

    @app.post("/api/auth/login")
    def login(req: LoginRequest, resp: Response):
        try:
            u = auth.check(req.username, req.password)
        except AuthError as e:
            time.sleep(0.4)
            raise HTTPException(401, str(e))
        set_cookie(resp, u["username"])
        return {"user": u}

    @app.post("/api/auth/logout")
    def logout(resp: Response):
        resp.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.post("/api/auth/password")
    def change_password(req: PasswordRequest, resp: Response, user: dict = Depends(current_user)):
        try:
            auth.set_password(user["username"], req.old, req.new)
        except AuthError as e:
            raise HTTPException(400, str(e))
        set_cookie(resp, user["username"])
        return {"ok": True}

    @app.patch("/api/auth/profile")
    def update_profile(req: ProfileRequest, resp: Response, user: dict = Depends(current_user)):
        if not auth_enabled:
            raise HTTPException(400, "Sign-in is turned off on this server")
        name = user["username"]
        try:
            if req.display_name is not None:
                auth.set_display_name(name, req.display_name)
            if req.username and req.username != name:
                auth.rename(name, req.username)
                svc.rename_author(name, req.username)
                name = req.username
                set_cookie(resp, name)
        except AuthError as e:
            raise HTTPException(400, str(e))
        return {"user": auth.public(name)}

    @app.get("/api/users")
    def users(_: dict = Depends(admin_user)):
        return auth.list_users()

    @app.post("/api/users")
    def add_user(req: UserRequest, _: dict = Depends(admin_user)):
        try:
            return auth.add_user(req.username, req.password, req.admin)
        except AuthError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/users/{username}")
    def delete_user(username: str, user: dict = Depends(admin_user)):
        if username == user["username"]:
            raise HTTPException(400, "You cannot delete your own account")
        try:
            auth.delete_user(username)
        except AuthError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    # ---------- meta ----------
    @app.get("/api/health")
    def health():
        r = renderer_status()
        return {"ok": True, "renderer": r["ok"], "renderer_missing": r["missing"],
                "server_key": bool(os.environ.get("ANTHROPIC_API_KEY")), "models": MODELS, "auth": auth_enabled}

    # ---------- templates ----------
    @app.get("/api/templates")
    def list_templates(_: dict = Depends(current_user)):
        return store.list_templates()

    @app.post("/api/templates/inspect")
    async def inspect_template(file: UploadFile = File(...), x_api_key: Optional[str] = Header(None),
                               _: dict = Depends(current_user)):
        """Check an uploaded .docx before it joins the library. Nothing is saved."""
        if not (file.filename or "").lower().endswith(".docx"):
            raise HTTPException(400, "Upload a .docx file")
        data = await _read(file)
        return svc.inspect_template(data, file.filename or "template.docx", {"api_key": x_api_key})

    @app.post("/api/templates")
    async def add_template(file: UploadFile = File(...), name: str = Form(""), force: str = Form("false"),
                           x_api_key: Optional[str] = Header(None), _: dict = Depends(current_user)):
        if not (file.filename or "").lower().endswith(".docx"):
            raise HTTPException(400, "Upload a .docx file")
        data = await _read(file)
        report = svc.inspect_template(data, file.filename or "template.docx", {"api_key": x_api_key})
        if report["verdict"] == "reject":
            raise HTTPException(400, "Not usable as a template: " + " ".join(report["structure"]["errors"]))
        if report["verdict"] == "warn" and not _truthy(force):
            return JSONResponse({"detail": "This document may not be a proposal. Review the check and confirm.",
                                 "report": report}, status_code=422)
        meta = store.add_template(name, file.filename, data)
        meta["inspection"] = report
        store._write(store.template_dir(meta["id"]) / "meta.json", meta)
        svc.render_template_preview(meta["id"])
        return meta

    @app.patch("/api/templates/{tid}")
    def rename_template(tid: str, req: TemplatePatch, _: dict = Depends(current_user)):
        try:
            meta = store.get_template(tid)
        except KeyError as e:
            not_found(e)
        name = req.name.strip()[:120]
        if name:
            meta["name"] = name
            store._write(store.template_dir(tid) / "meta.json", meta)
        return meta

    @app.post("/api/templates/{tid}/default")
    def set_default(tid: str, _: dict = Depends(current_user)):
        try:
            store.set_default_template(tid)
        except KeyError as e:
            not_found(e)
        return {"ok": True}

    @app.delete("/api/templates/{tid}")
    def delete_template(tid: str, _: dict = Depends(current_user)):
        try:
            store.delete_template(tid)
        except KeyError as e:
            not_found(e)
        return {"ok": True}

    @app.get("/api/templates/{tid}/pages")
    def template_pages(tid: str, _: dict = Depends(current_user)):
        try:
            d = store.template_dir(tid) / "preview"
            with _render_lock(d):
                if not any(d.glob("page-*.png")):
                    render(store.template_dir(tid) / "doc.docx", d, dpi=90)
        except KeyError as e:
            not_found(e)
        return {"count": len(page_files(d))}

    @app.get("/api/templates/{tid}/pdf")
    def template_pdf(tid: str, _: dict = Depends(current_user)):
        try:
            d = store.template_dir(tid) / "preview"
            with _render_lock(d):
                if not list(d.glob("*.pdf")):
                    render(store.template_dir(tid) / "doc.docx", d, dpi=90)
        except KeyError as e:
            not_found(e)
        pdfs = list(d.glob("*.pdf"))
        if not pdfs:
            raise HTTPException(404, "Not rendered")
        return FileResponse(pdfs[0], media_type="application/pdf", headers={"Cache-Control": "no-store"})

    @app.get("/api/templates/{tid}/preview/{n}")
    def template_preview(tid: str, n: int, _: dict = Depends(current_user)):
        try:
            pages = page_files(store.template_dir(tid) / "preview")
        except KeyError as e:
            not_found(e)
        if not 1 <= n <= len(pages):
            raise HTTPException(404, "No preview")
        return FileResponse(pages[n - 1], media_type="image/png")

    @app.get("/api/templates/{tid}/docx")
    def template_docx(tid: str, download: int = 0, _: dict = Depends(current_user)):
        try:
            meta = store.get_template(tid)
            d = store.template_dir(tid)
        except KeyError as e:
            not_found(e)
        return FileResponse(d / "doc.docx", filename=meta["filename"] if download else None, media_type=DOCX_MIME)

    # ---------- proposals ----------
    def proposal_full(pid: str) -> dict:
        prop = store.get_proposal(pid)
        prop["turn_jobs"] = [j for j in (job_or_none(jid) for jid in prop["turns"]) if j]
        return prop

    @app.get("/api/proposals")
    def list_proposals(q: str = "", status: str = "", client: str = "", tag: str = "",
                       date_from: str = "", date_to: str = "", _: dict = Depends(current_user)):
        out = []
        for p in store.list_proposals():
            if status and p.get("status") != status:
                continue
            if client and (p.get("client") or "").lower() != client.lower():
                continue
            if tag and tag.lower() not in [t.lower() for t in p.get("tags", [])]:
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(p["created"]))
            if (date_from and day < date_from) or (date_to and day > date_to):
                continue
            if q:
                hay = " ".join([p.get("title", ""), p.get("client", ""), " ".join(p.get("tags", [])),
                                p.get("notes") or "", p.get("base_name", "")]).lower()
                if q.lower() not in hay:
                    continue
            last = None
            for jid in reversed(p["turns"]):
                if (j := job_or_none(jid)) is not None:
                    last = {"status": j["status"], "instructions": j["instructions"][:200], "id": j["id"]}
                    break
            out.append({**{k: p.get(k) for k in ("id", "title", "client", "tags", "status", "created", "updated",
                                                  "approved_at", "approved_version", "created_by", "base_name",
                                                  "mode", "due_date", "notes")},
                        "versions": len(p["versions"]) - 1, "turns": len(p["turns"]), "last_turn": last})
        return out

    @app.post("/api/proposals")
    async def create_proposal(
        title: str = Form(""), client: str = Form(""), tags: str = Form("[]"), mode: str = Form("new"),
        instructions: str = Form(""), template_id: str = Form(""),
        model: str = Form(""), effort: str = Form(""), auto_apply: str = Form("false"),
        review: str = Form("true"), visual: str = Form("false"),
        base: Optional[UploadFile] = File(None), inputs: list[UploadFile] = File(default=[]),
        x_api_key: Optional[str] = Header(None), user: dict = Depends(current_user),
    ):
        if base is not None and base.filename:
            if not base.filename.lower().endswith(".docx"):
                raise HTTPException(400, "The base document must be a .docx file")
            base_bytes, base_name = await _read(base), base.filename
        elif template_id:
            try:
                meta = store.get_template(template_id)
                base_bytes = (store.template_dir(template_id) / "doc.docx").read_bytes()
            except KeyError as e:
                not_found(e)
            base_name = meta["filename"]
        else:
            raise HTTPException(400, "Choose a template or upload a document")
        try:
            tag_list = json.loads(tags) if tags.strip().startswith("[") else tags.split(",")
        except json.JSONDecodeError:
            tag_list = []
        files = [(f.filename or "file", await _read(f)) for f in inputs if f.filename]
        try:
            prop = svc.create_proposal(
                title=title, client=client, tags=tag_list, mode=mode if mode in ("new", "edit") else "new",
                base_name=base_name, base_bytes=base_bytes, instructions=instructions, inputs=files,
                template_id=template_id or None, author=user["username"],
                settings=_form_settings(model, effort, auto_apply, review, visual, x_api_key))
        except PackageError as e:
            raise HTTPException(400, str(e))
        return proposal_full(prop["id"])

    @app.get("/api/proposals/{pid}")
    def get_proposal(pid: str, _: dict = Depends(current_user)):
        try:
            return proposal_full(pid)
        except KeyError as e:
            not_found(e)

    @app.patch("/api/proposals/{pid}")
    def patch_proposal(pid: str, req: ProposalPatch, _: dict = Depends(current_user)):
        try:
            store.get_proposal(pid)
        except KeyError as e:
            not_found(e)
        changes = {k: v for k, v in req.model_dump().items() if v is not None}
        if "status" in changes and changes["status"] not in ("draft", "approved", "sent", "archived"):
            raise HTTPException(400, "Unknown status")
        if "tags" in changes:
            changes["tags"] = _clean_tags(changes["tags"])
        if "title" in changes:
            changes["title_auto"] = False
        if changes.get("status") == "draft":
            changes.update(approved_at=None, approved_version=None)
        store.update_proposal(pid, **changes)
        return proposal_full(pid)

    @app.delete("/api/proposals/{pid}")
    def delete_proposal(pid: str, _: dict = Depends(current_user)):
        try:
            store.delete_proposal(pid)
        except KeyError as e:
            not_found(e)
        return {"ok": True}

    @app.post("/api/proposals/{pid}/messages")
    async def post_message(
        pid: str, instructions: str = Form(""), base_version: str = Form(""),
        model: str = Form(""), effort: str = Form(""), auto_apply: str = Form("false"),
        review: str = Form("true"), visual: str = Form("false"),
        inputs: list[UploadFile] = File(default=[]), x_api_key: Optional[str] = Header(None),
        user: dict = Depends(current_user),
    ):
        if not instructions.strip() and not any(f.filename for f in inputs):
            raise HTTPException(400, "Write a message or attach a file")
        files = [(f.filename or "file", await _read(f)) for f in inputs if f.filename]
        try:
            svc.add_message(pid, instructions=instructions, inputs=files, author=user["username"],
                            settings=_form_settings(model, effort, auto_apply, review, visual, x_api_key),
                            base_version=int(base_version) if base_version.strip() else None)
        except KeyError as e:
            not_found(e)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return proposal_full(pid)

    @app.post("/api/proposals/{pid}/approve")
    def approve(pid: str, req: VersionRequest, user: dict = Depends(current_user)):
        try:
            svc.approve(pid, req.version, user["username"])
        except KeyError as e:
            not_found(e)
        return proposal_full(pid)

    @app.post("/api/proposals/{pid}/duplicate")
    def duplicate(pid: str, req: VersionRequest, user: dict = Depends(current_user)):
        try:
            return svc.duplicate(pid, req.version, user["username"])
        except KeyError as e:
            not_found(e)

    def version_path(pid: str, n: int) -> Path:
        try:
            return store.version_file(pid, n)
        except KeyError as e:
            not_found(e)

    def version_render(pid: str, n: int) -> Path:
        try:
            d = store.version_render_dir(pid, n)
        except KeyError as e:
            not_found(e)
        with _render_lock(d):
            if not any(d.glob("page-*.png")):
                render(version_path(pid, n), d, dpi=110)
        return d

    @app.get("/api/proposals/{pid}/versions/{n}/docx")
    def version_docx(pid: str, n: int, download: int = 0, _: dict = Depends(current_user)):
        path = version_path(pid, n)
        prop = store.get_proposal(pid)
        stem = Path(prop.get("base_name") or "proposal.docx").stem
        title = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in prop.get("title") or stem).strip() or stem
        return FileResponse(path, media_type=DOCX_MIME, filename=f"{title}_v{n}.docx" if download else None,
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/proposals/{pid}/versions/{n}/pages")
    def version_pages(pid: str, n: int, _: dict = Depends(current_user)):
        return {"count": len(page_files(version_render(pid, n)))}

    @app.get("/api/proposals/{pid}/versions/{n}/pages/{p}")
    def version_page(pid: str, n: int, p: int, _: dict = Depends(current_user)):
        pages = page_files(version_render(pid, n))
        if not 1 <= p <= len(pages):
            raise HTTPException(404, "No such page")
        return FileResponse(pages[p - 1], media_type="image/png")

    @app.get("/api/proposals/{pid}/versions/{n}/pdf")
    def version_pdf(pid: str, n: int, _: dict = Depends(current_user)):
        pdfs = list(version_render(pid, n).glob("*.pdf"))
        if not pdfs:
            raise HTTPException(404, "Not rendered")
        return FileResponse(pdfs[0], media_type="application/pdf", headers={"Cache-Control": "no-store"})

    # ---------- changes view (QA/QC) ----------
    def _changes_dir(pid: str, n: int, against: int) -> Path:
        from ..engine.diff import build_diff
        from ..pipeline.service import load_base

        prop = store.get_proposal(pid)
        nums = [v["n"] for v in prop["versions"]]
        if n not in nums or against not in nums or against >= n:
            raise HTTPException(400, "Pick an earlier version to compare with")
        d = store.proposal_dir(pid) / "changes" / f"v{n}_vs_v{against}"
        with _render_lock(d):
            if not list(d.glob("*.pdf")) or not (d / "stats.json").exists():
                d.mkdir(parents=True, exist_ok=True)
                marked, stats = build_diff(load_base(version_path(pid, against)), load_base(version_path(pid, n)))
                marked.save(d / "changes.docx")
                render(d / "changes.docx", d, dpi=60)
                (d / "stats.json").write_text(json.dumps(stats.__dict__))
        return d

    @app.get("/api/proposals/{pid}/versions/{n}/changes")
    def version_changes(pid: str, n: int, against: int, _: dict = Depends(current_user)):
        try:
            d = _changes_dir(pid, n, against)
        except KeyError as e:
            not_found(e)
        return json.loads((d / "stats.json").read_text())

    @app.get("/api/proposals/{pid}/versions/{n}/changes.pdf")
    def version_changes_pdf(pid: str, n: int, against: int, _: dict = Depends(current_user)):
        try:
            d = _changes_dir(pid, n, against)
        except KeyError as e:
            not_found(e)
        pdfs = list(d.glob("*.pdf"))
        if not pdfs:
            raise HTTPException(500, "Could not render the changes")
        return FileResponse(pdfs[0], media_type="application/pdf", headers={"Cache-Control": "no-store"})

    # ---------- search (proposals and every chat message) ----------
    @app.get("/api/search")
    def search(q: str = "", limit: int = 30, _: dict = Depends(current_user)):
        q_l = q.strip().lower()
        out = []
        for p in store.list_proposals():
            head = " ".join([p.get("title", ""), p.get("client", ""), " ".join(p.get("tags", [])), p.get("notes") or ""])
            hit, where, snippet = (not q_l), "proposal", ""
            if q_l and q_l in head.lower():
                hit, where = True, "title"
            msgs = [job_or_none(j) for j in p.get("turns", [])]
            msgs = [m for m in msgs if m]
            if q_l and not hit:
                for m in reversed(msgs):
                    texts = [m.get("instructions", "")] + list(((m.get("plan") or {}).get("summary") or {}).get("changes", []))
                    for t in texts:
                        i = t.lower().find(q_l)
                        if i >= 0:
                            hit, where = True, "message"
                            snippet = ("…" if i > 40 else "") + t[max(0, i - 40): i + 120]
                            break
                    if hit:
                        break
            if not hit:
                continue
            if not snippet and msgs:
                snippet = msgs[-1].get("instructions", "")[:160]
            out.append({"id": p["id"], "title": p.get("title"), "client": p.get("client", ""), "tags": p.get("tags", []),
                        "status": p.get("status"), "updated": p["updated"], "created": p["created"],
                        "matched_in": where, "snippet": snippet})
            if len(out) >= limit:
                break
        return out

    # ---------- history ----------
    @app.get("/api/history")
    def history(limit: int = 300, _: dict = Depends(current_user)):
        props = {p["id"]: p for p in store.list_proposals()}
        out = []
        for j in store.list_jobs()[:limit]:
            job = store.get_job(j["id"])
            prop = props.get(job.get("proposal_id") or "")
            out.append({"id": job["id"], "proposal_id": job.get("proposal_id"),
                        "proposal_title": prop["title"] if prop else job.get("title"),
                        "client": (prop or {}).get("client", ""), "status": job["status"],
                        "instructions": job["instructions"][:240], "created": job["created"],
                        "author": job.get("author"), "version": job.get("version"), "mode": job.get("mode"),
                        "usage": job.get("usage", {})})
        return out

    # ---------- turns ----------
    @app.get("/api/jobs/{jid}")
    def get_job(jid: str, _: dict = Depends(current_user)):
        if (j := job_or_none(jid)) is None:
            not_found()
        return j

    @app.post("/api/jobs/{jid}/plan")
    def plan(jid: str, req: PlanRequest, x_api_key: Optional[str] = Header(None), _: dict = Depends(current_user)):
        try:
            if req.instructions is not None:
                store.update_job(jid, instructions=req.instructions)
            return svc.start_plan(jid, _settings(req, x_api_key), answers=req.answers)
        except KeyError as e:
            not_found(e)
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/jobs/{jid}/apply")
    def apply(jid: str, req: ApplyRequest, x_api_key: Optional[str] = Header(None), _: dict = Depends(current_user)):
        try:
            return svc.start_apply(jid, _settings(req, x_api_key), selected=req.selected)
        except KeyError as e:
            not_found(e)
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/jobs/{jid}/discard")
    def discard(jid: str, _: dict = Depends(current_user)):
        """Drop a plan that was not applied, so the chat can move on."""
        if (job := job_or_none(jid)) is None:
            not_found()
        if job["status"] in ("planning", "applying", "done"):
            raise HTTPException(409, "This step cannot be discarded now")
        return store.update_job(jid, status="discarded", stage="")

    @app.get("/api/jobs/{jid}/inputs/{name}")
    def job_input(jid: str, name: str, _: dict = Depends(current_user)):
        try:
            p = store.job_dir(jid) / "inputs" / Path(name).name
        except KeyError as e:
            not_found(e)
        if not p.is_file():
            not_found()
        # images may show inline; everything else downloads, so uploaded HTML/SVG never runs in our origin
        inline = p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf")
        return FileResponse(p, filename=p.name, content_disposition_type="inline" if inline else "attachment",
                            headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})

    @app.exception_handler(PackageError)
    def package_error(_, exc: PackageError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    else:
        @app.get("/")
        def no_ui():
            return JSONResponse({"detail": "Web UI not built. Run `npm run build` in frontend/, or use `npm run dev`."}, 404)
    return app
