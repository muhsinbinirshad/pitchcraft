"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { RunOptions } from "@/components/RunOptions";
import { useApp } from "@/components/Shell";
import { TemplateCheck } from "@/components/TemplateCheck";
import { Button, Dialog } from "@/components/ui";
import { api, displayName } from "@/lib/api";
import type { Inspection, Template } from "@/lib/types";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.gif,.pdf,.docx,.doc,.odt,.rtf,.xlsx,.xlsm,.xls,.ods,.csv,.tsv,.pptx,.ppt,.odp,.txt,.md,.eml,.json,.xml,.html,.htm";

/** Popover anchored above a button inside the composer; closes on outside click. */
function Pop({ open, onClose, children, align = "left", width = 300 }:
  { open: boolean; onClose: () => void; children: React.ReactNode; align?: "left" | "right"; width?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!ref.current?.parentElement?.contains(e.target as Node)) onClose(); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", h);
    window.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); window.removeEventListener("keydown", k); };
  }, [open, onClose]);
  if (!open) return null;
  return <div ref={ref} className="pop" style={{ [align]: 0, width }}>{children}</div>;
}

function Tile({ t, on, onClick }: { t: Template; on: boolean; onClick: () => void }) {
  const [ok, setOk] = useState(true);
  return (
    <button type="button" className={`pk ${on ? "on" : ""}`} onClick={onClick} title={t.name}>
      <span className="pk-pv">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {t.has_preview && ok ? <img src={`/api/templates/${t.id}/preview/1`} alt="" loading="lazy" onError={() => setOk(false)} /> : <Icon name="docText" size={34} />}
        {t.is_default ? <span className="pk-badge">Default</span> : null}
        {on ? <span className="pk-check"><Icon name="check" size={14} /></span> : null}
      </span>
      <span className="pk-name">{t.name}</span>
      <span className="pk-sub">{t.inspection?.ai?.document_type || "Proposal template"}</span>
    </button>
  );
}

