"""Persistent Supabase-backed training worker. Run as a separate service process."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.supabase_store import SupabaseStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("economic-pulse-worker")
POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "5"))


def process_job(store: SupabaseStore, job: dict) -> None:
    job_id, dataset_id, user_id = job["id"], job["dataset_id"], job["user_id"]
    dataset_rows = store.select("datasets", {
        "select": "*", "id": f"eq.{dataset_id}", "user_id": f"eq.{user_id}", "limit": "1"
    })
    if not dataset_rows:
        raise ValueError("Dataset metadata not found or not owned by the job owner")
    dataset = dataset_rows[0]
    store.update("datasets", {"id": f"eq.{dataset_id}"}, {"status": "training"})

    with tempfile.TemporaryDirectory(prefix=f"ep-{job_id}-") as temporary:
        root = Path(temporary)
        csv_path = root / "dataset.csv"
        csv_path.write_bytes(store.download("economic-datasets", dataset["storage_path"]))
        output_dir = root / "bundle"

        from app.source_policy import validate_official_source_url
        source_url = validate_official_source_url(dataset["source_url"])
        from packages.ml.train import run_training
        from packages.ml.publish_bundle import validate_bundle

        result = run_training(csv_path, output_dir, dataset["series_id"],
                              dataset["source_name"], dataset["rights_tag"])
        validation = validate_bundle(output_dir)
        if not validation.get("valid"):
            raise ValueError("Model bundle did not pass publication validation")

        manifest = result["manifest"]
        manifest["source_url"] = source_url
        manifest["dataset_id"] = dataset_id
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        forecast_rows = json.loads((output_dir / "forecast_rows.json").read_text(encoding="utf-8"))
        observations = json.loads((output_dir / "observations.json").read_text(encoding="utf-8"))
        version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "economic-pulse-training:" + job_id))
        version = f'{manifest.get("selection", "baseline")}-{manifest.get("created_at", "")[:10]}-{version_id[:8]}'
        artifact_prefix = f"{user_id}/{version_id}"
        artifact_files = []
        for artifact in sorted(output_dir.iterdir()):
            if artifact.is_file():
                content_type = "application/json" if artifact.suffix == ".json" else "text/plain" if artifact.suffix == ".md" else "application/octet-stream"
                store.upload("model-artifacts", f"{artifact_prefix}/{artifact.name}",
                             artifact.read_bytes(), content_type)
                artifact_files.append(artifact.name)

        backtest = json.loads((output_dir / "backtest.json").read_text(encoding="utf-8"))
        challenger = json.loads((output_dir / "challenger_validation.json").read_text(encoding="utf-8"))
        evaluation = {"backtest": backtest, "challenger": challenger, "bundle_validation": validation}
        model = store.upsert("model_versions", {
            "id": version_id, "user_id": user_id, "dataset_id": dataset_id,
            "training_job_id": job_id, "series_id": dataset["series_id"],
            "version": version, "status": "candidate", "is_published": False,
            "storage_path": artifact_prefix, "manifest": manifest,
            "metrics": backtest.get("metrics", {}),
            "forecast_payload": forecast_rows, "observations_payload": observations,
            "model_card": (output_dir / "model_card.md").read_text(encoding="utf-8") + "\n\nOfficial source: " + dataset["source_url"],
        }, "id")
        store.upsert("model_evaluations", {
            "user_id": user_id, "model_version_id": model["id"], "report": evaluation,
        }, "user_id,model_version_id")
        for forecast in forecast_rows:
            store.upsert("forecasts", {
                "user_id": user_id, "model_version_id": model["id"],
                "series_id": dataset["series_id"], "target": forecast["target"],
                "origin": forecast["origin"], "horizon_end": forecast["horizon_end"],
                "median": forecast["median"], "lower_bound": forecast.get("lower"),
                "upper_bound": forecast.get("upper"), "unit": forecast["unit"],
                "mode": forecast.get("mode", "research"),
            }, "model_version_id,target")
        store.update("model_versions", {"id": f"eq.{model['id']}"}, {
            "status": "published", "is_published": True,
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        store.update("datasets", {"id": f"eq.{dataset_id}"}, {"status": "completed"})
        store.update("training_jobs", {"id": f"eq.{job_id}"}, {
            "status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": {"model_version_id": model["id"], "version": version,
                       "forecast": forecast_rows[0], "backtest_status": result["backtest_status"],
                       "challenger_status": result["challenger_status"],
                       "artifacts": artifact_files, "validation": validation},
        })


def main() -> None:
    store = SupabaseStore()
    log.info("Economic Pulse worker started; polling Supabase training queue")
    while True:
        try:
            claimed = store.client.post(
                f"{store.url}/rest/v1/rpc/claim_economic_pulse_training_job",
                headers=store.headers(),
            )
            claimed.raise_for_status()
            jobs = claimed.json()
            if not jobs:
                time.sleep(POLL_SECONDS)
                continue
            for job in jobs:
                try:
                    process_job(store, job)
                    log.info("Completed training job %s", job["id"])
                except Exception as exc:
                    log.exception("Training job %s failed", job["id"])
                    attempt = int(job.get("attempt_count", 1))
                    terminal = attempt >= int(job.get("max_attempts", 2))
                    update = {"status": "failed" if terminal else "queued", "error": str(exc)[:1500]}
                    if terminal:
                        update["completed_at"] = datetime.now(timezone.utc).isoformat()
                    store.update("training_jobs", {"id": f'eq.{job["id"]}'}, update)
                    store.update("datasets", {"id": f'eq.{job["dataset_id"]}'}, {
                        "status": "failed" if terminal else "queued"
                    })
        except Exception:
            log.exception("Worker polling failed")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
