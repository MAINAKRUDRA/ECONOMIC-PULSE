import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import main
from app.supabase_store import SupabaseStore
from app.worker import process_job
from packages.ml.synthetic import make_synthetic


USER_ID = "11111111-1111-4111-8111-111111111111"
DATASET_ID = "22222222-2222-4222-8222-222222222222"
JOB_ID = "33333333-3333-4333-8333-333333333333"


class FakeStore:
    def __init__(self, dataset=None):
        self.dataset = dataset or {
            "id": DATASET_ID, "user_id": USER_ID, "storage_path": USER_ID + "/dataset.csv",
            "status": "uploaded", "source_url": "https://rbi.org.in/scripts/Statistics.aspx",
            "series_id": "upi_monthly", "source_name": "Reserve Bank of India",
            "rights_tag": "official-public-data", "file_name": "upi.csv",
        }
        self.updates = []
        self.inserts = []
        self.upserts = []
        self.uploads = {}
        self.csv_bytes = b""

    def verify_user(self, token):
        assert token == "valid-session"
        return {"id": USER_ID}

    def select(self, table, params):
        if table == "datasets":
            if params.get("user_id") == "eq." + USER_ID and self.dataset["user_id"] == USER_ID:
                return [self.dataset]
            return []
        return []

    def insert(self, table, payload):
        self.inserts.append((table, payload))
        return {"id": "44444444-4444-4444-8444-444444444444", **payload}

    def upsert(self, table, payload, on_conflict):
        self.upserts.append((table, payload, on_conflict))
        return {"id": payload.get("id", "55555555-5555-4555-8555-555555555555"), **payload}

    def update(self, table, filters, payload):
        self.updates.append((table, filters, payload))
        return []

    def download(self, bucket, path):
        assert bucket == "economic-datasets"
        assert path.startswith(USER_ID + "/")
        return self.csv_bytes

    def upload(self, bucket, path, content, content_type):
        assert bucket == "model-artifacts"
        self.uploads[path] = (content, content_type)

    def close(self):
        pass


def test_training_enqueue_checks_owner_and_queues(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(main, "_store", lambda: store)
    result = main.create_training_job(main.TrainingRequest(dataset_id=DATASET_ID), "Bearer valid-session")
    assert result["status"] == "queued"
    assert store.inserts[0][0] == "training_jobs"
    assert store.updates[0][0] == "datasets"


def test_training_enqueue_rejects_dataset_owned_by_another_user(monkeypatch):
    store = FakeStore()
    store.dataset["user_id"] = "99999999-9999-4999-8999-999999999999"
    monkeypatch.setattr(main, "_store", lambda: store)
    with pytest.raises(HTTPException) as error:
        main.create_training_job(main.TrainingRequest(dataset_id=DATASET_ID), "Bearer valid-session")
    assert error.value.status_code == 404
    assert not store.inserts


def test_training_enqueue_rejects_non_official_source(monkeypatch):
    store = FakeStore()
    store.dataset["source_url"] = "https://example.com/not-official.csv"
    monkeypatch.setattr(main, "_store", lambda: store)
    with pytest.raises(HTTPException) as error:
        main.create_training_job(main.TrainingRequest(dataset_id=DATASET_ID), "Bearer valid-session")
    assert error.value.status_code == 400


def test_upload_uses_private_bucket_path(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "server-only-test-key")
    store = SupabaseStore()
    calls = {}

    class FakeClient:
        def post(self, url, content, headers):
            calls.update({"url": url, "content": content, "headers": headers})
            class Response:
                def raise_for_status(self):
                    return None
            return Response()

    store.client = FakeClient()
    store.upload("economic-datasets", USER_ID + "/one.csv", b"csv", "text/csv")
    assert "/storage/v1/object/economic-datasets/" in calls["url"]
    assert USER_ID + "/one.csv" in calls["url"]
    assert calls["content"] == b"csv"
    assert calls["headers"]["x-upsert"] == "true"


def test_worker_persists_artifacts_evaluation_forecasts_and_model_version(tmp_path):
    csv = make_synthetic(tmp_path / "source.csv", months=60)
    frame = pd.read_csv(csv)
    frame["series_id"] = "upi_monthly"
    frame.to_csv(csv, index=False)

    store = FakeStore()
    store.csv_bytes = csv.read_bytes()
    process_job(store, {
        "id": JOB_ID, "dataset_id": DATASET_ID, "user_id": USER_ID,
        "attempt_count": 1, "max_attempts": 2,
    })

    assert store.uploads
    assert any(table == "model_versions" for table, _, _ in store.upserts)
    assert any(table == "model_evaluations" for table, _, _ in store.upserts)
    assert any(table == "forecasts" for table, _, _ in store.upserts)
    model = next(payload for table, payload, _ in store.upserts if table == "model_versions")
    assert model["manifest"]["source_url"].startswith("https://rbi.org.in/")
    assert model["status"] == "candidate"
    assert any(table == "model_versions" and payload.get("status") == "published"
               for table, _, payload in store.updates)
    assert any(table == "training_jobs" and payload.get("status") == "completed"
               for table, _, payload in store.updates)

def test_training_status_query_is_scoped_to_authenticated_owner(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(main, "_store", lambda: store)
    with pytest.raises(HTTPException) as error:
        main.get_training_job(JOB_ID, "Bearer valid-session")
    assert error.value.status_code == 404
