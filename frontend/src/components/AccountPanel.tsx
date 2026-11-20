import { useCallback, useEffect, useState, type FormEvent, type ChangeEvent } from "react";
import type { Session } from "@supabase/supabase-js";
import { Bookmark, Building2, Download, FileText, LogIn, LogOut, Trash2, Upload, UserRound, X } from "lucide-react";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

type SavedSeries = { id: string; series_id: string; label: string; created_at: string };
type Profile = {
  id: string;
  full_name: string;
  phone: string;
  account_type: "personal" | "business";
  job_title: string;
  business_name: string;
  business_website: string;
  business_industry: string;
  business_registration_no: string;
  business_address: string;
};
type EvidenceFile = {
  id: string;
  file_name: string;
  storage_path: string;
  mime_type: string | null;
  size_bytes: number;
  created_at: string;
  category: string;
};

const emptyProfile = (id = ""): Profile => ({
  id, full_name: "", phone: "", account_type: "personal", job_title: "",
  business_name: "", business_website: "", business_industry: "",
  business_registration_no: "", business_address: "",
});
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const ALLOWED_TYPES = new Set([
  "application/pdf", "image/jpeg", "image/png", "image/webp",
  "text/csv", "text/plain", "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]);

function formatBytes(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export default function AccountPanel() {
  const [session, setSession] = useState<Session | null>(null);
  const [saved, setSaved] = useState<SavedSeries[]>([]);
  const [profile, setProfile] = useState<Profile>(emptyProfile());
  const [evidence, setEvidence] = useState<EvidenceFile[]>([]);
  const [evidenceCategory, setEvidenceCategory] = useState("general");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [signupName, setSignupName] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  const loadSaved = useCallback(async (userId: string) => {
    if (!supabase) return;
    const { data, error } = await supabase.from("saved_series")
      .select("id, series_id, label, created_at").eq("user_id", userId)
      .order("created_at", { ascending: false });
    if (error) setMessage(error.message);
    else setSaved(data ?? []);
  }, []);

  const loadProfile = useCallback(async (userId: string) => {
    if (!supabase) return;
    const { data, error } = await supabase.from("profiles")
      .select("id, full_name, phone, account_type, job_title, business_name, business_website, business_industry, business_registration_no, business_address")
      .eq("id", userId).maybeSingle();
    if (error) {
      setMessage(error.message);
      return;
    }
    setProfile({ ...emptyProfile(userId), ...(data ?? {}) });
  }, []);

  const loadEvidence = useCallback(async (userId: string) => {
    if (!supabase) return;
    const { data, error } = await supabase.from("evidence_files")
      .select("id, file_name, storage_path, mime_type, size_bytes, created_at, category")
      .eq("user_id", userId).order("created_at", { ascending: false });
    if (error) setMessage(error.message);
    else setEvidence(data ?? []);
  }, []);

  const loadWorkspace = useCallback(async (userId: string) => {
    await Promise.all([loadProfile(userId), loadSaved(userId), loadEvidence(userId)]);
  }, [loadProfile, loadSaved, loadEvidence]);

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    void supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error) setMessage(error.message);
      setSession(data.session);
      if (data.session) void loadWorkspace(data.session.user.id);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (nextSession) {
        window.setTimeout(() => void loadWorkspace(nextSession.user.id), 0);
      } else {
        setSaved([]);
        setEvidence([]);
        setProfile(emptyProfile());
      }
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [loadWorkspace]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setMessage("");
    const result = mode === "signup"
      ? await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { data: { full_name: signupName.trim() } },
        })
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
      setExpanded(false);
    }
  }

  async function signOut() {
    if (!supabase) return;
    setBusy(true);
    const { error } = await supabase.auth.signOut();
    setBusy(false);
    setMessage(error ? error.message : "Signed out.");
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase || !session) return;
    setBusy(true);
    setMessage("");
    const payload = { ...profile, id: session.user.id, updated_at: new Date().toISOString() };
    const { error } = await supabase.from("profiles").upsert(payload, { onConflict: "id" });
    setBusy(false);
    setMessage(error ? error.message : "Profile saved.");
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

  async function uploadEvidence(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !supabase || !session) return;
    if (file.size > MAX_FILE_BYTES) {
      setMessage("File exceeds the 20 MB limit.");
      return;
    }
    if (!ALLOWED_TYPES.has(file.type)) {
      setMessage("Unsupported file type. Upload PDF, DOC/DOCX, XLS/XLSX, CSV, TXT, JPG, PNG or WEBP.");
      return;
    }
    setUploading(true);
    setMessage("");
    const safeName = file.name.normalize("NFKD").replace(/[^a-zA-Z0-9._-]/g, "_").slice(-100);
    const storagePath = session.user.id + "/" + crypto.randomUUID() + "-" + safeName;
    const { error: uploadError } = await supabase.storage.from("evidence-vault")
      .upload(storagePath, file, { contentType: file.type, upsert: false });
    if (uploadError) {
      setUploading(false);
      setMessage(uploadError.message);
      return;
    }
    const { error: rowError } = await supabase.from("evidence_files").insert({
      user_id: session.user.id,
      file_name: file.name,
      storage_path: storagePath,
      mime_type: file.type || null,
      size_bytes: file.size,
      category: evidenceCategory,
    });
    if (rowError) {
      await supabase.storage.from("evidence-vault").remove([storagePath]);
      setMessage(rowError.message);
    } else {
      setMessage("Evidence uploaded securely.");
      await loadEvidence(session.user.id);
    }
    setUploading(false);
  }

  async function downloadEvidence(item: EvidenceFile) {
    if (!supabase) return;
    const { data, error } = await supabase.storage.from("evidence-vault")
      .createSignedUrl(item.storage_path, 60);
    if (error) setMessage(error.message);
    else window.open(data.signedUrl, "_blank", "noopener,noreferrer");
  }

  async function deleteEvidence(item: EvidenceFile) {
    if (!supabase) return;
    setBusy(true);
    const { error: storageError } = await supabase.storage.from("evidence-vault").remove([item.storage_path]);
    if (storageError) {
      setBusy(false);
      setMessage(storageError.message);
      return;
    }
    const { error: rowError } = await supabase.from("evidence_files").delete().eq("id", item.id);
    setBusy(false);
    if (rowError) setMessage(rowError.message);
    else {
      setEvidence((items) => items.filter((entry) => entry.id !== item.id));
      setMessage("Evidence deleted.");
    }
  }

  const update = (key: keyof Profile, value: string) => setProfile((current) => ({ ...current, [key]: value }) as Profile);

  return (
    <section className="account-panel">
      <div className="account-summary">
        <div className="account-heading">
          <span className="account-icon"><UserRound size={16} /></span>
          <div><strong>{session ? (profile.full_name || "Your workspace") : "Personal workspace"}</strong><small>{session ? session.user.email : "Sign in to manage your profile and saved data"}</small></div>
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
        {mode === "signup" && <label>Full name<input autoComplete="name" value={signupName} onChange={(event) => setSignupName(event.target.value)} required /></label>}
        <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>Password<input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        <button className="account-button" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}</button>
      </form>}

      {session && <>
        <form className="profile-form" onSubmit={(event) => void saveProfile(event)}>
          <div className="vault-section-heading"><UserRound size={15} /><strong>Personal details</strong></div>
          <div className="profile-grid">
            <label>Full name<input autoComplete="name" value={profile.full_name} onChange={(e) => update("full_name", e.target.value)} required /></label>
            <label>Phone number<input type="tel" autoComplete="tel" value={profile.phone} onChange={(e) => update("phone", e.target.value)} placeholder="+91…" /></label>
            <label>Account type<select value={profile.account_type} onChange={(e) => update("account_type", e.target.value)}><option value="personal">Personal</option><option value="business">Business</option></select></label>
            <label>Job title / role<input value={profile.job_title} onChange={(e) => update("job_title", e.target.value)} placeholder="e.g. Founder, Analyst" /></label>
          </div>
          {profile.account_type === "business" && <div className="business-fields">
            <div className="vault-section-heading"><Building2 size={15} /><strong>Business details</strong></div>
            <div className="profile-grid">
              <label>Business / legal name<input value={profile.business_name} onChange={(e) => update("business_name", e.target.value)} required /></label>
              <label>Business website<input type="url" value={profile.business_website} onChange={(e) => update("business_website", e.target.value)} placeholder="https://" /></label>
              <label>Industry<input value={profile.business_industry} onChange={(e) => update("business_industry", e.target.value)} placeholder="e.g. Financial services" /></label>
              <label>Registration number <span className="field-optional">(optional)</span><input value={profile.business_registration_no} onChange={(e) => update("business_registration_no", e.target.value)} /></label>
              <label className="field-wide">Business address<textarea rows={2} value={profile.business_address} onChange={(e) => update("business_address", e.target.value)} /></label>
            </div>
          </div>}
          <button className="account-button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
        </form>

        <div className="evidence-vault">
          <div className="vault-header">
            <div><div className="vault-section-heading"><FileText size={15} /><strong>Evidence Vault</strong><span className="vault-count">{evidence.length}</span></div><p>Private documents linked to your account. Only you can access these files.</p></div>
            <div className="vault-upload-controls"><select aria-label="Evidence category" value={evidenceCategory} onChange={(event) => setEvidenceCategory(event.target.value)} disabled={uploading}><option value="general">General</option><option value="financial">Financial</option><option value="legal">Legal</option><option value="compliance">Compliance</option><option value="operational">Operational</option><option value="research">Research</option></select><label className="account-button upload-button"><Upload size={14} /> {uploading ? "Uploading…" : "Upload evidence"}<input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.jpg,.jpeg,.png,.webp" onChange={(event) => void uploadEvidence(event)} disabled={uploading} /></label></div>
          </div>
          <p className="vault-hint">PDF, Office documents, CSV, TXT and images · Maximum 20 MB per file</p>
          {evidence.length ? <div className="evidence-list">{evidence.map((item) => <div className="evidence-row" key={item.id}><span className="evidence-file-icon"><FileText size={15} /></span><div className="evidence-file-info"><strong>{item.file_name}</strong><small>{item.category} · {formatBytes(item.size_bytes)} · {new Date(item.created_at).toLocaleDateString()}</small></div><div className="evidence-actions"><button title="Download securely" aria-label={`Download ${item.file_name}`} onClick={() => void downloadEvidence(item)}><Download size={14} /></button><button title="Delete file" aria-label={`Delete ${item.file_name}`} onClick={() => void deleteEvidence(item)} disabled={busy}><Trash2 size={14} /></button></div></div>)}</div> : <div className="vault-empty">No evidence uploaded yet. Add documents, reports or supporting files to your private vault.</div>}
        </div>

        <div className="saved-series">
          <div className="saved-heading">Saved series <span>{saved.length}</span></div>
          {saved.length ? saved.map((item) => <div className="saved-row" key={item.id}><span>{item.label}</span><button aria-label={`Remove ${item.label}`} onClick={() => void removeSeries(item.id)}><X size={13} /></button></div>) : <p>No saved series yet. Save the demo series to add it to this account.</p>}
        </div>
      </>}
      {!isSupabaseConfigured && <p className="account-message">Supabase is not configured yet. Add the frontend environment variables in your hosting dashboard to enable accounts.</p>}
      {message && <p className="account-message" role="status">{message}</p>}
    </section>
  );
}
