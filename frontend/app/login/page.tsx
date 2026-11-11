"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";

type Mode = "signin" | "setup" | "change";

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<Mode>(params.get("change") === "1" ? "change" : params.get("setup") === "1" ? "setup" : "signin");
  const [defaultLogin, setDefaultLogin] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [current, setCurrent] = useState<string | null>(null); // known after signing in with the default password
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.me().then((m) => {
      setDefaultLogin(Boolean(m.default_login));
      if (m.user?.must_change) setMode("change");
      else if (m.user) router.replace("/");
      else setMode(m.setup_needed ? "setup" : "signin");
    }).catch(() => {});
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (mode !== "signin" && (mode === "change" ? next : password) !== confirm) { setErr("The passwords don't match"); return; }
    setBusy(true);
    try {
      if (mode === "setup") {
        await api.setup(username, password);
      } else if (mode === "change") {
        await api.changePassword(current ?? password, next);
      } else {
        const r = await api.login(username, password);
        if (r.user.must_change) {
          setCurrent(password); setMode("change"); setBusy(false);
          return;
        }
      }
      window.location.href = "/";
    } catch (e2) {
      setErr((e2 as Error).message);
      setBusy(false);
    }
  }

  const title = { signin: "Sign in", setup: "Create the admin account", change: "Choose a new password" }[mode];
  const sub = {
    signin: "Use your Pitchcraft account.",
    setup: "This is the first visit. The admin can add more users later in Settings.",
    change: "You signed in with the default password. Set your own to continue.",
  }[mode];

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <div className="row" style={{ gap: 12 }}>
          <span className="brand-mark"><Icon name="logo" size={22} /></span>
          <span className="brand-name">Pitch<b>craft</b></span>
        </div>
        <div>
          <h1 style={{ fontSize: 24, lineHeight: "32px" }}>{title}</h1>
          <div className="muted" style={{ marginTop: 4 }}>{sub}</div>
        </div>

        {mode === "signin" && defaultLogin ? (
          <div className="banner info"><Icon name="info" size={18} />
            <span>First time? Sign in with <b>admin</b> / <b>admin</b>. You&apos;ll choose a new password right after.</span>
          </div>
        ) : null}

        {mode !== "change" ? <>
          <div className="field"><label htmlFor="u">Username</label>
            <input id="u" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus /></div>
          <div className="field"><label htmlFor="p">Password</label>
            <input id="p" className="input" type="password" autoComplete={mode === "setup" ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === "setup" ? 8 : 1} />
            {mode === "setup" ? <span className="hint">At least 8 characters.</span> : null}</div>
        </> : <>
          {current === null ? <div className="field"><label htmlFor="cur">Current password</label>
            <input id="cur" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus /></div> : null}
          <div className="field"><label htmlFor="n">New password</label>
            <input id="n" className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required minLength={8} autoFocus={current !== null} />
            <span className="hint">At least 8 characters.</span></div>
        </>}

        {mode !== "signin" ? <div className="field"><label htmlFor="c">Confirm password</label>
          <input id="c" className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></div> : null}
        {err ? <div className="banner err"><Icon name="error" size={18} /><span>{err}</span></div> : null}
        <Button type="submit" busy={busy} icon={mode === "signin" ? "lock" : mode === "setup" ? "user" : "key"}>
          {mode === "signin" ? "Sign in" : mode === "setup" ? "Create account" : "Save and continue"}
        </Button>
        {mode === "change" ? <button type="button" className="btn text sm" onClick={async () => { await api.logout().catch(() => {}); window.location.href = "/login/"; }}>Sign out</button> : null}
      </form>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense fallback={null}><LoginInner /></Suspense>;
}
