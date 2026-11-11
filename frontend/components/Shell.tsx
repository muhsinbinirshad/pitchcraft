"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, ReactNode, Suspense, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import { Onboarding } from "./Onboarding";
import { SearchModal } from "./SearchModal";
import { ago } from "./ui";
import { api, displayName } from "@/lib/api";
import { useSettings } from "@/lib/settings";
import { useTheme } from "@/lib/theme";
import type { Health, ProposalSummary, User } from "@/lib/types";

interface AppCtx {
  setUser: (u: User) => void;
  toast: (msg: string) => void;
  health: Health;
  user: User | null;
  keyReady: boolean;
  openImage: (src: string) => void;
  refreshRecent: () => void;
}

const DEFAULT_HEALTH: Health = { ok: false, renderer: true, server_key: false, models: { "claude-opus-5-5": "Claude Opus 5.5" }, auth: true };
const Ctx = createContext<AppCtx>({ setUser: () => {}, toast: () => {}, health: DEFAULT_HEALTH, user: null, keyReady: false, openImage: () => {}, refreshRecent: () => {} });
export const useApp = () => useContext(Ctx);

const NAV = [
  { href: "/proposals/", label: "Proposals", icon: "folder" },
  { href: "/templates/", label: "Templates", icon: "layers" },
  { href: "/settings/", label: "Settings", icon: "sliders" },
];

function Sidebar({ open, recent, user, onSearch }: { open: boolean; recent: ProposalSummary[]; user: User | null; onSearch: () => void }) {
  const path = usePathname() || "/";
  const params = useSearchParams();
  const current = path.startsWith("/p") ? params.get("id") : null;
  const active = (href: string) => path.startsWith(href);
  const router = useRouter();
  return (
    <aside className={`side ${open ? "open" : ""}`} aria-label="Main navigation">
      <Link href="/proposals/" className="brand">
        <span className="brand-mark"><Icon name="logo" size={22} /></span>
        <span className="brand-name">Pitch<b>craft</b></span>
      </Link>
      <Link href="/new/" className="new-btn"><Icon name="sparkle" size={22} />New proposal</Link>
      <button type="button" className="side-search" onClick={onSearch} aria-label="Search proposals (Ctrl+K)">
        <Icon name="search" size={18} /><span className="grow">Search proposals</span><kbd>Ctrl K</kbd>
      </button>
      {NAV.map((n) => (
        <Link key={n.href} href={n.href} className={`nav-item ${active(n.href) ? "on" : ""}`}>
          <Icon name={n.icon} size={20} />{n.label}
        </Link>
      ))}
      {recent.length ? <div className="side-label">Recent proposals</div> : null}
      <div className="recent">
        {recent.slice(0, 10).map((p) => (
          <Link key={p.id} href={`/p/?id=${p.id}`} className={current === p.id ? "on" : ""} title={`${p.title}${p.client ? ` · ${p.client}` : ""}`}>
            <span className={`dot ${p.status}`} /><span className="ellipsis grow">{p.title}</span><span className="rc-ago">{ago(p.updated).replace(" ago", "")}</span>
          </Link>
        ))}
      </div>
      <div className="side-foot">
        {user ? <AccountCard user={user} /> : null}
      </div>
    </aside>
  );
}

const AV_COLORS = ["#1a73e8", "#188038", "#e37400", "#a142f4", "#d93025", "#007b83", "#c5221f", "#1967d2"];
function avatarColor(name: string) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AV_COLORS[h % AV_COLORS.length];
}

/** Google-style account card with a menu: profile, theme and sign out. */
function AccountCard({ user }: { user: User }) {
  const router = useRouter();
  const [pref, setPref] = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const name = displayName(user);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", h);
    window.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); window.removeEventListener("keydown", k); };
  }, [open]);
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]!.toUpperCase()).join("") || "?";
  const av = (size: number) => (
    <span className="acc-av" style={{ width: size, height: size, background: avatarColor(user.username), fontSize: size * 0.4 }}>{initials}</span>
  );
  return (
    <div className="acc" ref={ref}>
      {open ? (
        <div className="acc-menu" role="menu">
          <div className="acc-head">
            {av(56)}
            <div className="acc-hname">Hi, {name.split(" ")[0]}!</div>
            <div className="acc-hsub">@{user.username} · {user.admin ? "Admin" : "Member"}</div>
            <button className="acc-manage" onClick={() => { setOpen(false); router.push("/settings/"); }}>Manage your profile</button>
          </div>
          <div className="acc-sec">
            <div className="acc-label">Theme</div>
            <div className="acc-theme" role="radiogroup" aria-label="Theme">
              {([["light", "sun", "Light"], ["dark", "moon", "Dark"], ["system", "monitor", "System"]] as const).map(([id, ic, label]) => (
                <button key={id} role="radio" aria-checked={pref === id} className={pref === id ? "on" : ""} onClick={() => setPref(id)}>
                  <Icon name={ic} size={16} />{label}
                </button>
              ))}
            </div>
          </div>
          <div className="acc-sec acc-items">
            <button role="menuitem" onClick={() => { setOpen(false); router.push("/settings/"); }}><Icon name="sliders" size={18} />Settings</button>
            <button role="menuitem" onClick={async () => { await api.logout().catch(() => {}); router.push("/login/"); }}><Icon name="logout" size={18} />Sign out</button>
          </div>
        </div>
      ) : null}
      <button className={`acc-card ${open ? "open" : ""}`} onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} title="Account">
        {av(30)}
        <span className="acc-text">
          <span className="acc-name">{name}</span>
          <span className="acc-sub">@{user.username}</span>
        </span>
        <Icon name="chevronDown" size={18} className={open ? "" : "rot"} />
      </button>
    </div>
  );
}

