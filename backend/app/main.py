from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

app = FastAPI(
    title="Economic Pulse API",
    version="0.5.0",
    description="Economic observations, user-owned model forecasts and persistent training orchestration.",
)
cors_origins = [
    origin.strip() for origin in os.getenv(
        "CORS_ORIGINS",
        "https://economic-pulse.pages.dev,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if origin.strip()
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


class TrainingRequest(BaseModel):
    dataset_id: str = Field(min_length=36, max_length=36)


def envelope(data: Any, mode: str = "synthetic", batch_id: str = "demo_v1", data_as_of: str | None = None):
    return {"data": data, "meta": {
        "mode": mode, "batch_id": batch_id,
        "data_as_of": data_as_of or DATA_AS_OF.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }}


def _store():
    from app.supabase_store import SupabaseStore
    try:
        return SupabaseStore()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _current_user(store, authorization: str | None) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="A signed-in Supabase session is required")
    return store.verify_user(token)


def _latest_model(store, user_id: str) -> dict | None:
    rows = store.select("model_versions", {
        "select": "id,version,series_id,manifest,forecast_payload,observations_payload,published_at",
        "user_id": f"eq.{user_id}", "is_published": "eq.true",
        "order": "published_at.desc", "limit": "1",
    })
    return rows[0] if rows else None


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    configured = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    return {"status": "ready" if configured else "degraded", "supabase_configured": configured}


@app.post("/v1/training-jobs", status_code=202)
def create_training_job(payload: TrainingRequest, authorization: str | None = Header(default=None)):
    store = _store()
    try:
        user = _current_user(store, authorization)
        dataset_rows = store.select("datasets", {
            "select": "id,user_id,storage_path,status,source_url", "id": f"eq.{payload.dataset_id}",
            "user_id": f"eq.{user['id']}", "limit": "1",
        })
        if not dataset_rows:
            raise HTTPException(status_code=404, detail="Dataset not found for this account")
        dataset = dataset_rows[0]
        if not dataset["storage_path"].startswith(user["id"] + "/"):
            raise HTTPException(status_code=403, detail="Dataset storage ownership mismatch")
        from app.source_policy import validate_official_source_url
        try:
            validate_official_source_url(dataset.get("source_url", ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if dataset["status"] in {"queued", "training"}:
            raise HTTPException(status_code=409, detail="Dataset already has an active training run")
        job = store.insert("training_jobs", {
            "user_id": user["id"], "dataset_id": dataset["id"], "status": "queued",
        })
        store.update("datasets", {"id": f"eq.{dataset['id']}"}, {"status": "queued"})
        return {"job_id": job["id"], "status": job["status"], "status_url": f"/v1/training-jobs/{job['id']}"}
    finally:
        store.close()


@app.get("/v1/training-jobs/{job_id}")
def get_training_job(job_id: str, authorization: str | None = Header(default=None)):
    store = _store()
    try:
        user = _current_user(store, authorization)
        rows = store.select("training_jobs", {
            "select": "id,dataset_id,status,attempt_count,error,result,created_at,started_at,completed_at",
            "id": f"eq.{job_id}", "user_id": f"eq.{user['id']}", "limit": "1",
        })
        if not rows:
            raise HTTPException(status_code=404, detail="Training job not found")
        return rows[0]
    finally:
        store.close()


@app.get("/v1/model-versions")
def list_model_versions(authorization: str | None = Header(default=None)):
    store = _store()
    try:
        user = _current_user(store, authorization)
        return store.select("model_versions", {
            "select": "id,series_id,version,status,is_published,manifest,metrics,created_at,published_at",
            "user_id": f"eq.{user['id']}", "order": "created_at.desc", "limit": "50",
        })
    finally:
        store.close()


@app.get("/v1/model-versions/{model_id}/evaluation")
def get_model_evaluation(model_id: str, authorization: str | None = Header(default=None)):
    store = _store()
    try:
        user = _current_user(store, authorization)
        rows = store.select("model_evaluations", {
            "select": "id,model_version_id,report,created_at",
            "model_version_id": f"eq.{model_id}", "user_id": f"eq.{user['id']}", "limit": "1",
        })
        if not rows:
            raise HTTPException(status_code=404, detail="Evaluation report not found")
        return rows[0]
    finally:
        store.close()


@app.get("/v1/forecasts")
def forecasts(authorization: str | None = Header(default=None)):
    if not authorization:
        return envelope([FORECAST])
    store = _store()
    try:
        user = _current_user(store, authorization)
        model = _latest_model(store, user["id"])
        if not model:
            return envelope([FORECAST])
        return envelope(model["forecast_payload"], "research", model["id"],
                        (model.get("manifest") or {}).get("training_cutoff", DATA_AS_OF.isoformat())[:10])
    finally:
        store.close()


@app.get("/v1/observations")
def observations(limit: int = 200, authorization: str | None = Header(default=None)):
    limit = max(1, min(limit, 200))
    if not authorization:
        return envelope(OBSERVATIONS[-limit:])
    store = _store()
    try:
        user = _current_user(store, authorization)
        model = _latest_model(store, user["id"])
        if not model:
            return envelope(OBSERVATIONS[-limit:])
        return envelope(model["observations_payload"][-limit:], "research", model["id"],
                        (model.get("manifest") or {}).get("training_cutoff", DATA_AS_OF.isoformat())[:10])
    finally:
        store.close()


@app.get("/v1/series")
def series(authorization: str | None = Header(default=None)):
    if not authorization:
        return envelope([{"series_id": "demo_upi", "name": "Illustrative UPI activity index",
                          "frequency": "monthly", "unit": "synthetic index", "mode": "synthetic"}])
    store = _store()
    try:
        user = _current_user(store, authorization)
        model = _latest_model(store, user["id"])
        if not model:
            return envelope([])
        return envelope([{"series_id": model["series_id"], "name": model["series_id"],
                          "frequency": "monthly", "unit": "transaction_count", "mode": "research"}],
                        "research", model["id"])
    finally:
        store.close()


@app.get("/v1/status")
def status(authorization: str | None = Header(default=None)):
    if not authorization:
        return envelope({"service": "economic-pulse-api", "publication_status": "demo",
                         "stale": False, "warning": "Synthetic demonstration data; not official economic estimates."})
    store = _store()
    try:
        user = _current_user(store, authorization)
        model = _latest_model(store, user["id"])
        return envelope({"service": "economic-pulse-api",
                         "publication_status": "published" if model else "demo",
                         "stale": False,
                         "warning": "Research publication. Review source provenance, model card and validation." if model
                         else "No model has been published for this account."},
                        "research" if model else "synthetic", model["id"] if model else BATCH_ID)
    finally:
        store.close()


@app.get("/v1/model-card")
def model_card(authorization: str | None = Header(default=None)):
    if not authorization:
        return envelope({"model_version": "baseline-demo-0.1", "model_type": "illustrative naive baseline",
                         "evaluation_status": "not evaluated", "limitations": ["Synthetic data only."]})
    store = _store()
    try:
        user = _current_user(store, authorization)
        model = _latest_model(store, user["id"])
        if not model:
            return envelope({"evaluation_status": "no published model"})
        return envelope({"manifest": model["manifest"], "version": model["version"]},
                        "research", model["id"])
    finally:
        store.close()


@app.get("/v1/pulse")
def pulse(authorization: str | None = Header(default=None)):
    data = observations(authorization=authorization).get("data", OBSERVATIONS)
    if len(data) < 2:
        raise HTTPException(status_code=503, detail="Insufficient observations for pulse change")
    change = round(float(data[-1]["value"]) - float(data[-2]["value"]), 2)
    return envelope({"score": None, "label": "Experimental activity signal",
                     "direction": "up" if change >= 0 else "down", "latest_period_change": change,
                     "method_version": "demo-method-0.1", "coverage": "published series only",
                     "warning": "This activity proxy is not GDP growth or an official economic indicator."})
