"use client";

import { useEffect, useState } from "react";
import { Icon } from "./Icon";
import { OpRow } from "./OpRow";
import { Button, Status, fmtDateTime } from "./ui";
import type { Audit, Job } from "@/lib/types";

const CHECK_LABEL: Record<string, string> = {
  numbers: "Numbers", stale: "Old values", placeholders: "No placeholders", leftovers: "Old client details", style: "Style", structure: "Structure", render: "Opens cleanly",
};

export function ChecksRow({ audits }: { audits: Audit[] }) {
  return (
    <div className="checks">
      {audits.map((a) => (
        <span key={a.check} className={`status lv-${a.level}`} title={a.message}>
          <Icon name={a.level === "pass" ? "check" : a.level === "warn" ? "warning" : "error"} size={13} />{CHECK_LABEL[a.check] || a.check}
        </span>
      ))}
    </div>
  );
}

function Questions({ job, onAnswer, busy }: { job: Job; onAnswer: (a: Record<string, string>) => void; busy: boolean }) {
  const [answers, setAnswers] = useState<Record<string, string>>(job.answers || {});
  useEffect(() => setAnswers(job.answers || {}), [job.id, job.answers]);
  const missing = job.questions.filter((q) => q.blocking && !answers[q.id]?.trim()).length;
  return (
    <div className="ai-card q">
      <div className="row"><Icon name="help" size={18} /><b>A few things I need to know</b></div>
      {job.questions.map((q) => (
        <div key={q.id} className="qbox">
          <div className="row" style={{ alignItems: "flex-start" }}>
            <span className="grow"><b>{q.question}</b>{q.why ? <span className="hint">{q.why}</span> : null}</span>
            {q.blocking ? <span className="status st-draft">Needed</span> : <span className="status">Optional</span>}
          </div>
          {q.options.length ? (
            <div className="row wrap" style={{ gap: 6 }}>
              {q.options.map((o) => (
                <button key={o} className={`chip wraps ${answers[q.id] === o ? "on" : ""}`} onClick={() => setAnswers({ ...answers, [q.id]: o })}>{o}</button>
              ))}
            </div>
          ) : null}
          <input className="input sm" placeholder="Type an answer" value={answers[q.id] || ""} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />
        </div>
      ))}
      <div className="row">
        <div className="grow small muted">{missing ? `${missing} answer${missing === 1 ? "" : "s"} still needed` : "Ready to continue"}</div>
        <Button small icon="send" busy={busy} disabled={missing > 0} onClick={() => onAnswer(answers)}>Continue</Button>
      </div>
    </div>
  );
}

