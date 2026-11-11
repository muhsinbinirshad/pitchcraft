"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./Icon";
import { ago } from "./ui";
import { searchProposals } from "@/lib/api";

interface Hit { id: string; title: string; client: string; tags: string[]; status: string; updated: number; created: number; matched_in: string; snippet: string }

const STATUS_LABEL: Record<string, string> = { draft: "Draft", approved: "Approved", sent: "Sent", archived: "Archived" };

function bucket(t: number) {
  const day = 86400, now = Date.now() / 1000;
  const start = new Date(); start.setHours(0, 0, 0, 0);
  const s = start.getTime() / 1000;
  if (t >= s) return "Today";
  if (t >= s - day) return "Yesterday";
  if (t >= now - 7 * day) return "Previous 7 days";
  if (t >= now - 30 * day) return "Previous 30 days";
  return "Older";
}

/** Ctrl/Cmd+K: search proposals and every chat message. */
export function SearchModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [hi, setHi] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => { if (open) { setQ(""); setHi(0); setHits(null); setTimeout(() => input.current?.focus(), 20); } }, [open]);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => { searchProposals(q).then((h: Hit[]) => { setHits(h); setHi(0); }).catch(() => setHits([])); }, 140);
    return () => clearTimeout(t);
  }, [q, open]);
  useEffect(() => { list.current?.querySelector(".sx-item.hi")?.scrollIntoView({ block: "nearest" }); }, [hi]);

  const grouped = useMemo(() => {
    const out: { label: string; items: { h: Hit; i: number }[] }[] = [];
    (hits || []).forEach((h, i) => {
      const label = bucket(h.updated);
      const g = out.find((x) => x.label === label);
      if (g) g.items.push({ h, i }); else out.push({ label, items: [{ h, i }] });
    });
    return out;
  }, [hits]);

  if (!open) return null;
  const go = (h?: Hit) => { if (!h) return; onClose(); router.push(`/p/?id=${h.id}`); };
  const term = q.trim();
  const mark = (text: string) => {
    if (!term) return text;
    const i = text.toLowerCase().indexOf(term.toLowerCase());
    if (i < 0) return text;
    return <>{text.slice(0, i)}<mark>{text.slice(i, i + term.length)}</mark>{text.slice(i + term.length)}</>;
  };

  return (
    <div className="sx-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sx" role="dialog" aria-modal="true" aria-label="Search proposals">
        <div className="sx-top">
          <Icon name="search" size={22} />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search proposals and conversations"
            aria-label="Search" onKeyDown={(e) => {
              const n = hits?.length || 0;
              if (e.key === "Escape") onClose();
              else if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(n - 1, h + 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
              else if (e.key === "Enter") go(hits?.[hi]);
            }} />
          <button className="icon-btn sm" aria-label="Close search" onClick={onClose}><Icon name="x" size={20} /></button>
        </div>

        <div className="sx-body" ref={list}>
          {hits === null ? <div className="sx-empty"><Icon name="spinner" /></div>
            : hits.length === 0 ? (
              <div className="sx-empty">
                <span className="sx-empty-ic"><Icon name="search" size={22} /></span>
                <b>{term ? `No results for “${term}”` : "No proposals yet"}</b>
                <span className="muted small">{term ? "Search looks at clients, titles, tags and everything said in the chats." : "Create a proposal and it will show up here."}</span>
              </div>
            ) : grouped.map((g) => (
              <Fragment key={g.label}>
                <div className="sx-group">{g.label}</div>
                {g.items.map(({ h, i }) => (
                  <button key={h.id} className={`sx-item ${i === hi ? "hi" : ""}`} onMouseMove={() => setHi(i)} onClick={() => go(h)}>
                    <span className={`sx-ic ${h.matched_in === "message" ? "msg" : ""}`}><Icon name={h.matched_in === "message" ? "chat" : "docText"} size={18} /></span>
                    <span className="sx-text">
                      <span className="sx-line">
                        <span className="sx-title">{mark(h.client || h.title)}</span>
                        {h.client ? <span className="sx-sub">{mark(h.title)}</span> : null}
                      </span>
                      {h.snippet ? <span className="sx-snip">{h.matched_in === "message" ? <Icon name="quote" size={12} /> : null}{mark(h.snippet)}</span> : null}
                    </span>
                    <span className="sx-meta">
                      <span className={`sx-dot ${h.status}`} />{STATUS_LABEL[h.status] || h.status}
                      <span className="sx-time">{ago(h.updated)}</span>
                    </span>
                    <span className="sx-enter"><Icon name="arrowUp" size={14} className="rot90" /></span>
                  </button>
                ))}
              </Fragment>
            ))}
        </div>

        <div className="sx-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span>
          <span><kbd>Enter</kbd> to open</span>
          <span><kbd>Esc</kbd> to close</span>
          <span className="grow" />
          <span className="faint">{hits ? `${hits.length} result${hits.length === 1 ? "" : "s"}` : ""}</span>
        </div>
      </div>
    </div>
  );
}
