"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { EFFORTS } from "@/components/RunOptions";
import { Select } from "@/components/Select";
import { useApp } from "@/components/Shell";
import { Button, fmtDate } from "@/components/ui";
import { api, displayName } from "@/lib/api";
import { Settings, useSettings } from "@/lib/settings";
import { ThemePref, useTheme } from "@/lib/theme";
import type { User } from "@/lib/types";

type Section = "profile" | "appearance" | "security" | "ai" | "team" | "about";

function Appearance() {
  const [pref, setPref] = useTheme();
  const opts: { id: ThemePref; label: string; icon: string; side: string; main: string; line: string }[] = [
    { id: "light", label: "Light", icon: "sun", side: "#f0f4f9", main: "#ffffff", line: "#e1e3e1" },
    { id: "dark", label: "Dark", icon: "moon", side: "#131314", main: "#1e1f20", line: "#3c4043" },
    { id: "system", label: "Match system", icon: "monitor", side: "linear-gradient(90deg,#f0f4f9 50%,#131314 50%)", main: "linear-gradient(90deg,#ffffff 50%,#1e1f20 50%)", line: "#9aa0a6" },
  ];
  return (
    <section className="st-card">
      <div className="st-card-h"><h3>Theme</h3></div>
      <div className="theme-opts" role="radiogroup" aria-label="Theme">
        {opts.map((o) => (
          <button key={o.id} role="radio" aria-checked={pref === o.id} className={`theme-opt ${pref === o.id ? "on" : ""}`} onClick={() => setPref(o.id)}
            style={{ ["--tp-side" as string]: o.side, ["--tp-main" as string]: o.main, ["--tp-line" as string]: o.line, ["--tp-accent" as string]: "#4285f4" }}>
            <span className="theme-prev"><span className="a" /><span className="b"><i /><i /><i /></span></span>
            <span className="tl"><Icon name={o.icon} size={18} />{o.label}{pref === o.id ? <Icon name="check" size={16} /> : null}</span>
          </button>
        ))}
      </div>
      <div className="small muted" style={{ paddingBottom: 16 }}>Proposal pages always show on white, like the printed document. Saved in this browser.</div>
    </section>
  );
}

function Row({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="st-row">
      <div className="st-row-l"><div className="st-row-t">{title}</div>{hint ? <div className="st-row-h">{hint}</div> : null}</div>
      <div className="st-row-r">{children}</div>
    </div>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return <label className="switch" aria-label={label}><input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} /></label>;
}

function Profile() {
  const { user, setUser, toast } = useApp();
  const [name, setName] = useState(user?.display_name || "");
  const [username, setUsername] = useState(user?.username || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setName(user?.display_name || ""); setUsername(user?.username || ""); }, [user]);
  const dirty = name !== (user?.display_name || "") || username !== user?.username;
  const save = async () => {
    setBusy(true);
    try { const r = await api.updateProfile({ display_name: name, username }); setUser(r.user); toast("Profile saved"); }
    catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <>
      <div className="st-hero">
        <span className="st-avatar">{(name || username || "?").slice(0, 1).toUpperCase()}</span>
        <div><div className="st-hero-name">{name || username}</div><div className="muted">@{user?.username}{user?.admin ? " · Admin" : " · Member"}</div></div>
      </div>
      <section className="st-card">
        <Row title="Display name" hint="Shown in the sidebar, the greeting and next to your messages.">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Alex Morgan" maxLength={80} />
        </Row>
        <Row title="Username" hint="Used to sign in. Letters, digits, dot, underscore, @ and dash. Your history moves with it.">
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value.trim())} autoComplete="username" />
        </Row>
        <div className="st-actions"><Button busy={busy} disabled={!dirty || username.length < 3} onClick={save}>Save changes</Button></div>
      </section>
    </>
  );
}

