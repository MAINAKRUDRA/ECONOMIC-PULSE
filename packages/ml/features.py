from __future__ import annotations
import numpy as np
import pandas as pd
from .data import month_start
FEATURES=["g1","g3","yoy","month_sin","month_cos","h"]
FEATURE_VERSION="monthly-upi-asof-v1"
def features_asof(raw:pd.DataFrame,origin:pd.Timestamp,target_period:pd.Timestamp):
    origin=pd.Timestamp(origin); target_period=month_start(pd.Timestamp(target_period))
    known=raw[(raw.available_at<=origin)&(raw.period<target_period)].copy()
    if known.empty: raise ValueError("No observations available at origin")
    snap=known.sort_values(["available_at","revision"]).drop_duplicates("period",keep="last").sort_values("period")
    tail=snap.tail(13)
    if len(tail)<13: raise ValueError("Insufficient history: need 13 consecutive months")
    expected=pd.date_range(end=tail.period.iloc[-1],periods=13,freq="MS",tz="UTC")
    if not tail.period.reset_index(drop=True).equals(pd.Series(expected)): raise ValueError("Trailing 13 months are not consecutive")
    v=tail.volume_count.to_numpy(dtype=float)
    if not np.isfinite(v).all() or (v<=0).any(): raise ValueError("Invalid feature counts")
    anchor_period=tail.period.iloc[-1]
    h=(target_period.year-anchor_period.year)*12+target_period.month-anchor_period.month
    if h<1: raise ValueError("Target must be after latest known anchor")
    phase=2*np.pi*target_period.month/12
    x={"g1":float(np.log(v[-1]/v[-2])),"g3":float(np.log(v[-1]/v[-4])/3),
       "yoy":float(np.log(v[-1]/v[-13])),"month_sin":float(np.sin(phase)),
       "month_cos":float(np.cos(phase)),"h":float(h)}
    return x,float(v[-1]),anchor_period
def build_training_rows(raw:pd.DataFrame,series_id:str)->pd.DataFrame:
    subset=raw[raw.series_id==series_id]; rows=[]
    for target in sorted(subset.period.unique()):
        target=pd.Timestamp(target); prev=target-pd.DateOffset(months=1)
        origin=pd.Timestamp(year=prev.year,month=prev.month,day=20,tz="UTC")
        label=subset[subset.period==target].sort_values(["available_at","revision"])
        if label.empty: continue
        label=label.iloc[0]
        try: x,anchor,anchor_period=features_asof(subset,origin,target)
        except ValueError: continue
        rows.append({**x,"series_id":series_id,"origin":origin,"target_period":target,
          "anchor_period":anchor_period,"anchor_count":anchor,"target_count":float(label.volume_count),
          "y":float(np.log(float(label.volume_count)/anchor)),"label_available_at":label.available_at,
          "feature_version":FEATURE_VERSION})
    return pd.DataFrame(rows)
