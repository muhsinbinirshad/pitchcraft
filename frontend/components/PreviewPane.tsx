"use client";

import { useEffect, useState } from "react";
import { Icon } from "./Icon";
import { PdfView } from "./PdfView";
import { Select } from "./Select";
import { useApp } from "./Shell";
import { ChecksRow } from "./Turn";
import { Button, Status, TagInput, fmtDateTime } from "./ui";
import { api, changesPdf, versionDocx, versionPdf } from "@/lib/api";
import type { Proposal } from "@/lib/types";

type Tab = "doc" | "checks" | "versions" | "details";

export function PreviewPane({ prop, version, setVersion, baseVersion, setBaseVersion, onChange, allTags, onApprove, acting }: {
  prop: Proposal; version: number; setVersion: (n: number) => void;
  baseVersion: number | null; setBaseVersion: (n: number | null) => void;
  onChange: (p: Proposal) => void; allTags: string[];
  onApprove: (n: number) => void; acting: boolean;
}) {
  const { toast } = useApp();
  const [tab, setTab] = useState<Tab>("doc");
  const v = prop.versions.find((x) => x.n === version) || prop.versions[prop.versions.length - 1];
  const latest = prop.versions[prop.versions.length - 1].n;
  const job = v.job_id ? prop.turn_jobs.find((j) => j.id === v.job_id) : undefined;
  // outline changed pages only when it helps (a brand-new proposal changes nearly every page)
  const changedList = job?.changed_pages || [];
  const changed = new Set(job && job.page_count && changedList.length <= job.page_count * 0.6 ? changedList : []);
  const approved = prop.approved_version === v.n && prop.status !== "draft";
  const [mode, setMode] = useState<"clean" | "changes">("clean");
  const defaultAgainst = v.base_version ?? Math.max(0, v.n - 1);
  const [against, setAgainst] = useState<number>(defaultAgainst);
  const [stats, setStats] = useState<{ changed: number; added: number; removed: number } | null>(null);
  useEffect(() => { setAgainst(v.base_version ?? Math.max(0, v.n - 1)); if (v.n === 0) setMode("clean"); }, [v.n, v.base_version]);
  useEffect(() => {
    if (mode !== "changes" || v.n === 0) return;
    setStats(null);
    let alive = true;
    api.changeStats(prop.id, v.n, against).then((r) => alive && setStats(r)).catch(() => alive && setStats({ changed: 0, added: 0, removed: 0 }));
    return () => { alive = false; };
  }, [mode, prop.id, v.n, against]);
  const [meta, setMeta] = useState({ client: prop.client, tags: prop.tags, notes: prop.notes || "", due_date: prop.due_date || "", status: prop.status });
  useEffect(() => setMeta({ client: prop.client, tags: prop.tags, notes: prop.notes || "", due_date: prop.due_date || "", status: prop.status }), [prop]);

  const saveMeta = async () => {
    try { onChange(await api.patchProposal(prop.id, meta)); toast("Details saved"); } catch (e) { toast((e as Error).message); }
  };
  const tabBtn = (id: Tab, icon: string, label: string) => (
    <button className={`tab ${tab === id ? "on" : ""}`} onClick={() => setTab(id)}><Icon name={icon} size={16} />{label}</button>
  );

  return (
    <div className="pv-pane">
      <div className="pv-quick">
        <Select small label="Version shown" value={v.n} onChange={(n) => setVersion(n)} width={260}
          options={[...prop.versions].reverse().map((x) => ({ value: x.n, label: `Version ${x.n}${x.n === latest ? " (latest)" : ""}`, hint: x.n === 0 ? "Starting document" : x.label }))} />
        {approved ? <Status value="approved" label="Approved" /> : v.n === 0 ? <Status value="archived" label="Original" /> : <Status value="draft" label="Draft" />}
        {v.n > 0 ? (
          <div className="seg2" role="radiogroup" aria-label="View">
            <button role="radio" aria-checked={mode === "clean"} className={mode === "clean" ? "on" : ""} onClick={() => setMode("clean")}>Clean</button>
            <button role="radio" aria-checked={mode === "changes"} className={mode === "changes" ? "on" : ""} onClick={() => { setMode("changes"); setTab("doc"); }}><Icon name="replace" size={15} />Changes</button>
          </div>
        ) : null}
        <div className="grow" />
        {!approved && v.n > 0 ? <Button small icon="checkCircle" busy={acting} onClick={() => onApprove(v.n)}>Approve</Button> : null}
        <a className="icon-btn" href={versionDocx(prop.id, v.n, true)} title={`Download version ${v.n} (.docx)`} aria-label="Download .docx"><Icon name="download" /></a>
      </div>
      {mode === "changes" && v.n > 0 ? (
        <div className="pv-diffbar">
          <span className="small muted">Compared with</span>
          <Select small label="Compare with" value={against} onChange={setAgainst} width={240}
            options={[...prop.versions].filter((x) => x.n < v.n).reverse().map((x) => ({ value: x.n, label: x.n === 0 ? "Original (v0)" : `Version ${x.n}`, hint: x.n === (v.base_version ?? v.n - 1) ? "The version this one was made from" : undefined }))} />
          <span className="lg add">Added</span><span className="lg del">Removed</span>
          <div className="grow" />
          <span className="small muted">{stats ? `${stats.changed} edited · ${stats.added} new · ${stats.removed} removed paragraphs` : "Comparing…"}</span>
        </div>
      ) : null}
      <div className="pv-bar">
        <div className="tabs">
          {tabBtn("doc", "docText", "Document")}{tabBtn("checks", "shield", "Checks")}
          {tabBtn("versions", "branch", `Versions ${prop.versions.length}`)}{tabBtn("details", "info", "Details")}
        </div>
      </div>

      <div className="pv-scroll">
        {tab === "doc" ? (mode === "changes" && v.n > 0
          ? <PdfView url={changesPdf(prop.id, v.n, against)} />
          : <PdfView url={`${versionPdf(prop.id, v.n)}?v=${Math.round(job?.updated || prop.created)}`} changed={changed} />) : null}

        {tab === "checks" ? (
          <div className="pv-section">
            {!job ? <div className="banner info"><Icon name="info" size={18} />Version {v.n} is the starting document. Checks run on every new version.</div> : (
              <>
                <ChecksRow audits={job.audits} />
                <div className="audits">
                  {job.audits.map((a) => (
                    <div key={a.check} className={`audit ${a.level}`}>
                      <div className="h"><Icon name={a.level === "pass" ? "checkCircle" : a.level === "warn" ? "warning" : "error"} size={16} />{a.check}</div>
                      <div>{a.message}</div>
                      {a.details.length ? <ul>{a.details.slice(0, 12).map((d) => <li key={d}>{d}</li>)}</ul> : null}
                    </div>
                  ))}
                </div>
                {job.plan?.facts.length ? (
                  <div className="card"><h4>Facts Claude used</h4>
                    <ul className="ul">{job.plan.facts.map((f, i) => <li key={i}>{f.fact} <span className="small muted">({f.source})</span></li>)}</ul></div>
                ) : null}
              </>
            )}
          </div>
        ) : null}

        {tab === "versions" ? (
          <div className="pv-section">
            <div className="small muted">Every edit is a new version. The next message edits {baseVersion === null ? "the latest version" : `version ${baseVersion}`}.</div>
            {[...prop.versions].reverse().map((x) => {
              const j = x.job_id ? prop.turn_jobs.find((t) => t.id === x.job_id) : undefined;
              const isApproved = prop.approved_version === x.n && prop.status !== "draft";
              return (
                <div key={x.n} className={`ver-row ${x.n === v.n ? "on" : ""}`}>
                  <span className="ver-n">v{x.n}</span>
                  <div style={{ minWidth: 0 }}>
                    <div className="row"><b className="ellipsis">{x.n === 0 ? "Starting document" : x.label}</b>{isApproved ? <Status value="approved" /> : null}</div>
                    <div className="small muted">{fmtDateTime(x.created)}{j?.author ? ` · ${j.author}` : ""}{x.base_version !== undefined && x.base_version !== null ? ` · from v${x.base_version}` : ""}</div>
                  </div>
                  <div className="row" style={{ gap: 2 }}>
                    <button className="btn text sm" onClick={() => { setVersion(x.n); setTab("doc"); }}>View</button>
                    <button className="btn text sm" onClick={() => { setBaseVersion(x.n === latest ? null : x.n); toast(`Next message continues from v${x.n}`); }}>Continue from</button>
                    <a className="icon-btn sm" href={versionDocx(prop.id, x.n, true)} aria-label={`Download v${x.n}`}><Icon name="download" size={18} /></a>
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}

        {tab === "details" ? (
          <div className="pv-section">
            <div className="card">
              <div className="small muted">Filled in by Claude from the chat. Change them here if you like.</div>
              <div className="field"><label htmlFor="d-cl">Client</label><input id="d-cl" className="input sm" value={meta.client} onChange={(e) => setMeta({ ...meta, client: e.target.value })} /></div>
              <div className="field"><span className="label">Tags</span><TagInput value={meta.tags} onChange={(t) => setMeta({ ...meta, tags: t })} suggestions={allTags} /></div>
              <div className="row wrap" style={{ gap: 12 }}>
                <div className="field grow"><span className="label">Status</span>
                  <Select value={meta.status} onChange={(st) => setMeta({ ...meta, status: st })} label="Status"
                    options={[{ value: "draft", label: "Draft" }, { value: "approved", label: "Approved" }, { value: "sent", label: "Sent" }, { value: "archived", label: "Archived" }]} /></div>
                <div className="field grow"><label htmlFor="d-due">Due date</label><input id="d-due" type="date" className="input sm" value={meta.due_date} onChange={(e) => setMeta({ ...meta, due_date: e.target.value })} /></div>
              </div>
              <div className="field"><label htmlFor="d-notes">Notes</label><textarea id="d-notes" className="input sm" rows={4} value={meta.notes} onChange={(e) => setMeta({ ...meta, notes: e.target.value })} placeholder="Internal notes, contacts, follow-ups…" /></div>
              <div className="row"><Button small onClick={saveMeta}>Save details</Button></div>
            </div>
            <dl className="kv small">
              <dt>Created</dt><dd>{fmtDateTime(prop.created)}{prop.created_by ? ` by ${prop.created_by}` : ""}</dd>
              <dt>Started from</dt><dd>{prop.base_name} ({prop.mode === "new" ? "template, new proposal" : "edited as is"})</dd>
              {prop.approved_at ? (<><dt>Approved</dt><dd>v{prop.approved_version}, {fmtDateTime(prop.approved_at)}{prop.approved_by ? ` by ${prop.approved_by}` : ""}</dd></>) : null}
              <dt>Messages</dt><dd>{prop.turns.length}</dd>
            </dl>
          </div>
        ) : null}
      </div>
    </div>
  );
}