export default function NewProposal() {
  const router = useRouter();
  const { toast, keyReady, refreshRecent, user } = useApp();
  const [templates, setTemplates] = useState<Template[]>([]);
  // base document: the default company template, or a new style uploaded here
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [styleFile, setStyleFile] = useState<File | null>(null);
  // an existing proposal (made anywhere) to edit in place: only the requested changes are made
  const [editFile, setEditFile] = useState<File | null>(null);
  const [report, setReport] = useState<Inspection | null>(null);
  const [checking, setChecking] = useState(false);
  const [confirmUse, setConfirmUse] = useState(false);
  const [altId, setAltId] = useState<string | null>(null);  // another library template chosen as the style
  const [dropOver, setDropOver] = useState(false);
  // message
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  // ui
  const [optsOpen, setOptsOpen] = useState(false);
  const [tplModal, setTplModal] = useState(false);
  const [pickModal, setPickModal] = useState(false);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const attachRef = useRef<HTMLInputElement>(null);
  const styleRef = useRef<HTMLInputElement>(null);
  const editRef = useRef<HTMLInputElement>(null);
  const ta = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.templates().then((t) => { setTemplates(t); setTemplateId((t.find((x) => x.is_default) || t[0])?.id ?? null); }).catch((e) => toast(e.message));
  }, [toast]);
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const items = [...(e.clipboardData?.items || [])].filter((i) => i.kind === "file");
      if (!items.length) return;
      setFiles((x) => [...x, ...items.map((i, k) => { const f = i.getAsFile()!; return new File([f], `pasted-${Date.now()}-${k}.${f.type.split("/")[1] || "png"}`, { type: f.type }); })]);
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, []);
  useEffect(() => {
    const el = ta.current;
    if (el) { el.style.height = "auto"; el.style.height = `${Math.min(320, Math.max(96, el.scrollHeight))}px`; }
  }, [text]);

  const tpl = templates.find((t) => t.id === templateId) || null;
  const alt = templates.find((t) => t.id === altId) || null;
  const source: "template" | "library" | "newstyle" | "edit" = editFile ? "edit" : styleFile ? "newstyle" : alt ? "library" : "template";
  const styleReady = source !== "newstyle" || (report && report.verdict !== "reject" && (report.verdict !== "warn" || confirmUse));
  const canSend = !busy && (text.trim().length > 0 || files.length > 0) && (source !== "template" || templateId) && Boolean(styleReady)
    && (source !== "edit" || text.trim().length > 0);

  function pickEdit(f: File) {
    if (!f.name.toLowerCase().endsWith(".docx")) { toast("Choose a Word document (.docx)"); return; }
    setEditFile(f); setStyleFile(null); setReport(null); setAltId(null);
    ta.current?.focus();
  }

  async function pickStyle(f: File) {
    if (!f.name.toLowerCase().endsWith(".docx")) { toast("Choose a Word document (.docx)"); return; }
    setAltId(null); setStyleFile(f); setReport(null); setConfirmUse(false); setChecking(true); setTplModal(true);
    try { setReport(await api.inspectTemplate(f)); } catch (e) { toast((e as Error).message); setStyleFile(null); }
    finally { setChecking(false); }
  }

  async function send() {
    if (!keyReady) { toast("Add your Claude API key in Settings first"); router.push("/settings/"); return; }
    if (!canSend) return;
    setBusy(true);
    try {
      const fd = new FormData();
      if (source === "edit") {
        fd.append("base", editFile!);
        fd.append("mode", "edit");
      } else {
        let tid = source === "library" ? alt!.id : templateId!;
        if (source === "newstyle") tid = (await api.addTemplate(styleFile!, styleFile!.name.replace(/\.docx$/i, ""), report?.verdict === "warn")).id;
        fd.append("template_id", tid);
        fd.append("mode", "new");
      }
      fd.append("instructions", text);
      files.forEach((f) => fd.append("inputs", f));
      const prop = await api.createProposal(fd, true);
      refreshRecent();
      router.push(`/p/?id=${prop.id}`);
    } catch (e) { toast((e as Error).message); setBusy(false); }
  }

  return (
    <div className="chat-home">
      <div className="chat-center">
        <div className="greet">
          <span className="greet-mark"><Icon name="sparkle" size={26} /></span>
          <h1>{user ? `Hi ${displayName(user).split(" ")[0]}, ` : ""}<span className="grad">{source === "edit" ? "what should we change?" : "what are we proposing?"}</span></h1>
          <p className="muted">{source === "edit"
            ? <>Describe the client&apos;s changes. I&apos;ll edit <b>{editFile!.name}</b> and keep everything else exactly as it is.</>
            : <>Describe the client, scope, timeline and price, or attach the RFP. I&apos;ll write it in your template&apos;s style and ask about anything missing.</>}</p>
        </div>

        <div className={`cbox ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); setFiles((x) => [...x, ...Array.from(e.dataTransfer.files)]); }}>

          {files.length ? (
            <div className="atts">
              {files.map((f, i) => (
                <span key={`${f.name}-${i}`} className="att">
                  <span className="att-ic"><Icon name={f.type.startsWith("image/") ? "image" : f.name.toLowerCase().endsWith(".pdf") ? "pdf" : "file"} size={18} /></span>
                  <span className="nm">{f.name}</span>
                  <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, k) => k !== i))}><Icon name="x" size={16} /></button>
                </span>
              ))}
            </div>
          ) : null}

          <textarea ref={ta} value={text} onChange={(e) => setText(e.target.value)} aria-label="Message" autoFocus
            placeholder={source === "edit"
              ? "e.g. Add a web application pentest for AED 6,000, extend the timeline to 10 weeks and update the totals…"
              : "e.g. Create a proposal for ABC Group: external VAPT of 2 web apps, internal VAPT of 180 assets, 4 weeks, AED 39,500…"}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />

          <div className="cbar">
            <button type="button" className="cbtn round" aria-label="Attach files" title="Attach emails, screenshots, RFPs, Excel sheets, slides or notes" onClick={() => attachRef.current?.click()}><Icon name="paperclip" size={19} /></button>

            {source === "edit" ? (
              <span className="cbtn accent" title="Editing this proposal in place">
                <Icon name="edit" size={16} />
                <span className="chip-link ellipsis">{editFile!.name.replace(/\.docx$/i, "")}</span>
                <button type="button" className="chip-x" aria-label="Stop editing this file" onClick={() => setEditFile(null)}><Icon name="x" size={14} /></button>
              </span>
            ) : source === "newstyle" ? (
              <span className="cbtn accent" title="New style for this proposal">
                <Icon name={checking ? "spinner" : report?.verdict === "reject" ? "error" : "upload"} size={16} />
                <button type="button" className="chip-link ellipsis" onClick={() => setTplModal(true)}>{checking ? "Checking…" : styleFile!.name.replace(/\.docx$/i, "")}</button>
                <button type="button" className="chip-x" aria-label="Remove new style" onClick={() => { setStyleFile(null); setReport(null); }}><Icon name="x" size={14} /></button>
              </span>
            ) : (
              <button type="button" className="cbtn" onClick={() => setPickModal(true)} title="Choose the template (style) for this proposal">
                <Icon name="layers" size={16} /><span className="ellipsis">{(alt || tpl)?.name || "Choose a template"}</span><Icon name="chevronDown" size={16} />
              </button>
            )}
            {source !== "newstyle" && source !== "edit" ? (
              <button type="button" className="cbtn ghost" onClick={() => setTplModal(true)} title="Upload a proposal with a different style">
                <Icon name="upload" size={16} />New style
              </button>
            ) : null}
            {source !== "edit" && source !== "newstyle" ? (
              <button type="button" className="cbtn ghost" onClick={() => editRef.current?.click()} title="Upload a proposal you already have (.docx) and edit it in place">
                <Icon name="edit" size={16} />Edit existing
              </button>
            ) : null}

            <div className="grow" />
            <div className="rel">
              <button type="button" className="cbtn round ghost" aria-label="Options" title="Options" onClick={() => setOptsOpen((v) => !v)}><Icon name="sliders" size={18} /></button>
              <Pop open={optsOpen} onClose={() => setOptsOpen(false)} align="right" width={320}><RunOptions /></Pop>
            </div>
            <button type="button" className="send" disabled={!canSend} onClick={send} aria-label={source === "edit" ? "Edit proposal" : "Create proposal"} title={source === "edit" ? "Make these changes (Enter)" : "Create proposal (Enter)"}>
              {busy ? <Icon name="spinner" size={18} /> : <Icon name="arrowUp" size={20} />}
            </button>
          </div>
        </div>

        {source === "newstyle" && report && !tplModal ? (
          report.verdict === "reject" ? <div className="banner err"><Icon name="error" size={18} /><span>{styleFile!.name} can&apos;t be used as a template. <button className="linkbtn" onClick={() => setTplModal(true)}>See why</button></span></div>
          : report.verdict === "warn" && !confirmUse ? <div className="banner warn"><Icon name="warning" size={18} /><span>Check the new style before sending. <button className="linkbtn" onClick={() => setTplModal(true)}>Review</button></span></div>
          : null
        ) : null}

      </div>

      <input ref={attachRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { const l = Array.from(e.target.files || []); if (l.length) setFiles((x) => [...x, ...l]); e.target.value = ""; }} />
      <input ref={editRef} type="file" accept=".docx" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pickEdit(f); e.target.value = ""; }} />
      <input ref={styleRef} type="file" accept=".docx" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) pickStyle(f); e.target.value = ""; }} />

      <Dialog open={tplModal} onClose={() => setTplModal(false)} title="Use a new style"
        actions={<>
          <Button variant="text" onClick={() => { setStyleFile(null); setReport(null); setTplModal(false); }}>Cancel</Button>
          <Button onClick={() => setTplModal(false)} disabled={source !== "newstyle" || (source === "newstyle" && (!report || checking || report.verdict === "reject" || (report.verdict === "warn" && !confirmUse)))}>Use this style</Button>
        </>}>
        {source === "newstyle" ? (
          <div className="col">
            <div className="row"><Icon name="docText" /><b className="grow ellipsis">{styleFile!.name}</b><button className="btn text sm" onClick={() => styleRef.current?.click()}>Choose another file</button></div>
            <TemplateCheck report={checking ? null : report} fileName={styleFile!.name} />
            {report?.verdict === "warn" ? (
              <label className="row small"><input type="checkbox" className="checkbox" checked={confirmUse} onChange={(e) => setConfirmUse(e.target.checked)} />I checked this document and want to use it anyway</label>
            ) : null}
            {report && report.verdict !== "reject" ? <div className="small muted">It is saved to your template library when you send the message.</div> : null}
          </div>
        ) : (
          <div className="col" style={{ gap: 16 }}>
            <p className="muted" style={{ margin: 0 }}>
              Attach a finished proposal whose look you want: its fonts, colours, spacing, tables and section layout become the style of the new proposal.
              The content of that proposal is replaced with what you write in the chat.
            </p>
            <button type="button" className={`ns-drop ${dropOver ? "over" : ""}`} onClick={() => styleRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDropOver(true); }} onDragLeave={() => setDropOver(false)}
              onDrop={(e) => { e.preventDefault(); setDropOver(false); const f = e.dataTransfer.files[0]; if (f) pickStyle(f); }}>
              <span className="greet-mark" style={{ width: 44, height: 44 }}><Icon name="upload" size={20} /></span>
              <b>Choose a proposal (.docx)</b>
              <span className="small muted">or drop it here. It is checked first to make sure it really is a proposal.</span>
            </button>

          </div>
        )}
      </Dialog>

      <Dialog open={pickModal} onClose={() => setPickModal(false)} title="Choose a template" className="dialog-picker"
        actions={<>
          <Button variant="text" icon="upload" onClick={() => { setPickModal(false); setTplModal(true); }}>Upload a new style</Button>
          <Button onClick={() => setPickModal(false)}>Done</Button>
        </>}>
        <div className="muted small">The new proposal copies this template&apos;s look exactly. Its old content is replaced with what you write.</div>
        {templates.length ? (
          <div className="pk-grid">
            {templates.map((t) => {
              const on = (altId ?? templateId) === t.id;
              return <Tile key={t.id} t={t} on={on} onClick={() => { setAltId(t.id === templateId ? null : t.id); setStyleFile(null); setReport(null); }} />;
            })}
          </div>
        ) : <div className="muted">No templates yet. Upload a finished proposal to use as your style.</div>}
      </Dialog>
    </div>
  );
}
