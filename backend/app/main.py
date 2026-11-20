from __future__ import annotations
import json
import os
from datetime import date,datetime,timezone
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI(title="Economic Pulse API",version="0.2.1",
    description="Read-only API for published economic activity observations and forecasts.")

# Render production origins are configured with CORS_ORIGINS as a comma-separated
# environment variable. Local Vite development remains supported by default.
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATA_AS_OF=date(2026,10,1)
BATCH_ID="demo_v1"
OBSERVATIONS=[
 {"period":"2026-01","value":82.0,"unit":"synthetic index"},
 {"period":"2026-02","value":84.5,"unit":"synthetic index"},
 {"period":"2026-03","value":83.2,"unit":"synthetic index"},
 {"period":"2026-04","value":87.1,"unit":"synthetic index"},
 {"period":"2026-05","value":89.4,"unit":"synthetic index"},
 {"period":"2026-06","value":88.8,"unit":"synthetic index"},
 {"period":"2026-07","value":92.3,"unit":"synthetic index"},
 {"period":"2026-08","value":94.0,"unit":"synthetic index"},
 {"period":"2026-09","value":96.2,"unit":"synthetic index"},
]
FORECAST={"target":"demo_upi_activity_index","origin":"2026-09","horizon_end":"2026-10",
 "median":98.1,"lower":93.0,"upper":103.2,"unit":"synthetic index",
 "model_version":"baseline-demo-0.1","baseline":96.2,"interval_level":0.80,
 "mode":"synthetic"}

def published_bundle():
    path=os.getenv("ECONOMIC_PULSE_PUBLISHED_FILE")
    if not path: return None
    try:
        payload=json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("mode") not in {"synthetic","research"} or not isinstance(payload.get("forecasts"),list) or not isinstance(payload.get("observations"),list):
            raise ValueError("Invalid publication schema")
        return payload
    except FileNotFoundError:
        raise HTTPException(status_code=503,detail="Configured publication batch is unavailable")
    except (OSError,ValueError,json.JSONDecodeError):
        raise HTTPException(status_code=503,detail="Configured publication batch failed validation")

def envelope(data,mode="synthetic",batch_id="demo_v1",data_as_of=None):
    return {"data":data,"meta":{"mode":mode,"batch_id":batch_id,
      "data_as_of":data_as_of or DATA_AS_OF.isoformat(),
      "generated_at":datetime.now(timezone.utc).isoformat()}}

@app.get("/health/live")
def health_live(): return {"status":"ok"}

@app.get("/v1/status")
def status():
    bundle=published_bundle()
    return envelope({"service":"economic-pulse-api",
      "publication_status":"published" if bundle else "demo",
      "stale":False,"warning":"Synthetic demonstration data; not official GDP or economic estimates."
      if not bundle or bundle["mode"]=="synthetic" else "Research publication. Review model card and source rights."},
      bundle["mode"] if bundle else "synthetic",bundle["batch_id"] if bundle else BATCH_ID,
      bundle["manifest"].get("training_cutoff",DATA_AS_OF.isoformat())[:10] if bundle else DATA_AS_OF.isoformat())

@app.get("/v1/series")
def series():
    bundle=published_bundle()
    if bundle:
        return envelope([{"series_id":bundle["series_id"],"name":bundle["series_id"],
          "frequency":"monthly","unit":"transaction_count","mode":bundle["mode"]}],
          bundle["mode"],bundle["batch_id"])
    return envelope([{"series_id":"demo_upi","name":"Illustrative UPI activity index",
      "frequency":"monthly","unit":"synthetic index","mode":"synthetic"}])

@app.get("/v1/observations")
def observations(series_id:str|None=None,limit:int=Query(default=50,ge=1,le=200)):
    bundle=published_bundle()
    if bundle:
        if series_id and series_id not in {bundle["series_id"],"demo_upi"}:
            raise HTTPException(status_code=404,detail="Unknown series")
        return envelope(bundle["observations"][-limit:],bundle["mode"],bundle["batch_id"])
    if series_id not in {None,"demo_upi","demo_upi_count"}:
        raise HTTPException(status_code=404,detail="Unknown series")
    return envelope(OBSERVATIONS[-limit:])

@app.get("/v1/forecasts")
def forecasts(target:str|None=None):
    bundle=published_bundle()
    if bundle:
        rows=bundle["forecasts"]
        if target: rows=[r for r in rows if r["target"]==target]
        if not rows: raise HTTPException(status_code=404,detail="Unknown forecast target")
        return envelope(rows,bundle["mode"],bundle["batch_id"])
    if target and target!=FORECAST["target"]:
        raise HTTPException(status_code=404,detail="Unknown forecast target")
    return envelope([FORECAST])

@app.get("/v1/model-card")
def model_card():
    bundle=published_bundle()
    if bundle:
        return envelope({"manifest":bundle["manifest"],"model_card":bundle["model_card"],
          "validation":bundle["validation"]},bundle["mode"],bundle["batch_id"])
    return envelope({"model_version":"baseline-demo-0.1","model_type":"illustrative naive baseline",
      "evaluation_status":"not evaluated","limitations":["Synthetic data only; not a real UPI forecast.",
      "No out-of-time validation has been performed.","The pulse indicator is not official GDP growth."]})

@app.get("/v1/pulse")
def pulse():
    bundle=published_bundle()
    obs=bundle["observations"] if bundle else OBSERVATIONS
    if len(obs)<2: raise HTTPException(status_code=503,detail="Insufficient observations for pulse change")
    change=round(float(obs[-1]["value"])-float(obs[-2]["value"]),2)
    return envelope({"score":None,"label":"Experimental activity signal",
      "direction":"up" if change>=0 else "down","latest_period_change":change,
      "method_version":"demo-method-0.1","coverage":"published series only",
      "warning":"This activity proxy is not GDP growth or an official economic indicator."},
      bundle["mode"] if bundle else "synthetic",bundle["batch_id"] if bundle else BATCH_ID)
