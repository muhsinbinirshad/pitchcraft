"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import { useApp } from "./Shell";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.gif,.pdf,.docx,.doc,.odt,.rtf,.xlsx,.xlsm,.xls,.ods,.csv,.tsv,.pptx,.ppt,.odp,.txt,.md,.eml,.json,.xml,.html,.htm";

function Attachment({ f, onRemove }: { f: File; onRemove: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!f.type.startsWith("image/")) return;
    const u = URL.createObjectURL(f);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [f]);
  return (
    <span className="att">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {url ? <img src={url} alt="" /> : <span className="att-ic"><Icon name={f.name.toLowerCase().endsWith(".pdf") ? "pdf" : "file"} size={18} /></span>}
      <span className="nm">{f.name}</span>
      <button type="button" aria-label={`Remove ${f.name}`} onClick={onRemove}><Icon name="x" size={16} /></button>
    </span>
  );
}

/** Message box with attachments (drop, paste, pick) and an options slot. */
export function Composer({ text, setText, files, setFiles, onSend, busy, placeholder, big, disabled, options, sendLabel }: {
  text: string; setText: (v: string) => void; files: File[]; setFiles: (f: File[]) => void; onSend: () => void;
  busy?: boolean; placeholder: string; big?: boolean; disabled?: boolean; options?: ReactNode; sendLabel?: string;
}) {
  const { toast } = useApp();
  const [over, setOver] = useState(false);
  const [showOpts, setShowOpts] = useState(false);
  const pick = useRef<HTMLInputElement>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const add = (list: FileList | File[] | null) => { if (list && list.length) setFiles([...files, ...Array.from(list)]); };

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const items = [...(e.clipboardData?.items || [])].filter((i) => i.kind === "file");
      if (!items.length) return;
      const added = items.map((i, k) => { const f = i.getAsFile()!; return new File([f], `pasted-${Date.now()}-${k}.${f.type.split("/")[1] || "png"}`, { type: f.type }); });
      add(added);
      toast(`${added.length} attachment(s) added`);
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  });

  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(280, el.scrollHeight)}px`;
  }, [text]);

  const canSend = !disabled && !busy && (text.trim().length > 0 || files.length > 0);
  return (
    <div className={`composer ${big ? "big" : ""} ${over ? "over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}>
      {files.length ? <div className="atts">{files.map((f, i) => <Attachment key={`${f.name}-${i}`} f={f} onRemove={() => setFiles(files.filter((_, k) => k !== i))} />)}</div> : null}
      <textarea ref={ta} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label="Message" disabled={disabled}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canSend) { e.preventDefault(); onSend(); } }} />
      <div className="composer-bar">
        <button type="button" className="icon-btn" aria-label="Attach files" title="Attach files (or drop / paste)" onClick={() => pick.current?.click()}><Icon name="paperclip" /></button>
        {options ? <button type="button" className={`icon-btn ${showOpts ? "on" : ""}`} aria-label="Options" title="Options" onClick={() => setShowOpts((v) => !v)}><Icon name="sliders" /></button> : null}
        <span className="small faint hide-sm" style={{ marginLeft: 4 }}>Ctrl + Enter to send</span>
        <div className="grow" />
        {sendLabel
          ? <button type="button" className="btn ai" disabled={!canSend} onClick={onSend}>{busy ? <Icon name="spinner" size={18} /> : <Icon name="sparkle" size={18} />}{sendLabel}</button>
          : <button type="button" className="send" disabled={!canSend} onClick={onSend} aria-label="Send">{busy ? <Icon name="spinner" size={18} /> : <Icon name="arrowUp" size={20} />}</button>}
      </div>
      {showOpts && options ? <div className="opt-pop">{options}<button className="btn text sm" style={{ alignSelf: "flex-end" }} onClick={() => setShowOpts(false)}>Done</button></div> : null}
      <input ref={pick} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
    </div>
  );
}
