"""Small service-role Supabase REST client; never expose the service key to browsers."""
from __future__ import annotations

import os
from urllib.parse import quote

import httpx
from fastapi import HTTPException


class SupabaseStore:
    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")
        self.client = httpx.Client(timeout=45.0)

    def headers(self, extra: dict | None = None) -> dict:
        result = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if extra:
            result.update(extra)
        return result

    def verify_user(self, access_token: str) -> dict:
        response = self.client.get(
            f"{self.url}/auth/v1/user",
            headers={"apikey": self.key, "Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="A valid Supabase session is required")
        return response.json()

    def select(self, table: str, params: dict) -> list[dict]:
        response = self.client.get(f"{self.url}/rest/v1/{table}", params=params, headers=self.headers())
        response.raise_for_status()
        return response.json()

    def insert(self, table: str, payload: dict) -> dict:
        response = self.client.post(
            f"{self.url}/rest/v1/{table}", json=payload,
            headers=self.headers({"Prefer": "return=representation"}),
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else {}

    def upsert(self, table: str, payload: dict, on_conflict: str) -> dict:
        response = self.client.post(
            f"{self.url}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            json=payload,
            headers=self.headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else {}

    def update(self, table: str, filters: dict, payload: dict) -> list[dict]:
        response = self.client.patch(
            f"{self.url}/rest/v1/{table}", params=filters, json=payload,
            headers=self.headers({"Prefer": "return=representation"}),
        )
        response.raise_for_status()
        return response.json()

    def upload(self, bucket: str, path: str, content: bytes, content_type: str) -> None:
        encoded = quote(path, safe="/")
        response = self.client.post(
            f"{self.url}/storage/v1/object/{bucket}/{encoded}",
            content=content,
            headers=self.headers({"Content-Type": content_type, "x-upsert": "false"}),
        )
        response.raise_for_status()

    def download(self, bucket: str, path: str) -> bytes:
        encoded = quote(path, safe="/")
        response = self.client.get(
            f"{self.url}/storage/v1/object/{bucket}/{encoded}", headers=self.headers()
        )
        response.raise_for_status()
        return response.content

    def close(self) -> None:
        self.client.close()
