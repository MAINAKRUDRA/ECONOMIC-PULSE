from __future__ import annotations
import argparse,json,platform
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from .data import load_vintages,sha256_file
from .features import FEATURES,FEATURE_VERSION,build_training_rows,features_asof
from .backtest import expanding_backtest
from .challenger import validate_challenger,fit_final_models

def run_training(csv_path:Path,out_dir:Path,series_id:str):
    raw=load_vintages(csv_path); subset=raw[raw.series_id==series_id]
    if subset.empty: raise ValueError(f"Unknown series_id: {series_id}")
    rows=build_training_rows(raw,series_id)
    if rows.empty: raise ValueError("No eligible training rows; need at least 13 as-of monthly observations")
    out_dir.mkdir(parents=True,exist_ok=True)
    backtest=expanding_backtest(rows)
    challenger=validate_challenger(rows)
    (out_dir/"backtest.json").write_text(json.dumps(backtest,indent=2,allow_nan=False))
    (out_dir/"challenger_validation.json").write_text(json.dumps(challenger,indent=2,allow_nan=False))
    latest=subset.period.max(); target=latest+pd.DateOffset(months=1)
    origin=pd.Timestamp.now(tz="UTC")
    x,anchor,anchor_period=features_asof(subset,origin,target)
    xdf=pd.DataFrame([{k:x[k] for k in FEATURES}],columns=FEATURES)
    flat=float(anchor); trend=float(anchor*np.exp(x["g1"]*x["h"]))
    baseline_scores=backtest.get("metrics",{})
    champion="flat"
    fmae=baseline_scores.get("flat",{}).get("mae")
    tmae=baseline_scores.get("trend",{}).get("mae")
    if tmae is not None and (fmae is None or tmae<fmae): champion="trend"
    candidate_status="not_trained"; candidate=None
    lower=upper=None; interval_level=None; interval_status="withheld"
    eligible=rows[rows.label_available_at<=origin]
    if challenger.get("promote_xgboost") and len(eligible)>=30:
        champion="xgboost"
    try:
        if len(eligible)>=30:
            models=fit_final_models(eligible)
            candidate=float(anchor*np.exp(float(models["point"].predict(xdf)[0])))
            if champion=="xgboost":
                point=candidate
                models["point"].save_model(str(out_dir/"champion.ubj"))
            else:
                point=flat if champion=="flat" else trend
                models["point"].save_model(str(out_dir/"challenger.ubj"))
            qraw=[float(anchor*np.exp(float(models[k].predict(xdf)[0]))) for k in ("q10","q50","q90")]
            qsorted=sorted(qraw)
            if challenger.get("interval",{}).get("calibration_adequate"):
                lower,_,upper=qsorted
                interval_level=0.80; interval_status="validated_on_expanding_validation"
            for key in ("q10","q50","q90"):
                models[key].save_model(str(out_dir/f"{key}.ubj"))
            candidate_status="promoted" if champion=="xgboost" else "trained_not_promoted"
        else:
            point=flat if champion=="flat" else trend
            candidate_status="insufficient_training_rows"
    except RuntimeError:
        point=flat if champion=="flat" else trend
        candidate_status="xgboost_not_installed"
    mode="synthetic" if series_id.startswith("demo_") else "research"
    forecast={"target":series_id,"origin":origin.isoformat(),"horizon_end":target.strftime("%Y-%m"),
      "anchor_period":anchor_period.strftime("%Y-%m"),"anchor_count":float(anchor),"median":float(point),
      "lower":lower,"upper":upper,"unit":"transaction_count","model_version":champion+"-v1",
      "baseline":flat,"mode":mode,"interval_level":interval_level,"interval_status":interval_status,
      "candidate_prediction":candidate,"candidate_status":candidate_status}
    manifest={"created_at":datetime.now(timezone.utc).isoformat(),"series_id":series_id,
      "data_sha256":sha256_file(csv_path),"feature_version":FEATURE_VERSION,"features":FEATURES,
      "python":platform.python_version(),"pandas":pd.__version__,"numpy":np.__version__,
      "training_rows":int(len(rows)),"training_cutoff":origin.isoformat(),"mode":mode,
      "selection":champion,"candidate_status":candidate_status,
      "validation":challenger,"limitations":["Synthetic fixture validates pipeline plumbing only, not economic forecasting.",
        "UPI activity forecasting does not validate GDP forecasting.",
        "Quantile bounds are withheld unless expanding-validation coverage diagnostics meet minimum checks."]}
    (out_dir/"forecast_rows.json").write_text(json.dumps([forecast],indent=2,allow_nan=False))
    (out_dir/"features.json").write_text(json.dumps({"feature_version":FEATURE_VERSION,"features":FEATURES,
      "target":"log(target_count / anchor_count)","origin_policy":"Forecast origin timestamp; use only vintages available at origin"},indent=2))
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False))
    (out_dir/"model_card.md").write_text(f"""# Economic Pulse model card

- Series: {series_id}
- Mode: {mode}
- Selected champion: {champion}
- XGBoost status: {candidate_status}
- Training rows: {len(rows)}
- Forecast target: next monthly transaction count
- Interval status: {interval_status}
- Validation rows: {challenger.get('n',0)}

## Intended use
Experimental monthly UPI transaction-count forecasting research only.

## Limitations
- Synthetic fixture validates pipeline plumbing only, not economic forecasting.
- UPI activity is not GDP; this model makes no GDP forecast.
- Adoption, cash substitution and provider coverage may shift the data-generating process.
- Final reserved holdout is not used for model selection.
- Review source rights, vintages and first-availability timestamps before real-data runs.
""")
    return {"forecast":forecast,"manifest":manifest,"backtest_status":backtest["status"],
            "challenger_status":challenger.get("status")}

def main():
    p=argparse.ArgumentParser(description="Train and evaluate Economic Pulse offline model")
    p.add_argument("--data",required=True,type=Path)
    p.add_argument("--out",default=Path("artifacts/research"),type=Path)
    p.add_argument("--series-id",default="demo_upi_count")
    a=p.parse_args()
    print(json.dumps(run_training(a.data,a.out,a.series_id),indent=2,allow_nan=False))
if __name__=="__main__": main()
