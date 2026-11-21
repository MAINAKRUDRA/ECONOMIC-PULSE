from pathlib import Path

import pandas as pd
import pytest

from packages.ml.ingest_rbi_xlsx import convert_workbook, validate_official_url


def test_rejects_non_rbi_source():
    with pytest.raises(ValueError, match="official RBI"):
        validate_official_url("https://example.com/data.xlsx")


def test_converts_official_monthly_workbook(tmp_path: Path):
    source = tmp_path / "rbi.xlsx"
    pd.DataFrame({
        "Month": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "UPI Volume": [1_000_000, 1_100_000, 1_200_000],
    }).to_excel(source, index=False, sheet_name="UPI")
    output = tmp_path / "upi.csv"

    provenance = convert_workbook(
        source, output,
        source_url="https://rbidocs.rbi.org.in/sample.xlsx",
        sheet_name="UPI",
        period_column="Month",
        value_column="UPI Volume",
        series_id="upi_monthly",
        available_at="2025-04-15T10:00:00+05:30",
    )
    rows = pd.read_csv(output)
    assert list(rows.columns) == ["series_id", "period", "available_at", "revision", "volume_count"]
    assert rows["period"].tolist() == ["2025-01-01", "2025-02-01", "2025-03-01"]
    assert rows["revision"].tolist() == [0, 0, 0]
    assert provenance["row_count"] == 3
    assert output.with_suffix(".provenance.json").exists()


def test_rejects_duplicate_months(tmp_path: Path):
    source = tmp_path / "rbi.xlsx"
    pd.DataFrame({
        "Month": ["2025-01-01", "2025-01-19"],
        "UPI Volume": [100, 101],
    }).to_excel(source, index=False, sheet_name="UPI")
    with pytest.raises(ValueError, match="duplicate months"):
        convert_workbook(
            source, tmp_path / "out.csv",
            source_url="https://www.rbi.org.in/sample.xlsx",
            sheet_name="UPI", period_column="Month",
            value_column="UPI Volume", series_id="upi_monthly",
            available_at="2025-02-15T00:00:00Z",
        )
