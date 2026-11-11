import { getSettings } from "./settings";
import type { Health, HistoryItem, Inspection, Job, Proposal, ProposalSummary, Template, User } from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number, public data?: unknown) { super(message); }
}

async function call<T>(path: string, init: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const { apiKey } = getSettings();
  if (apiKey) headers["X-Api-Key"] = apiKey;
  let body: BodyInit | undefined;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  } else if (init.form) body = init.form;
  const res = await fetch(path, { method: init.method || "GET", headers, body, credentials: "same-origin" });
  const isJson = res.headers.get("content-type")?.includes("json");
  const data = isJson ? await res.json() : null;
  if (res.status === 401 && !path.startsWith("/api/auth/") && typeof window !== "undefined") {
    window.location.href = "/login/";
  }
  if (!res.ok) {
    const d = data?.detail;
    throw new ApiError(typeof d === "string" ? d : d ? JSON.stringify(d) : res.statusText, res.status, data);
  }
  return data as T;
}

/** Settings sent along with every AI step, as form fields. */
function aiForm(f: FormData, opts: { autoApply?: boolean } = {}) {
  const s = getSettings();
  f.append("model", s.model);
  f.append("effort", s.effort);
  f.append("review", String(s.review));
  f.append("visual", String(s.visual));
  f.append("auto_apply", String(opts.autoApply ?? s.autoApply));
  return f;
}

const enc = encodeURIComponent;

export const api = {
  health: () => call<Health>("/api/health"),
  // auth
  me: () => call<{ user: User | null; setup_needed: boolean; auth: boolean; default_login?: boolean }>("/api/auth/me"),
  setup: (username: string, password: string) => call<{ user: User }>("/api/auth/setup", { method: "POST", json: { username, password } }),
  login: (username: string, password: string) => call<{ user: User }>("/api/auth/login", { method: "POST", json: { username, password } }),
  logout: () => call("/api/auth/logout", { method: "POST" }),
  changePassword: (old: string, nw: string) => call("/api/auth/password", { method: "POST", json: { old, new: nw } }),
  updateProfile: (patch: { display_name?: string; username?: string }) => call<{ user: User }>("/api/auth/profile", { method: "PATCH", json: patch }),
  changeStats: (pid: string, n: number, against: number) => call<{ changed: number; added: number; removed: number }>(`/api/proposals/${pid}/versions/${n}/changes?against=${against}`),
  users: () => call<User[]>("/api/users"),
  addUser: (username: string, password: string, admin: boolean) => call<User>("/api/users", { method: "POST", json: { username, password, admin } }),
  deleteUser: (u: string) => call(`/api/users/${enc(u)}`, { method: "DELETE" }),
  // templates
  templates: () => call<Template[]>("/api/templates"),
  inspectTemplate: (file: File) => { const f = new FormData(); f.append("file", file); return call<Inspection>("/api/templates/inspect", { method: "POST", form: f }); },
  addTemplate: (file: File, name = "", force = false) => {
    const f = new FormData();
    f.append("file", file); f.append("name", name); f.append("force", String(force));
    return call<Template>("/api/templates", { method: "POST", form: f });
  },
  renameTemplate: (id: string, name: string) => call<Template>(`/api/templates/${id}`, { method: "PATCH", json: { name } }),
  setDefault: (id: string) => call(`/api/templates/${id}/default`, { method: "POST" }),
  deleteTemplate: (id: string) => call(`/api/templates/${id}`, { method: "DELETE" }),
  // proposals
  proposals: (q: Record<string, string> = {}) => call<ProposalSummary[]>(`/api/proposals?${new URLSearchParams(q)}`),
  proposal: (id: string) => call<Proposal>(`/api/proposals/${id}`),
  createProposal: (f: FormData, autoApply?: boolean) => call<Proposal>("/api/proposals", { method: "POST", form: aiForm(f, { autoApply }) }),
  patchProposal: (id: string, patch: Partial<Pick<Proposal, "title" | "client" | "tags" | "status" | "notes" | "due_date">>) =>
    call<Proposal>(`/api/proposals/${id}`, { method: "PATCH", json: patch }),
  deleteProposal: (id: string) => call(`/api/proposals/${id}`, { method: "DELETE" }),
  sendMessage: (id: string, text: string, files: File[], baseVersion: number | null, autoApply?: boolean) => {
    const f = new FormData();
    f.append("instructions", text);
    if (baseVersion !== null) f.append("base_version", String(baseVersion));
    files.forEach((x) => f.append("inputs", x));
    return call<Proposal>(`/api/proposals/${id}/messages`, { method: "POST", form: aiForm(f, { autoApply }) });
  },
  approve: (id: string, version?: number) => call<Proposal>(`/api/proposals/${id}/approve`, { method: "POST", json: { version: version ?? null } }),
  duplicate: (id: string, version?: number) => call<Proposal>(`/api/proposals/${id}/duplicate`, { method: "POST", json: { version: version ?? null } }),
  pageCount: (id: string, n: number) => call<{ count: number }>(`/api/proposals/${id}/versions/${n}/pages`),
  // turns
  job: (id: string) => call<Job>(`/api/jobs/${id}`),
  plan: (id: string, answers: Record<string, string>) => {
    const s = getSettings();
    return call<Job>(`/api/jobs/${id}/plan`, { method: "POST", json: { answers, model: s.model, effort: s.effort, review: s.review, visual: s.visual, auto_apply: s.autoApply } });
  },
  apply: (id: string, selected: number[]) => {
    const s = getSettings();
    return call<Job>(`/api/jobs/${id}/apply`, { method: "POST", json: { selected, model: s.model, effort: s.effort, review: s.review, visual: s.visual } });
  },
  discard: (id: string) => call<Job>(`/api/jobs/${id}/discard`, { method: "POST" }),
  history: () => call<HistoryItem[]>("/api/history"),
};

export const versionDocx = (pid: string, n: number, download = false) => `/api/proposals/${pid}/versions/${n}/docx${download ? "?download=1" : ""}`;
export const versionPdf = (pid: string, n: number) => `/api/proposals/${pid}/versions/${n}/pdf`;
export const versionPage = (pid: string, n: number, p: number) => `/api/proposals/${pid}/versions/${n}/pages/${p}`;
export const templatePage = (tid: string, n: number) => `/api/templates/${tid}/preview/${n}`;
export const searchProposals = (q: string) =>
  fetch(`/api/search?q=${encodeURIComponent(q)}`, { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : []));
export const templatePageCount = (tid: string) =>
  fetch(`/api/templates/${tid}/pages`, { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : { count: 0 })) as Promise<{ count: number }>;
export const changesPdf = (pid: string, n: number, against: number) => `/api/proposals/${pid}/versions/${n}/changes.pdf?against=${against}`;
export const displayName = (u?: { username: string; display_name?: string } | null) => (u ? u.display_name || u.username : "");
