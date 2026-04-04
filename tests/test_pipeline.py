"""
Integration tests — exercise the real pipeline functions end-to-end on small data.

    pytest tests/test_pipeline.py -v

test_data_engineering makes live API calls (~30 days). It is slow on first run
(networks) but fast on repeat runs once requests_cache warms up.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from weather.pipelines.data_engineering.nodes import fetch_raw, merge_features
from weather.pipelines.data_science.nodes import train_and_evaluate
from weather.pipelines.inference.nodes import run_inference

# ── Shared constants ──────────────────────────────────────────────────────────

_NYC_LAT, _NYC_LON = 40.7128, -74.0060
_COLD_C,  _HOT_C   = 4.44, 26.67

_FEATURE_COLS = [
    "ft_nyiso_load_mw", "ft_nyiso_delta_3h",
    "ft_mta_subway", "ft_mta_bus", "ft_mta_lirr",
    "ft_311_heat", "ft_311_flood", "ft_311_snow",
    "ft_crashes_total", "ft_crashes_slippery",
    "ft_floodnet_events", "ft_floodnet_max_depth_in",
    "ft_ped_bike", "ft_ped_pedestrian",
    "ft_cz_total", "ft_evictions",
]

_XGB_FAST   = {"n_estimators": 10, "max_depth": 2, "learning_rate": 0.1, "random_state": 42}
_THRESHOLDS = {"high": 0.7, "medium": 0.4}

_PRECIP_CLASSES = {"clear", "cloudy", "rainy", "snowy"}
_TEMP_CLASSES   = {"cold", "temperate", "hot"}


# ── 1. data_engineering ───────────────────────────────────────────────────────

def test_data_engineering():
    """fetch_raw (30-day window) + merge_features → valid hourly DataFrame."""
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=30)).isoformat()

    raws   = fetch_raw(
        start_date=start, end_date=end,
        nyc_lat=_NYC_LAT, nyc_lon=_NYC_LON,
        cold_c=_COLD_C, hot_c=_HOT_C,
    )
    hourly = merge_features(
        *raws,
        mta_lag=3, lag_311=2, crashes_lag=5,
        floodnet_lag=2, bike_ped_lag=1, cz_lag=21,
        evictions_lag=2, lag_window=1,
    )

    assert len(hourly) > 0,                       "merge_features returned empty DataFrame"
    assert "ft_nyiso_load_mw"   in hourly.columns, "missing NYISO load column"
    assert "ft_nyiso_delta_3h"  in hourly.columns, "missing NYISO delta column"
    assert hourly.index.is_monotonic_increasing,   "index is not sorted"
    assert not hourly.index.duplicated().any(),     "duplicate timestamps in output"


# ── 2. data_science ───────────────────────────────────────────────────────────

def _synthetic_hourly(n: int = 3000) -> pd.DataFrame:
    """Synthetic hourly_features with ground-truth labels."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2022-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "ft_nyiso_load_mw":         rng.uniform(3000, 8000, n),
        "ft_nyiso_delta_3h":        rng.uniform(-500,  500, n),
        "ft_mta_subway":            rng.uniform(1e6,   5e6, n),
        "ft_mta_bus":               rng.uniform(1e5,   5e5, n),
        "ft_mta_lirr":              rng.uniform(1e4,   1e5, n),
        "ft_311_heat":              rng.uniform(0,     500, n),
        "ft_311_flood":             rng.uniform(0,     100, n),
        "ft_311_snow":              rng.uniform(0,      50, n),
        "ft_crashes_total":         rng.uniform(100,   500, n),
        "ft_crashes_slippery":      rng.uniform(0,      50, n),
        "ft_floodnet_events":       rng.uniform(0,       5, n),
        "ft_floodnet_max_depth_in": rng.uniform(0,      10, n),
        "ft_ped_bike":              rng.uniform(0,    5000, n),
        "ft_ped_pedestrian":        rng.uniform(0,   10000, n),
        "ft_cz_total":              rng.uniform(0,  100000, n),
        "ft_evictions":             rng.uniform(0,      20, n),
        "tgt_precip_int":           rng.integers(0, 4, n),
        "tgt_temp_int":             rng.integers(0, 3, n),
    }, index=idx)


def test_data_science():
    """train_and_evaluate returns two trained models that can produce probabilities."""
    hourly = _synthetic_hourly()

    model_precip, model_temp, *figs = train_and_evaluate(
        hourly,
        feature_cols=_FEATURE_COLS,
        xgb=_XGB_FAST,
        train_end="2022-03-15",
        val_end="2022-04-01",
        random_test_frac=0.1,
        train_subsample_frac=1.0,
    )

    row = hourly[_FEATURE_COLS].iloc[[-1]]
    assert model_precip.predict_proba(row).shape == (1, 4)
    assert model_temp.predict_proba(row).shape   == (1, 3)


# ── 3. inference ──────────────────────────────────────────────────────────────

def test_inference():
    """run_inference produces a valid predictions dict from synthetic features + models."""
    hourly = _synthetic_hourly()

    model_precip, model_temp, *_ = train_and_evaluate(
        hourly,
        feature_cols=_FEATURE_COLS,
        xgb=_XGB_FAST,
        train_end="2022-03-15",
        val_end="2022-04-01",
        random_test_frac=0.1,
        train_subsample_frac=1.0,
    )
    result = run_inference(hourly, model_precip, model_temp, _FEATURE_COLS, _THRESHOLDS)

    assert {"timestamp", "features", "precip", "temp"} <= result.keys()
    assert result["precip"]["prediction"] in _PRECIP_CLASSES
    assert result["temp"]["prediction"]   in _TEMP_CLASSES
    assert result["precip"]["confidence"] in {"high", "medium", "low"}
    assert abs(sum(result["precip"]["probabilities"].values()) - 1.0) < 1e-3
    assert abs(sum(result["temp"]["probabilities"].values())   - 1.0) < 1e-3
    assert set(result["precip"]["shap"].keys()) == set(_FEATURE_COLS)