function Security() {
  const { toast } = useApp();
  const [oldPw, setOldPw] = useState(""); const [newPw, setNewPw] = useState(""); const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const mismatch = again.length > 0 && again !== newPw;
  return (
    <section className="st-card">
      <Row title="Current password"><input className="input" type="password" autoComplete="current-password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} /></Row>
      <Row title="New password" hint="At least 8 characters."><input className="input" type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNewPw(e.target.value)} /></Row>
      <Row title="Confirm new password">
        <input className="input" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        {mismatch ? <span className="hint" style={{ color: "var(--err)" }}>The passwords don&apos;t match</span> : null}
      </Row>
      <div className="st-actions">
        <span className="small muted grow">Changing your password signs you out on other devices.</span>
        <Button busy={busy} disabled={!oldPw || newPw.length < 8 || newPw !== again} onClick={async () => {
          setBusy(true);
          try { await api.changePassword(oldPw, newPw); setOldPw(""); setNewPw(""); setAgain(""); toast("Password changed"); }
          catch (e) { toast((e as Error).message); } finally { setBusy(false); }
        }}>Change password</Button>
      </div>
    </section>
  );
}

function AI() {
  const { toast, health } = useApp();
  const [settings, save] = useSettings();
  const [draft, setDraft] = useState<Settings>(settings);
  const [show, setShow] = useState(false);
  useEffect(() => setDraft(settings), [settings]);
  const set = (p: Partial<Settings>) => setDraft((d) => ({ ...d, ...p }));
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings);
  return (
    <>
      <section className="st-card">
        <div className="st-card-h"><h3>Claude API key</h3>
          {settings.apiKey ? <span className="status st-approved">Saved in this browser</span> : health.server_key ? <span className="status st-sent">Using the server key</span> : <span className="status st-draft">Not set</span>}</div>
        <div className="st-key">
          <input className="input" type={show ? "text" : "password"} autoComplete="off" placeholder="sk-ant-…" value={draft.apiKey} onChange={(e) => set({ apiKey: e.target.value.trim() })} />
          <button className="icon-btn" aria-label={show ? "Hide key" : "Show key"} onClick={() => setShow((v) => !v)}><Icon name={show ? "lock" : "eye"} /></button>
        </div>
        <div className="small muted">Stored only in this browser and sent with each AI request. The server never saves it.{health.server_key ? " When it's empty, the server's key is used." : ""}</div>
      </section>
      <section className="st-card">
        <Row title="Model" hint="Opus gives the most accurate plans; Sonnet is faster and cheaper.">
          <Select label="Model" value={draft.model} onChange={(v) => set({ model: v })} options={Object.entries(health.models).map(([id, label]) => ({ value: id, label }))} />
        </Row>
        <Row title="Effort" hint="How long Claude thinks before planning. High is recommended.">
          <Select label="Effort" value={draft.effort} onChange={(v) => set({ effort: v as Settings["effort"] })} options={EFFORTS} />
        </Row>
        <Row title="Apply automatically" hint="When Claude has no questions, apply the plan without waiting for you.">
          <Toggle label="Apply automatically" checked={draft.autoApply} onChange={(v) => set({ autoApply: v })} />
        </Row>
        <Row title="Review pass" hint="A second Claude pass that fixes missed updates and old client details.">
          <Toggle label="Review pass" checked={draft.review} onChange={(v) => set({ review: v })} />
        </Row>
        <Row title="Visual check" hint="Claude looks at the changed pages for layout problems after rendering.">
          <Toggle label="Visual check" checked={draft.visual} onChange={(v) => set({ visual: v })} />
        </Row>
        <div className="st-actions">
          {dirty ? <Button variant="text" onClick={() => setDraft(settings)}>Discard</Button> : null}
          <Button disabled={!dirty} onClick={() => { save(draft); toast("AI settings saved"); }}>Save</Button>
        </div>
      </section>
    </>
  );
}

