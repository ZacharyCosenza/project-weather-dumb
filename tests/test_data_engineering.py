import numpy as np
import pandas as pd

from weather.pipelines.data_engineering.nodes import merge_features

_LAG_MTA      = 3
_LAG_311      = 2
_LAG_CRASHES  = 5
_LAG_WINDOW   = 1


def _nyiso(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({"ft_nyiso_load_mw": rng.uniform(3000, 8000, n)}, index=idx)


def _mta(n: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "ft_mta_subway": rng.uniform(1e6, 5e6, n),
        "ft_mta_bus":    rng.uniform(1e5, 5e5, n),
        "ft_mta_lirr":  rng.uniform(1e4, 1e5, n),
    }, index=idx)


def _openmeteo(n: int = 200) -> pd.DataFrame:
    """Minimal openmeteo stub — same index as _nyiso(), no weather columns."""
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame(index=idx)


def _empty() -> pd.DataFrame:
    """Empty daily DataFrame — for optional sources (MTA, 311, crashes)."""
    return pd.DataFrame()


# ── Schema ─────────────────────────────────────────────────────────────────────

def test_merge_preserves_nyiso_length():
    nyiso = _nyiso()
    result = merge_features(nyiso, _openmeteo(), _empty(), _empty(), _empty(),
                            _LAG_MTA, _LAG_311, _LAG_CRASHES, _LAG_WINDOW)
    assert len(result) == len(nyiso)


def test_merge_produces_delta_column():
    nyiso = _nyiso()
    result = merge_features(nyiso, _openmeteo(), _empty(), _empty(), _empty(),
                            _LAG_MTA, _LAG_311, _LAG_CRASHES, _LAG_WINDOW)
    assert "ft_nyiso_delta_3h" in result.columns


def test_merge_delta_values_correct():
    nyiso = _nyiso()
    result = merge_features(nyiso, _openmeteo(), _empty(), _empty(), _empty(),
                            _LAG_MTA, _LAG_311, _LAG_CRASHES, _LAG_WINDOW)
    expected = nyiso["ft_nyiso_load_mw"].diff(3)
    pd.testing.assert_series_equal(
        result["ft_nyiso_delta_3h"], expected, check_names=False,
    )


def test_merge_empty_optional_sources_no_crash():
    result = merge_features(_nyiso(), _empty(), _empty(), _empty(), _empty(),
                            _LAG_MTA, _LAG_311, _LAG_CRASHES, _LAG_WINDOW)
    assert "ft_nyiso_load_mw" in result.columns


# ── Lag correctness ────────────────────────────────────────────────────────────

def test_mta_lag_shifts_data():
    """MTA values should not appear until lag_days * 24 hours have elapsed."""
    result = merge_features(_nyiso(), _openmeteo(), _mta(), _empty(), _empty(),
                            _LAG_MTA, _LAG_311, _LAG_CRASHES, _LAG_WINDOW)
    lag_hours = _LAG_MTA * 24
    assert result["ft_mta_subway"].iloc[:lag_hours].isna().all(), (
        "MTA values appeared before the lag window"
    )
    assert result["ft_mta_subway"].iloc[lag_hours:].notna().any(), (
        "No MTA values found after the lag window"
    )


def test_mta_columns_all_present():
    result = merge_features(_nyiso(), _openmeteo(), _mta(), _empty(), _empty(),
                            _LAG_MTA, _LAG_311, _LAG_CRASHES, _LAG_WINDOW)
    for col in ("ft_mta_subway", "ft_mta_bus", "ft_mta_lirr"):
        assert col in result.columns
