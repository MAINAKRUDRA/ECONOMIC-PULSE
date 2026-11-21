from packages.ml.evidence import build_evidence_report


def test_evidence_report_labels_synthetic_and_never_claims_accuracy():
    report = build_evidence_report(
        {"status": "ok", "folds": [{
            "origin": "2024-01-01T00:00:00Z",
            "target_periods": ["2024-02", "2024-03"],
            "actual": [100, 110],
            "predictions": {"flat": [95, 105], "trend": [102, 112]},
        }]},
        {"status": "insufficient_history", "n": 0, "promote_xgboost": False,
         "final_test": {"reserved": True, "evaluated": False, "periods": ["2024-04"]}},
        {"mode": "synthetic", "series_id": "demo_upi", "unit": "transaction_count",
         "training_rows": 24, "training_cutoff": "2024-03-31T00:00:00Z",
         "limitations": ["Synthetic fixture only."]},
    )
    assert report["data_classification"] == "synthetic"
    assert report["publication"]["accuracy_claim"] is None
    assert report["publication"]["decision_grade"] is False
    assert report["sample"]["validation_target_periods"]["start"] == "2024-02"
    assert report["metrics"]["chronological_baselines"]["flat"]["mae"] == 5
    assert report["metrics"]["chronological_baselines"]["flat"]["mape_pct"] is not None
    assert any("not GDP" in item for item in report["limitations"])
    assert any("Synthetic data" in item for item in report["limitations"])


def test_evidence_report_preserves_real_source_claim_and_missing_holdout():
    report = build_evidence_report(
        {"folds": []},
        {"final_test": {"evaluated": False, "periods": []}},
        {"mode": "research", "series_id": "upi_monthly", "source_name": "RBI",
         "source_url": "https://rbi.org.in/data.csv", "rights_tag": "public",
         "data_sha256": "abc", "limitations": []},
    )
    assert report["data_classification"] == "real_official_source_claimed"
    assert report["source"]["sha256"] == "abc"
    assert report["publication"]["accuracy_claim"] is None
    assert any("authenticity" in item for item in report["limitations"])
    assert any("holdout was not evaluated" in item for item in report["limitations"])
