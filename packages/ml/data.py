from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

REQUIRED = ["series_id", "period", "available_at", "revision", "volume_count"]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_vintages(path: str | Path) -> pd.DataFrame:
    """Load and strictly validate first-release/revision observations.

    Keep every vintage. Feature construction selects only vintages that were
    available at a forecast origin, while training labels use the first release.
    """
    raw = pd.read_csv(path)
    missing = sorted(set(REQUIRED) - set(raw.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    raw = raw[REQUIRED].copy()
    if raw["series_id"].isna().any():
        raise ValueError("series_id cannot be empty")
    raw["series_id"] = raw["series_id"].astype(str).str.strip()
    if raw["series_id"].eq("").any():
        raise ValueError("series_id cannot be empty")

    raw["period"] = pd.to_datetime(raw["period"], utc=True, errors="coerce")
    raw["available_at"] = pd.to_datetime(raw["available_at"], utc=True, errors="coerce")
    if raw[["period", "available_at"]].isna().any().any():
        raise ValueError("Invalid timestamps")
    if (raw["period"].dt.day != 1).any():
        raise ValueError("period must be first day of reference month")
    if (raw["available_at"] < raw["period"]).any():
        raise ValueError("available_at precedes reference period")

    revision = pd.to_numeric(raw["revision"], errors="raise")
    if not revision.map(lambda value: pd.notna(value) and float(value).is_integer()).all():
        raise ValueError("revision must contain finite integers")
    raw["revision"] = revision.astype("int64")
    if (raw["revision"] < 0).any():
        raise ValueError("revision cannot be negative")

    raw["volume_count"] = pd.to_numeric(raw["volume_count"], errors="raise")
    values = raw["volume_count"].to_numpy(dtype=float)
    if not (pd.notna(values).all() and (values > 0).all() and __import__("numpy").isfinite(values).all()):
        raise ValueError("volume_count must be positive and finite")

    if raw.duplicated(["series_id", "period", "available_at", "revision"]).any():
        raise ValueError("Duplicate vintage")

    return raw.sort_values(
        ["series_id", "period", "available_at", "revision"]
    ).reset_index(drop=True)


def month_start(ts):
    return pd.Timestamp(year=ts.year, month=ts.month, day=1, tz="UTC")
