"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import type { Op, OpResult } from "@/lib/types";

const q = (s?: string | null, n = 70) => `“${(s || "").length > n ? (s || "").slice(0, n) + "…" : s || ""}”`;

export function describeOp(op: Op, refs: Record<string, string>): string {
  switch (op.op) {
    case "replace_text": return `Replace ${q(op.find, 50)} → ${q(op.replace, 50)}${op.expect && op.expect > 1 ? ` (${op.expect} places)` : ""}`;
    case "set_text": return `Rewrite ${op.target && refs[op.target] ? q(refs[op.target], 60) : op.target}`;
    case "insert_after": return `Add ${op.items?.length || 0} new block${op.items?.length === 1 ? "" : "s"}${op.items?.[0]?.text ? `: ${q(op.items[0].text, 50)}` : ""}`;
    case "insert_rows": return `Add ${op.rows?.length || 0} table row${op.rows?.length === 1 ? "" : "s"}${op.rows?.[0]?.[0] ? `: ${q(op.rows[0][0], 40)}` : ""}`;
    case "delete": return `Remove ${(op.targets || []).length} item${(op.targets || []).length === 1 ? "" : "s"}${op.targets?.[0] && refs[op.targets[0]] ? `: ${q(refs[op.targets[0]], 50)}` : ""}`;
    case "insert_table": return `New table, ${op.rows?.[0]?.length || 0} columns × ${Math.max(0, (op.rows?.length || 1) - 1)} rows${op.rows?.[0]?.length ? `: ${q(op.rows[0].join(" | "), 50)}` : ""}`;
    case "delete_range": return `Remove a section${op.anchor && refs[op.anchor] ? `: from ${q(refs[op.anchor], 40)}` : ""}${op.target && refs[op.target] ? ` to ${q(refs[op.target], 30)}` : ""}`;
  }
}

function Diff({ kind, tag, children }: { kind: "add" | "del" | "ctx"; tag: string; children: React.ReactNode }) {
  return <div className={`diff ${kind}`}><span className="tg">{tag}</span>{children}</div>;
}

function Body({ op, refs }: { op: Op; refs: Record<string, string> }) {
  const parts: React.ReactNode[] = [];
  if (op.op === "replace_text") parts.push(<Diff key="f" kind="del" tag="Before">{op.find}</Diff>, <Diff key="r" kind="add" tag="After">{op.replace}</Diff>);
  if (op.op === "set_text") {
    if (op.target && refs[op.target]) parts.push(<Diff key="c" kind="del" tag="Before">{refs[op.target]}</Diff>);
    parts.push(<Diff key="n" kind="add" tag="After">{op.replace}</Diff>);
  }
  if (op.op === "insert_after") {
    if (op.anchor && refs[op.anchor]) parts.push(<Diff key="a" kind="ctx" tag="After this">{refs[op.anchor]}</Diff>);
    (op.items || []).forEach((it, i) => parts.push(<Diff key={i} kind="add" tag={`New · styled like ${it.like}`}>{it.text ?? `Copy of table ${it.like}`}</Diff>));
  }
  if (op.op === "insert_rows") {
    if (op.anchor && refs[op.anchor]) parts.push(<Diff key="a" kind="ctx" tag="After row">{refs[op.anchor]}</Diff>);
    (op.rows || []).forEach((r, i) => parts.push(<Diff key={i} kind="add" tag="New row">{r.filter(Boolean).join("  |  ")}</Diff>));
  }
  if (op.op === "delete") (op.targets || []).forEach((t) => parts.push(<Diff key={t} kind="del" tag="Removed">{refs[t] || t}</Diff>));
  if (op.op === "insert_table") {
    if (op.anchor && refs[op.anchor]) parts.push(<Diff key="a" kind="ctx" tag="After this">{refs[op.anchor]}</Diff>);
    (op.rows || []).forEach((r, i) => parts.push(<Diff key={i} kind="add" tag={i === 0 ? `Header · styled like ${op.like}` : `Row ${i}`}>{r.join("  |  ")}</Diff>));
  }
  if (op.op === "delete_range") {
    if (op.anchor && refs[op.anchor]) parts.push(<Diff key="a" kind="del" tag="From">{refs[op.anchor]}</Diff>);
    if (op.target && refs[op.target]) parts.push(<Diff key="b" kind="del" tag="Through">{refs[op.target]}</Diff>);
  }
  if (op.evidence) parts.push(<div key="e" className="evidence"><Icon name="quote" size={14} /><span>{op.evidence}</span></div>);
  return <div className="op-body">{parts}</div>;
}

export function OpRow({ op, index, refs, selectable, selected, result, onToggle }: {
  op: Op; index: number; refs: Record<string, string>; selectable?: boolean; selected?: boolean;
  result?: OpResult; onToggle?: (v: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const failed = result && !result.ok;
  return (
    <div className={`op ${failed ? "failed" : ""}`}>
      {selectable
        ? <input type="checkbox" className="checkbox" style={{ marginTop: 2 }} checked={selected} aria-label={`Include change ${index + 1}`} onChange={(e) => onToggle?.(e.target.checked)} />
        : <span className="small faint" style={{ minWidth: 18 }}>{index + 1}</span>}
      <div style={{ minWidth: 0 }}>
        <div className="op-title">{describeOp(op, refs)}</div>
        <div className="op-reason">{failed ? `Not applied: ${result!.error}` : op.reason}</div>
        {open ? <Body op={op} refs={refs} /> : null}
      </div>
      <button className="icon-btn sm" aria-label={open ? "Hide details" : "Show details"} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="chevronDown" size={18} className={open ? "rot" : ""} />
      </button>
    </div>
  );
}
