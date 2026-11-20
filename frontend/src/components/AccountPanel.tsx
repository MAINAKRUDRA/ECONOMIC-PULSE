import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { Session } from "@supabase/supabase-js";
import { Bookmark, LogIn, LogOut, UserRound, X } from "lucide-react";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

type SavedSeries = {
  id: string;
  series_id: string;
  label: string;
  created_at: string;
};

export default function AccountPanel() {
  const [session, setSession] = useState<Session | null>(null);
  const [saved, setSaved] = useState<SavedSeries[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const loadSaved = useCallback(async (userId: string) => {
    if (!supabase) return;
    const { data, error } = await supabase
      .from("saved_series")
      .select("id, series_id, label, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false });
    if (error) {
      setMessage(error.message);
      return;
    }
    setSaved(data ?? []);
  }, []);

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    void supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error) setMessage(error.message);
      setSession(data.session);
      if (data.session) void loadSaved(data.session.user.id);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (nextSession) {
        // Defer Supabase queries until the auth callback has completed.
        window.setTimeout(() => void loadSaved(nextSession.user.id), 0);
      } else {
        setSaved([]);
      }
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [loadSaved]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setMessage("");
    const result = mode === "signup"
      ? await supabase.auth.signUp({ email: email.trim(), password })
      : await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (result.error) {
      setMessage(result.error.message);
      return;
    }
    if (mode === "signup" && !result.data.session) {
      setMessage("Account created. Check your email to confirm your address, then sign in.");
    } else {
      setMessage("You are signed in.");
      setPassword("");
    }
  }

  async function signOut() {
    if (!supabase) return;
    setBusy(true);
    const { error } = await supabase.auth.signOut();
    setBusy(false);
    setMessage(error ? error.message : "Signed out.");
  }

  async function saveDemoSeries() {
    if (!supabase || !session) return;
    setBusy(true);
    setMessage("");
    const { error } = await supabase.from("saved_series").upsert(
      { user_id: session.user.id, series_id: "demo_upi", label: "Illustrative UPI activity index" },
      { onConflict: "user_id,series_id" },
    );
    if (error) setMessage(error.message);
    else {
      setMessage("Series saved to your account.");
      await loadSaved(session.user.id);
    }
    setBusy(false);
  }

  async function removeSeries(id: string) {
    if (!supabase) return;
    const { error } = await supabase.from("saved_series").delete().eq("id", id);
    if (error) setMessage(error.message);
    else setSaved((items) => items.filter((item) => item.id !== id));
  }

  return (
    <section className="account-panel">
      <div className="account-summary">
        <div className="account-heading">
          <span className="account-icon"><UserRound size={16} /></span>
          <div><strong>{session ? "Your workspace" : "Personal workspace"}</strong><small>{session ? session.user.email : "Sign in to save your series and preferences"}</small></div>
        </div>
        <div className="account-actions">
          {session ? <>
            <button className="account-button" onClick={() => void saveDemoSeries()} disabled={busy}><Bookmark size={14} /> Save demo series</button>
            <button className="account-button secondary" onClick={() => void signOut()} disabled={busy}><LogOut size={14} /> Sign out</button>
          </> : <button className="account-button" onClick={() => setExpanded((value) => !value)}><LogIn size={14} /> {expanded ? "Close sign in" : "Sign in / Create account"}</button>}
        </div>
      </div>
      {expanded && !session && <form className="auth-form" onSubmit={(event) => void submitAuth(event)}>
        <div className="auth-mode"><button type="button" className={mode === "signin" ? "selected" : ""} onClick={() => setMode("signin")}>Sign in</button><button type="button" className={mode === "signup" ? "selected" : ""} onClick={() => setMode("signup")}>Create account</button></div>
        <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>Password<input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        <button className="account-button" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}</button>
      </form>}
      {session && <div className="saved-series">
        <div className="saved-heading">Saved series <span>{saved.length}</span></div>
        {saved.length ? saved.map((item) => <div className="saved-row" key={item.id}><span>{item.label}</span><button aria-label={`Remove ${item.label}`} onClick={() => void removeSeries(item.id)}><X size={13} /></button></div>) : <p>No saved series yet. Save the demo series to add it to this account.</p>}
      </div>}
      {!isSupabaseConfigured && <p className="account-message">Supabase is not configured yet. Add the frontend environment variables in your hosting dashboard to enable accounts.</p>}
      {message && <p className="account-message" role="status">{message}</p>}
    </section>
  );
}
