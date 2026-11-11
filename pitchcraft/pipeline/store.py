"""File-based storage for templates and jobs. One folder per item."""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_name(name: str, default: str = "file") -> str:
    name = Path(name or default).name
    name = _SAFE.sub("_", name).strip(" .") or default
    return name[:120]


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.jobs = root / "jobs"
        self.templates = root / "templates"
        self.proposals = root / "proposals"
        self.proposals.mkdir(parents=True, exist_ok=True)
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.templates.mkdir(parents=True, exist_ok=True)

    # ---------- generic json ----------
    @staticmethod
    def _read(path: Path) -> dict:
        with _LOCK:
            return json.loads(path.read_text())

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        with _LOCK:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            tmp.replace(path)

    # ---------- templates ----------
    def template_dir(self, tid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", tid):
            raise KeyError(tid)
        d = self.templates / tid
        if not d.exists():
            raise KeyError(tid)
        return d

    def add_template(self, name: str, filename: str, data: bytes) -> dict:
        tid = new_id()
        d = self.templates / tid
        d.mkdir()
        (d / "doc.docx").write_bytes(data)
        meta = {"id": tid, "name": name or Path(filename).stem, "filename": safe_name(filename),
                "created": time.time(), "is_default": not self.list_templates()}
        self._write(d / "meta.json", meta)
        return meta

    def list_templates(self) -> list[dict]:
        out = []
        for d in self.templates.iterdir():
            if (d / "meta.json").exists():
                m = self._read(d / "meta.json")
                m["has_preview"] = any((d / "preview").glob("page-*.png"))
                out.append(m)
        return sorted(out, key=lambda m: (not m.get("is_default"), -m["created"]))

    def get_template(self, tid: str) -> dict:
        return self._read(self.template_dir(tid) / "meta.json")

    def set_default_template(self, tid: str) -> None:
        self.template_dir(tid)
        for m in self.list_templates():
            m.pop("has_preview", None)
            m["is_default"] = m["id"] == tid
            self._write(self.templates / m["id"] / "meta.json", m)

    def delete_template(self, tid: str) -> None:
        shutil.rmtree(self.template_dir(tid))

    # ---------- jobs ----------
    def job_dir(self, jid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", jid):
            raise KeyError(jid)
        d = self.jobs / jid
        if not d.exists():
            raise KeyError(jid)
        return d

    def create_job(self, data: dict) -> dict:
        jid = new_id()
        d = self.jobs / jid
        (d / "inputs").mkdir(parents=True)
        job = {"id": jid, "created": time.time(), "updated": time.time(), "status": "created",
               "stage": "", "error": None, **data}
        self._write(d / "job.json", job)
        return job

    def get_job(self, jid: str) -> dict:
        return self._read(self.job_dir(jid) / "job.json")

    def update_job(self, jid: str, **changes: Any) -> dict:
        with _LOCK:
            job = self.get_job(jid)
            job.update(changes)
            job["updated"] = time.time()
            self._write(self.job_dir(jid) / "job.json", job)
            return job

    def list_jobs(self) -> list[dict]:
        out = []
        for d in self.jobs.iterdir():
            if (d / "job.json").exists():
                j = self._read(d / "job.json")
                out.append({k: j.get(k) for k in ("id", "title", "mode", "status", "created", "updated", "base_name")})
        return sorted(out, key=lambda j: -j["created"])

    def delete_job(self, jid: str) -> None:
        shutil.rmtree(self.job_dir(jid))

    # ---------- proposals (chat threads with versions) ----------
    def proposal_dir(self, pid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", pid):
            raise KeyError(pid)
        d = self.proposals / pid
        if not d.exists():
            raise KeyError(pid)
        return d

    def create_proposal(self, data: dict, base_bytes: bytes) -> dict:
        pid = new_id()
        d = self.proposals / pid
        d.mkdir()
        (d / "v0.docx").write_bytes(base_bytes)
        now = time.time()
        prop = {"id": pid, "created": now, "updated": now, "status": "draft", "approved_at": None,
                "approved_version": None, "turns": [],
                "versions": [{"n": 0, "job_id": None, "created": now, "label": "Starting document"}], **data}
        self._write(d / "proposal.json", prop)
        return prop

    def get_proposal(self, pid: str) -> dict:
        return self._read(self.proposal_dir(pid) / "proposal.json")

    def update_proposal(self, pid: str, **changes: Any) -> dict:
        with _LOCK:
            prop = self.get_proposal(pid)
            prop.update(changes)
            prop["updated"] = time.time()
            self._write(self.proposal_dir(pid) / "proposal.json", prop)
            return prop

    def list_proposals(self) -> list[dict]:
        out = []
        for d in self.proposals.iterdir():
            if (d / "proposal.json").exists():
                out.append(self._read(d / "proposal.json"))
        return sorted(out, key=lambda p: -p["updated"])

    def delete_proposal(self, pid: str) -> None:
        prop = self.get_proposal(pid)
        for jid in prop.get("turns", []):
            try:
                self.delete_job(jid)
            except KeyError:
                pass
        shutil.rmtree(self.proposal_dir(pid))

    def version_file(self, pid: str, n: int) -> Path:
        prop = self.get_proposal(pid)
        v = next((v for v in prop["versions"] if v["n"] == n), None)
        if v is None:
            raise KeyError(n)
        if v["job_id"] is None:
            return self.proposal_dir(pid) / "v0.docx"
        return self.job_dir(v["job_id"]) / "out.docx"

    def version_render_dir(self, pid: str, n: int) -> Path:
        prop = self.get_proposal(pid)
        v = next((v for v in prop["versions"] if v["n"] == n), None)
        if v is None:
            raise KeyError(n)
        if v["job_id"] is None:
            return self.proposal_dir(pid) / "v0_render"
        return self.job_dir(v["job_id"]) / "render"