function Frame({ children }: { children: ReactNode }) {
  const path = usePathname() || "/";
  const router = useRouter();
  const [settings] = useSettings();
  const [health, setHealth] = useState<Health>(DEFAULT_HEALTH);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [recent, setRecent] = useState<ProposalSummary[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [img, setImg] = useState<string | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [needsStyle, setNeedsStyle] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const isAuthPage = path.startsWith("/login");

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    api.me().then((m) => {
      if (!m.user && !isAuthPage) { router.replace(m.setup_needed ? "/login/?setup=1" : "/login/"); return; }
      if (m.user?.must_change && !isAuthPage) { router.replace("/login/?change=1"); return; }
      setUser(m.user);
      setReady(true);
    }).catch(() => setReady(true));
  }, [isAuthPage, router]);

  const refreshRecent = useCallback(() => { api.proposals().then(setRecent).catch(() => {}); }, []);
  useEffect(() => { if (ready && user && !user.must_change && !isAuthPage) refreshRecent(); }, [ready, user, path, refreshRecent, isAuthPage]);
  useEffect(() => { setNavOpen(false); }, [path]);
  // first run: no style template yet, so the tour blocks the app until one is added
  useEffect(() => { if (ready && user && !user.must_change && !isAuthPage) api.templates().then((t) => setNeedsStyle(t.length === 0)).catch(() => {}); }, [ready, user, path, isAuthPage]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") setImg(null);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const toast = useCallback((m: string) => {
    setMsg(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 4500);
  }, []);

  const value: AppCtx = { setUser, toast, health, user, keyReady: Boolean(settings.apiKey || health.server_key), openImage: setImg, refreshRecent };
  const overlays = (
    <>
      <div className={`snackbar ${msg ? "show" : ""}`} role="status" aria-live="polite">{msg}</div>
      {img ? (
        <div className="lightbox" onClick={() => setImg(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={img} alt="Page" />
          <button className="icon-btn lb-close" aria-label="Close"><Icon name="x" /></button>
        </div>
      ) : null}
    </>
  );

  if (isAuthPage) return <Ctx.Provider value={value}>{children}{overlays}</Ctx.Provider>;
  if (!ready || !user) return <div className="auth-wrap"><div className="progress" style={{ width: 200 }} /></div>;

  return (
    <Ctx.Provider value={value}>
      <div className="app">
        <Sidebar open={navOpen} recent={recent} user={user} onSearch={() => setSearchOpen(true)} />
        <div className="content">
          <div className="mobile-bar">
            <button className="icon-btn" aria-label="Menu" onClick={() => setNavOpen((v) => !v)}><Icon name="menu" /></button>
            <span className="brand-name grow">Pitch<b>craft</b></span>
            <button className="icon-btn" aria-label="Search" onClick={() => setSearchOpen(true)}><Icon name="search" /></button>
          </div>
          {health.ok && !health.renderer ? (
            <div className="sys-banner" role="status">
              <Icon name="warning" size={18} />
              <span>Previews are off: {(health.renderer_missing || ["LibreOffice"]).join(", ")} not installed on the server. Run <code>pitchcraft doctor</code> for the fix.</span>
            </div>
          ) : null}
          {children}
        </div>
      </div>
      {navOpen ? <div className="scrim" style={{ zIndex: 55, background: "rgba(0,0,0,.2)" }} onClick={() => setNavOpen(false)} /> : null}
      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
      {needsStyle ? <Onboarding name={displayName(user)} onDone={(go) => { setNeedsStyle(false); window.location.assign(go ? "/new/" : window.location.href); }} /> : null}
      {overlays}
    </Ctx.Provider>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}><Frame>{children}</Frame></Suspense>;
}
