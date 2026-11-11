export type JobStatus = "created" | "planning" | "needs_answers" | "planned" | "applying" | "done" | "error" | "discarded";
export type ProposalStatus = "draft" | "approved" | "sent" | "archived";

export interface InsertItem { like: string; text: string | null; new_id: string | null }

export interface Op {
  op: "replace_text" | "set_text" | "insert_after" | "insert_rows" | "delete" | "insert_table" | "delete_range";
  find: string | null;
  replace: string | null;
  expect: number | null;
  target: string | null;
  anchor: string | null;
  like: string | null;
  items: InsertItem[] | null;
  rows: string[][] | null;
  targets: string[] | null;
  new_id?: string | null;
  reason: string;
  evidence: string;
}

export interface Question { id: string; question: string; why: string; options: string[]; blocking: boolean }

export interface Plan {
  understanding: string;
  facts: { fact: string; source: string }[];
  questions: Question[];
  fact_changes: { old: string; new: string }[];
  reference_terms?: string[];
  ops: Op[];
  summary: { changes: string[]; please_check: string[] };
}

export interface OpResult { index: number; ok: boolean; error: string | null }
export interface Audit { check: string; level: "pass" | "warn" | "fail"; message: string; details: string[] }

export interface Job {
  id: string;
  proposal_id: string | null;
  base_version: number | null;
  version: number | null;
  author: string | null;
  title: string;
  mode: "edit" | "new";
  status: JobStatus;
  stage: string;
  error: string | null;
  created: number;
  updated: number;
  base_name: string;
  instructions: string;
  inputs: string[];
  questions: Question[];
  answers: Record<string, string>;
  plan: Plan | null;
  plan_refs?: Record<string, string>;
  plan_errors?: string[];
  selected_ops: number[] | null;
  review_plan: Plan | null;
  review_results?: OpResult[];
  op_results: OpResult[];
  audits: Audit[];
  usage: Record<string, number>;
  changed_pages: number[];
  page_count: number;
  visual_issues: { page: number; severity: string; issue: string }[];
}

export interface Version { n: number; job_id: string | null; created: number; label: string; base_version?: number | null }

export interface Proposal {
  id: string;
  title: string;
  client: string;
  tags: string[];
  status: ProposalStatus;
  mode: "edit" | "new";
  created: number;
  updated: number;
  approved_at: number | null;
  approved_version: number | null;
  approved_by?: string | null;
  created_by: string | null;
  template_id: string | null;
  base_name: string;
  notes?: string;
  due_date?: string;
  turns: string[];
  versions: Version[];
  turn_jobs: Job[];
}

export interface ProposalSummary {
  id: string;
  title: string;
  client: string;
  tags: string[];
  status: ProposalStatus;
  created: number;
  updated: number;
  approved_at: number | null;
  approved_version: number | null;
  created_by: string | null;
  base_name: string;
  mode: string;
  due_date?: string;
  notes?: string;
  versions: number;
  turns: number;
  last_turn: { status: JobStatus; instructions: string; id: string } | null;
}

export interface Inspection {
  structure: { ok: boolean; errors: string[]; warnings: string[]; stats: Record<string, number>; headings: string[] };
  ai: { is_proposal: boolean; confidence: string; document_type: string; company: string; client: string; summary: string; concerns: string[]; unsafe_content: boolean } | null;
  ai_error: string | null;
  verdict: "ok" | "warn" | "reject" | "unchecked";
}

export interface Template {
  id: string;
  name: string;
  filename: string;
  created: number;
  is_default: boolean;
  has_preview: boolean;
  inspection?: Inspection;
}

export interface HistoryItem {
  id: string;
  proposal_id: string | null;
  proposal_title: string;
  client: string;
  status: JobStatus;
  instructions: string;
  created: number;
  author: string | null;
  version: number | null;
  mode: string;
  usage: Record<string, number>;
}

export interface User { username: string; admin: boolean; display_name?: string; created?: number; must_change?: boolean }
export interface Health { ok: boolean; renderer: boolean; renderer_missing?: string[]; server_key: boolean; models: Record<string, string>; auth: boolean }
