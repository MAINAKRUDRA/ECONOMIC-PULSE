from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client


class SupabaseStore:
    """Server-side Supabase access. The service-role key must never reach the browser."""

    def __init__(self) -> None:
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured on the API service")
        self.client: Client = create_client(url, key)

    def authenticate(self, access_token: str) -> dict[str, Any]:
        response = self.client.auth.get_user(access_token)
        user = getattr(response, "user", None)
        if not user:
            raise ValueError("Invalid or expired Supabase access token")
        return {"id": str(user.id), "email": getattr(user, "email", None)}

    def create_dataset(self, user_id: str, file_name: str, content: bytes,
                       source_name: str, rights_tag: str) -> dict[str, Any]:
        import uuid
        path = f"{user_id}/{uuid.uuid4().hex}-{file_name}"
        self.client.storage.from_("economic-datasets").upload(
            path, content, {"content-type": "text/csv", "upsert": "false"}
        )
        try:
            result = self.client.table("datasets").insert({
                "user_id": user_id, "file_name": file_name, "storage_path": path,
                "size_bytes": len(content), "source_name": source_name, "rights_tag": rights_tag,
            }).execute()
            return result.data[0]
        except Exception:
            self.client.storage.from_("economic-datasets").remove([path])
            raise

    def create_job(self, job_id: str, user_id: str, dataset_id: str,
                   series_id: str, source_name: str, rights_tag: str) -> None:
        self.client.table("training_jobs").insert({
            "id": job_id, "user_id": user_id, "dataset_id": dataset_id,
            "series_id": series_id, "source_name": source_name,
            "rights_tag": rights_tag, "status": "queued",
        }).execute()

    def update_job(self, job_id: str, values: dict[str, Any]) -> None:
        self.client.table("training_jobs").update(values).eq("id", job_id).execute()

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any] | None:
        result = (self.client.table("training_jobs").select("*")
                  .eq("id", job_id).eq("user_id", user_id).maybe_single().execute())
        return result.data

    def download_dataset(self, path: str) -> bytes:
        return self.client.storage.from_("economic-datasets").download(path)

    def save_artifacts(self, user_id: str, job_id: str, series_id: str,
                       archive: bytes, bundle: bytes, manifest: dict[str, Any]) -> None:
        archive_path = f"{user_id}/{job_id}/model-artifacts.zip"
        bundle_path = f"published/{job_id}/bundle.json"
        self.client.storage.from_("model-artifacts").upload(
            archive_path, archive, {"content-type": "application/zip", "upsert": "true"}
        )
        self.client.storage.from_("model-artifacts").upload(
            bundle_path, bundle, {"content-type": "application/json", "upsert": "true"}
        )
        self.client.table("model_artifacts").insert({
            "user_id": user_id, "training_job_id": job_id,
            "artifact_type": "training_bundle", "storage_path": archive_path,
            "size_bytes": len(archive),
        }).execute()
        self.client.table("published_bundles").insert({
            "training_job_id": job_id, "series_id": series_id,
            "storage_path": bundle_path, "manifest": manifest,
        }).execute()

    def latest_bundle(self) -> dict[str, Any] | None:
        rows = (self.client.table("published_bundles").select("storage_path,training_job_id,series_id")
                .order("created_at", desc=True).limit(1).execute()).data
        if not rows:
            return None
        raw = self.client.storage.from_("model-artifacts").download(rows[0]["storage_path"])
        import json
        payload = json.loads(raw.decode("utf-8"))
        return payload
