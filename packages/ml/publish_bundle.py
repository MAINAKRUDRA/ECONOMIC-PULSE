from __future__ import annotations
import argparse,hashlib,json,math,os,tempfile
from pathlib import Path
def validate_bundle(directory:Path):
    required=["manifest.json","features.json","forecast_rows.json","observations.json","model_card.md"]
    missing=[x for x in required if not (directory/x).is_file()]
    if missing: raise ValueError(f"Bundle missing files: {missing}")
    m=json.loads((directory/"manifest.json").read_text()); f=json.loads((directory/"features.json").read_text())
    rows=json.loads((directory/"forecast_rows.json").read_text())
    observations=json.loads((directory/"observations.json").read_text())
    if not isinstance(rows,list) or not rows: raise ValueError("forecast_rows must be a non-empty list")
    if m.get("feature_version")!=f.get("feature_version"): raise ValueError("Feature version mismatch")
    if m.get("mode") not in {"synthetic","research"}: raise ValueError("Invalid mode")
    if m.get("mode")=="research" and (not m.get("source_name") or not m.get("rights_tag")):
        raise ValueError("Research bundle lacks source provenance or rights tag")
    for name,digest in m.get("model_artifacts",{}).items():
        artifact=directory/name
        if not artifact.is_file(): raise ValueError(f"Missing model artifact: {name}")
        actual=hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual!=digest: raise ValueError(f"Model artifact hash mismatch: {name}")
    for r in rows:
        for k in ["target","origin","horizon_end","median","unit","model_version","mode"]:
            if k not in r: raise ValueError(f"Missing forecast field: {k}")
        if r["mode"]!=m["mode"]: raise ValueError("Forecast mode differs from manifest")
        if not math.isfinite(float(r["median"])) or float(r["median"])<0: raise ValueError("Invalid median")
        lo,hi=r.get("lower"),r.get("upper")
        if (lo is None)!=(hi is None): raise ValueError("Both interval bounds must be present or withheld")
        if lo is not None and not (math.isfinite(float(lo)) and math.isfinite(float(hi)) and 0<=float(lo)<=float(r["median"])<=float(hi)):
            raise ValueError("Interval must be finite, nonnegative and ordered")
    if not isinstance(observations,list) or not observations:
        raise ValueError("observations.json must contain a non-empty list")
    for obs in observations:
        if obs.get("series_id")!=m.get("series_id") or not math.isfinite(float(obs.get("value",float("nan")))) or float(obs["value"])<=0:
            raise ValueError("Invalid observation row")
    hashes={n:hashlib.sha256((directory/n).read_bytes()).hexdigest() for n in required if n.endswith(".json")}
    return {"valid":True,"mode":m["mode"],"rows":len(rows),"observations":len(observations),"sha256":hashes}

def publish_local_bundle(directory:Path,destination:Path):
    validation=validate_bundle(directory)
    manifest=json.loads((directory/"manifest.json").read_text())
    payload={"batch_id":hashlib.sha256((directory/"manifest.json").read_bytes()).hexdigest()[:16],
      "published_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
      "mode":manifest["mode"],"series_id":manifest["series_id"],
      "manifest":manifest,"forecasts":json.loads((directory/"forecast_rows.json").read_text()),
      "observations":json.loads((directory/"observations.json").read_text()),
      "model_card":(directory/"model_card.md").read_text(),"validation":validation}
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=destination.name+".",suffix=".tmp",dir=destination.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(payload,stream,indent=2,allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,destination)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return {"published":True,"destination":str(destination),"batch_id":payload["batch_id"],"mode":payload["mode"]}

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("bundle",type=Path)
    p.add_argument("--publish-to",type=Path,default=None,help="Atomically write a local API publication file")
    a=p.parse_args()
    result=validate_bundle(a.bundle)
    if a.publish_to: result["publication"]=publish_local_bundle(a.bundle,a.publish_to)
    print(json.dumps(result,indent=2))
