from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
def make_synthetic(path:Path,months=60,seed=7):
    rng=np.random.default_rng(seed); periods=pd.date_range("2019-01-01",periods=months,freq="MS",tz="UTC")
    level=100000.; rows=[]
    for i,p in enumerate(periods):
        seasonal=1+0.06*np.sin(2*np.pi*p.month/12); level*=np.exp(.012+rng.normal(0,.018))
        value=max(1.,level*seasonal); release=p+pd.Timedelta(days=35)
        rows.append({"series_id":"demo_upi_count","period":p.date().isoformat(),"available_at":release.isoformat(),"revision":0,"volume_count":round(value)})
        if i%6==0: rows.append({"series_id":"demo_upi_count","period":p.date().isoformat(),"available_at":(release+pd.Timedelta(days=30)).isoformat(),"revision":1,"volume_count":round(value*1.003)})
    path.parent.mkdir(parents=True,exist_ok=True); pd.DataFrame(rows).to_csv(path,index=False); return path
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--out",type=Path,default=Path("data/synthetic/monthly_upi_demo.csv")); p.add_argument("--months",type=int,default=60)
    a=p.parse_args(); print(make_synthetic(a.out,a.months))
