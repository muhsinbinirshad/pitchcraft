"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "./Icon";

export interface Option<T extends string | number> { value: T; label: string; hint?: string }

/** Material 3 style dropdown (menu) replacing the native <select>. Keyboard: arrows, Enter, Esc, type-ahead. */
export function Select<T extends string | number>({ value, options, onChange, label, icon, small, align = "left", width }: {
  value: T; options: Option<T>[]; onChange: (v: T) => void; label?: string; icon?: string; small?: boolean;
  align?: "left" | "right"; width?: number;
}) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const listId = useId();
  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    setHi(Math.max(0, options.findIndex((o) => o.value === value)));
    const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open, options, value]);

  const pick = (i: number) => { const o = options[i]; if (o) { onChange(o.value); setOpen(false); } };
  const onKey = (e: React.KeyboardEvent) => {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ")) { e.preventDefault(); setOpen(true); return; }
    if (!open) return;
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(options.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(hi); }
    else if (e.key.length === 1) {
      const i = options.findIndex((o) => o.label.toLowerCase().startsWith(e.key.toLowerCase()));
      if (i >= 0) setHi(i);
    }
  };

  return (
    <div className="sel" ref={ref}>
      <button type="button" className={`sel-btn ${small ? "sm" : ""} ${open ? "open" : ""}`} aria-haspopup="listbox" aria-expanded={open}
        aria-controls={listId} aria-label={label} onClick={() => setOpen((v) => !v)} onKeyDown={onKey}>
        {icon ? <Icon name={icon} size={16} /> : null}
        <span className="ellipsis">{current?.label ?? label}</span>
        <Icon name="chevronDown" size={16} className={open ? "rot" : ""} />
      </button>
      {open ? (
        <div className="sel-menu" role="listbox" id={listId} style={{ [align]: 0, minWidth: width }}>
          {options.map((o, i) => (
            <div key={String(o.value)} role="option" aria-selected={o.value === value} className={`sel-opt ${i === hi ? "hi" : ""} ${o.value === value ? "on" : ""}`}
              onMouseEnter={() => setHi(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(i)}>
              <span className="grow"><span>{o.label}</span>{o.hint ? <span className="hint">{o.hint}</span> : null}</span>
              {o.value === value ? <Icon name="check" size={16} /> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
