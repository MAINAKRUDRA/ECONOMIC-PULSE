import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, CircleHelp, Database, Gauge, RefreshCw, ShieldCheck } from "lucide-react";

type Observation = { period: string; value: number; unit: string };
type Forecast = { median: number; lower: number; upper: number; baseline: number; horizon_end: string; unit: string };
type ApiEnvelope<T> = { data: T; meta: { mode: string; data_as_of: string; batch_id: string } };

const API = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const sample: Observation[] = [
  { period: "2026-01", value: 82.0, unit: "synthetic index" },
  { period: "2026-02", value: 84.5, unit: "synthetic index" },
  { period: "2026-03", value: 83.2, unit: "synthetic index" },
  { period: "2026-04", value: 87.1, unit: "synthetic index" },
  { period: "2026-05", value: 89.4, unit: "synthetic index" },
  { period: "2026-06", value: 88.8, unit: "synthetic index" },
  { period: "2026-07", value: 92.3, unit: "synthetic index" },
  { period: "2026-08", value: 94.0, unit: "synthetic index" },
  { period: "2026-09", value: 96.2, unit: "synthetic index" },
];

const sampleForecast: Forecast = {
  median: 98.1, lower: 93.0, upper: 103.2, baseline: 96.2,
  horizon_end: "2026-10", unit: "synthetic index",
};

