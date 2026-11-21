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
    actual_values = actual[mask]
    predicted_values = predicted[mask]
    denominator = np.abs(actual_values) + np.abs(predicted_values)
    smape_mask = denominator > 0
    return {
        "n": int(mask.sum()),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mape_pct": float(np.mean(np.abs(err) / np.abs(actual_values)) * 100) if np.all(actual_values != 0) else None,
        "smape_pct": float(np.mean(200 * np.abs(err[smape_mask]) / denominator[smape_mask])) if smape_mask.any() else None,
    }
