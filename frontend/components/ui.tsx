"use client";

import Link from "next/link";
import { ButtonHTMLAttributes, ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

type Variant = "filled" | "tonal" | "outlined" | "text" | "danger" | "ai";

export function Button({ variant = "filled", icon, children, className = "", busy, small, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: string; busy?: boolean; small?: boolean }) {
  return (
    <button className={`btn ${variant} ${small ? "sm" : ""} ${className}`} {...rest} disabled={rest.disabled || busy}>
      {busy ? <Icon name="spinner" size={18} /> : icon ? <Icon name={icon} size={18} /> : null}
      {children}
    </button>
  );
}

export function LinkButton({ href, variant = "filled", icon, children, small, external }:
  { href: string; variant?: Variant; icon?: string; children: ReactNode; small?: boolean; external?: boolean }) {
  const cls = `btn ${variant} ${small ? "sm" : ""}`;
  const inner = <>{icon ? <Icon name={icon} size={18} /> : null}{children}</>;
  return external ? <a className={cls} href={href} target="_blank" rel="noreferrer">{inner}</a> : <Link className={cls} href={href}>{inner}</Link>;
}

export function IconButton({ icon, label, onClick, active, small, disabled }:
  { icon: string; label: string; onClick?: (e: React.MouseEvent) => void; active?: boolean; small?: boolean; disabled?: boolean }) {
  return (
    <button type="button" className={`icon-btn ${small ? "sm" : ""} ${active ? "on" : ""}`} aria-label={label} title={label} onClick={onClick} disabled={disabled}>
      <Icon name={icon} size={small ? 18 : 20} fill={active && icon === "star"} />
    </button>
  );
}

export function Switch({ label, hint, checked, onChange, small }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; small?: boolean }) {
  return (
    <label className={`switch ${small ? "sm" : ""}`}>
      <span><span>{label}</span>{hint ? <span className="hint">{hint}</span> : null}</span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

const LABELS: Record<string, string> = {
  draft: "Draft", approved: "Approved", sent: "Sent", archived: "Archived",
  created: "Waiting", planning: "Planning", needs_answers: "Needs answers", planned: "Ready to apply",
  applying: "Applying", done: "Done", error: "Error", discarded: "Discarded",
  ok: "Proposal", warn: "Check", reject: "Rejected", unchecked: "Not checked by AI",
};

export function Status({ value, label }: { value: string; label?: string }) {
  const busy = value === "planning" || value === "applying";
  return <span className={`status st-${value}`}>{busy ? <Icon name="spinner" size={13} /> : null}{label || LABELS[value] || value}</span>;
}

export function Empty({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-ic"><Icon name={icon} size={28} /></span>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Dialog({ open, onClose, title, children, actions, wide }:
  { open: boolean; onClose: () => void; title?: string; children: ReactNode; actions?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`dialog ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        {title ? <div className="row"><h2 className="grow">{title}</h2><IconButton icon="x" label="Close" onClick={onClose} /></div> : null}
        {children}
        {actions ? <div className="dialog-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

export function Menu({ items, icon = "more", label = "More actions" }:
  { items: ({ label: string; icon: string; onClick: () => void; danger?: boolean } | null)[]; icon?: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; up: boolean } | null>(null);
  const btn = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const list = items.filter(Boolean) as { label: string; icon: string; onClick: () => void; danger?: boolean }[];

  // the menu is drawn on <body> (fixed position) so card borders and overflow never clip it
  const place = () => {
    const r = btn.current?.getBoundingClientRect();
    if (!r) return;
    const w = 236, h = list.length * 40 + 16;
    const up = r.bottom + h + 8 > window.innerHeight && r.top - h - 8 > 0;
    const left = Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w));
    setPos({ top: up ? r.top - h - 6 : r.bottom + 6, left, up });
  };
  useEffect(() => {
    if (!open) return;
    place();
    const close = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const away = () => setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", key);
    window.addEventListener("resize", away);
    window.addEventListener("scroll", away, true);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", key);
      window.removeEventListener("resize", away);
      window.removeEventListener("scroll", away, true);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <div className="rel" ref={btn} onClick={(e) => e.stopPropagation()}>
      <IconButton icon={icon} label={label} onClick={() => setOpen((v) => !v)} />
      {open && pos ? createPortal(
        <div ref={menu} className={`menu menu-float ${pos.up ? "up" : ""}`} role="menu" style={{ top: pos.top, left: pos.left }}
          onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
          {list.map((it) => (
            <button key={it.label} role="menuitem" className={it.danger ? "danger" : ""} onClick={() => { setOpen(false); it.onClick(); }}>
              <Icon name={it.icon} size={18} />{it.label}
            </button>
          ))}
        </div>, document.body) : null}
    </div>
  );
}

export function TagInput({ value, onChange, suggestions = [] }: { value: string[]; onChange: (v: string[]) => void; suggestions?: string[] }) {
  const [text, setText] = useState("");
  const add = (t: string) => {
    const x = t.trim();
    if (x && !value.some((v) => v.toLowerCase() === x.toLowerCase())) onChange([...value, x]);
    setText("");
  };
  const listId = useRef(`tags-${Math.random().toString(36).slice(2)}`).current;
  return (
    <div className="input row wrap" style={{ padding: "6px 8px", minHeight: 48 }}>
      {value.map((t) => (
        <span key={t} className="tag">{t}<button aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((v) => v !== t))}><Icon name="x" size={14} /></button></span>
      ))}
      <input list={listId} value={text} onChange={(e) => setText(e.target.value)} placeholder={value.length ? "" : "Add tags…"}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(text); } else if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1)); }}
        onBlur={() => text && add(text)} style={{ border: 0, outline: 0, flex: 1, minWidth: 80, background: "transparent" }} />
      <datalist id={listId}>{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
    </div>
  );
}

export const fmtDate = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
export const fmtTime = (t: number) => new Date(t * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
export const fmtDateTime = (t: number) => `${fmtDate(t)}, ${fmtTime(t)}`;
export function ago(t: number) {
  const s = Date.now() / 1000 - t;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return fmtDate(t);
}
