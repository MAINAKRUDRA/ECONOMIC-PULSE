import { useEffect, useState, type FormEvent } from "react";
import { BrainCircuit, UploadCloud, FileSpreadsheet, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

const API = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://economic-pulse-api.onrender.com");

type Job = {
  job_id: string; status: string; series_id?: string; source_name?: string;
  created_at?: string; completed_at?: string; error?: string;
  forecast?: { median: number; horizon_end: string; model_version: string; candidate_status: string };
  backtest_status?: string; challenger_status?: string; validation?: { valid?: boolean };
};

export default function TrainingPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [seriesId, setSeriesId] = useState("upi_monthly");
  const [sourceName, setSourceName] = useState("");
  const [rightsTag, setRightsTag] = useState("approved-public-use");
  const [token, setToken] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!job?.job_id || !["queued", "training"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/v1/admin/train/${job.job_id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error(response.status === 404 ? "Job not found on this API instance. The service may have restarted." : "Could not read training status.");
        const next = await response.json() as Job;
        setJob(next);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Status request failed.");
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, token]);

  async function startTraining(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) { setMessage("Choose a CSV dataset first."); return; }
    setBusy(true); setMessage(""); setJob(null);
    const body = new FormData();
    body.append("file", file);
    body.append("series_id", seriesId.trim());
    body.append("source_name", sourceName.trim());
    body.append("rights_tag", rightsTag.trim());
    try {
      const response = await fetch(`${API}/v1/admin/train`, {
        method: "POST", headers: { Authorization: `Bearer ${token.trim()}` }, body,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Training request failed.");
      setJob(result as Job);
      setMessage("Dataset accepted. Training has been queued.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not connect to the training API.");
    } finally { setBusy(false); }
  }

  const running = job && ["queued", "training"].includes(job.status);
  return <section className="panel training-panel">
    <div className="panel-head"><div><h2>Train an economic forecasting model</h2><p>Upload your dataset and run the backend training pipeline</p></div><span className="training-icon"><BrainCircuit size={19} /></span></div>
    <div className="notice training-notice"><AlertCircle size={16} /><span>Training uses your uploaded data. A successful run publishes a research bundle to the API. It does not automatically make the model an official economic estimate.</span></div>
    <form className="training-form" onSubmit={startTraining}>
      <label>Dataset CSV <span>Required · maximum 20 MB</span>
        <div className="dataset-picker"><FileSpreadsheet size={19}/><strong>{file ? file.name : "Choose your CSV file"}</strong><small>{file ? `${(file.size / 1024).toFixed(1)} KB` : "Monthly observations with vintage columns"}</small><input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] ?? null)} /></div>
      </label>
      <div className="training-fields">
        <label>Series ID<input required value={seriesId} onChange={e => setSeriesId(e.target.value)} placeholder="upi_monthly" /></label>
        <label>Source name<input required value={sourceName} onChange={e => setSourceName(e.target.value)} placeholder="RBI Payment System Indicators" /></label>
        <label>Data rights tag<input required value={rightsTag} onChange={e => setRightsTag(e.target.value)} placeholder="approved-public-use" /></label>
        <label>Admin API token<input required type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} placeholder="Configured on the backend service" /></label>
      </div>
      <div className="training-actions"><button className="account-button" type="submit" disabled={busy || !!running || !token.trim()}>{busy ? <Loader2 size={14} className="spin"/> : <UploadCloud size={14}/>} {busy ? "Submitting…" : "Start model training"}</button><span>Token stays in this page's memory and is sent only to the API.</span></div>
    </form>
    {message && <p className="training-message" role="status">{message}</p>}
    {job && <div className="training-job">
      <div className="job-heading"><strong>Training job</strong><span className={job.status === "completed" ? "job-status success" : job.status === "failed" ? "job-status failed" : "job-status"}>{running && <Loader2 size={12} className="spin"/>}{job.status}</span></div>
      <small>Job ID: {job.job_id}</small>
      {job.error && <p className="job-error">{job.error}</p>}
      {job.forecast && <div className="job-result"><CheckCircle2 size={17}/><div><strong>Research bundle published</strong><p>Forecast for {job.forecast.horizon_end}: {job.forecast.median.toLocaleString()} · Selected model: {job.forecast.model_version} · Candidate: {job.forecast.candidate_status}</p><small>Backtest: {job.backtest_status} · Challenger: {job.challenger_status}</small></div></div>}
      {job.status === "completed" && <p className="muted-note">Refresh the Overview or Forecasts view to load the published model from the API.</p>}
    </div>}
    <div className="training-schema"><strong>Expected CSV columns</strong><code>series_id, period, available_at, revision, volume_count</code><p>Use actual release timestamps. If your file has different column names, share it and we can adapt the importer without inventing vintage dates.</p></div>
  </section>;
}
