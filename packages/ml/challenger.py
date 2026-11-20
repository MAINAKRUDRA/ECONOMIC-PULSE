from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import eligible_training
from .baselines import metrics, predict_baselines
from .features import FEATURES

QUANTILES = (0.10, 0.50, 0.90)


def _model(train, objective="reg:squarederror", alpha=None):
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise RuntimeError("Install requirements-training.txt to run XGBoost") from exc

    kw = dict(
        objective=objective,
        tree_method="hist",
        n_estimators=100,
        max_depth=2,
        learning_rate=0.04,
        min_child_weight=8,
        reg_lambda=10,
        n_jobs=2,
        random_state=42,
    )
    if alpha is not None:
        kw["quantile_alpha"] = alpha
    return XGBRegressor(**kw).fit(train[FEATURES], train["y"])


def pinball(actual, predicted, q):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = actual - predicted
    return float(np.mean(np.maximum(q * error, (q - 1) * error)))


def _count_prediction(anchor, log_change):
    value = float(anchor) * float(np.exp(float(log_change)))
    if not np.isfinite(value) or value <= 0:
        raise ValueError("Model produced a non-finite or non-positive count forecast")
    return value


def _fit_origin(train, test):
    point_model = _model(train)
    quantile_models = {
        q: _model(train, "reg:quantileerror", q) for q in QUANTILES
    }
    point = point_model.predict(test[FEATURES])
    quantiles = {q: model.predict(test[FEATURES]) for q, model in quantile_models.items()}
    baselines = predict_baselines(train, test)

    records = []
    for i, row in enumerate(test.itertuples()):
        anchor = float(row.anchor_count)
        record = {
            "actual": float(row.target_count),
            "xgboost": _count_prediction(anchor, point[i]),
            "q10": _count_prediction(anchor, quantiles[0.10][i]),
            "q50": _count_prediction(anchor, quantiles[0.50][i]),
            "q90": _count_prediction(anchor, quantiles[0.90][i]),
            "flat": float(baselines["flat"][i]),
            "trend": float(baselines["trend"][i]),
            "seasonal": (
                float(baselines["seasonal"][i])
                if np.isfinite(baselines["seasonal"][i])
                else None
            ),
        }
        if not np.isfinite(record["actual"]) or record["actual"] <= 0:
            raise ValueError("Non-finite or non-positive actual count")
        records.append(record)
    return records


def _metric_pair(frame, model_name):
    return metrics(
        frame["actual"].to_numpy(dtype=float),
        frame[model_name].to_numpy(dtype=float),
    )


