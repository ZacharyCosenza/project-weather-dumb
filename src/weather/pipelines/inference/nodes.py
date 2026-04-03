import math
from datetime import datetime, timezone

import shap
import pandas as pd
from xgboost import XGBClassifier

_PRECIP_ORDER = ["clear", "cloudy", "rainy", "snowy"]
_TEMP_ORDER   = ["cold", "temperate", "hot"]


def _predict_target(
    model: XGBClassifier,
    X: pd.DataFrame,
    class_order: list[str],
    thresholds: dict,
) -> dict:
    probs    = model.predict_proba(X)[0]
    pred_idx = int(probs.argmax())
    prob     = float(probs[pred_idx])

    confidence = (
        "high"   if prob >= thresholds["high"]   else
        "medium" if prob >= thresholds["medium"]  else
        "low"
    )

    # SHAP for the predicted class only
    exp        = shap.TreeExplainer(model)(X)
    shap_vals  = {col: round(float(exp.values[0, i, pred_idx]), 4)
                  for i, col in enumerate(X.columns)}

    return {
        "prediction":    class_order[pred_idx],
        "confidence":    confidence,
        "probability":   round(prob, 4),
        "probabilities": {c: round(float(p), 4) for c, p in zip(class_order, probs)},
        "shap":          shap_vals,
    }


def run_inference(
    hourly_features: pd.DataFrame,
    model_precip: XGBClassifier,
    model_temp: XGBClassifier,
    feature_cols: list[str],
    confidence_thresholds: dict,
) -> dict:
    feat    = [c for c in feature_cols if c in hourly_features.columns]
    latest  = hourly_features[feat].dropna().iloc[[-1]]
    ts      = str(latest.index[0])

    return {
        "timestamp": ts,
        "features":  {col: round(float(latest[col].iloc[0]), 2) for col in feat},
        "precip":    _predict_target(model_precip, latest, _PRECIP_ORDER, confidence_thresholds),
        "temp":      _predict_target(model_temp,   latest, _TEMP_ORDER,   confidence_thresholds),
    }


def run_qc(predictions: dict, feature_cols: list[str]) -> dict:
    """Annotate predictions with QC check results before writing to disk.

    Checks
    ------
    timestamp_age_h   : hours since the feature timestamp. Warn >12h, fail >48h.
    feature_coverage  : fraction of expected feature_cols present in the output.
    prob_sum          : probability mass for each target (should be ~1.0).
    shap_finite       : all SHAP values are finite numbers.
    """
    checks: dict[str, dict] = {}

    # 1. Timestamp age
    ts = datetime.fromisoformat(predictions["timestamp"]).replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    checks["timestamp_age_h"] = {
        "value":  round(age_h, 1),
        "status": "pass" if age_h <= 12 else ("warn" if age_h <= 48 else "fail"),
    }

    # 2. Feature coverage
    present = set(predictions.get("features", {}).keys())
    expected = set(feature_cols)
    coverage = len(present & expected) / len(expected) if expected else 1.0
    checks["feature_coverage"] = {
        "value":   round(coverage, 4),
        "missing": sorted(expected - present),
        "status":  "pass" if coverage == 1.0 else ("warn" if coverage >= 0.8 else "fail"),
    }

    # 3. Probability sums
    prob_checks = {}
    for target in ("precip", "temp"):
        total = sum(predictions[target]["probabilities"].values())
        prob_checks[target] = {
            "value":  round(total, 4),
            "status": "pass" if abs(total - 1.0) < 0.01 else "fail",
        }
    checks["prob_sum"] = prob_checks

    # 4. SHAP finiteness
    shap_ok = all(
        math.isfinite(v)
        for target in ("precip", "temp")
        for v in predictions[target]["shap"].values()
    )
    checks["shap_finite"] = {"status": "pass" if shap_ok else "fail"}

    # Overall
    all_statuses = (
        [checks["timestamp_age_h"]["status"],
         checks["feature_coverage"]["status"],
         checks["shap_finite"]["status"]]
        + [checks["prob_sum"][t]["status"] for t in ("precip", "temp")]
    )
    overall = "fail" if "fail" in all_statuses else ("warn" if "warn" in all_statuses else "pass")

    return {**predictions, "qc": {"overall": overall, "checks": checks}}
