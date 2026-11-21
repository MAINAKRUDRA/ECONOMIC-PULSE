"""Build an auditable evidence report for every Economic Pulse model version."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _window(values: list[str]) -> dict[str, Any]:
    clean = sorted(str(value) for value in values if value)
    return {"start": clean[0] if clean else None, "end": clean[-1] if clean else None,
            "observations": len(clean)}


def _errors(records: list[dict], prediction_key: str) -> dict[str, Any]:
    pairs = []
    for row in records:
        actual, predicted = row.get("actual"), row.get(prediction_key)
        if actual is None or predicted is None:
            continue
        try:
            actual, predicted = float(actual), float(predicted)
        except (TypeError, ValueError):
            continue
        if actual <= 0 or predicted != predicted:
            continue
        pairs.append((actual, predicted))
    if not pairs:
        return {"n": 0, "mae": None, "rmse": None, "mape_pct": None, "smape_pct": None}
    errors = [predicted - actual for actual, predicted in pairs]
    absolute = [abs(error) for error in errors]
    mape = [abs(error) / abs(actual) * 100 for (actual, _), error in zip(pairs, errors)]
    smape = [
        200 * abs(predicted - actual) / (abs(actual) + abs(predicted))
        for actual, predicted in pairs if abs(actual) + abs(predicted) > 0
    ]
    return {
        "n": len(pairs),
        "mae": sum(absolute) / len(absolute),
        "rmse": (sum(error * error for error in errors) / len(errors)) ** 0.5,
        "mape_pct": sum(mape) / len(mape),
        "smape_pct": sum(smape) / len(smape) if smape else None,
    }


def build_evidence_report(backtest: dict, challenger: dict, manifest: dict) -> dict:
    """Create transparent evaluation metadata; never synthesize missing metrics."""
    folds = backtest.get("folds") or []
    validation_origins = [str(fold.get("origin")) for fold in folds if fold.get("origin")]
    holdout = (challenger.get("final_test") or {})
    holdout_periods = holdout.get("periods") or []
    data_mode = manifest.get("mode", "unknown")
    is_real = data_mode == "research"
    records = []
    for fold in folds:
        actuals = fold.get("actual") or []
        predictions = fold.get("predictions") or {}
        for index, actual in enumerate(actuals):
            row = {"actual": actual}
            for name, values in predictions.items():
                if index < len(values):
                    row[name] = values[index]
            records.append(row)
    validation_metrics = {
        name: _errors(records, name)
        for name in ("flat", "trend", "seasonal")
        if any(name in row for row in records)
    }
    challenger_metrics = {
        "xgboost": challenger.get("xgboost"),
        "baselines": challenger.get("baselines", {}),
        "best_baseline": challenger.get("best_baseline"),
        "promote_xgboost": bool(challenger.get("promote_xgboost", False)),
    }
    holdout_metrics = {}
    if holdout.get("evaluated"):
        holdout_metrics = {
            "xgboost": holdout.get("xgboost"),
            "baselines": holdout.get("baselines", {}),
            "interval": holdout.get("interval"),
        }
    limitations = list(manifest.get("limitations") or [])
    limitations.extend([
        "Forecasts are experimental research outputs and are not investment, policy or official-statistics advice.",
        "UPI transaction activity is not GDP, GDP growth, inflation or a comprehensive measure of economic output.",
        "Source-domain allowlisting checks URL provenance only; it does not independently authenticate the uploaded file.",
        "Metrics describe the recorded chronological evaluation sample and may not generalize to future regimes.",
    ])
    if not is_real:
        limitations.append("Synthetic data validates software and pipeline behaviour only; it provides no evidence of real-world forecast skill.")
    if not holdout.get("evaluated"):
        limitations.append("A reserved final holdout was not evaluated; out-of-sample performance remains unverified.")
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_classification": "real_official_source_claimed" if is_real else "synthetic",
        "source": {
            "name": manifest.get("source_name"),
            "url": manifest.get("source_url"),
            "rights_tag": manifest.get("rights_tag"),
            "sha256": manifest.get("data_sha256"),
            "authentication": "Source URL domain allowlisted; uploaded file authenticity not independently verified.",
        },
        "series": {
            "id": manifest.get("series_id"),
            "unit": manifest.get("unit"),
            "forecast_scope": "Monthly UPI transaction activity only; not GDP.",
        },
        "sample": {
            "training_rows": manifest.get("training_rows"),
            "training_cutoff": manifest.get("training_cutoff"),
            "validation_origins": _window(validation_origins),
            "reserved_holdout": {
                "periods": holdout_periods,
                "window": _window(holdout_periods),
                "evaluated": bool(holdout.get("evaluated")),
                "n": holdout.get("n", 0),
                "selection_used": bool(holdout.get("selection_used", False)),
            },
        },
        "metrics": {
            "chronological_baselines": validation_metrics,
            "challenger_comparison": challenger_metrics,
            "reserved_holdout": holdout_metrics,
        },
        "interval_diagnostics": challenger.get("interval", {}),
        "limitations": list(dict.fromkeys(limitations)),
        "publication": {
            "status": "experimental",
            "accuracy_claim": None,
            "decision_grade": False,
            "reason": "No universal accuracy claim is made; inspect the exact series, windows, baselines and holdout evidence.",
        },
    }
