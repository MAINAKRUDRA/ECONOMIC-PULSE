import { useEffect, useState, type FormEvent } from "react";
import { BrainCircuit, UploadCloud, FileSpreadsheet, CheckCircle2, AlertCircle, Loader2, History } from "lucide-react";
import { supabase, isSupabaseConfigured } from "../lib/supabase";

const API = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://economic-pulse-api.onrender.com");
const MAX_FILE_BYTES = 20 * 1024 * 1024;

type Job = {
  job_id: string; status: string; error?: string;
  result?: {
    version?: string;
    forecast?: { median: number; horizon_end: string; model_version: string; candidate_status: string };
    backtest_status?: string; challenger_status?: string;
  };
};
type ModelVersion = {
  id: string; series_id: string; version: string; status: string;
  is_published: boolean; created_at: string; published_at: string | null;
  metrics: Record<string, unknown>;
};

export default function TrainingPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [seriesId, setSeriesId] = useState("upi_monthly");
  const [sourceName, setSourceName] = useState("Reserve Bank of India");
  const [sourceUrl, setSourceUrl] = useState("https://rbi.org.in/scripts/EntityWiseRetailStatistics.aspx");
  const [rightsTag, setRightsTag] = useState("official-public-data");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [userId, setUserId] = useState("");
  const [versions, setVersions] = useState<ModelVersion[]>([]);

  async function loadVersions(token: string) {
    try {
      const response = await fetch(API + "/v1/model-versions", { headers: { Authorization: "Bearer " + token } });
      if (response.ok) setVersions(await response.json() as ModelVersion[]);
    } catch { /* Keep history empty while the API is unavailable. */ }
  }

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      const session = data.session;
      setAccessToken(session?.access_token ?? "");
      setUserId(session?.user.id ?? "");
      if (session?.access_token) void loadVersions(session.access_token);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setAccessToken(session?.access_token ?? "");
      setUserId(session?.user.id ?? "");
      if (session?.access_token) void loadVersions(session.access_token);
      else setVersions([]);
    });
    return () => { active = false; listener.subscription.unsubscribe(); };
  }, []);

  useEffect(() => {
    if (!job?.job_id || !["queued", "running"].includes(job.status) || !accessToken) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(API + "/v1/training-jobs/" + job.job_id, {
          headers: { Authorization: "Bearer " + accessToken },
        });
        if (!response.ok) throw new Error(response.status === 404 ? "Training job not found." : "Could not read training status.");
        const next = await response.json() as { id: string; status: string; error?: string; result?: Job["result"] };
        setJob({ ...next, job_id: next.id });
        if (next.status === "completed") {
          setMessage("Training completed. The validated model version and forecast are saved.");
          void loadVersions(accessToken);
        } else if (next.status === "failed") setMessage(next.error || "Training failed. Review the job error.");
      } catch (error) { setMessage(error instanceof Error ? error.message : "Status request failed."); }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, accessToken]);

  async function startTraining(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase || !accessToken || !userId) { setMessage("Sign in to your Supabase account before uploading a dataset."); return; }
    if (!file) { setMessage("Choose an official-source CSV dataset first."); return; }
    if (!file.name.toLowerCase().endsWith(".csv") || file.size === 0 || file.size > MAX_FILE_BYTES) {
      setMessage("Choose a non-empty CSV file no larger than 20 MB."); return;
    }
    if (!seriesId.trim() || seriesId.startsWith("demo_") || !sourceName.trim() || !rightsTag.trim()) {
      setMessage("Use a real series ID and provide source and rights provenance."); return;
    }
    const officialDomains = ["rbi.org.in", "npci.org.in", "mospi.gov.in", "data.gov.in", "imf.org", "worldbank.org", "oecd.org", "fred.stlouisfed.org"];
    let sourceHost = "";
    try { sourceHost = new URL(sourceUrl).hostname.toLowerCase(); } catch { /* Invalid URL is rejected below. */ }
    if (!sourceUrl.startsWith("https://") || !officialDomains.some(domain => sourceHost === domain || sourceHost.endsWith("." + domain))) {
      setMessage("Use an HTTPS URL from an approved official statistics domain."); return;
    }
    setBusy(true); setMessage(""); setJob(null);
    let storagePath = "";
    try {
      const safeName = file.name.normalize("NFKD").replace(/[^a-zA-Z0-9._-]/g, "_").slice(-100);
      storagePath = userId + "/" + crypto.randomUUID() + "-" + safeName;
      const { error: uploadError } = await supabase.storage.from("economic-datasets").upload(storagePath, file, {
        contentType: "text/csv", upsert: false,
      });
      if (uploadError) throw uploadError;

      const { data: dataset, error: rowError } = await supabase.from("datasets").insert({
        user_id: userId, series_id: seriesId.trim(), source_name: sourceName.trim(),
        source_url: sourceUrl.trim(), rights_tag: rightsTag.trim(), file_name: file.name, storage_path: storagePath,
        content_type: "text/csv", size_bytes: file.size, status: "uploaded",
      }).select("id").single();
      if (rowError) {
        await supabase.storage.from("economic-datasets").remove([storagePath]);
        throw rowError;
      }

      const response = await fetch(API + "/v1/training-jobs", {
        method: "POST",
        headers: { Authorization: "Bearer " + accessToken, "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.id }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not enqueue training.");
      setJob({ job_id: result.job_id, status: result.status });
      setMessage("Dataset stored privately. A persistent worker has been queued to train it.");
      setFile(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Dataset upload or training enqueue failed.");
    } finally { setBusy(false); }
  }

  const running = job && ["queued", "running"].includes(job.status);
  return <section className="panel training-panel">
    <div className="panel-head"><div><h2>Train an economic forecasting model</h2><p>Private dataset storage, persistent training queue and versioned model publication</p></div><span className="training-icon"><BrainCircuit size={19} /></span></div>
    {(!isSupabaseConfigured || !accessToken) && <div className="notice training-notice"><AlertCircle size={16}/><span>Sign in and configure Supabase to upload datasets. Training uses your account identity; no shared admin token is used.</span></div>}
    <div className="notice training-notice"><AlertCircle size={16}/><span>Only upload official public datasets for this project. Provide the exact source and usage-rights tag. Uploaded data and model artifacts are private to your account.</span></div>
    <form className="training-form" onSubmit={startTraining}>
      <label>Official dataset CSV <span>Required · maximum 20 MB</span>
        <div className="dataset-picker"><FileSpreadsheet size={19}/><strong>{file ? file.name : "Choose your CSV file"}</strong><small>{file ? (file.size / 1024).toFixed(1) + " KB" : "Monthly observations with vintage columns"}</small><input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] ?? null)} /></div>
      </label>
      <div className="training-fields">
        <label>Series ID<input required value={seriesId} onChange={e => setSeriesId(e.target.value)} placeholder="upi_monthly" /></label>
        <label>Official source<input required value={sourceName} onChange={e => setSourceName(e.target.value)} placeholder="Reserve Bank of India" /></label>
        <label>Official source URL<input required type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} placeholder="https://rbi.org.in/…" /></label>
        <label>Data rights tag<input required value={rightsTag} onChange={e => setRightsTag(e.target.value)} placeholder="official-public-data" /></label>
      </div>
      <div className="training-actions"><button className="account-button" type="submit" disabled={busy || !!running || !accessToken}>{busy ? <Loader2 size={14} className="spin"/> : <UploadCloud size={14}/>} {busy ? "Uploading…" : "Upload and train"}</button><span>Stored in private Supabase Storage; job state is saved in PostgreSQL.</span></div>
    </form>
    {message && <p className="training-message" role="status">{message}</p>}
    {job && <div className="training-job">
      <div className="job-heading"><strong>Training job</strong><span className={job.status === "completed" ? "job-status success" : job.status === "failed" ? "job-status failed" : "job-status"}>{running && <Loader2 size={12} className="spin"/>}{job.status}</span></div>
      <small>Job ID: {job.job_id}</small>
      {job.error && <p className="job-error">{job.error}</p>}
      {job.result?.forecast && <div className="job-result"><CheckCircle2 size={17}/><div><strong>Model version published: {job.result.version}</strong><p>Forecast for {job.result.forecast.horizon_end}: {job.result.forecast.median.toLocaleString()} · Selected model: {job.result.forecast.model_version}</p><small>Backtest: {job.result.backtest_status} · Challenger: {job.result.challenger_status}</small></div></div>}
    </div>}
    <div className="training-schema"><strong>Expected CSV columns</strong><code>series_id, period, available_at, revision, volume_count</code><p>Use actual first-publication timestamps and revision numbers. Never infer missing vintage dates.</p></div>
    <div className="training-job">
      <div className="job-heading"><strong><History size={15}/> Model version history</strong><span>{versions.length} versions</span></div>
      {versions.length ? versions.map(version => <div className="evidence-row" key={version.id}><div className="evidence-file-info"><strong>{version.version}</strong><small>{version.series_id} · {new Date(version.created_at).toLocaleString()}</small></div><span className={version.is_published ? "job-status success" : "job-status"}>{version.status}</span></div>) : <p className="muted-note">No model versions published for this account yet.</p>}
    </div>
  </section>;
}
