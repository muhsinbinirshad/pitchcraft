"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Composer } from "@/components/Composer";
import { Icon } from "@/components/Icon";
import { PreviewPane } from "@/components/PreviewPane";
import { RunOptions } from "@/components/RunOptions";
import { useApp } from "@/components/Shell";
import { Turn } from "@/components/Turn";
import { Button, Empty, Menu, Status } from "@/components/ui";
import { api, versionDocx, versionPdf } from "@/lib/api";
import type { Proposal } from "@/lib/types";

function Workspace({ id }: { id: string }) {
  const router = useRouter();
  const { toast, keyReady, refreshRecent } = useApp();
  const [prop, setProp] = useState<Proposal | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [acting, setActing] = useState(false);
  const [title, setTitle] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [hidePreview, setHidePreview] = useState(false);
  useEffect(() => { try { setHidePreview(localStorage.getItem("pitchcraft.hidePreview") === "1"); } catch { /* ignore */ } }, []);
  const togglePreview = () => setHidePreview((v) => {
    try { localStorage.setItem("pitchcraft.hidePreview", v ? "0" : "1"); } catch { /* ignore */ }
    return !v;
  });
  const [allTags, setAllTags] = useState<string[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const thread = useRef<HTMLDivElement>(null);
  const lastVersions = useRef(0);
  const editingTitle = useRef(false);

  const load = useCallback(async () => {
    clearTimeout(timer.current);
    try {
      const p = await api.proposal(id);
      setProp(p);
      if (!editingTitle.current) setTitle(p.title);
      const latest = p.versions[p.versions.length - 1].n;
      if (p.versions.length !== lastVersions.current) {
        if (lastVersions.current) refreshRecent();  // a new version may have renamed the proposal
        setVersion(latest); lastVersions.current = p.versions.length;
      }
      if (p.turn_jobs.some((j) => j.status === "planning" || j.status === "applying")) timer.current = setTimeout(load, 2000);
    } catch (e) { setErr((e as Error).message); }
  }, [id, refreshRecent]);

  useEffect(() => { load(); api.proposals().then((l) => setAllTags([...new Set(l.flatMap((x) => x.tags))])).catch(() => {}); return () => clearTimeout(timer.current); }, [load]);
  const turnCount = prop?.turn_jobs.length ?? 0;
  const lastStatus = prop?.turn_jobs[turnCount - 1]?.status;
  useEffect(() => { thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: "smooth" }); }, [turnCount, lastStatus]);

  const busy = Boolean(prop?.turn_jobs.some((j) => j.status === "planning" || j.status === "applying"));
  const pending = prop?.turn_jobs.find((j) => j.status === "planned" || j.status === "needs_answers");

  const run = async (fn: () => Promise<unknown>) => {
    setActing(true);
    try { await fn(); await load(); } catch (e) { toast((e as Error).message); } finally { setActing(false); }
  };

  async function send() {
    if (!keyReady) { toast("Add your Claude API key in Settings first"); router.push("/settings/"); return; }
    if (pending) { toast("Apply or discard the open plan first"); return; }
    setSending(true);
    try {
      await api.sendMessage(id, text, files, baseVersion);
      setText(""); setFiles([]); setBaseVersion(null);
      await load();
    } catch (e) { toast((e as Error).message); } finally { setSending(false); }
  }

  const saveTitle = async () => {
    if (!prop || !title.trim() || title === prop.title) return;
    try { setProp(await api.patchProposal(id, { title: title.trim() })); refreshRecent(); } catch (e) { toast((e as Error).message); }
  };

  const latest = prop ? prop.versions[prop.versions.length - 1].n : 0;
  const shown = version ?? latest;
  const menu = useMemo(() => !prop ? [] : [
    { label: "Download PDF", icon: "pdf", onClick: () => window.open(versionPdf(prop.id, shown), "_blank") },
    prop.status !== "sent" ? { label: "Mark as sent", icon: "send", onClick: () => run(() => api.patchProposal(prop.id, { status: "sent" })) } : null,
    prop.status !== "draft" ? { label: "Back to draft", icon: "edit", onClick: () => run(() => api.patchProposal(prop.id, { status: "draft" })) } : null,
    { label: `Duplicate v${shown} as new proposal`, icon: "copy", onClick: () => run(async () => { const d = await api.duplicate(prop.id, shown); refreshRecent(); router.push(`/p/?id=${d.id}`); }) },
    prop.status !== "archived" ? { label: "Archive", icon: "archive", onClick: () => run(() => api.patchProposal(prop.id, { status: "archived" })) } : null,
    { label: "Delete proposal", icon: "trash", danger: true, onClick: () => { if (confirm("Delete this proposal, its chat and all versions?")) run(async () => { await api.deleteProposal(prop.id); refreshRecent(); router.push("/proposals/"); }); } },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [prop, shown]);

  if (err) return <div className="sheet"><Empty icon="error" title="Proposal not found">{err}</Empty></div>;
  if (!prop) return <div className="sheet"><div className="progress" /></div>;

  return (
    <div className={`ws ${showPreview ? "show-preview" : ""} ${hidePreview ? "no-preview" : ""}`}>
      <div className="ws-head">
        <button className="icon-btn" aria-label="Back to proposals" onClick={() => router.push("/proposals/")}><Icon name="chevronLeft" /></button>
        <div className="grow" style={{ minWidth: 160 }}>
          <input className="ws-title" value={title} onChange={(e) => setTitle(e.target.value)} onFocus={() => { editingTitle.current = true; }} onBlur={() => { editingTitle.current = false; saveTitle(); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} aria-label="Proposal title" />
          <div className="row small muted" style={{ paddingLeft: 8, gap: 6, flexWrap: "wrap" }}>
            {prop.client ? <span className="row" style={{ gap: 4 }}><Icon name="user" size={13} />{prop.client}</span> : null}
            {prop.tags.map((t) => <span key={t} className="tag">{t}</span>)}
          </div>
        </div>
        <div className="viewmode only-wide" role="radiogroup" aria-label="View">
          <button role="radio" aria-checked={hidePreview} className={hidePreview ? "on" : ""} onClick={() => { if (!hidePreview) togglePreview(); }} title="Focus: the conversation only">
            <Icon name="chat" size={16} />Focus
          </button>
          <button role="radio" aria-checked={!hidePreview} className={!hidePreview ? "on" : ""} onClick={() => { if (hidePreview) togglePreview(); }} title="Canvas: the conversation with the live document">
            <Icon name="docText" size={16} />Canvas
          </button>
        </div>
        <Status value={prop.status} label={prop.status === "approved" ? `Approved v${prop.approved_version}` : undefined} />
        <button className="btn tonal sm only-narrow" onClick={() => setShowPreview((v) => !v)}>
          <Icon name={showPreview ? "chat" : "docText"} size={16} />{showPreview ? "Chat" : "Document"}
        </button>
        <a className="btn outlined sm" href={versionDocx(prop.id, shown, true)}><Icon name="download" size={16} />.docx</a>
        <Menu items={menu} />
      </div>
      <div className="ws-body">
        <div className="chat">
          <div className="thread" ref={thread}>
            {prop.turn_jobs.length === 0 ? (
              <Empty icon="chat" title="Start the conversation">Describe what this proposal should say, or what to change. The document on the right is version 0.</Empty>
            ) : prop.turn_jobs.map((j) => (
              <Turn key={j.id} job={j} busyAction={acting}
                onAnswer={(a) => run(() => api.plan(j.id, a))}
                onApply={(sel) => run(() => api.apply(j.id, sel))}
                onDiscard={() => run(() => api.discard(j.id))}
                onRetry={() => run(() => j.plan ? api.apply(j.id, j.selected_ops ?? []) : api.plan(j.id, j.answers || {}))}
                onShowVersion={(n) => { setVersion(n); setShowPreview(true); setHidePreview(false); }} />
            ))}
          </div>
          {hidePreview ? (
            <button className="canvas-fab only-wide" onClick={togglePreview} title="Show the document next to the chat">
              <Icon name="docText" size={18} />Open Canvas
            </button>
          ) : null}
          <div className="chat-foot">
            {baseVersion !== null ? <div className="row small" style={{ padding: "0 8px 6px" }}><Icon name="branch" size={14} />Continuing from v{baseVersion}<button className="btn text sm" onClick={() => setBaseVersion(null)}>Use latest</button></div> : null}
            <Composer text={text} setText={setText} files={files} setFiles={setFiles} onSend={send} busy={sending} disabled={busy || sending}
              options={<RunOptions />}
              placeholder={busy ? "Claude is working…" : pending ? "Apply or discard the plan above first" : "Ask for a change, e.g. make the scope of work section shorter and more diplomatic"} />
          </div>
        </div>
        <PreviewPane prop={prop} version={shown} setVersion={setVersion} baseVersion={baseVersion} setBaseVersion={setBaseVersion}
          onChange={(p) => { setProp(p); refreshRecent(); }} allTags={allTags} acting={acting}
          onApprove={(n) => run(async () => { await api.approve(prop.id, n); refreshRecent(); toast(`Version ${n} approved`); })}
          />
      </div>
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <div className="sheet"><Empty icon="inbox" title="No proposal selected" /></div>;
  return <Workspace key={id} id={id} />;
}

export default function ProposalPage() {
  return <Suspense fallback={<div className="sheet"><div className="progress" /></div>}><Inner /></Suspense>;
}