function Team() {
  const { toast, user } = useApp();
  const [users, setUsers] = useState<User[]>([]);
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [admin, setAdmin] = useState(false);
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => api.users().then(setUsers).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  return (
    <section className="st-card">
      <div className="st-card-h"><h3>Members</h3><Button variant="tonal" small icon="plus" onClick={() => setAdding((v) => !v)}>Add member</Button></div>
      {adding ? (
        <div className="st-add">
          <input className="input" placeholder="Username" value={u} onChange={(e) => setU(e.target.value.trim())} />
          <input className="input" placeholder="Temporary password (8+ chars)" type="password" autoComplete="new-password" value={p} onChange={(e) => setP(e.target.value)} />
          <label className="row small" style={{ whiteSpace: "nowrap" }}><input type="checkbox" className="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} />Admin</label>
          <Button disabled={u.length < 3 || p.length < 8} onClick={async () => {
            try { await api.addUser(u, p, admin); setU(""); setP(""); setAdmin(false); setAdding(false); toast("Member added"); load(); } catch (e) { toast((e as Error).message); }
          }}>Add</Button>
        </div>
      ) : null}
      <div className="st-members">
        {users.map((x) => (
          <div key={x.username} className="st-member">
            <span className="avatar">{displayName(x).slice(0, 1).toUpperCase()}</span>
            <div className="grow" style={{ minWidth: 0 }}>
              <div className="ellipsis"><b>{displayName(x)}</b>{x.username === user?.username ? <span className="muted"> (you)</span> : null}</div>
              <div className="small muted">@{x.username}{x.created ? ` · joined ${fmtDate(x.created)}` : ""}</div>
            </div>
            <span className={`status ${x.admin ? "st-sent" : ""}`}>{x.admin ? "Admin" : "Member"}</span>
            {x.username !== user?.username ? (
              <button className="icon-btn sm" aria-label={`Remove ${x.username}`} onClick={async () => {
                if (!confirm(`Remove ${displayName(x)}?`)) return;
                try { await api.deleteUser(x.username); load(); } catch (e) { toast((e as Error).message); }
              }}><Icon name="trash" size={18} /></button>
            ) : <span style={{ width: 32 }} />}
          </div>
        ))}
      </div>
    </section>
  );
}

function About() {
  const { health } = useApp();
  return (
    <section className="st-card">
      <Row title="Page renderer" hint="Used for previews and the render check."><span>{health.renderer ? "LibreOffice available" : "LibreOffice missing"}</span></Row>
      <Row title="Server API key"><span>{health.server_key ? "Configured" : "Not set"}</span></Row>
      <Row title="Sign-in"><span>{health.auth ? "Required" : "Off"}</span></Row>
      <Row title="Version"><span>Pitchcraft 0.3.0</span></Row>
    </section>
  );
}

const SECTIONS: { id: Section; label: string; icon: string; desc: string; admin?: boolean }[] = [
  { id: "profile", label: "Profile", icon: "user", desc: "Your name and username" },
  { id: "appearance", label: "Appearance", icon: "sun", desc: "Light or dark theme" },
  { id: "security", label: "Security", icon: "lock", desc: "Password" },
  { id: "ai", label: "Claude & AI", icon: "sparkle", desc: "API key, model and defaults" },
  { id: "team", label: "Team", icon: "users", desc: "Who can sign in", admin: true },
  { id: "about", label: "About", icon: "info", desc: "Server status" },
];

export default function SettingsPage() {
  const { user } = useApp();
  const [section, setSection] = useState<Section>("profile");
  const items = SECTIONS.filter((s) => !s.admin || user?.admin);
  const current = items.find((s) => s.id === section) || items[0];
  return (
    <div className="soft-page">
      <div className="soft-col" style={{ width: "min(1040px, 100%)" }}>
        <div className="soft-head"><div><h1>Settings</h1><p className="muted">Manage your profile, security and how Claude works for you.</p></div></div>
        <div className="st-layout">
          <nav className="st-nav" aria-label="Settings sections">
            {items.map((s) => (
              <button key={s.id} className={`st-nav-i ${current.id === s.id ? "on" : ""}`} onClick={() => setSection(s.id)}>
                <Icon name={s.icon} size={20} /><span><b>{s.label}</b><span>{s.desc}</span></span>
              </button>
            ))}
          </nav>
          <div className="st-main">
            <h2 className="st-title">{current.label}</h2>
            {current.id === "profile" ? <Profile /> : current.id === "appearance" ? <Appearance /> : current.id === "security" ? <Security /> : current.id === "ai" ? <AI /> : current.id === "team" ? <Team /> : <About />}
          </div>
        </div>
      </div>
    </div>
  );
}