export function Turn({ job, onAnswer, onApply, onDiscard, onRetry, onShowVersion, busyAction }: {
  job: Job;
  onAnswer: (a: Record<string, string>) => void;
  onApply: (selected: number[]) => void;
  onDiscard: () => void;
  onRetry: () => void;
  onShowVersion: (n: number) => void;
  busyAction: boolean;
}) {
  const plan = job.plan;
  const ops = plan?.ops || [];
  const refs = job.plan_refs || {};
  const [selected, setSelected] = useState<Set<number>>(new Set(job.selected_ops ?? ops.map((_, i) => i)));
  const [showOps, setShowOps] = useState(false);
  useEffect(() => { setSelected(new Set(job.selected_ops ?? (job.plan?.ops || []).map((_, i) => i))); }, [job.id, job.plan, job.selected_ops]);
  const busy = job.status === "planning" || job.status === "applying";
  const results = Object.fromEntries(job.op_results.map((r) => [r.index, r]));
  const failed = job.op_results.filter((r) => !r.ok).length;
  const reviewOps = job.review_plan?.ops || [];

  return (
    <>
      <div className="msg-user">
        {job.instructions ? <div className="bubble">{job.instructions}</div> : null}
        {job.inputs.length ? (
          <div className="row wrap" style={{ justifyContent: "flex-end", gap: 6 }}>
            {job.inputs.map((n) => (
              <a key={n} className="tag" href={`/api/jobs/${job.id}/inputs/${encodeURIComponent(n)}`} target="_blank" rel="noreferrer">
                <Icon name={/\.(png|jpe?g|gif|webp)$/i.test(n) ? "image" : "file"} size={14} />{n}
              </a>
            ))}
          </div>
        ) : null}
        <div className="msg-meta">
          {job.author ? <span>{job.author}</span> : null}<span>{fmtDateTime(job.created)}</span>
          {job.base_version !== null ? <span>· on v{job.base_version}</span> : null}
          {job.mode === "new" ? <span>· new proposal from template</span> : null}
        </div>
      </div>

      <div className="msg-ai">
        <span className={`ai-av ${busy ? "busy" : ""}`}><Icon name="sparkle" size={18} /></span>
        <div className="ai-body">
          {busy ? (
            <div className="ai-card thinking">
              <div className="row"><b className="grow">{job.stage || "Working…"}</b><Status value={job.status} /></div>
              <div className="progress" />
              <div className="small muted">{job.status === "planning" ? "Claude reads the whole document and every attachment. A full new proposal can take a few minutes." : "Applying the edits, re-reading the result and rendering the pages."}</div>
            </div>
          ) : null}

          {job.status === "error" ? (
            <div className="banner err"><Icon name="error" size={18} />
              <div className="col" style={{ gap: 8 }}><span>{job.error}</span>
                <div className="row"><Button small variant="tonal" icon="refresh" onClick={onRetry}>Try again</Button><Button small variant="text" onClick={onDiscard}>Dismiss</Button></div></div>
            </div>
          ) : null}

          {job.status === "discarded" ? <div className="small muted">Plan discarded. Nothing was changed.</div> : null}

          {plan && !busy && job.status !== "discarded" ? (
            <div className="ai-card">
              <div>{plan.understanding}</div>
              {job.status === "done" ? (
                <>
                  <div className="row wrap">
                    {job.version !== null ? <button className="ver-badge" onClick={() => onShowVersion(job.version!)}><Icon name="docText" size={14} />Version {job.version}</button> : null}
                    <span className="small muted">{job.op_results.length - failed} of {job.op_results.length} edits applied{reviewOps.length ? `, review pass added ${reviewOps.length}` : ""}{failed ? `, ${failed} skipped` : ""}</span>
                  </div>
                  <ChecksRow audits={job.audits} />
                </>
              ) : null}
              {plan.summary.changes.length ? (
                <div><div className="label" style={{ marginBottom: 4 }}>{job.status === "done" ? "What changed" : "What I'll change"}</div>
                  <ul className="ul">{plan.summary.changes.map((c) => <li key={c}>{c}</li>)}</ul></div>
              ) : null}
              {plan.summary.please_check.length ? (
                <div><div className="label" style={{ marginBottom: 4 }}>To finish this, reply with</div>
                  <ul className="ul">{plan.summary.please_check.map((c) => <li key={c}>{c}</li>)}</ul></div>
              ) : null}
              {job.visual_issues.length ? (
                <div className="banner warn"><Icon name="eye" size={18} /><ul className="ul">{job.visual_issues.map((v, i) => <li key={i}>Page {v.page}: {v.issue}</li>)}</ul></div>
              ) : null}
              {job.audits.filter((a) => a.level !== "pass" && a.details.length).map((a) => (
                <details key={a.check}><summary className="small">{CHECK_LABEL[a.check] || a.check}: {a.message}</summary>
                  <ul className="ul small muted">{a.details.slice(0, 15).map((d) => <li key={d}>{d}</li>)}</ul></details>
              ))}
              {ops.length ? (
                <div>
                  <button className="btn text sm" style={{ marginLeft: -12 }} onClick={() => setShowOps((v) => !v)}>
                    <Icon name="chevronDown" size={16} className={showOps ? "rot" : ""} />{showOps ? "Hide" : "Show"} the {ops.length} edit{ops.length === 1 ? "" : "s"}
                  </button>
                  {showOps ? (
                    <div className="ops">
                      {job.status === "planned" ? (
                        <div className="row" style={{ padding: "6px 0" }}>
                          <button className="btn text sm" onClick={() => setSelected(new Set(ops.map((_, i) => i)))}>Select all</button>
                          <button className="btn text sm" onClick={() => setSelected(new Set())}>None</button>
                        </div>
                      ) : null}
                      {ops.map((op, i) => (
                        <OpRow key={i} op={op} index={i} refs={refs} selectable={job.status === "planned"} selected={selected.has(i)} result={results[i]}
                          onToggle={(on) => setSelected((s) => { const n = new Set(s); on ? n.add(i) : n.delete(i); return n; })} />
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {job.status === "planned" ? (
                <div className="row wrap">
                  <Button small icon="check" busy={busyAction} disabled={!selected.size} onClick={() => onApply([...selected].sort((a, b) => a - b))}>
                    Apply {selected.size === ops.length ? "" : `${selected.size} of `}{ops.length} edit{ops.length === 1 ? "" : "s"}
                  </Button>
                  <Button small variant="text" onClick={onDiscard}>Discard</Button>
                </div>
              ) : null}
            </div>
          ) : null}

          {job.status === "needs_answers" || (job.questions.length && job.status === "planned" && !ops.length) ? (
            <Questions job={job} busy={busyAction} onAnswer={onAnswer} />
          ) : null}
        </div>
      </div>
    </>
  );
}
