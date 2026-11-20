from __future__ import annotations
import argparse,json,platform
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from .data import load_vintages,sha256_file
from .features import FEATURES,FEATURE_VERSION,build_training_rows,features_asof
from .backtest import expanding_backtest
def fit_xgb(train,objective="reg:squarederror",alpha=None):
    try: from xgboost import XGBRegressor
    except ImportError as exc: raise RuntimeError("Install requirements-training.txt for XGBoost") from exc
    kw=dict(objective=objective,tree_method="hist",n_estimators=100,max_depth=2,
      learning_rate=0.04,min_child_weight=8,reg_lambda=10,n_jobs=2,random_state=42)
    if alpha is not None: kw["quantile_alpha"]=alpha
    return XGBRegressor(**kw).fit(train[FEATURES],train["y"])
def run_training(csv_path:Path,out_dir:Path,series_id:str):
    raw=load_vintages(csv_path); subset=raw[raw.series_id==series_id]
    if subset.empty: raise ValueError(f"Unknown series_id: {series_id}")
    rows=build_training_rows(raw,series_id)
    if rows.empty: raise ValueError("No eligible training rows; need at least 13 as-of monthly observations")
    out_dir.mkdir(parents=True,exist_ok=True)
    backtest=expanding_backtest(rows)
    (out_dir/"backtest.json").write_text(json.dumps(backtest,indent=2,allow_nan=False))
    latest=subset.period.max(); target=latest+pd.DateOffset(months=1)
    origin=pd.Timestamp.now(tz="UTC")
    x,anchor,anchor_period=features_asof(subset,origin,target)
    xdf=pd.DataFrame([{k:x[k] for k in FEATURES}],columns=FEATURES)
    flat=float(anchor); trend=float(anchor*np.exp(x["g1"]*x["h"]))
    scores=backtest.get("metrics",{}); champion="flat"
    fmae=scores.get("flat",{}).get("mae"); tmae=scores.get("trend",{}).get("mae")
    if tmae is not None and (fmae is None or tmae<fmae): champion="trend"
    candidate=None; candidate_status="not_trained"
    eligible=rows[rows.label_available_at<=origin]
    if len(eligible)>=30:
        try:
            model=fit_xgb(eligible)
            candidate=float(anchor*np.exp(float(model.predict(xdf)[0])))
            candidate_status="trained_not_promoted"
            # Store model artifact only in private operator output, never public repo.
            model.save_model(str(out_dir/"challenger.ubj"))
        except RuntimeError: candidate_status="xgboost_not_installed"
    point=flat if champion=="flat" else trend
    mode="synthetic" if series_id.startswith("demo_") else "research"
    forecast={"target":series_id,"origin":origin.isoformat(),"horizon_end":target.strftime("%Y-%m"),
      "anchor_period":anchor_period.strftime("%Y-%m"),"anchor_count":float(anchor),"median":point,
      "lower":None,"upper":None,"unit":"transaction_count","model_version":champion+"-v1",
      "baseline":flat,"mode":mode,"interval_level":None,"interval_status":"withheld",
      "candidate_prediction":candidate,"candidate_status":candidate_status}
    manifest={"created_at":datetime.now(timezone.utc).isoformat(),"series_id":series_id,
      "data_sha256":sha256_file(csv_path),"feature_version":FEATURE_VERSION,"features":FEATURES,
      "python":platform.python_version(),"pandas":pd.__version__,"numpy":np.__version__,
      "training_rows":int(len(rows)),"training_cutoff":origin.isoformat(),"mode":mode,
      "selection":champion,"candidate_status":candidate_status,
      "limitations":["Synthetic data validates pipeline plumbing only, not economic forecasting.",
        "UPI activity forecasting does not validate GDP forecasting.",
        "Intervals withheld until chronological calibration is demonstrated."]}
    (out_dir/"forecast_rows.json").write_text(json.dumps([forecast],indent=2,allow_nan=False))
    (out_dir/"features.json").write_text(json.dumps({"feature_version":FEATURE_VERSION,"features":FEATURES,
      "target":"log(target_count / anchor_count)","origin_policy":"Forecast origin timestamp; use only vintages available at origin"},indent=2))
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2))
    (out_dir/"model_card.md").write_text(f"""# Economic Pulse model card

- Series: {series_id}
- Mode: {mode}
- Selected baseline: {champion}
- XGBoost challenger: {candidate_status}
- Training rows: {len(rows)}
- Forecast target: next monthly transaction count
- Prediction interval: withheld; no calibration evidence is available.

## Limitations
- Synthetic fixture validates pipeline plumbing only.
- UPI activity is not GDP; this model makes no GDP forecast.
- Adoption, cash substitution and provider coverage may shift the data-generating process.
- Review source rights, vintages and first-availability timestamps before real-data runs.
""")
    return {"forecast":forecast,"manifest":manifest,"backtest_status":backtest["status"]}
def main():
    p=argparse.ArgumentParser(description="Train and evaluate Economic Pulse offline model")
    p.add_argument("--data",required=True,type=Path); p.add_argument("--out",default=Path("artifacts/research"),type=Path)
    p.add_argument("--series-id",default="demo_upi_count"); a=p.parse_args()
    print(json.dumps(run_training(a.data,a.out,a.series_id),indent=2))
if __name__=="__main__": main()
