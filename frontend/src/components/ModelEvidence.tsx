import { useEffect, useState } from "react";
import { AlertTriangle, ShieldCheck, FileSearch, Activity, Database } from "lucide-react";
import { supabase } from "../lib/supabase";

const API = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://economic-pulse-api.onrender.com");

type Metrics = { n?: number; mae?: number | null; rmse?: number | null; mape_pct?: number | null; smape_pct?: number | null };
type Evidence = {
  data_classification?: string;
  source?: { name?: string; url?: string; rights_tag?: string; sha256?: string; authentication?: string };
  series?: { id?: string; unit?: string; forecast_scope?: string };
  sample?: {
    training_rows?: number; training_cutoff?: string;
    validation_origins?: { start?: string | null; end?: string | null; observations?: number };
    validation_target_periods?: { start?: string | null; end?: string | null; observations?: number };
    reserved_holdout?: { window?: { start?: string | null; end?: string | null }; periods?: string[]; evaluated?: boolean; n?: number };
  };
  metrics?: {
    chronological_baselines?: Record<string, Metrics>;
    challenger_comparison?: { xgboost?: Metrics; baselines?: Record<string, Metrics>; best_baseline?: string; promote_xgboost?: boolean };
    reserved_holdout?: { xgboost?: Metrics; baselines?: Record<string, Metrics> };
  };
  interval_diagnostics?: { nominal_level?: number; empirical_coverage?: number; calibration_adequate?: boolean };
  limitations?: string[];
  publication?: { status?: string; accuracy_claim?: number | null; decision_grade?: boolean; reason?: string };
};
type Version = { id: string; series_id: string; version: string; status: string; is_published: boolean; created_at: string };
type EvidenceRow = { version: Version; evidence?: Evidence; error?: string };

function metric(value?: number | null, digits = 2) {
  return value == null || !Number.isFinite(value) ? "Not available" : value.toFixed(digits);
}
function dateLabel(value?: string | null) {
  return value ? value.slice(0, 10) : "Not recorded";
}

