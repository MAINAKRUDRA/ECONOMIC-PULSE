from __future__ import annotations
import numpy as np
import pandas as pd
def predict_baselines(train_rows:pd.DataFrame,test_rows:pd.DataFrame):
    flat=test_rows.anchor_count.to_numpy(dtype=float)
    trend=flat*np.exp(test_rows.g1.to_numpy(dtype=float)*test_rows.h.to_numpy(dtype=float))
    seasonal=[]
    for row in test_rows.itertuples():
        p=row.target_period-pd.DateOffset(months=12)
        eligible=train_rows[(train_rows.target_period==p)&(train_rows.label_available_at<=row.origin)]
        seasonal.append(float(eligible.iloc[-1].target_count) if not eligible.empty else np.nan)
    return {"flat":flat,"trend":trend,"seasonal":np.asarray(seasonal,dtype=float)}
def metrics(actual,predicted):
    mask=np.isfinite(actual)&np.isfinite(predicted)
    if not mask.any(): return {"n":0,"mae":None,"rmse":None}
    err=predicted[mask]-actual[mask]
    return {"n":int(mask.sum()),"mae":float(np.mean(np.abs(err))),"rmse":float(np.sqrt(np.mean(err**2)))}
