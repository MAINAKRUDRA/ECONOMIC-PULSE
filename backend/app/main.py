from __future__ import annotations

import hmac
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_DIR = Path(os.getenv("ECONOMIC_PULSE_ARTIFACT_DIR", "/tmp/economic-pulse"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
PUBLISHED_FILE = Path(os.getenv("ECONOMIC_PULSE_PUBLISHED_FILE", str(ARTIFACT_DIR / "current.json")))
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
TRAINING_JOBS: dict[str, dict[str, Any]] = {}

app = FastAPI(
    title="Economic Pulse API",
    version="0.3.0",
    description="Economic observations, model forecasts and controlled model-training API.",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://economic-pulse.pages.dev,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

DATA_AS_OF = date(2026, 10, 1)
BATCH_ID = "demo_v1"
OBSERVATIONS = [
    {"period": "2026-01", "value": 82.0, "unit": "synthetic index"},
    {"period": "2026-02", "value": 84.5, "unit": "synthetic index"},
    {"period": "2026-03", "value": 83.2, "unit": "synthetic index"},
    {"period": "2026-04", "value": 87.1, "unit": "synthetic index"},
    {"period": "2026-05", "value": 89.4, "unit": "synthetic index"},
    {"period": "2026-06", "value": 88.8, "unit": "synthetic index"},
    {"period": "2026-07", "value": 92.3, "unit": "synthetic index"},
    {"period": "2026-08", "value": 94.0, "unit": "synthetic index"},
    {"period": "2026-09", "value": 96.2, "unit": "synthetic index"},
]
FORECAST = {
    "target": "demo_upi_activity_index", "origin": "2026-09", "horizon_end": "2026-10",
    "median": 98.1, "lower": 93.0, "upper": 103.2, "unit": "synthetic index",
    "model_version": "baseline-demo-0.1", "baseline": 96.2, "interval_level": 0.80,
    "mode": "synthetic",
}


def _admin_check(authorization: str | None) -> None:
    expected = os.getenv("ECONOMIC_PULSE_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Model-training endpoint is disabled until ECONOMIC_PULSE_ADMIN_TOKEN is configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def published_bundle():
    if not PUBLISHED_FILE.exists():
        return None
    try:
        payload = json.loads(PUBLISHED_FILE.read_text(encoding="utf-8"))
        if payload.get("mode") not in {"synthetic", "research"} or not isinstance(payload.get("forecasts"), list) or not isinstance(payload.get("observations"), list):
            raise ValueError("Invalid publication schema")
        return payload
    except FileNotFoundError:
        return None
    except (OSError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail="Configured publication batch failed validation")


def envelope(data, mode="synthetic", batch_id="demo_v1", data_as_of=None):
    return {"data": data, "meta": {"mode": mode, "batch_id": batch_id,
        "data_as_of": data_as_of or DATA_AS_OF.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat()}}


def _train_uploaded_csv(job_id: str, csv_path: Path, series_id: str, source_name: str, rights_tag: str):
    job = TRAINING_JOBS[job_id]
    job["status"] = "training"
    try:
        from packages.ml.train import run_training
        from packages.ml.publish_bundle import publish_local_bundle, validate_bundle

        output_dir = ARTIFACT_DIR / "runs" / job_id
        result = run_training(csv_path, output_dir, series_id, source_name, rights_tag)
        validation = validate_bundle(output_dir)
        if not validation.get("valid") or validation.get("mode") != "research":
            raise ValueError("Research model bundle did not pass publication validation")
        publication = publish_local_bundle(output_dir, PUBLISHED_FILE)
        job.update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "forecast": result["forecast"],
            "backtest_status": result["backtest_status"],
            "challenger_status": result["challenger_status"],
            "candidate_status": result["forecast"]["candidate_status"],
            "publication": publication,
            "validation": validation,
        })
    except Exception as exc:
        job.update({"status": "failed", "error": str(exc)[:1000],
                    "completed_at": datetime.now(timezone.utc).isoformat()})


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.post("/v1/admin/train", status_code=202)
async def start_training(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    series_id: str = Form(...),
    source_name: str = Form(...),
    rights_tag: str = Form(...),
    authorization: str | None = Header(default=None),
):
    _admin_check(authorization)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    if not series_id.strip() or series_id.startswith("demo_"):
        raise HTTPException(status_code=400, detail="Provide a real series_id; demo_ series are not accepted")
    if not source_name.strip() or not rights_tag.strip():
        raise HTTPException(status_code=400, detail="Source name and data-rights tag are required")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 20 MB upload limit")
    job_id = uuid.uuid4().hex
    upload_dir = ARTIFACT_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    csv_path = upload_dir / f"{job_id}.csv"
    csv_path.write_bytes(content)
    TRAINING_JOBS[job_id] = {
        "job_id": job_id, "status": "queued", "series_id": series_id.strip(),
        "source_name": source_name.strip(), "created_at": datetime.now(timezone.utc).isoformat(),
    }
    background_tasks.add_task(_train_uploaded_csv, job_id, csv_path, series_id.strip(), source_name.strip(), rights_tag.strip())
    return {"job_id": job_id, "status": "queued", "status_url": f"/v1/admin/train/{job_id}",
            "message": "Training queued. Poll the status URL for evaluation and publication results."}


@app.get("/v1/admin/train/{job_id}")
def training_status(job_id: str, authorization: str | None = Header(default=None)):
    _admin_check(authorization)
    job = TRAINING_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found on this API instance")
    return job


@app.get("/v1/status")
def status():
    bundle = published_bundle()
    return envelope({"service": "economic-pulse-api",
        "publication_status": "published" if bundle else "demo",
        "stale": False,
        "warning": ("Synthetic demonstration data; not official GDP or economic estimates."
                    if not bundle or bundle["mode"] == "synthetic"
                    else "Research publication. Review model card, source rights and validation before use.")},
        bundle["mode"] if bundle else "synthetic", bundle["batch_id"] if bundle else BATCH_ID,
        bundle["manifest"].get("training_cutoff", DATA_AS_OF.isoformat())[:10] if bundle else DATA_AS_OF.isoformat())


@app.get("/v1/series")
def series():
    bundle = published_bundle()
    if bundle:
        return envelope([{"series_id": bundle["series_id"], "name": bundle["series_id"],
            "frequency": "monthly", "unit": "transaction_count", "mode": bundle["mode"]}],
            bundle["mode"], bundle["batch_id"])
    return envelope([{"series_id": "demo_upi", "name": "Illustrative UPI activity index",
        "frequency": "monthly", "unit": "synthetic index", "mode": "synthetic"}])


@app.get("/v1/observations")
def observations(series_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    bundle = published_bundle()
    if bundle:
        if series_id and series_id not in {bundle["series_id"], "demo_upi"}:
            raise HTTPException(status_code=404, detail="Unknown series")
        return envelope(bundle["observations"][-limit:], bundle["mode"], bundle["batch_id"])
    if series_id not in {None, "demo_upi", "demo_upi_count"}:
        raise HTTPException(status_code=404, detail="Unknown series")
    return envelope(OBSERVATIONS[-limit:])


@app.get("/v1/forecasts")
def forecasts(target: str | None = None):
    bundle = published_bundle()
    if bundle:
        rows = bundle["forecasts"]
        if target:
            rows = [row for row in rows if row["target"] == target]
        if not rows:
            raise HTTPException(status_code=404, detail="Unknown forecast target")
        return envelope(rows, bundle["mode"], bundle["batch_id"])
    if target and target != FORECAST["target"]:
        raise HTTPException(status_code=404, detail="Unknown forecast target")
    return envelope([FORECAST])


@app.get("/v1/model-card")
def model_card():
    bundle = published_bundle()
    if bundle:
        return envelope({"manifest": bundle["manifest"], "model_card": bundle["model_card"],
            "validation": bundle["validation"]}, bundle["mode"], bundle["batch_id"])
    return envelope({"model_version": "baseline-demo-0.1", "model_type": "illustrative naive baseline",
        "evaluation_status": "not evaluated", "limitations": [
            "Synthetic data only; not a real UPI forecast.",
            "No out-of-time validation has been performed.",
            "The pulse indicator is not official GDP growth."]})


@app.get("/v1/pulse")
def pulse():
    bundle = published_bundle()
    obs = bundle["observations"] if bundle else OBSERVATIONS
    if len(obs) < 2:
        raise HTTPException(status_code=503, detail="Insufficient observations for pulse change")
    change = round(float(obs[-1]["value"]) - float(obs[-2]["value"]), 2)
    return envelope({"score": None, "label": "Experimental activity signal",
        "direction": "up" if change >= 0 else "down", "latest_period_change": change,
        "method_version": "demo-method-0.1", "coverage": "published series only",
        "warning": "This activity proxy is not GDP growth or an official economic indicator."},
        bundle["mode"] if bundle else "synthetic", bundle["batch_id"] if bundle else BATCH_ID)
