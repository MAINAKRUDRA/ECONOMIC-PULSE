"""Convert an RBI-published monthly workbook into the Economic Pulse vintage CSV contract.

This adapter deliberately does not guess which table/row is UPI total volume.
An operator selects the RBI workbook, worksheet, date/value columns and the
actual RBI publication timestamp. That keeps provenance auditable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

RBI_HOSTS = {"rbi.org.in", "www.rbi.org.in", "rbidocs.rbi.org.in"}
RBI_SOURCE_PAGE = "https://rbi.org.in/scripts/Statistics.aspx"
REQUIRED_OUTPUT = ["series_id", "period", "available_at", "revision", "volume_count"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in RBI_HOSTS:
        raise ValueError("Source URL must use HTTPS on an official RBI host")


def convert_workbook(
    source_file: str | Path,
    output_file: str | Path,
    *,
    source_url: str,
    sheet_name: str,
    period_column: str,
    value_column: str,
    series_id: str,
    available_at: str,
) -> dict:
    validate_official_url(source_url)
    if not series_id.strip() or series_id.startswith("demo_"):
        raise ValueError("A non-demo series_id is required")
    released = pd.Timestamp(available_at)
    if released.tzinfo is None:
        released = released.tz_localize("UTC")
    else:
        released = released.tz_convert("UTC")

    source = Path(source_file)
    frame = pd.read_excel(source, sheet_name=sheet_name, engine="openpyxl")
    missing = [c for c in (period_column, value_column) if c not in frame.columns]
    if missing:
        raise ValueError(f"Workbook is missing selected columns: {missing}")

    periods = pd.to_datetime(frame[period_column], errors="coerce")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    if periods.isna().any() or values.isna().any():
        raise ValueError("Selected period/value columns contain blank or invalid rows")
    if not np.isfinite(values.to_numpy(dtype=float)).all() or (values <= 0).any():
        raise ValueError("UPI transaction volume must be positive and finite")

    normalized_periods = periods.dt.to_period("M").dt.to_timestamp()
    if normalized_periods.duplicated().any():
        raise ValueError("Selected workbook rows contain duplicate months; select an aggregate total row/column")
    if (normalized_periods.dt.tz_localize("UTC") > released).any():
        raise ValueError("Publication timestamp cannot precede a reference month")

    output = pd.DataFrame({
        "series_id": series_id.strip(),
        "period": normalized_periods.dt.strftime("%Y-%m-01"),
        "available_at": released.isoformat(),
        "revision": 0,
        "volume_count": values.astype(float),
    }).sort_values("period")
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)

    provenance = {
        "source_name": "Reserve Bank of India",
        "source_url": source_url,
        "source_file": source.name,
        "source_sha256": sha256_file(source),
        "source_page": RBI_SOURCE_PAGE,
        "sheet_name": sheet_name,
        "period_column": period_column,
        "value_column": value_column,
        "available_at": released.isoformat(),
        "revision_policy": "revision 0 represents the selected published snapshot; re-ingest later revisions as separate vintages",
        "row_count": int(len(output)),
        "series_id": series_id.strip(),
        "unit": "transactions",
    }
    destination.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="RBI XLSX workbook downloaded from an official RBI page")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-url", required=True, help="Exact HTTPS RBI download URL")
    parser.add_argument("--sheet", required=True, dest="sheet_name")
    parser.add_argument("--period-column", required=True)
    parser.add_argument("--value-column", required=True)
    parser.add_argument("--series-id", default="upi_monthly")
    parser.add_argument("--available-at", required=True, help="Actual RBI publication timestamp, e.g. 2026-08-15T10:00:00+05:30")
    args = parser.parse_args()
    print(json.dumps(convert_workbook(
        args.input, args.output, source_url=args.source_url,
        sheet_name=args.sheet_name, period_column=args.period_column,
        value_column=args.value_column, series_id=args.series_id,
        available_at=args.available_at,
    ), indent=2))


if __name__ == "__main__":
    main()
