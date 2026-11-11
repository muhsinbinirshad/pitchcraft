"use client";

import { Icon } from "./Icon";
import type { Inspection } from "@/lib/types";

/** Shows whether an uploaded .docx is a real proposal and safe to use as a style template. */
export function TemplateCheck({ report, fileName }: { report: Inspection | null; fileName: string; }) {
  if (!report) {
    return (
      <div className="card flat">
        <div className="row"><Icon name="spinner" /><b>Checking {fileName}…</b></div>
        <div className="small muted">Reading the document structure, then Claude checks whether it is a real proposal.</div>
        <div className="progress" />
      </div>
    );
  }
  const st = report.structure;
  const ai = report.ai;
  const tone = report.verdict === "ok" ? "ok" : report.verdict === "reject" ? "err" : report.verdict === "warn" ? "warn" : "info";
  const title = {
    ok: "This is a proposal and can be used as a style template",
    warn: ai && !ai.is_proposal ? "This doesn't look like a proposal" : "Check this document before using it",
    reject: "This file can't be used as a template",
    unchecked: "Structure looks fine (Claude did not check the content)",
  }[report.verdict];
  return (
    <div className="col" style={{ gap: 10 }}>
      <div className={`banner ${tone}`}>
        <Icon name={report.verdict === "ok" ? "checkCircle" : report.verdict === "reject" ? "error" : "warning"} />
        <div className="col" style={{ gap: 4 }}>
          <b>{title}</b>
          {ai ? <span>{ai.document_type}{ai.company ? ` by ${ai.company}` : ""}{ai.client ? `, written for ${ai.client}` : ""}. {ai.summary}</span> : null}
          {report.ai_error ? <span className="small">{report.ai_error}</span> : null}
        </div>
      </div>
      {st.errors.length ? <ul className="ul">{st.errors.map((e) => <li key={e}>{e}</li>)}</ul> : null}
      {ai?.unsafe_content ? <div className="banner err"><Icon name="shield" /><span>It contains text addressed to an AI system. Don't use it as a template unless you trust its source.</span></div> : null}
      {ai?.concerns?.length ? <div><div className="label">Notes</div><ul className="ul small">{ai.concerns.map((c) => <li key={c}>{c}</li>)}</ul></div> : null}
      {st.ok ? (
        <div className="row wrap small muted" style={{ gap: 14 }}>
          <span>{st.stats.words?.toLocaleString()} words</span><span>{st.stats.headings} headings</span>
          <span>{st.stats.tables} tables</span><span>{st.stats.lists} list items</span><span>{st.stats.images} images</span>
        </div>
      ) : null}
      {st.warnings.length ? <ul className="ul small muted">{st.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : null}
    </div>
  );
}
