from __future__ import annotations
import numpy as np
import pandas as pd
from .features import FEATURES
from .backtest import eligible_training
from .baselines import metrics

QUANTILES=(0.10,0.50,0.90)

def _model(train, objective="reg:squarederror", alpha=None):
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise RuntimeError("Install requirements-training.txt to run XGBoost") from exc
    kw=dict(objective=objective,tree_method="hist",n_estimators=100,max_depth=2,
            learning_rate=0.04,min_child_weight=8,reg_lambda=10,n_jobs=2,random_state=42)
    if alpha is not None: kw["quantile_alpha"]=alpha
    return XGBRegressor(**kw).fit(train[FEATURES],train["y"])

def pinball(actual,predicted,q):
    e=np.asarray(actual)-np.asarray(predicted)
    return float(np.mean(np.maximum(q*e,(q-1)*e)))

def validate_challenger(rows:pd.DataFrame,min_train=30,min_validation=12):
    rows=rows.sort_values(["origin","target_period"]).reset_index(drop=True)
    targets=sorted(rows.target_period.unique())
    reserve=set(targets[-12:]) if len(targets)>=min_train+12 else set()
    dev=rows[~rows.target_period.isin(reserve)] if reserve else rows
    records=[]
    origins=sorted(dev.origin.unique())
    for origin in origins:
        train=eligible_training(dev,origin)
        test=dev[dev.origin==origin]
        if len(train)<min_train or test.empty: continue
        try:
            point_model=_model(train)
            preds=point_model.predict(test[FEATURES])
            qpred={}
            for q in QUANTILES:
                qm=_model(train,"reg:quantileerror",q)
                qpred[q]=qm.predict(test[FEATURES])
            for i,row in enumerate(test.itertuples()):
                anchor=float(row.anchor_count)
                records.append({"actual":float(row.target_count),
                    "xgb":float(anchor*np.exp(float(preds[i]))),
                    "flat":anchor,
                    "trend":float(anchor*np.exp(float(row.g1)*float(row.h))),
                    "q10":float(anchor*np.exp(float(qpred[0.10][i]))),
                    "q50":float(anchor*np.exp(float(qpred[0.50][i]))),
                    "q90":float(anchor*np.exp(float(qpred[0.90][i])))})
        except (ValueError,RuntimeError,OverflowError):
            continue
    if not records:
        return {"status":"insufficient_history","n":0,"promote_xgboost":False,
                "reason":"No eligible chronological XGBoost validation folds."}
    df=pd.DataFrame(records)
    xgb=metrics(df.actual.to_numpy(),df.xgb.to_numpy())
    flat=metrics(df.actual.to_numpy(),df.flat.to_numpy())
    trend=metrics(df.actual.to_numpy(),df.trend.to_numpy())
    best_baseline=min([("flat",flat),("trend",trend)],key=lambda z:z[1]["mae"] if z[1]["mae"] is not None else float("inf"))
    coverage=float(((df.actual>=np.minimum(df.q10,df.q90))&(df.actual<=np.maximum(df.q10,df.q90))).mean())
    crossing=float((df.q10>df.q90).mean())
    interval_width=float(np.mean(np.abs(df.q90-df.q10)))
    n=len(df)
    calibrated=(n>=min_validation and 0.65<=coverage<=0.95 and crossing<=0.10)
    promote=(n>=min_validation and xgb["mae"] is not None and best_baseline[1]["mae"] is not None and xgb["mae"]<best_baseline[1]["mae"])
    holdout_rows=rows[rows.target_period.isin(reserve)] if reserve else rows.iloc[0:0]
    holdout_records=[]
    for origin in sorted(holdout_rows.origin.unique()):
        train=eligible_training(dev,origin); test=holdout_rows[holdout_rows.origin==origin]
        if len(train)<min_train or test.empty: continue
        try:
            pm=_model(train)
            qms={q:_model(train,"reg:quantileerror",q) for q in QUANTILES}
            pp=pm.predict(test[FEATURES])
            qp={q:m.predict(test[FEATURES]) for q,m in qms.items()}
            for i,row in enumerate(test.itertuples()):
                a=float(row.anchor_count)
                holdout_records.append({"actual":float(row.target_count),
                    "xgboost":float(a*np.exp(float(pp[i]))),
                    "q10":float(a*np.exp(float(qp[0.10][i]))),
                    "q50":float(a*np.exp(float(qp[0.50][i]))),
                    "q90":float(a*np.exp(float(qp[0.90][i])))})
        except (ValueError,RuntimeError,OverflowError):
            continue
    final_test={"reserved":bool(reserve),"evaluated":bool(holdout_records),
        "n":len(holdout_records),"selection_used":False}
    if holdout_records:
        hdf=pd.DataFrame(holdout_records)
        final_test["xgboost"]=metrics(hdf.actual.to_numpy(),hdf.xgboost.to_numpy())
        final_test["interval"]={"coverage":float(((hdf.actual>=np.minimum(hdf.q10,hdf.q90))&(hdf.actual<=np.maximum(hdf.q10,hdf.q90))).mean()),
          "mean_width":float(np.mean(np.abs(hdf.q90-hdf.q10))),
          "crossing_rate":float((hdf.q10>hdf.q90).mean())}
    return {"status":"ok","n":n,"xgboost":xgb,"flat":flat,"trend":trend,
      "best_baseline":best_baseline[0],"promote_xgboost":bool(promote),
      "interval":{"nominal_level":0.80,"empirical_coverage":coverage,
        "mean_width":interval_width,"crossing_rate":crossing,
        "calibration_adequate":bool(calibrated),"pinball_q10":pinball(df.actual,df.q10,0.10),
        "pinball_q50":pinball(df.actual,df.q50,0.50),"pinball_q90":pinball(df.actual,df.q90,0.90)},
      "final_test":{**final_test,"periods":[str(x) for x in sorted(reserve)]}}

def fit_final_models(train):
    return {"point":_model(train),
            "q10":_model(train,"reg:quantileerror",0.10),
            "q50":_model(train,"reg:quantileerror",0.50),
            "q90":_model(train,"reg:quantileerror",0.90)}
