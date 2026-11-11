"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [setup, setSetup] = useState(params.get("setup") === "1");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.me().then((m) => {
      if (m.user) router.replace("/");
      else setSetup(m.setup_needed);
    }).catch(() => {});
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (setup && password !== confirm) { setErr("The passwords don't match"); return; }
    setBusy(true);
    try {
      if (setup) await api.setup(username, password);
      else await api.login(username, password);
      window.location.href = "/";
    } catch (e2) {
      setErr((e2 as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <div className="row" style={{ gap: 12 }}>
          <span className="brand-mark"><Icon name="logo" size={22} /></span>
          <span className="brand-name">Pitch<b>craft</b></span>
        </div>
        <div>
          <h1 style={{ fontSize: 24, lineHeight: "32px" }}>{setup ? "Create the admin account" : "Sign in"}</h1>
          <div className="muted" style={{ marginTop: 4 }}>{setup ? "This is the first visit. The admin can add more users later in Settings." : "Use your Pitchcraft account."}</div>
        </div>
        <div className="field"><label htmlFor="u">Username</label>
          <input id="u" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus /></div>
        <div className="field"><label htmlFor="p">Password</label>
          <input id="p" className="input" type="password" autoComplete={setup ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={setup ? 8 : 1} />
          {setup ? <span className="hint">At least 8 characters.</span> : null}</div>
        {setup ? <div className="field"><label htmlFor="c">Confirm password</label>
          <input id="c" className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></div> : null}
        {err ? <div className="banner err"><Icon name="error" size={18} /><span>{err}</span></div> : null}
        <Button type="submit" busy={busy} icon={setup ? "user" : "lock"}>{setup ? "Create account" : "Sign in"}</Button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense fallback={null}><LoginInner /></Suspense>;
}
