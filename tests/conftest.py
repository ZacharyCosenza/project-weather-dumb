import numpy as np
import pandas as pd
import pytest
from xgboost import XGBClassifier

_FEAT_COLS = [
    "ft_nyiso_load_mw", "ft_nyiso_delta_3h",
    "ft_mta_subway", "ft_mta_bus", "ft_mta_lirr",
    "ft_311_heat", "ft_311_flood", "ft_311_snow",
    "ft_crashes_total", "ft_crashes_slippery",
]


@pytest.fixture
def fake_hourly():
    rng = np.random.default_rng(42)
    idx = pd.date_range("2024-01-01", periods=200, freq="h")
    return pd.DataFrame({
        "ft_nyiso_load_mw":    rng.uniform(3000, 8000, 200),
        "ft_nyiso_delta_3h":   rng.uniform(-500,  500, 200),
        "ft_mta_subway":       rng.uniform(1e6,   5e6, 200),
        "ft_mta_bus":          rng.uniform(1e5,   5e5, 200),
        "ft_mta_lirr":         rng.uniform(1e4,   1e5, 200),
        "ft_311_heat":         rng.uniform(0,      500, 200),
        "ft_311_flood":        rng.uniform(0,      100, 200),
        "ft_311_snow":         rng.uniform(0,       50, 200),
        "ft_crashes_total":    rng.uniform(100,    500, 200),
        "ft_crashes_slippery": rng.uniform(0,       50, 200),
    }, index=idx)


def _tiny_xgb(X: pd.DataFrame, n_classes: int) -> XGBClassifier:
    rng = np.random.default_rng(42)
    y = rng.integers(0, n_classes, len(X))
    m = XGBClassifier(
        objective="multi:softprob", num_class=n_classes,
        n_estimators=5, max_depth=2, verbosity=0,
    )
    m.fit(X, y)
    return m


@pytest.fixture
def fake_model_precip(fake_hourly):
    return _tiny_xgb(fake_hourly[_FEAT_COLS], 4)


@pytest.fixture
def fake_model_temp(fake_hourly):
    return _tiny_xgb(fake_hourly[_FEAT_COLS], 3)
