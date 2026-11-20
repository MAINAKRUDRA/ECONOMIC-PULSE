from __future__ import annotations
import hashlib
from pathlib import Path
import pandas as pd
REQUIRED = ["series_id", "period", "available_at", "revision", "volume_count"]
def sha256_file(path: str | Path) -> str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()
def load_vintages(path: str | Path) -> pd.DataFrame:
    raw=pd.read_csv(path); missing=sorted(set(REQUIRED)-set(raw.columns))
    if missing: raise ValueError(f"Missing required columns: {missing}")
    raw=raw[REQUIRED].copy()
    raw["period"]=pd.to_datetime(raw["period"],utc=True,errors="coerce")
    raw["available_at"]=pd.to_datetime(raw["available_at"],utc=True,errors="coerce")
    if raw[["period","available_at"]].isna().any().any(): raise ValueError("Invalid timestamps")
    if (raw["period"].dt.day!=1).any(): raise ValueError("period must be first day of reference month")
    if (raw["available_at"]<raw["period"]).any(): raise ValueError("available_at precedes reference period")
    raw["revision"]=pd.to_numeric(raw["revision"],errors="raise").astype(int)
    raw["volume_count"]=pd.to_numeric(raw["volume_count"],errors="raise")
    if (raw["volume_count"]<=0).any() or not raw["volume_count"].map(lambda x:pd.notna(x) and abs(x)!=float("inf")).all():
        raise ValueError("volume_count must be positive and finite")
    if raw.duplicated(["series_id","period","available_at","revision"]).any(): raise ValueError("Duplicate vintage")
    return raw.sort_values(["series_id","period","available_at","revision"]).reset_index(drop=True)
def month_start(ts):
    return pd.Timestamp(year=ts.year,month=ts.month,day=1,tz="UTC")
