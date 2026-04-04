import pandas as pd
import pytest

from weather.pipelines.inference.nodes import run_inference

_PRECIP_CLASSES = {"clear", "cloudy", "rainy", "snowy"}
_TEMP_CLASSES   = {"cold", "temperate", "hot"}
_THRESHOLDS     = {"high": 0.7, "medium": 0.4}


def _run(fake_hourly, fake_model_precip, fake_model_temp, extra_cols=()):
    feature_cols = list(fake_hourly.columns) + list(extra_cols)
    return run_inference(
        fake_hourly, fake_model_precip, fake_model_temp,
        feature_cols, _THRESHOLDS,
    )


# ── Output schema ───────────────────────────────────────────────────────────────

def test_output_has_required_keys(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    assert {"timestamp", "features", "precip", "temp"} <= result.keys()


def test_precip_prediction_is_valid_class(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    assert result["precip"]["prediction"] in _PRECIP_CLASSES


def test_temp_prediction_is_valid_class(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    assert result["temp"]["prediction"] in _TEMP_CLASSES


def test_confidence_is_valid_bucket(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    for target in ("precip", "temp"):
        assert result[target]["confidence"] in ("high", "medium", "low")


def test_probabilities_sum_to_one(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    for target in ("precip", "temp"):
        total = sum(result[target]["probabilities"].values())
        assert abs(total - 1.0) < 1e-3, f"{target} probabilities sum to {total}"


def test_shap_keys_match_features(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    expected_feat = set(fake_hourly.columns)
    for target in ("precip", "temp"):
        assert set(result[target]["shap"].keys()) == expected_feat


# ── Row selection ───────────────────────────────────────────────────────────────

def test_uses_most_recent_non_null_row(fake_hourly, fake_model_precip, fake_model_temp):
    result = _run(fake_hourly, fake_model_precip, fake_model_temp)
    assert result["timestamp"] == str(fake_hourly.index[-1])


def test_uses_last_row_regardless_of_nans(fake_hourly, fake_model_precip, fake_model_temp):
    """Inference always uses the most recent row, even if it contains NaN features."""
    df = fake_hourly.copy()
    df.iloc[-5:] = float("nan")
    result = _run(df, fake_model_precip, fake_model_temp)
    assert result["timestamp"] == str(df.index[-1])


# ── Feature filtering ───────────────────────────────────────────────────────────

def test_unknown_feature_cols_are_ignored(fake_hourly, fake_model_precip, fake_model_temp):
    """feature_cols entries not present in the DataFrame should be silently dropped."""
    result = _run(fake_hourly, fake_model_precip, fake_model_temp,
                  extra_cols=["ft_does_not_exist"])
    assert result["precip"]["prediction"] in _PRECIP_CLASSES
