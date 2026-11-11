"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import { TemplateCheck } from "./TemplateCheck";
import { Button } from "./ui";
import { api, templatePage, templatePageCount } from "@/lib/api";
import type { Inspection, Template } from "@/lib/types";

const STEPS = ["Welcome", "Add your style", "Ready"];

const HOW = [
  { icon: "layers", title: "Add a style template", text: "One finished proposal (.docx). Its fonts, colours, spacing and tables become your house style." },
  { icon: "chat", title: "Describe the proposal", text: "Type the client, scope and price, or attach the RFP and emails. Claude asks for anything missing." },
  { icon: "checkCircle", title: "Review and send", text: "See every change, ask for edits, approve, then download the Word file." },
];

const TIPS = [
  "A finished proposal your team already sent, not a draft",
  "Has the parts you reuse: cover, headings, tables, pricing",
  "No tracked changes or open comments",
];

/**
 * First-run tour. It blocks the app while the library has no template, because every proposal needs one.
 */
export function Onboarding({ name, onDone }: { name: string; onDone: (go: boolean) => void }) {
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<Inspection | null>(null);
  const [tname, setTname] = useState("");
  const [confirmUse, setConfirmUse] = useState(false);
  const [saving, setSaving] = useState(false);
  const [over, setOver] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [added, setAdded] = useState<Template | null>(null);
  const [cover, setCover] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  // show the new template's cover once its preview has rendered
  useEffect(() => {
    if (!added) return;
    let stop = false;
    const tick = async (n: number) => {
      const { count } = await templatePageCount(added.id).catch(() => ({ count: 0 }));
      if (stop) return;
      if (count > 0) setCover(templatePage(added.id, 1));
      else if (n < 20) setTimeout(() => tick(n + 1), 1500);
    };
    tick(0);
    return () => { stop = true; };
  }, [added]);

  async function pick(f: File) {
    setErr(null);
    if (!f.name.toLowerCase().endsWith(".docx")) { setErr("Choose a Word document (.docx)."); return; }
    if (f.size > 50 * 1024 * 1024) { setErr("That file is over 50 MB."); return; }
    setFile(f); setReport(null); setConfirmUse(false); setTname(f.name.replace(/\.docx$/i, ""));
    try { setReport(await api.inspectTemplate(f)); } catch (e) { setErr((e as Error).message); setFile(null); }
  }
  async function save() {
    if (!file || !report) return;
    setSaving(true);
    try {
      const t = await api.addTemplate(file, tname, report.verdict === "warn");
      setAdded(t); setStep(2);
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  }
  const canAdd = Boolean(report) && report!.verdict !== "reject" && (report!.verdict !== "warn" || confirmUse);

  return (
    <div className="ob-scrim">
      <div className="ob" role="dialog" aria-modal="true" aria-label="Get started with Pitchcraft">
        <div className="ob-top">
          <span className="ob-count">Step {step + 1} of {STEPS.length} · {STEPS[step]}</span>
        </div>
        <div className="ob-bar" aria-hidden="true">{STEPS.map((s, i) => <span key={s} className={i <= step ? "on" : ""} />)}</div>

        {step === 0 ? (
          <div className="ob-body">
            <div className="ob-head">
              <span className="ob-hero"><Icon name="logo" size={26} /></span>
              <div>
                <h2>Welcome, {name.split(" ")[0]}</h2>
                <p className="muted">Proposals in your company&apos;s exact style, written from a chat.</p>
              </div>
            </div>
            <ol className="ob-how">
              {HOW.map((h, i) => (
                <li key={h.title}>
                  <span className="ob-dot">{i + 1}</span>
                  <span className="ob-how-text"><b>{h.title}</b><span>{h.text}</span></span>
                </li>
              ))}
            </ol>
            <div className="ob-actions">
              <span className="small muted"><Icon name="clock" size={14} /> About a minute to set up</span>
              <span className="grow" />
              <Button onClick={() => setStep(1)} autoFocus>Get started</Button>
            </div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="ob-body">
            <div>
              <h2>Add your style template</h2>
              <p className="muted">Only its look is used. Its content is replaced in every new proposal.</p>
            </div>
            {!file ? (
              <>
                <button type="button" className={`ob-drop ${over ? "over" : ""}`} onClick={() => input.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                  onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) pick(f); }}>
                  <span className="ob-drop-ic"><Icon name="upload" size={22} /></span>
                  <b>Drop a proposal here, or browse</b>
                  <span className="small muted">.docx · up to 50 MB · checked before it&apos;s added</span>
                </button>
                <ul className="ob-tips">
                  {TIPS.map((t) => <li key={t}><Icon name="check" size={16} />{t}</li>)}
                </ul>
              </>
            ) : (
              <div className="col" style={{ gap: 12 }}>
                <div className="ob-file"><Icon name="docText" /><b className="ellipsis grow">{file.name}</b>
                  <button className="btn text sm" onClick={() => { setFile(null); setReport(null); }}>Change</button></div>
                <TemplateCheck report={report} fileName={file.name} />
                {report && report.verdict !== "reject" ? <div className="field"><label htmlFor="ob-tn">Template name</label><input id="ob-tn" className="input sm" value={tname} onChange={(e) => setTname(e.target.value)} /></div> : null}
                {report?.verdict === "warn" ? <label className="row small"><input type="checkbox" className="checkbox" checked={confirmUse} onChange={(e) => setConfirmUse(e.target.checked)} />I checked this document and want to use it anyway</label> : null}
              </div>
            )}
            {err ? <div className="banner err"><Icon name="error" /><span>{err}</span></div> : null}
            <input ref={input} type="file" accept=".docx" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ""; }} />
            <div className="ob-actions">
              <Button variant="text" onClick={() => setStep(0)}>Back</Button>
              <span className="grow" />
              <Button icon="check" busy={saving} disabled={!canAdd} onClick={save}>Add template</Button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="ob-body">
            <div className="ob-done">
              <div className="ob-cover">
                {cover
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={cover} alt={`First page of ${added?.name}`} />
                  : <span className="ob-cover-wait"><><Icon name="spinner" size={20} />Rendering preview…</></span>}
              </div>
              <div className="col" style={{ gap: 8 }}>
                <span className="ob-ok"><Icon name="checkCircle" size={18} />Template added</span>
                <h2>Your style is ready</h2>
                <p className="muted">“{added?.name}” is now your default template. Every new proposal copies its look. Add more styles any time from Templates.</p>
              </div>
            </div>
            <div className="ob-actions">
              <Button variant="text" onClick={() => onDone(false)}>Look around first</Button>
              <span className="grow" />
              <Button icon="sparkle" onClick={() => onDone(true)}>Create your first proposal</Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
