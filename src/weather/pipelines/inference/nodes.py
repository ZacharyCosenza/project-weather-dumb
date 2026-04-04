import logging
import math
from datetime import datetime, timezone

import shap
import pandas as pd
from xgboost import XGBClassifier

log = logging.getLogger(__name__)

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
    latest  = hourly_features[feat].iloc[[-1]]
    ts      = str(latest.index[0])

    log.info(f"Model Inference Input: {latest.T}")
    if latest.empty:
        logging.warning("INFERENCE DATA EMPTY")

    return {
        "timestamp": ts,
        "features":  {col: (None if pd.isna(v := latest[col].iloc[0]) else round(float(v), 2)) for col in feat},
        "precip":    _predict_target(model_precip, latest, _PRECIP_ORDER, confidence_thresholds),
        "temp":      _predict_target(model_temp,   latest, _TEMP_ORDER,   confidence_thresholds),
    }