function App() {
  const [observations, setObservations] = useState<Observation[]>(sample);
  const [forecast, setForecast] = useState<Forecast>(sampleForecast);
  const [source, setSource] = useState<"sample" | "api">("sample");
  const [lastUpdated, setLastUpdated] = useState("Bundled demo fixture");
  const [active, setActive] = useState("Overview");

  async function refresh() {
    try {
      const [obsRes, forecastRes] = await Promise.all([
        fetch(`${API}/v1/observations?series_id=demo_upi`),
        fetch(`${API}/v1/forecasts`),
      ]);
      if (!obsRes.ok || !forecastRes.ok) throw new Error("API unavailable");
      const obs = await obsRes.json() as ApiEnvelope<Observation[]>;
      const fc = await forecastRes.json() as ApiEnvelope<Forecast[]>;
      if (obs.meta.mode !== "synthetic" || fc.meta.mode !== "synthetic") {
        throw new Error("Unexpected data mode");
      }
      setObservations(obs.data);
      setForecast(fc.data[0]);
      setSource("api");
      setLastUpdated(new Date().toLocaleString());
    } catch {
      setObservations(sample);
      setForecast(sampleForecast);
      setSource("sample");
      setLastUpdated("Bundled demo fixture — API unavailable");
    }
  }

  useEffect(() => { void refresh(); }, []);

  const latest = observations[observations.length - 1]?.value ?? 0;
  const previous = observations[observations.length - 2]?.value ?? latest;
  const change = latest - previous;
  const chartData = useMemo(() => [
    ...observations.map((o) => ({ period: o.period.slice(2), observed: o.value })),
    { period: forecast.horizon_end.slice(2), forecast: forecast.median, lower: forecast.lower, upper: forecast.upper },
  ], [observations, forecast]);

  const nav = ["Overview", "Trends", "Forecasts", "Methodology", "Model evidence"];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Activity size={22} /></div><div><strong>ECONOMIC PULSE</strong><small>BY COSMO ADVISORY CO.</small></div></div>
        <div className="side-label">WORKSPACE</div>
        <nav>{nav.map((item, i) => <button key={item} className={active === item ? "nav-item active" : "nav-item"} onClick={() => setActive(item)}>{i === 0 ? <Gauge /> : i === 1 ? <BarChart3 /> : i === 2 ? <Activity /> : i === 3 ? <CircleHelp /> : <ShieldCheck />}{item}</button>)}</nav>
        <div className="sidebar-bottom"><div className="status-dot" /> Demo environment <span>v0.1</span></div>
      </aside>

      <main className="main">
        <header className="topbar"><div className="crumb">Intelligence <span>/</span> {active}</div><div className="top-actions"><span className="sample-pill"><span /> {source === "api" ? "API · SYNTHETIC" : "SAMPLE DATA"}</span><button className="refresh" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button></div></header>
        <section className="page-heading"><div><div className="eyebrow">ECONOMIC ACTIVITY INTELLIGENCE</div><h1>{active === "Overview" ? "Economic pulse overview" : active}</h1><p>Explore activity signals, trend direction and experimental forecasts.</p></div><div className="date-chip"><Database size={15} /> Data as of Oct 01, 2026</div></section>

        {active === "Overview" || active === "Trends" ? <>
          <div className="notice"><ShieldCheck size={17} /><span><strong>Demonstration environment.</strong> All displayed values are synthetic and do not represent official UPI statistics or actual economic activity.</span></div>
          <section className="metric-grid">
            <Metric title="Latest activity index" value={latest.toFixed(1)} detail="Synthetic index · Sep 2026" icon={<Activity />} />
            <Metric title="Period movement" value={`${change >= 0 ? "+" : ""}${change.toFixed(1)}`} detail="Versus previous period" icon={change >= 0 ? <ArrowUpRight /> : <ArrowDownRight />} />
            <Metric title="Next-period forecast" value={forecast.median.toFixed(1)} detail={`Median · ${forecast.horizon_end}`} icon={<BarChart3 />} />
            <Metric title="Forecast range" value={`${forecast.lower.toFixed(0)}–${forecast.upper.toFixed(0)}`} detail="Illustrative 80% interval" icon={<Gauge />} />
          </section>
          <section className="panel chart-panel"><div className="panel-head"><div><h2>Activity trend & forecast</h2><p>Monthly synthetic index · observed values and illustrative forecast</p></div><span className="legend"><i /> Observed <i className="legend-forecast" /> Forecast</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 12, right: 12, left: -18, bottom: 0 }}><defs><linearGradient id="observedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1b8b85" stopOpacity={0.2} /><stop offset="100%" stopColor="#1b8b85" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#e9eef2" vertical={false} /><XAxis dataKey="period" tickLine={false} axisLine={false} tick={{ fill: "#83919d", fontSize: 12 }} /><YAxis tickLine={false} axisLine={false} tick={{ fill: "#83919d", fontSize: 12 }} domain={["dataMin - 5", "dataMax + 5"]} /><Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e5ebef" }} /><Area type="monotone" dataKey="observed" stroke="#16847e" strokeWidth={2.5} fill="url(#observedFill)" connectNulls /><Line type="monotone" dataKey="forecast" stroke="#e19a48" strokeWidth={2.5} strokeDasharray="6 5" dot={{ r: 4 }} connectNulls /></AreaChart></ResponsiveContainer></div></section>
          <section className="bottom-grid"><div className="panel"><div className="panel-head"><div><h2>Recent observations</h2><p>Sample series · latest periods</p></div></div><div className="table-wrap"><table><thead><tr><th>PERIOD</th><th>VALUE</th><th>DATA TYPE</th></tr></thead><tbody>{observations.slice(-5).reverse().map(o => <tr key={o.period}><td>{o.period}</td><td className="table-value">{o.value.toFixed(1)}</td><td><span className="tag">Synthetic</span></td></tr>)}</tbody></table></div></div><div className="panel forecast-card"><div className="panel-head"><div><h2>Forecast snapshot</h2><p>Next available period</p></div><span className="forecast-icon"><Activity size={18} /></span></div><div className="forecast-number">{forecast.median.toFixed(1)} <small>index</small></div><div className="range-line"><span style={{ left: "10%", width: "80%" }} /></div><div className="range-labels"><span>Lower {forecast.lower.toFixed(1)}</span><span>Upper {forecast.upper.toFixed(1)}</span></div><div className="baseline">Baseline comparison <strong>{forecast.baseline.toFixed(1)}</strong></div><p className="muted-note">Illustrative baseline only. No model accuracy claim is made.</p></div></section>
        </> : <section className="panel info-panel"><div className="info-icon"><ShieldCheck /></div><h2>{active}</h2><p>{active === "Forecasts" ? "Forecast output is currently an illustrative sample. The next milestone is to add a reproducible offline training and out-of-time evaluation pipeline." : active === "Methodology" ? "The experimental pulse signal will be versioned, documented and accompanied by data coverage and source provenance. It is not an official GDP growth estimate." : "Model evidence will report evaluation windows, baseline comparisons, error metrics, limitations and whether data is synthetic or real. No accuracy claim is currently available."}</p><div className="notice"><ShieldCheck size={17} /> <span>This section is intentionally marked as a prototype. No unsupported economic or predictive claims are displayed.</span></div></section>}

        <footer><span>ECONOMIC PULSE <b>·</b> COSMO ADVISORY CO.</span><span>Last refreshed: {lastUpdated}</span></footer>
      </main>
    </div>
  );
}

function Metric({ title, value, detail, icon }: { title: string; value: string; detail: string; icon: React.ReactNode }) {
  return <div className="metric-card"><div className="metric-top"><span>{title}</span><span className="metric-icon">{icon}</span></div><div className="metric-value">{value}</div><div className="metric-detail">{detail}</div></div>;
}

export default App;
