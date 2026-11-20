from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
def validate_bundle(directory:Path):
    required=["manifest.json","features.json","forecast_rows.json","model_card.md"]
    missing=[x for x in required if not (directory/x).is_file()]
    if missing: raise ValueError(f"Bundle missing files: {missing}")
    m=json.loads((directory/"manifest.json").read_text()); f=json.loads((directory/"features.json").read_text())
    rows=json.loads((directory/"forecast_rows.json").read_text())
    if not isinstance(rows,list) or not rows: raise ValueError("forecast_rows must be a non-empty list")
    if m.get("feature_version")!=f.get("feature_version"): raise ValueError("Feature version mismatch")
    if m.get("mode") not in {"synthetic","research"}: raise ValueError("Invalid mode")
    for r in rows:
        for k in ["target","origin","horizon_end","median","unit","model_version","mode"]:
            if k not in r: raise ValueError(f"Missing forecast field: {k}")
        if r["mode"]!=m["mode"]: raise ValueError("Forecast mode differs from manifest")
        if not math.isfinite(float(r["median"])) or float(r["median"])<0: raise ValueError("Invalid median")
        lo,hi=r.get("lower"),r.get("upper")
        if (lo is None)!=(hi is None): raise ValueError("Both interval bounds must be present or withheld")
        if lo is not None and not (math.isfinite(float(lo)) and math.isfinite(float(hi)) and 0<=float(lo)<=float(r["median"])<=float(hi)):
            raise ValueError("Interval must be finite, nonnegative and ordered")
    hashes={n:hashlib.sha256((directory/n).read_bytes()).hexdigest() for n in required if n.endswith(".json")}
    return {"valid":True,"mode":m["mode"],"rows":len(rows),"sha256":hashes}
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("bundle",type=Path); a=p.parse_args()
    print(json.dumps(validate_bundle(a.bundle),indent=2))
