"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/Icon";
import { Select } from "@/components/Select";
import { useApp } from "@/components/Shell";
import { LinkButton, Menu, Status, fmtTime } from "@/components/ui";
import { api, versionPage } from "@/lib/api";
import type { ProposalSummary } from "@/lib/types";

const DAY = 86400000;
const startOfDay = (d: Date) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x.getTime(); };

/** People remember when a proposal was made: group by day, then week, then month. */
function dateGroup(t: number, now = new Date()) {
  const ms = t * 1000, today = startOfDay(now), d = new Date(ms);
  if (ms >= today) return { key: "today", label: "Today", order: today };
  if (ms >= today - DAY) return { key: "yesterday", label: "Yesterday", order: today - DAY };
  if (ms >= today - 6 * DAY) { const day = startOfDay(d); return { key: `d${day}`, label: d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" }), order: day }; }
  if (ms >= today - 13 * DAY) return { key: "lastweek", label: "Last week", order: today - 7 * DAY };
  const m = new Date(d.getFullYear(), d.getMonth(), 1).getTime();
  return { key: `m${m}`, label: d.toLocaleDateString(undefined, { month: "long", year: "numeric" }), order: m };
}

function Cover({ p }: { p: ProposalSummary }) {
  const [ok, setOk] = useState(true);
  return (
    <span className="sq-cover">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {ok ? <img src={versionPage(p.id, p.approved_version ?? p.versions, 1)} alt="" loading="lazy" onError={() => setOk(false)} /> : <Icon name="docText" size={36} />}
    </span>
  );
}

function Thumb({ p }: { p: ProposalSummary }) {
  const [ok, setOk] = useState(true);
  return (
    <span className="pr-thumb">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {ok ? <img src={versionPage(p.id, p.approved_version ?? p.versions, 1)} alt="" loading="lazy" onError={() => setOk(false)} /> : <Icon name="docText" size={22} />}
    </span>
  );
}

export default function Proposals() {
  const router = useRouter();
  const { toast, refreshRecent } = useApp();
  const [all, setAll] = useState<ProposalSummary[] | null>(null);
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const [status, setStatus] = useState("");

  const load = useCallback(() => api.proposals().then(setAll).catch((e) => toast(e.message)), [toast]);
  useEffect(() => { load(); }, [load]);

  const tagCounts = useMemo(() => {
    const m = new Map<string, number>();
    (all || []).forEach((p) => p.tags.forEach((t) => m.set(t, (m.get(t) || 0) + 1)));
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [all]);

  const groups = useMemo(() => {
    const list = (all || []).filter((p) => {
      if (tag && !p.tags.includes(tag)) return false;
      if (status ? p.status !== status : p.status === "archived") return false;
      if (q) {
        const hay = `${p.client} ${p.title} ${p.tags.join(" ")} ${p.notes || ""} ${p.last_turn?.instructions || ""}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    }).sort((a, b) => b.created - a.created);
    const m = new Map<string, { label: string; order: number; items: ProposalSummary[] }>();
    for (const p of list) {
      const g = dateGroup(p.created);
      if (!m.has(g.key)) m.set(g.key, { label: g.label, order: g.order, items: [] });
      m.get(g.key)!.items.push(p);
    }
    return [...m.values()].sort((a, b) => b.order - a.order);
  }, [all, tag, status, q]);

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast(msg); load(); refreshRecent(); } catch (e) { toast((e as Error).message); }
  };
  const menuFor = (p: ProposalSummary) => [
    p.status !== "approved" ? { label: "Approve latest version", icon: "checkCircle", onClick: () => act(() => api.approve(p.id), "Approved") } : null,
    p.status !== "sent" ? { label: "Mark as sent", icon: "send", onClick: () => act(() => api.patchProposal(p.id, { status: "sent" }), "Marked as sent") } : null,
    p.status !== "draft" ? { label: "Back to draft", icon: "edit", onClick: () => act(() => api.patchProposal(p.id, { status: "draft" }), "Moved to drafts") } : null,
    { label: "Duplicate", icon: "copy", onClick: () => act(() => api.duplicate(p.id), "Duplicated") },
    p.status !== "archived" ? { label: "Archive", icon: "archive", onClick: () => act(() => api.patchProposal(p.id, { status: "archived" }), "Archived") } : null,
    { label: "Delete", icon: "trash", danger: true, onClick: () => { if (confirm(`Delete “${p.title}” and all its versions?`)) act(() => api.deleteProposal(p.id), "Deleted"); } },
  ];
  const total = (all || []).filter((p) => p.status !== "archived").length;

  return (
    <div className="soft-page">
      <div className="sq-wrap">
        <div className="sq-head">
          <div className="sq-title">
            <h1>Proposals</h1>
            <span className="sq-count">{all === null ? "…" : total}</span>
          </div>
          <label className="sq-search">
            <Icon name="search" size={20} />
            <input placeholder="Search clients, titles, tags or requests" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search proposals" />
            {q ? <button className="icon-btn sm" aria-label="Clear search" onClick={() => setQ("")}><Icon name="x" size={18} /></button> : null}
          </label>
          <LinkButton href="/new/" icon="sparkle" variant="ai">New proposal</LinkButton>
        </div>

        <div className="sq-bar">
          <div className="soft-filters" style={{ padding: 0, flex: 1 }}>
            <div className="pill-row">
              <button className={`pill-chip ${!tag ? "on" : ""}`} onClick={() => setTag("")}>All</button>
              {tagCounts.map(([t, n]) => (
                <button key={t} className={`pill-chip ${tag === t ? "on" : ""}`} onClick={() => setTag(tag === t ? "" : t)}>{t}<span>{n}</span></button>
              ))}
            </div>
            <Select small align="right" label="Status" value={status} onChange={setStatus} width={200}
              options={[{ value: "", label: "All active" }, { value: "draft", label: "Drafts" }, { value: "approved", label: "Approved" }, { value: "sent", label: "Sent" }, { value: "archived", label: "Archived" }]} />
          </div>
        </div>

        {all === null ? <div className="progress" /> : groups.length === 0 ? (
          <div className="soft-empty">
            <span className="greet-mark"><Icon name={all.length ? "search" : "sparkle"} size={24} /></span>
            <h3>{all.length ? "Nothing matches" : "No proposals yet"}</h3>
            <p className="muted">{all.length ? "Try another word or tag." : "Describe a client and its scope in one message, and Claude writes the proposal in your template's style."}</p>
            {!all.length ? <LinkButton href="/new/" icon="sparkle" variant="ai">Create a proposal</LinkButton> : null}
          </div>
        ) : groups.map((g) => (
          <section key={g.label} className="soft-group">
            <div className="sq-group-h"><span>{g.label}</span><span className="faint">{g.items.length}</span></div>
            <div className="sq-grid">
              {g.items.map((p) => (
                <div key={p.id} className="sq" role="link" tabIndex={0}
                  onClick={() => router.push(`/p/?id=${p.id}`)} onKeyDown={(e) => { if (e.key === "Enter") router.push(`/p/?id=${p.id}`); }}>
                  <div className="sq-top">
                    <Cover p={p} />
                    <span className={`sq-status st-${p.status}`}>{p.status === "approved" ? `Approved v${p.approved_version}` : p.status === "draft" ? `Draft · v${p.versions}` : p.status === "sent" ? "Sent" : "Archived"}</span>
                    <span className="sq-menu" onClick={(e) => e.stopPropagation()}><Menu items={menuFor(p)} /></span>
                  </div>
                  <div className="sq-body">
                    <div className="sq-client">{p.client || "No client yet"}</div>
                    <div className="sq-sub">{p.title}</div>
                    <div className="sq-foot">
                      <span className="sq-tags">{p.tags.slice(0, 3).map((t) => <span key={t} className="pr-tag">{t}</span>)}{p.tags.length > 3 ? <span className="pr-tag">+{p.tags.length - 3}</span> : null}</span>
                      <span className="sq-time">{fmtTime(p.created)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