def validate_challenger(rows: pd.DataFrame, min_train=30, min_validation=12):
    """Evaluate XGBoost against baselines using release-aware expanding origins.

    The most recent 12 target months are reserved from model selection when
    enough history exists. Seasonal comparisons use a common eligible sample.
    """
    rows = rows.sort_values(["origin", "target_period"]).reset_index(drop=True)
    targets = sorted(rows.target_period.unique())
    reserve = set(targets[-12:]) if len(targets) >= min_train + 12 else set()
    dev = rows[~rows.target_period.isin(reserve)] if reserve else rows

    records = []
    skipped_folds = 0
    origins = sorted(dev.origin.unique())
    for origin in origins:
        train = eligible_training(dev, origin)
        test = dev[dev.origin == origin]
        if len(train) < min_train or test.empty:
            continue
        try:
            records.extend(_fit_origin(train, test))
        except (ValueError, RuntimeError, OverflowError, FloatingPointError):
            skipped_folds += 1

    if not records:
        return {
            "status": "insufficient_history",
            "n": 0,
            "promote_xgboost": False,
            "skipped_folds": skipped_folds,
            "reason": "No eligible chronological XGBoost validation folds.",
        }

    df = pd.DataFrame(records)
    core = df.dropna(subset=["xgboost", "flat", "trend"]).copy()
    if core.empty:
        return {
            "status": "insufficient_history",
            "n": 0,
            "promote_xgboost": False,
            "skipped_folds": skipped_folds,
            "reason": "No common finite rows for candidate and baseline comparison.",
        }

    seasonal_common = core.dropna(subset=["seasonal"])
    use_seasonal_for_selection = len(seasonal_common) >= min_validation
    selection = seasonal_common if use_seasonal_for_selection else core
    baseline_names = ["flat", "trend"] + (["seasonal"] if use_seasonal_for_selection else [])
    baseline_metrics = {name: _metric_pair(selection, name) for name in baseline_names}
    xgb_metrics = _metric_pair(selection, "xgboost")
    best_baseline = min(
        baseline_metrics.items(),
        key=lambda item: item[1]["mae"] if item[1]["mae"] is not None else float("inf"),
    )

    interval = core.copy()
    interval_coverage = float(
        ((interval.actual >= np.minimum(interval.q10, interval.q90)) &
         (interval.actual <= np.maximum(interval.q10, interval.q90))).mean()
    )
    crossing = float((interval.q10 > interval.q90).mean())
    interval_width = float(np.mean(np.abs(interval.q90 - interval.q10)))
    interval_ok = (
        len(interval) >= min_validation
        and 0.65 <= interval_coverage <= 0.95
        and crossing <= 0.10
    )
    promote = (
        len(selection) >= min_validation
        and xgb_metrics["mae"] is not None
        and best_baseline[1]["mae"] is not None
        and xgb_metrics["mae"] < best_baseline[1]["mae"]
    )

    # The reserved holdout is evaluated only after selection and never changes it.
    holdout_rows = rows[rows.target_period.isin(reserve)] if reserve else rows.iloc[0:0]
    holdout_records = []
    for origin in sorted(holdout_rows.origin.unique()):
        train = eligible_training(dev, origin)
        test = holdout_rows[holdout_rows.origin == origin]
        if len(train) < min_train or test.empty:
            continue
        try:
            holdout_records.extend(_fit_origin(train, test))
        except (ValueError, RuntimeError, OverflowError, FloatingPointError):
            continue

    final_test = {
        "reserved": bool(reserve),
        "evaluated": bool(holdout_records),
        "n": len(holdout_records),
        "selection_used": False,
        "periods": [str(x) for x in sorted(reserve)],
    }
    if holdout_records:
        hdf = pd.DataFrame(holdout_records)
        final_test["xgboost"] = _metric_pair(hdf, "xgboost")
        final_test["baselines"] = {
            name: _metric_pair(hdf.dropna(subset=[name]), name)
            for name in ("flat", "trend", "seasonal")
            if hdf[name].notna().any()
        }
        final_test["interval"] = {
            "nominal_level": 0.80,
            "coverage": float(
                ((hdf.actual >= np.minimum(hdf.q10, hdf.q90)) &
                 (hdf.actual <= np.maximum(hdf.q10, hdf.q90))).mean()
            ),
            "mean_width": float(np.mean(np.abs(hdf.q90 - hdf.q10))),
            "crossing_rate": float((hdf.q10 > hdf.q90).mean()),
        }

    seasonal_diagnostic = (
        _metric_pair(seasonal_common, "seasonal")
        if not seasonal_common.empty
        else {"n": 0, "mae": None, "rmse": None}
    )
    return {
        "status": "ok",
        "n": int(len(selection)),
        "skipped_folds": skipped_folds,
        "xgboost": xgb_metrics,
        "baselines": baseline_metrics,
        "seasonal_diagnostic": seasonal_diagnostic,
        "baseline_selection_sample": "common_with_seasonal" if use_seasonal_for_selection else "flat_trend_common",
        "best_baseline": best_baseline[0],
        "promote_xgboost": bool(promote),
        "interval": {
            "nominal_level": 0.80,
            "empirical_coverage": interval_coverage,
            "mean_width": interval_width,
            "crossing_rate": crossing,
            "calibration_adequate": bool(interval_ok),
            "pinball_q10": pinball(core.actual, core.q10, 0.10),
            "pinball_q50": pinball(core.actual, core.q50, 0.50),
            "pinball_q90": pinball(core.actual, core.q90, 0.90),
        },
        "final_test": final_test,
    }


def fit_final_models(train):
    return {
        "point": _model(train),
        "q10": _model(train, "reg:quantileerror", 0.10),
        "q50": _model(train, "reg:quantileerror", 0.50),
        "q90": _model(train, "reg:quantileerror", 0.90),
    }
