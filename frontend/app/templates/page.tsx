"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { PdfView } from "@/components/PdfView";
import { useApp } from "@/components/Shell";
import { TemplateCheck } from "@/components/TemplateCheck";
import { Button, Dialog, Menu, Status, fmtDate } from "@/components/ui";
import { api, templatePage } from "@/lib/api";
import type { Inspection, Template } from "@/lib/types";

function Cover({ t }: { t: Template }) {
  const [ok, setOk] = useState(true);
  return (
    <span className="sq-cover">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {t.has_preview && ok ? <img src={templatePage(t.id, 1)} alt="" loading="lazy" onError={() => setOk(false)} /> : <Icon name="docText" size={36} />}
    </span>
  );
}

export default function Templates() {
  const { toast } = useApp();
  const [list, setList] = useState<Template[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<Inspection | null>(null);
  const [name, setName] = useState("");
  const [confirmUse, setConfirmUse] = useState(false);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<Template | null>(null);
  const [info, setInfo] = useState<Template | null>(null);
  const [q, setQ] = useState("");
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => api.templates().then(setList).catch((e) => toast(e.message)), [toast]);
  useEffect(() => { load(); }, [load]);

  async function pick(f: File) {
    if (!f.name.toLowerCase().endsWith(".docx")) { toast("Choose a Word document (.docx)"); return; }
    setFile(f); setReport(null); setConfirmUse(false); setName(f.name.replace(/\.docx$/i, ""));
    try { setReport(await api.inspectTemplate(f)); } catch (e) { toast((e as Error).message); setFile(null); }
  }
  async function save() {
    if (!file || !report) return;
    setSaving(true);
    try {
      await api.addTemplate(file, name, report.verdict === "warn");
      toast("Template added");
      setFile(null); load(); setTimeout(load, 6000);
    } catch (e) { toast((e as Error).message); } finally { setSaving(false); }
  }
  const rename = async (t: Template) => {
    const n = prompt("Template name", t.name);
    if (n && n.trim()) { await api.renameTemplate(t.id, n.trim()); load(); }
  };
  const shown = (list || []).filter((t) => !q || `${t.name} ${t.inspection?.ai?.document_type || ""} ${t.inspection?.ai?.company || ""}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className={`soft-page ${over ? "drop-over" : ""}`}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setOver(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setOver(false); }}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) pick(f); }}>
      <div className="sq-wrap">
        <div className="sq-head">
          <div className="sq-title">
            <h1>Templates</h1>
            <span className="sq-count">{list === null ? "…" : list.length}</span>
          </div>
          <label className="sq-search">
            <Icon name="search" size={20} />
            <input placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search templates" />
          </label>
          <Button icon="upload" onClick={() => input.current?.click()}>Add template</Button>
        </div>
        <div className="sq-bar"><span className="muted small">Your company&apos;s proposals that define the look. New proposals copy their fonts, spacing, colours and tables exactly. The default is used unless you pick another in the chat box.</span></div>
        <input ref={input} type="file" accept=".docx" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ""; }} />

        {list === null ? <div className="progress" /> : (
          <div className="sq-grid">
            <button type="button" className="sq sq-add" onClick={() => input.current?.click()}>
              <span className="greet-mark" style={{ width: 52, height: 52 }}><Icon name="upload" size={22} /></span>
              <b>Add a template</b>
              <span className="small muted">Choose or drop a finished proposal (.docx). It&apos;s checked first.</span>
            </button>
            {shown.map((t) => (
              <div key={t.id} className={`sq ${t.is_default ? "sq-default" : ""}`} role="button" tabIndex={0}
                onClick={() => setPreview(t)} onKeyDown={(e) => { if (e.key === "Enter") setPreview(t); }}>
                <div className="sq-top">
                  <Cover t={t} />
                  {t.is_default ? <span className="sq-status st-sent"><Icon name="star" size={12} fill />&nbsp;Default</span> : null}
                  <span className="sq-menu" onClick={(e) => e.stopPropagation()}>
                    <Menu items={[
                      { label: "Preview", icon: "eye", onClick: () => setPreview(t) },
                      !t.is_default ? { label: "Make default", icon: "star", onClick: async () => { await api.setDefault(t.id); load(); toast(`“${t.name}” is now the default`); } } : null,
                      { label: "Check report", icon: "shield", onClick: () => setInfo(t) },
                      { label: "Rename", icon: "edit", onClick: () => rename(t) },
                      { label: "Download", icon: "download", onClick: () => { window.location.href = `/api/templates/${t.id}/docx?download=1`; } },
                      { label: "Delete", icon: "trash", danger: true, onClick: async () => { if (confirm(`Delete template “${t.name}”? Proposals made from it keep their own copy.`)) { await api.deleteTemplate(t.id); load(); } } },
                    ]} />
                  </span>
                </div>
                <div className="sq-body">
                  <div className="sq-client">{t.name}</div>
                  <div className="sq-sub">{t.inspection?.ai?.document_type || "Proposal template"}{t.inspection?.ai?.company ? ` · ${t.inspection.ai.company}` : ""}</div>
                  <div className="sq-foot">
                    <span className="sq-tags">
                      {t.inspection?.structure?.stats ? <span className="pr-tag">{t.inspection.structure.stats.headings} sections</span> : null}
                      {t.inspection?.structure?.stats ? <span className="pr-tag">{t.inspection.structure.stats.tables} tables</span> : null}
                    </span>
                    <span className="sq-time">{fmtDate(t.created)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        {list && list.length > 0 && shown.length === 0 ? <div className="muted" style={{ textAlign: "center", padding: 24 }}>No templates match “{q}”.</div> : null}
      </div>

      {over ? <div className="drop-hint"><Icon name="upload" size={28} /><b>Drop the proposal to add it as a template</b></div> : null}

      <Dialog open={Boolean(file)} onClose={() => setFile(null)} title="Add a template"
        actions={<>
          <Button variant="text" onClick={() => setFile(null)}>Cancel</Button>
          <Button icon="check" busy={saving} disabled={!report || report.verdict === "reject" || (report.verdict === "warn" && !confirmUse)} onClick={save}>Add to library</Button>
        </>}>
        {file ? <>
          <div className="row"><Icon name="docText" /><b className="ellipsis">{file.name}</b></div>
          <TemplateCheck report={report} fileName={file.name} />
          {report && report.verdict !== "reject" ? <div className="field"><label htmlFor="tn">Name</label><input id="tn" className="input sm" value={name} onChange={(e) => setName(e.target.value)} /></div> : null}
          {report?.verdict === "warn" ? <label className="row small"><input type="checkbox" className="checkbox" checked={confirmUse} onChange={(e) => setConfirmUse(e.target.checked)} />I checked this document and want to use it anyway</label> : null}
        </> : null}
      </Dialog>

      <Dialog open={Boolean(preview)} onClose={() => setPreview(null)} title={preview?.name} wide
        actions={preview ? <>
          {!preview.is_default ? <Button variant="text" icon="star" onClick={async () => { await api.setDefault(preview.id); load(); setPreview(null); toast("Default template changed"); }}>Make default</Button> : null}
          <a className="btn outlined" href={`/api/templates/${preview.id}/docx?download=1`}><Icon name="download" size={18} />Download</a>
        </> : null}>
        {preview ? <div style={{ flex: 1, minHeight: 0, overflow: "auto", background: "var(--s1)", borderRadius: 16 }}><PdfView url={`/api/templates/${preview.id}/pdf`} /></div> : null}
      </Dialog>

      <Dialog open={Boolean(info)} onClose={() => setInfo(null)} title="Template check">
        {info?.inspection ? <TemplateCheck report={info.inspection} fileName={info.filename} /> : <div className="muted">This template was added before checks existed.</div>}
        {info?.inspection ? <div className="row small muted"><Status value={info.inspection.verdict} />Checked when it was added</div> : null}
      </Dialog>
    </div>
  );
}
