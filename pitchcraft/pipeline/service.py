"""Job workflow: plan -> (questions) -> apply -> review pass -> checks -> render.

Every step writes its result into job.json so the UI can poll progress and
the work survives a restart.
"""

from __future__ import annotations

import logging
import time
import threading
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ..ai import AIError, ClaudeJSON, JSONModel, Usage, make_plan, make_review, prepare_inputs, visual_check
from ..engine import DocxPackage, Op, apply_plan, build_package_outline, merge_runs, plain_text, run_audits
from ..engine.audits import find_leftovers
from ..engine.render import RenderError, page_files, pages_containing, render, render_lock
from .store import Store, safe_name

log = logging.getLogger("pitchcraft")

ModelFactory = Callable[[dict], JSONModel]


def default_model_factory(settings: dict) -> JSONModel:
    return ClaudeJSON(api_key=settings.get("api_key"), model=settings.get("model") or "claude-opus-5-5",
                      effort=settings.get("effort") or "high")


def load_base(path: Path) -> DocxPackage:
    pkg = DocxPackage.load(path)
    for r in pkg.roots().values():
        merge_runs(r)
    return pkg


def parse_ops(raw: list[dict]) -> tuple[list[Op], list[str]]:
    ops, errors = [], []
    for i, r in enumerate(raw):
        try:
            ops.append(Op.model_validate(r))
        except ValidationError as e:
            errors.append(f"Operation {i + 1}: {e.errors()[0]['msg']}")
            ops.append(Op(op="delete", targets=[], reason="invalid", evidence=""))
    return ops, errors


def ref_texts(outline, ops: list[dict]) -> dict[str, str]:
    """Short text of every id the plan refers to, for display next to each op."""
    lookup: dict[str, str] = {}
    for b in outline.blocks:
        if b["kind"] == "p":
            lookup[b["id"]] = b["text"]
        else:
            rows = b["rows"]
            lookup[b["id"]] = "Table: " + (" | ".join(c["text"] for c in rows[0]["cells"]) if rows else "")
            for r in rows:
                lookup[r["id"]] = " | ".join(c["text"] for c in r["cells"])
                for c in r["cells"]:
                    lookup[c["id"]] = c["text"]
    refs: dict[str, str] = {}
    for op in ops:
        ids = [op.get("target"), op.get("anchor"), op.get("like"), *(op.get("targets") or []),
               *[(it or {}).get("like") for it in (op.get("items") or [])]]
        for i in ids:
            if i and i in lookup:
                refs[i] = lookup[i][:300]
    return refs


def _usage_dict(u: Usage | None, prev: dict | None = None) -> dict:
    out = dict(prev or {})
    if u is not None:
        for k, v in asdict(u).items():
            out[k] = out.get(k, 0) + v
    return out


