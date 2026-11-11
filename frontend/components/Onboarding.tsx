"use client";

import { useRef, useState } from "react";
import { Icon } from "./Icon";
import { TemplateCheck } from "./TemplateCheck";
import { Button } from "./ui";
import { api } from "@/lib/api";
import type { Inspection, Template } from "@/lib/types";

const STEPS = ["Welcome", "Add your style", "Ready"];

/** First-run tour. Shown while the library has no template: a style template is required before any proposal. */
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
  const input = useRef<HTMLInputElement>(null);

  async function pick(f: File) {
    setErr(null);
    if (!f.name.toLowerCase().endsWith(".docx")) { setErr("Choose a Word document (.docx)."); return; }
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
  const finish = (go: boolean) => onDone(go);
  const canAdd = Boolean(report) && report!.verdict !== "reject" && (report!.verdict !== "warn" || confirmUse);

  return (
    <div className="ob-scrim">
      <div className="ob" role="dialog" aria-modal="true" aria-label="Get started with Pitchcraft">
        <div className="ob-steps" aria-label={`Step ${step + 1} of ${STEPS.length}`}>
          {STEPS.map((s, i) => (
            <span key={s} className={`ob-step ${i === step ? "on" : ""} ${i < step ? "done" : ""}`}>
              <span className="ob-num">{i < step ? <Icon name="check" size={14} /> : i + 1}</span>{s}
            </span>
          ))}
        </div>

        {step === 0 ? (
          <div className="ob-body">
            <span className="ob-hero"><Icon name="logo" size={30} /></span>
            <h2>Welcome, {name.split(" ")[0]}</h2>
            <p className="muted">Pitchcraft writes proposals that look exactly like your company&apos;s own. Before the first one, it needs one finished proposal to copy the style from.</p>
            <ol className="ob-how">
              <li><span className="ob-ic"><Icon name="layers" size={20} /></span><span><b>Add a style template</b><span className="small muted">Any finished proposal (.docx). Fonts, colours, spacing and tables are kept.</span></span></li>
              <li><span className="ob-ic"><Icon name="chat" size={20} /></span><span><b>Describe the proposal in chat</b><span className="small muted">Paste the RFP, emails or notes. Claude asks for anything missing.</span></span></li>
              <li><span className="ob-ic"><Icon name="checkCircle" size={20} /></span><span><b>Review and approve</b><span className="small muted">See every change, ask for edits, then download the Word file.</span></span></li>
            </ol>
            <div className="ob-actions"><span className="grow" /><Button onClick={() => setStep(1)}>Get started</Button></div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="ob-body">
            <h2>Add your first style template</h2>
            <p className="muted">Pick a proposal your team already sent. Only its look is used; its content is replaced in every new proposal.</p>
            {!file ? (
              <button type="button" className={`ob-drop ${over ? "over" : ""}`} onClick={() => input.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) pick(f); }}>
                <span className="greet-mark" style={{ width: 52, height: 52 }}><Icon name="upload" size={22} /></span>
                <b>Choose or drop a .docx proposal</b>
                <span className="small muted">It&apos;s checked first to make sure it&apos;s a proposal.</span>
              </button>
            ) : (
              <div className="col" style={{ gap: 12 }}>
                <div className="row"><Icon name="docText" /><b className="ellipsis grow">{file.name}</b>
                  <button className="btn text sm" onClick={() => { setFile(null); setReport(null); }}>Choose another</button></div>
                <TemplateCheck report={report} fileName={file.name} />
                {report && report.verdict !== "reject" ? <div className="field"><label htmlFor="ob-tn">Name</label><input id="ob-tn" className="input sm" value={tname} onChange={(e) => setTname(e.target.value)} /></div> : null}
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
            <span className="ob-hero ok"><Icon name="checkCircle" size={30} /></span>
            <h2>Your style is ready</h2>
            <p className="muted">“{added?.name}” is your default template. New proposals copy its look. You can add more styles any time from Templates.</p>
            <div className="ob-actions">
              <Button variant="text" onClick={() => finish(false)}>Look around first</Button>
              <span className="grow" />
              <Button icon="sparkle" onClick={() => finish(true)}>Create your first proposal</Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