export default function ModelEvidence() {
  const [rows, setRows] = useState<EvidenceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load(token: string) {
      setLoading(true); setError(""); setSignedIn(true);
      try {
        const response = await fetch(API + "/v1/model-versions", { headers: { Authorization: "Bearer " + token } });
        if (!response.ok) throw new Error(response.status === 401 ? "Sign in to inspect account-scoped model evidence." : "Could not load model versions.");
        const versions = await response.json() as Version[];
        const evidenceRows = await Promise.all(versions.map(async version => {
          try {
            const reportResponse = await fetch(API + "/v1/model-versions/" + version.id + "/evaluation", {
              headers: { Authorization: "Bearer " + token },
            });
            if (!reportResponse.ok) throw new Error("Evaluation report unavailable.");
            const report = await reportResponse.json() as { report?: { evidence?: Evidence } };
            return { version, evidence: report.report?.evidence };
          } catch (cause) {
            return { version, error: cause instanceof Error ? cause.message : "Evidence unavailable." };
          }
        }));
        if (alive) setRows(evidenceRows);
      } catch (cause) {
        if (alive) setError(cause instanceof Error ? cause.message : "Evidence request failed.");
      } finally { if (alive) setLoading(false); }
    }
    if (!supabase) { setSignedIn(false); setLoading(false); return () => { alive = false; }; }
    void supabase.auth.getSession().then(({ data }) => {
      if (!alive) return;
      if (data.session?.access_token) void load(data.session.access_token);
      else { setSignedIn(false); setRows([]); setLoading(false); }
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token) void load(session.access_token);
      else { setSignedIn(false); setRows([]); setLoading(false); }
    });
    return () => { alive = false; listener.subscription.unsubscribe(); };
  }, []);

  return <div className="model-evidence">
    <section className="panel">
      <div className="panel-head"><div><h2><FileSearch size={18} style={{ verticalAlign: "middle", marginRight: 8 }}/> Model evidence registry</h2><p>Version-specific provenance, evaluation windows, baseline comparisons and limitations</p></div><span className="job-status">Experimental</span></div>
      <div className="notice training-notice"><ShieldCheck size={17}/><span><strong>No universal accuracy claim.</strong> Metrics are reported only when computed from a model's actual evaluation records. Missing evidence stays missing; it is never replaced with a fabricated score.</span></div>
      {!signedIn && <p className="muted-note">Sign in to view model evidence belonging to your account. The public demo uses synthetic data and has no validated accuracy claim.</p>}
      {loading && <p className="muted-note">Loading model versions and evaluation reports…</p>}
      {error && <p className="job-error">{error}</p>}
      {!loading && signedIn && rows.length === 0 && !error && <p className="muted-note">No model versions have been published to this account yet. Upload an eligible dataset in Model training to create the first evidence report.</p>}
    </section>
    {rows.map(({ version, evidence, error: rowError }) => <section className="panel" key={version.id}>
      <div className="panel-head"><div><h2>{version.version}</h2><p>{version.series_id} · Created {new Date(version.created_at).toLocaleString()}</p></div><span className={version.is_published ? "job-status success" : "job-status"}>{evidence?.publication?.status || version.status}</span></div>
      {rowError && <p className="job-error">{rowError}</p>}
      {evidence && <>
        <div className="notice training-notice"><AlertTriangle size={17}/><span><strong>Experimental publication · Not decision-grade.</strong> {evidence.publication?.reason || "Review the evidence before using this forecast."}</span></div>
        <div className="evidence-grid">
          <div className="metric-card"><div className="metric-top">Data classification <Database size={15}/></div><div className="metric-value">{evidence.data_classification === "synthetic" ? "Synthetic" : "Real-source claim"}</div><div className="metric-detail">{evidence.sample?.training_rows ?? "—"} training rows</div></div>
          <div className="metric-card"><div className="metric-top">Validation origins <Activity size={15}/></div><div className="metric-value">{evidence.sample?.validation_origins?.observations ?? "—"}</div><div className="metric-detail">{dateLabel(evidence.sample?.validation_origins?.start)} to {dateLabel(evidence.sample?.validation_origins?.end)}</div></div>
          <div className="metric-card"><div className="metric-top">Reserved holdout <ShieldCheck size={15}/></div><div className="metric-value">{evidence.sample?.reserved_holdout?.evaluated ? "Evaluated" : "Not evaluated"}</div><div className="metric-detail">{evidence.sample?.reserved_holdout?.n ?? 0} holdout predictions</div></div>
        </div>
        <h3>Source and data provenance</h3>
        <p><strong>{evidence.source?.name || "Source not recorded"}</strong> · {evidence.source?.rights_tag || "Rights tag missing"}</p>
        {evidence.source?.url && <p><a href={evidence.source.url} target="_blank" rel="noreferrer">{evidence.source.url}</a></p>}
        <p className="muted-note">{evidence.source?.authentication || "Source authenticity not independently verified."}</p>
        <p className="muted-note">Dataset SHA-256: {evidence.source?.sha256 || "Not recorded"} · Training cutoff: {dateLabel(evidence.sample?.training_cutoff)}</p>
        <h3>Chronological baseline metrics</h3>
        <MetricTable metrics={evidence.metrics?.chronological_baselines || {}} />
        <h3>Challenger comparison</h3>
        <p className="muted-note">Best baseline: {evidence.metrics?.challenger_comparison?.best_baseline || "Not determined"} · XGBoost promotion: {evidence.metrics?.challenger_comparison?.promote_xgboost ? "Passed validation comparison" : "Not promoted"}</p>
        <MetricTable metrics={{ xgboost: evidence.metrics?.challenger_comparison?.xgboost, ...(evidence.metrics?.challenger_comparison?.baselines || {}) }} />
        <h3>Reserved final holdout</h3>
        <p className="muted-note">{evidence.sample?.reserved_holdout?.window?.start || "No holdout window"} to {evidence.sample?.reserved_holdout?.window?.end || "not recorded"} · {evidence.sample?.reserved_holdout?.evaluated ? "Evaluated after model selection" : "No evaluated holdout metrics"}</p>
        <MetricTable metrics={{ xgboost: evidence.metrics?.reserved_holdout?.xgboost, ...(evidence.metrics?.reserved_holdout?.baselines || {}) }} />
        <h3>Prediction interval diagnostics</h3>\n        <p className="muted-note">Nominal level: {evidence.interval_diagnostics?.nominal_level == null ? "Not available" : (evidence.interval_diagnostics.nominal_level * 100) + "%"} · Empirical coverage: {evidence.interval_diagnostics?.empirical_coverage == null ? "Not available" : (evidence.interval_diagnostics.empirical_coverage * 100).toFixed(1) + "%"} · Calibration: {evidence.interval_diagnostics?.calibration_adequate ? "Adequate by configured threshold" : "Not adequate / not established"}</p>\n        <h3>Limitations</h3>
        <ul>{(evidence.limitations || []).map((item, index) => <li key={index}>{item}</li>)}</ul>
        <p className="muted-note"><strong>Scope:</strong> {evidence.series?.forecast_scope || "UPI activity is not a GDP forecast."}</p>
      </>}
    </section>)}
  </div>;
}

function MetricTable({ metrics }: { metrics: Record<string, Metrics | undefined> }) {
  const entries = Object.entries(metrics).filter((entry): entry is [string, Metrics] => !!entry[1]);
  if (!entries.length) return <p className="muted-note">No comparable metrics are available for this window.</p>;
  return <div className="table-wrap"><table><thead><tr><th>MODEL</th><th>N</th><th>MAE</th><th>RMSE</th><th>MAPE</th><th>sMAPE</th></tr></thead><tbody>
    {entries.map(([name, values]) => <tr key={name}><td>{name}</td><td>{values.n ?? "—"}</td><td>{metric(values.mae)}</td><td>{metric(values.rmse)}</td><td>{metric(values.mape_pct) === "Not available" ? "—" : metric(values.mape_pct) + "%"}</td><td>{metric(values.smape_pct) === "Not available" ? "—" : metric(values.smape_pct) + "%"}</td></tr>)}
  </tbody></table></div>;
}
