from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Economic Pulse API",
    version="0.1.0",
    description="Experimental economic activity dashboard API. Bundled data is synthetic.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATA_MODE = "synthetic"
BATCH_ID = "demo_v1"
DATA_AS_OF = date(2026, 10, 1)


class Observation(BaseModel):
    period: str
    value: float
    unit: str


class Forecast(BaseModel):
    target: str
    origin: str
    horizon_end: str
    median: float
    lower: float
    upper: float
    unit: str
    model_version: str
    baseline: float
    interval_level: float


# Illustrative values only. Replace only with provenance-checked observations.
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
    "target": "demo_upi_activity_index",
    "origin": "2026-09",
    "horizon_end": "2026-10",
    "median": 98.1,
    "lower": 93.0,
    "upper": 103.2,
    "unit": "synthetic index",
    "model_version": "baseline-demo-0.1",
    "baseline": 96.2,
    "interval_level": 0.80,
}


def envelope(data):
    return {
        "data": data,
        "meta": {
            "mode": DATA_MODE,
            "batch_id": BATCH_ID,
            "data_as_of": DATA_AS_OF.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/v1/status")
def status():
    return envelope({
        "service": "economic-pulse-api",
        "publication_status": "demo",
        "stale": False,
        "warning": "All bundled values are synthetic demonstration data.",
    })


@app.get("/v1/series")
def series():
    return envelope([{
        "series_id": "demo_upi",
        "name": "Illustrative UPI activity index",
        "frequency": "monthly",
        "unit": "synthetic index",
        "mode": DATA_MODE,
    }])


@app.get("/v1/observations")
def observations(
    series_id: str = Query(default="demo_upi"),
    limit: int = Query(default=50, ge=1, le=200),
):
    if series_id != "demo_upi":
        raise HTTPException(status_code=404, detail="Unknown series")
    return envelope(OBSERVATIONS[-limit:])


@app.get("/v1/forecasts")
def forecasts(target: str = Query(default="demo_upi_activity_index")):
    if target != FORECAST["target"]:
        raise HTTPException(status_code=404, detail="Unknown forecast target")
    return envelope([FORECAST])


@app.get("/v1/model-card")
def model_card():
    return envelope({
        "model_version": "baseline-demo-0.1",
        "model_type": "illustrative naive baseline",
        "evaluation_status": "not evaluated",
        "limitations": [
            "Synthetic data only; not a real UPI forecast.",
            "No out-of-time validation has been performed.",
            "The pulse indicator is experimental and is not official GDP growth.",
        ],
    })


@app.get("/v1/pulse")
def pulse():
    latest = OBSERVATIONS[-1]["value"]
    previous = OBSERVATIONS[-2]["value"]
    change = round(latest - previous, 2)
    return envelope({
        "score": 62,
        "label": "Experimental activity signal",
        "direction": "up" if change >= 0 else "down",
        "latest_period_change": change,
        "method_version": "demo-method-0.1",
        "coverage": "synthetic sample only",
        "warning": "Not an official economic indicator or GDP growth estimate.",
    })