class Service:
    def __init__(self, store: Store, model_factory: ModelFactory = default_model_factory):
        self.store = store
        self.model_factory = model_factory
        self.recover_interrupted()

    def recover_interrupted(self) -> int:
        """Jobs run in background threads, so a restart kills them mid-way. Mark them failed so they can be retried."""
        n = 0
        for j in self.store.list_jobs():
            if j.get("status") in ("planning", "applying"):
                self.store.update_job(j["id"], status="error", stage="",
                                      error="The server restarted while this was running. Nothing was changed. Try again.")
                n += 1
        if n:
            log.warning("marked %d interrupted job(s) as failed after a restart", n)
        return n

    # ---------- turns (jobs) ----------
    def create_job(self, *, mode: str, title: str, instructions: str, base_name: str, base_bytes: bytes,
                   inputs: list[tuple[str, bytes]], template_id: str | None = None,
                   proposal_id: str | None = None, base_version: int | None = None,
                   author: str | None = None, history: list[dict] | None = None,
                   inherited_inputs: list[str] | None = None) -> dict:
        DocxPackage.load(base_bytes)  # validate early
        job = self.store.create_job({
            "mode": mode if mode in ("edit", "new") else "edit",
            "title": title.strip() or Path(base_name).stem,
            "instructions": instructions,
            "base_name": safe_name(base_name, "base.docx"),
            "template_id": template_id, "proposal_id": proposal_id, "base_version": base_version,
            "author": author, "history": history or [], "inherited_inputs": inherited_inputs or [],
            "inputs": [], "questions": [], "answers": {}, "plan": None, "review_plan": None,
            "op_results": [], "audits": [], "usage": {}, "changed_pages": [], "page_count": 0,
            "visual_issues": [], "selected_ops": None, "version": None,
        })
        d = self.store.job_dir(job["id"])
        (d / "base.docx").write_bytes(base_bytes)
        names = []
        for name, data in inputs:
            n = safe_name(name)
            while (d / "inputs" / n).exists():
                n = "_" + n
            (d / "inputs" / n).write_bytes(data)
            names.append(n)
        return self.store.update_job(job["id"], inputs=names)

    def add_inputs(self, jid: str, inputs: list[tuple[str, bytes]]) -> dict:
        d = self.store.job_dir(jid)
        job = self.store.get_job(jid)
        names = list(job["inputs"])
        for name, data in inputs:
            n = safe_name(name)
            (d / "inputs" / n).write_bytes(data)
            if n not in names:
                names.append(n)
        return self.store.update_job(jid, inputs=names)

    # ---------- proposals (chat threads) ----------
    def create_proposal(self, *, title: str, client: str, tags: list[str], mode: str, base_name: str,
                        base_bytes: bytes, instructions: str, inputs: list[tuple[str, bytes]],
                        template_id: str | None, author: str | None, settings: dict | None,
                        start: bool = True) -> dict:
        DocxPackage.load(base_bytes)
        prop = self.store.create_proposal({
            "title": title.strip() or "New proposal", "title_auto": not title.strip(), "client": client.strip(),
            "tags": _clean_tags(tags), "template_id": template_id, "mode": mode,
            "base_name": safe_name(base_name, "proposal.docx"), "created_by": author,
        }, base_bytes)
        self.render_version0(prop["id"])
        if instructions.strip() or inputs:
            self.add_message(prop["id"], instructions=instructions, inputs=inputs, author=author,
                             settings=settings, mode=mode, start=start)
        return self.store.get_proposal(prop["id"])

    def add_message(self, pid: str, *, instructions: str, inputs: list[tuple[str, bytes]],
                    author: str | None, settings: dict | None, base_version: int | None = None,
                    mode: str | None = None, start: bool = True) -> dict:
        prop = self.store.get_proposal(pid)
        for jid in prop["turns"]:
            try:
                if self.store.get_job(jid)["status"] in ("planning", "applying"):
                    raise RuntimeError("Wait for the current step to finish")
            except KeyError:
                continue
        latest = max(v["n"] for v in prop["versions"])
        bv = latest if base_version is None else base_version
        base_file = self.store.version_file(pid, bv)
        history, inherited = [], []
        for jid in prop["turns"]:
            try:
                j = self.store.get_job(jid)
            except KeyError:
                continue
            if j.get("plan"):
                history.append({"request": j["instructions"],
                                "answers": j.get("answers", {}),
                                "changes": (j["plan"].get("summary") or {}).get("changes", []),
                                "status": j["status"], "version": j.get("version")})
            inherited += [f"{jid}/{n}" for n in j.get("inputs", [])]
        first = not prop["turns"]
        job = self.create_job(
            mode=(mode or prop.get("mode") or "edit") if first else "edit",
            title=prop["title"], instructions=instructions, base_name=prop["base_name"],
            base_bytes=base_file.read_bytes(), inputs=inputs, template_id=prop.get("template_id"),
            proposal_id=pid, base_version=bv, author=author, history=history, inherited_inputs=inherited)
        self.store.update_proposal(pid, turns=prop["turns"] + [job["id"]])
        if start:
            self.start_plan(job["id"], settings or {})
        return self.store.get_job(job["id"])

    def approve(self, pid: str, version: int | None, user: str | None) -> dict:
        prop = self.store.get_proposal(pid)
        n = max(v["n"] for v in prop["versions"]) if version is None else version
        self.store.version_file(pid, n)
        return self.store.update_proposal(pid, status="approved", approved_version=n,
                                          approved_at=time.time(), approved_by=user)

    def duplicate(self, pid: str, version: int | None, author: str | None) -> dict:
        prop = self.store.get_proposal(pid)
        n = max(v["n"] for v in prop["versions"]) if version is None else version
        data = self.store.version_file(pid, n).read_bytes()
        return self.create_proposal(title=f"{prop['title']} (copy)", client=prop.get("client", ""),
                                    tags=prop.get("tags", []), mode="edit", base_name=prop["base_name"],
                                    base_bytes=data, instructions="", inputs=[],
                                    template_id=prop.get("template_id"), author=author, settings=None)

    def render_version0(self, pid: str) -> None:
        d = self.store.proposal_dir(pid)

        def work():
            try:
                with render_lock(d / "v0_render"):
                    if not any((d / "v0_render").glob("page-*.png")):
                        render(d / "v0.docx", d / "v0_render", dpi=110)
            except Exception:  # noqa: BLE001
                log.warning("render failed for proposal %s v0", pid)
        threading.Thread(target=work, daemon=True).start()

    def _record_version(self, job: dict) -> int | None:
        pid = job.get("proposal_id")
        if not pid:
            return None
        try:
            prop = self.store.get_proposal(pid)
        except KeyError:
            return None
        n = max(v["n"] for v in prop["versions"]) + 1
        label = (job["instructions"] or "Edit").strip().splitlines()[0][:90]
        prop["versions"].append({"n": n, "job_id": job["id"], "created": time.time(), "label": label,
                                 "base_version": job.get("base_version")})
        status = "draft" if prop.get("status") == "approved" else prop.get("status", "draft")
        self.store.update_proposal(pid, versions=prop["versions"], status=status)
        return n

    def migrate_orphan_jobs(self) -> int:
        """Wrap jobs created before proposals existed into their own proposal."""
        n = 0
        for j in self.store.list_jobs():
            job = self.store.get_job(j["id"])
            if job.get("proposal_id"):
                continue
            d = self.store.job_dir(job["id"])
            prop = self.store.create_proposal({
                "title": job.get("title") or "Imported", "client": "", "tags": ["imported"],
                "template_id": job.get("template_id"), "mode": job.get("mode", "edit"),
                "base_name": job.get("base_name", "proposal.docx"), "created_by": None,
            }, (d / "base.docx").read_bytes())
            self.store.update_job(job["id"], proposal_id=prop["id"], base_version=0, history=[], inherited_inputs=[])
            self.store.update_proposal(prop["id"], turns=[job["id"]], created=job["created"])
            if job["status"] == "done" and (d / "out.docx").exists():
                v = self._record_version(self.store.get_job(job["id"]))
                self.store.update_job(job["id"], version=v)
            self.render_version0(prop["id"])
            n += 1
        return n

    # ---------- background runner ----------
    def _spawn(self, jid: str, fn: Callable[[], None]) -> None:
        def run():
            try:
                fn()
            except AIError as e:
                self.store.update_job(jid, status="error", stage="", error=str(e))
            except Exception as e:  # noqa: BLE001
                log.error("job %s failed: %s", jid, traceback.format_exc())
                self.store.update_job(jid, status="error", stage="", error=f"{type(e).__name__}: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _context(self, jid: str):
        d = self.store.job_dir(jid)
        job = self.store.get_job(jid)
        paths = [d / "inputs" / n for n in job["inputs"]]
        for ref in job.get("inherited_inputs", []):
            ojid, name = ref.split("/", 1)
            try:
                p = self.store.job_dir(ojid) / "inputs" / safe_name(name)
            except KeyError:
                continue
            if p.exists():
                paths.append(p)
        return d, job, prepare_inputs(paths)

    @staticmethod
    def _instructions(job: dict) -> str:
        """Current request, preceded by the earlier turns of the same chat."""
        hist = job.get("history") or []
        if not hist:
            return job["instructions"]
        lines = ["Earlier requests in this conversation (already reflected in the document unless marked otherwise):"]
        for i, h in enumerate(hist, 1):
            state = "applied" if h.get("status") == "done" else f"not applied ({h.get('status')})"
            lines.append(f"{i}. [{state}] {h['request'].strip()}")
            for k, v in (h.get("answers") or {}).items():
                lines.append(f"   answer: {v}")
            for c in h.get("changes", [])[:12]:
                lines.append(f"   - {c}")
        lines.append("")
        lines.append("Current request (do this now):")
        lines.append(job["instructions"])
        return "\n".join(lines)

    # ---------- planning ----------
    def start_plan(self, jid: str, settings: dict, answers: dict | None = None, sync: bool = False) -> dict:
        job = self.store.get_job(jid)
        if job["status"] in ("planning", "applying"):
            raise RuntimeError("This step is already running")
        merged = {**job.get("answers", {}), **(answers or {})}
        self.store.update_job(jid, status="planning", stage="Reading the document and attachments",
                              error=None, answers=merged,
                              settings={k: v for k, v in settings.items() if k != "api_key"})
        work = lambda: self._plan(jid, settings)  # noqa: E731
        if sync:
            work()
        else:
            self._spawn(jid, work)
        return self.store.get_job(jid)

    def _plan(self, jid: str, settings: dict) -> None:
        d, job, inputs = self._context(jid)
        base = load_base(d / "base.docx")
        outline = build_package_outline(base)
        model = self.model_factory(settings)
        self.store.update_job(jid, stage="Claude is reading the document and planning the edits")
        plan, usage = make_plan(model, mode=job["mode"], outline=outline, inputs=inputs,
                                instructions=self._instructions(job), answers=job["answers"],
                                prior_questions=job.get("questions") or [], doc_name=job["base_name"],
                                existing_tags=sorted({t for p in self.store.list_proposals() for t in p.get("tags", [])}))
        questions = plan.get("questions", [])
        answered = job["answers"]
        open_blocking = [q for q in questions if q.get("blocking") and not answered.get(q["id"], "").strip()]
        _, errors = parse_ops(plan.get("ops", []))
        status = "needs_answers" if open_blocking else "planned"
        self.store.update_job(
            jid, plan=plan, questions=questions, plan_errors=errors,
            plan_refs=ref_texts(outline, plan.get("ops", [])),
            usage=_usage_dict(usage, job.get("usage")), status=status, stage="",
            selected_ops=list(range(len(plan.get("ops", [])))),
        )
        self._apply_meta(job, plan.get("proposal_meta") or {})
        if status == "planned" and settings.get("auto_apply") and plan.get("ops"):
            self.store.update_job(jid, status="applying", stage="Applying the plan")
            self._apply(jid, settings)

    def _apply_meta(self, job: dict, meta: dict) -> None:
        """Fill the proposal's client, title and tags from what Claude read in the chat."""
        pid = job.get("proposal_id")
        if not pid:
            return
        try:
            prop = self.store.get_proposal(pid)
        except KeyError:
            return
        changes = {}
        client = (meta.get("client") or "").strip()[:120]
        title = (meta.get("title") or "").strip()[:160]
        if client and not prop.get("client"):
            changes["client"] = client
        if title and (not prop.get("title") or prop.get("title_auto", True)):
            changes["title"] = title
            changes["title_auto"] = True
        tags = _clean_tags(list(prop.get("tags", [])) + list(meta.get("tags") or []))
        if tags != prop.get("tags", []):
            changes["tags"] = tags
        if changes:
            self.store.update_proposal(pid, **changes)

    # ---------- applying ----------
    def start_apply(self, jid: str, settings: dict, selected: list[int] | None = None,
                    sync: bool = False) -> dict:
        job = self.store.get_job(jid)
        if not job.get("plan"):
            raise RuntimeError("Plan the job first")
        if job["status"] in ("planning", "applying"):
            raise RuntimeError("This step is already running")
        self.store.update_job(jid, status="applying", stage="Applying the plan", error=None,
                              selected_ops=selected if selected is not None else job.get("selected_ops"))
        work = lambda: self._apply(jid, settings)  # noqa: E731
        if sync:
            work()
        else:
            self._spawn(jid, work)
        return self.store.get_job(jid)

    def _apply(self, jid: str, settings: dict) -> None:
        d, job, inputs = self._context(jid)
        base = load_base(d / "base.docx")
        plan = job["plan"]
        ops, _ = parse_ops(plan.get("ops", []))
        selected = job.get("selected_ops")
        chosen = [(i, op) for i, op in enumerate(ops) if selected is None or i in selected]
        res = apply_plan(base, [op for _, op in chosen])
        op_results = [{"index": chosen[r.index][0], "ok": r.ok, "error": r.error} for r in res.results]
        out_pkg, new_texts = res.package, list(res.new_texts)
        fact_changes = list(plan.get("fact_changes", []))
        usage = job.get("usage", {})
        review_plan, review_results = None, []
        is_new = job["mode"] == "new"
        sources = "\n".join([inputs.text, job["instructions"], "\n".join(job["answers"].values()),
                             "\n".join(f["fact"] for f in plan.get("facts", []))])
        base_text = plain_text(base)
        ref_terms = list(plan.get("reference_terms", []))

        if settings.get("review", True):
            self.store.update_job(jid, stage="Review pass: Claude re-reads the edited document")
            model = self.model_factory(settings)
            leftovers = find_leftovers(base_text, plain_text(out_pkg), sources, ref_terms) if is_new else None
            review_plan, u = make_review(model, mode=job["mode"], outline=build_package_outline(out_pkg),
                                         inputs=inputs, instructions=self._instructions(job),
                                         answers=job["answers"], prior_questions=job.get("questions") or [],
                                         first_plan=plan, doc_name=job["base_name"], leftovers=leftovers)
            usage = _usage_dict(u, usage)
            rops, _ = parse_ops(review_plan.get("ops", []))
            if rops:
                rres = apply_plan(out_pkg, rops)
                review_results = [{"index": r.index, "ok": r.ok, "error": r.error} for r in rres.results]
                out_pkg = rres.package
                new_texts += rres.new_texts
                fact_changes += review_plan.get("fact_changes", [])
                ref_terms += review_plan.get("reference_terms", [])

        self.store.update_job(jid, stage="Running checks")
        corpus = "\n".join([base_text, sources])
        leftovers = find_leftovers(base_text, plain_text(out_pkg), sources, ref_terms) if is_new else None
        audits = run_audits(base, out_pkg, new_texts, corpus, fact_changes, leftovers=leftovers)
        out_name = safe_name(Path(job["base_name"]).stem + ".docx")
        out_path = d / "out.docx"
        out_pkg.save(out_path)

        self.store.update_job(jid, stage="Rendering pages")
        changed, page_count, render_ok = [], 0, True
        try:
            rendered = render(out_path, d / "render", dpi=110)
            page_count = len(rendered.pages)
            changed = pages_containing(rendered.page_texts, new_texts)
            if rendered.missing_fonts:
                audits.append({"check": "render", "level": "warn",
                               "message": f"Renders ({page_count} pages), but the preview substitutes fonts that aren't available. Word shows the real fonts if they are installed.",
                               "details": [f"Font not found: {f}" for f in rendered.missing_fonts]})
            else:
                audits.append({"check": "render", "level": "pass",
                               "message": f"Opens and renders cleanly ({page_count} pages).", "details": []})
        except (RenderError, OSError) as e:
            render_ok = False
            audits.append({"check": "render", "level": "fail", "message": str(e), "details": []})

        visual_issues = []
        if render_ok and settings.get("visual", False) and changed:
            self.store.update_job(jid, stage="Visual check of changed pages")
            model = self.model_factory(settings)
            before_dir = d / "base_render"
            try:
                before = page_files(before_dir) if any(before_dir.glob("page-*.png")) else render(d / "base.docx", before_dir).pages
            except (RenderError, OSError):
                before = []
            pages = [(n, rendered.pages[n - 1], before[n - 1] if n <= len(before) else None)
                     for n in changed if n <= len(rendered.pages)]
            qa, u = visual_check(model, pages)
            usage = _usage_dict(u, usage)
            visual_issues = qa.get("issues", [])

        job = self.store.update_job(
            jid, status="done", stage="", op_results=op_results, review_plan=review_plan,
            review_results=review_results, audits=audits, usage=usage, changed_pages=changed,
            page_count=page_count, visual_issues=visual_issues, out_name=out_name,
        )
        version = self._record_version(job)
        if version is not None:
            self.store.update_job(jid, version=version)

    def rename_author(self, old: str, new: str) -> None:
        """Keep history readable after a username change."""
        for p in self.store.list_proposals():
            changes = {}
            if p.get("created_by") == old:
                changes["created_by"] = new
            if p.get("approved_by") == old:
                changes["approved_by"] = new
            if changes:
                self.store.update_proposal(p["id"], **changes)
        for j in self.store.list_jobs():
            job = self.store.get_job(j["id"])
            if job.get("author") == old:
                self.store.update_job(j["id"], author=new)

    # ---------- template checks ----------
    def inspect_template(self, data: bytes, name: str, settings: dict | None) -> dict:
        """Structure check, then (when a key is available) Claude's verdict.

        The upload dialog checks the file, then "Add" sends the same file again; the report is cached by
        content hash so Claude is only asked once per file.
        """
        import hashlib

        key = hashlib.sha256(data).hexdigest()
        cache = self.__dict__.setdefault("_inspect_cache", {})
        hit = cache.get(key)
        if hit and time.time() - hit[0] < 3600 and (hit[1]["ai"] is not None or settings is None):
            return hit[1]
        report = self._inspect_template(data, name, settings)
        if len(cache) > 32:
            cache.pop(next(iter(cache)))
        cache[key] = (time.time(), report)
        return report

    def _inspect_template(self, data: bytes, name: str, settings: dict | None) -> dict:
        from ..ai import check_document
        from ..engine.inspect import inspect_docx

        st = inspect_docx(data)
        report = {"structure": st.to_dict(), "ai": None, "ai_error": None}
        if st.ok and settings is not None:
            try:
                pkg = DocxPackage.load(data)
                for r in pkg.roots().values():
                    merge_runs(r)
                model = self.model_factory({**settings, "effort": "low"})
                verdict, _ = check_document(model, build_package_outline(pkg), name)
                report["ai"] = verdict
            except AIError as e:
                report["ai_error"] = str(e)
        ai = report["ai"]
        if not st.ok:
            report["verdict"] = "reject"
        elif ai is not None and (not ai.get("is_proposal") or ai.get("unsafe_content")):
            report["verdict"] = "warn"
        elif ai is None:
            report["verdict"] = "unchecked"
        else:
            report["verdict"] = "ok"
        return report

    # ---------- previews ----------
    def render_template_preview(self, tid: str) -> None:
        d = self.store.template_dir(tid)

        def work():
            try:
                with render_lock(d / "preview"):
                    if not any((d / "preview").glob("page-*.png")):
                        render(d / "doc.docx", d / "preview", dpi=90)
            except Exception:  # noqa: BLE001
                log.warning("preview failed for template %s", tid)
        threading.Thread(target=work, daemon=True).start()


def _clean_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags or []:
        t = " ".join(str(t).split())[:40]
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out[:20]
