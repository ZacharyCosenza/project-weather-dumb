import logging

import shap
import pandas as pd
from xgboost import XGBRegressor

log = logging.getLogger(__name__)


def run_inference(
    hourly_features: pd.DataFrame,
    model_temp: XGBRegressor,
    feature_cols: list[str],
) -> dict:
    feat   = feature_cols
    latest = hourly_features.reindex(columns=feat).iloc[[-1]]
    ts     = str(latest.index[0])

    log.info("Model Inference Input:\n%s", latest.T)
    if latest.empty:
        log.warning("INFERENCE DATA EMPTY")

    pred_c = float(model_temp.predict(latest)[0])

    # SHAP values shape: (n_samples, n_features) for regression
    exp       = shap.TreeExplainer(model_temp)(latest)
    shap_vals = {col: round(float(exp.values[0, i]), 4)
                 for i, col in enumerate(latest.columns)}

    return {
        "timestamp":   ts,
        "features":    {col: (None if pd.isna(v := latest[col].iloc[0]) else round(float(v), 2))
                        for col in feat},
        "temp": {
            "prediction_c": round(pred_c, 2),
            "prediction_f": round(pred_c * 9 / 5 + 32, 1),
            "shap":         shap_vals,
        },
    }
