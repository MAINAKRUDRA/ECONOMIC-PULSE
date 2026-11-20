from __future__ import annotations
import numpy as np
import pandas as pd
from .baselines import metrics,predict_baselines
def eligible_training(rows,test_origin):
    return rows[(rows.origin<test_origin)&(rows.label_available_at<=test_origin)].copy()
def expanding_backtest(rows,min_train=18,final_test_months=12):
    rows=rows.sort_values(["origin","target_period"]).reset_index(drop=True)
    origins=sorted(rows.origin.unique())
    if len(origins)<=min_train:
        return {"status":"insufficient_history","reason":"Not enough origins for expanding validation","folds":[],"metrics":{},"final_test":{"reserved":False}}
    targets=sorted(rows.target_period.unique())
    reserve=set(targets[-final_test_months:]) if len(targets)>=min_train+final_test_months else set()
    development=rows[~rows.target_period.isin(reserve)] if reserve else rows
    dev_origins=sorted(development.origin.unique()); folds=[]; raw_folds=[]
    for origin in dev_origins[min_train:]:
        train=eligible_training(development,origin); test=development[development.origin==origin]
        if len(train)<min_train or test.empty: continue
        pred=predict_baselines(train,test); actual=test.target_count.to_numpy(dtype=float)
        raw_folds.append((actual,pred))
        folds.append({"origin":pd.Timestamp(origin).isoformat(),"n_train":int(len(train)),
          "n_test":int(len(test)),"actual":actual.tolist(),
          "predictions":{k:[float(x) if np.isfinite(x) else None for x in v] for k,v in pred.items()}})
    summary={}
    for name in ["flat","trend","seasonal"]:
        ys=[]; ps=[]
        for actual,pred in raw_folds:
            for y,p in zip(actual,pred[name]):
                if np.isfinite(p): ys.append(float(y)); ps.append(float(p))
        summary[name]=metrics(np.asarray(ys),np.asarray(ps))
    return {"status":"ok" if folds else "insufficient_history","folds":folds,"metrics":summary,
      "final_test":{"reserved":bool(reserve),"periods":[str(x) for x in sorted(reserve)],"evaluated":False}}
