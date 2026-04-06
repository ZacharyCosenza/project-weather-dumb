"""
Pipeline integration tests — each stage consumes the previous stage's output.

    pytest tests/test_pipeline.py -v

Fixtures are session-scoped: data_engineering runs once and its output flows
into data_science, which flows into inference. If data_engineering fails all
downstream tests are skipped automatically.
"""
import json
from datetime import date, timedelta

import pytest

from weather.pipelines.data_engineering.nodes import fetch_raw, merge_features
from weather.pipelines.data_science.nodes import train_and_evaluate
from weather.pipelines.inference.nodes import run_inference

# ── Constants ─────────────────────────────────────────────────────────────────

_NYC_LAT, _NYC_LON = 40.7128, -74.0060
_COLD_C,  _HOT_C   = 4.44, 26.67

_FEATURE_COLS = [
    "ft_nyiso_load_mw", "ft_nyiso_delta_3h",
    "ft_mta_subway", "ft_mta_bus", "ft_mta_lirr",
    "ft_311_heat", "ft_311_snow",
    "ft_crashes_total", "ft_crashes_slippery",
    "ft_floodnet_events", "ft_floodnet_max_depth_in",
    "ft_ped_bike", "ft_ped_pedestrian",
    "ft_cz_total", "ft_evictions",
    "ft_mets_win_pct", "ft_yankees_win_pct",
    "ft_restaurant_inspections", "ft_restaurant_critical",
    "ft_hpd_class_a", "ft_hpd_class_b", "ft_hpd_class_c",
]

_XGB_FAST   = {"n_estimators": 10, "max_depth": 2, "learning_rate": 0.1, "random_state": 42}
_THRESHOLDS = {"high": 0.7, "medium": 0.4}

_PRECIP_CLASSES = {"clear", "cloudy", "rainy", "snowy"}
_TEMP_CLASSES   = {"cold", "temperate", "hot"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def hourly():
    """30-day real fetch → merged features. Runs once; shared by all tests."""
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=365)).isoformat()
    raws  = fetch_raw(
        start_date=start, end_date=end,
        nyc_lat=_NYC_LAT, nyc_lon=_NYC_LON,
        cold_c=_COLD_C, hot_c=_HOT_C,
    )
    return merge_features(
        *raws,
        mta_lag=3, lag_311=2, crashes_lag=5,
        floodnet_lag=2, bike_ped_lag=1, cz_lag=21,
        evictions_lag=2, restaurant_lag=3, hpd_lag=3,
        lag_window=1,
    )


@pytest.fixture(scope="session")
def models(hourly):
    """Train on the real hourly data. Fast XGB params; splits within the 30-day window."""
    train_end = (date.today() - timedelta(days=15)).isoformat()
    val_end   = (date.today() - timedelta(days=7)).isoformat()
    model_precip, model_temp, *_ = train_and_evaluate(
        hourly,
        feature_cols=_FEATURE_COLS,
        xgb=_XGB_FAST,
        train_end=train_end,
        val_end=val_end,
        random_test_frac=0.1,
        train_subsample_frac=1.0,
    )
    return model_precip, model_temp


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_data_engineering(hourly):
    assert len(hourly) > 0,                       "merge_features returned empty DataFrame"
    assert "ft_nyiso_load_mw"  in hourly.columns, "missing NYISO load column"
    assert "ft_nyiso_delta_3h" in hourly.columns, "missing NYISO delta column"
    assert hourly.index.is_monotonic_increasing,  "index is not sorted"
    assert not hourly.index.duplicated().any(),    "duplicate timestamps in output"


def test_data_science(models):
    model_precip, model_temp = models
    assert model_precip.n_features_in_ > 0
    assert model_temp.n_features_in_   > 0


def test_inference(hourly, models):
    model_precip, model_temp = models
    result = run_inference(hourly, model_precip, model_temp, _FEATURE_COLS, _THRESHOLDS)

    assert {"timestamp", "features", "precip", "temp"} <= result.keys()
    assert result["precip"]["prediction"] in _PRECIP_CLASSES
    assert result["temp"]["prediction"]   in _TEMP_CLASSES
    assert result["precip"]["confidence"] in {"high", "medium", "low"}
    assert abs(sum(result["precip"]["probabilities"].values()) - 1.0) < 1e-3
    assert abs(sum(result["temp"]["probabilities"].values())   - 1.0) < 1e-3
    assert set(result["precip"]["shap"].keys()) == set(_FEATURE_COLS)


def test_predictions_schema():
    """predictions.json on disk matches the schema the app expects."""
    with open("data/03_primary/predictions.json") as f:
        p = json.load(f)

    assert "timestamp" in p
    assert "precip"    in p
    assert "temp"      in p

    for target in ("precip", "temp"):
        assert "prediction"   in p[target]
        assert "confidence"   in p[target]
        assert "probabilities" in p[target]
        assert "shap"         in p[target]
        assert abs(sum(p[target]["probabilities"].values()) - 1.0) < 1e-3
