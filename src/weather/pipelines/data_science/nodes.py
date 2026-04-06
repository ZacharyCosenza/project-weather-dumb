import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

_NAVY, _ORANGE = "#1B3A6B", "#E87722"
_GREY_DARK, _GREY_MID, _GREY_LIGHT = "#6B6B6B", "#9E9E9E", "#D4D4D4"
_SPLIT_COLORS = {"temporal": _NAVY, "random": _ORANGE}
_DIV_CMAP     = LinearSegmentedColormap.from_list("navy_orange", [_NAVY, "#F5F5F5", _ORANGE])


def _train_xgb(X_tr, y_tr, X_val, y_val, xgb_params: dict) -> XGBRegressor:
    m = XGBRegressor(objective="reg:squarederror", verbosity=0, **xgb_params)
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    return m


def _compute_metrics(model: XGBRegressor, X: pd.DataFrame, y: pd.Series) -> dict:
    yp = model.predict(X)
    return {
        "rmse": round(float(mean_squared_error(y, yp) ** 0.5), 4),
        "mae":  round(float(mean_absolute_error(y, yp)), 4),
        "r2":   round(float(r2_score(y, yp)), 4),
    }


def _evaluate(model_temp, splits, feat):
    return {
        name: _compute_metrics(model_temp, te[feat], te["tgt_temp_c"])
        for name, te in splits.items()
    }


def _metrics_figure(model_temp, splits, feat, eval_results) -> Figure:
    """Bar chart of RMSE / MAE / R² across splits."""
    metric_names = ["rmse", "mae", "r2"]
    fig, ax = plt.subplots(figsize=(8, 5))

    n_splits = len(splits)
    width    = 0.7 / n_splits
    x        = np.arange(len(metric_names))

    for i, (split_name, _) in enumerate(splits.items()):
        vals   = [eval_results[split_name][m] for m in metric_names]
        offset = (i - (n_splits - 1) / 2) * width
        bars   = ax.bar(x + offset, vals, width, label=split_name,
                        color=_SPLIT_COLORS.get(split_name, f"C{i}"), alpha=0.85)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + abs(v) * 0.02,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(["RMSE (°C)", "MAE (°C)", "R²"], fontsize=11)
    ax.set_title("Temperature Regression — Metrics by Split", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    plt.close(fig)
    return fig


def _shap_beeswarm(model: XGBRegressor, X: pd.DataFrame) -> Figure:
    # For regression, exp.values shape is (n_samples, n_features) — no per-class loop needed.
    exp = shap.TreeExplainer(model)(X)
    shap.plots.beeswarm(exp, max_display=len(X.columns), color=_DIV_CMAP, show=False)
    plt.title("Temperature — SHAP Feature Importance", fontsize=12, fontweight="bold")
    plt.tight_layout()
    fig = plt.gcf()
    plt.close(fig)
    return fig


def plot_eda(hourly_features: pd.DataFrame, feature_cols: list[str]) -> tuple[Figure, Figure, Figure, Figure]:
    proxy_cols = feature_cols
    hourly_features = hourly_features.reindex(columns=proxy_cols + ["tgt_temp_c"])

    # ── Feature correlations with temperature ─────────────────────────────────
    n_cols = min(3, len(proxy_cols))
    n_rows = (len(proxy_cols) + n_cols - 1) // n_cols
    fig_dist, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
    axes = np.array(axes).flatten()

    n_total = len(hourly_features)
    for ax, col in zip(axes, proxy_cols):
        null_pct = hourly_features[col].isna().sum() / n_total * 100
        subset = hourly_features[[col, "tgt_temp_c"]].dropna()
        ax.scatter(subset[col], subset["tgt_temp_c"],
                   alpha=0.05, s=1, color=_NAVY)
        ax.set_xlabel(col.replace("_", " "), fontsize=9)
        ax.set_ylabel("Temp (°C)", fontsize=9)
        ax.set_title(f"{col.replace('_', ' ')}  ({null_pct:.1f}% null)", fontsize=10)
        ax.grid(alpha=0.2)

    for ax in axes[len(proxy_cols):]:
        ax.set_visible(False)

    fig_dist.suptitle("Feature vs. Temperature (°C)", fontsize=13, fontweight="bold")
    fig_dist.tight_layout()
    plt.close(fig_dist)

    # ── Correlations ──────────────────────────────────────────────────────────
    full = hourly_features[proxy_cols + ["tgt_temp_c"]]
    corr = pd.DataFrame(
        {"tgt_temp_c": {col: full[[col, "tgt_temp_c"]].dropna().corr().loc[col, "tgt_temp_c"]
                        for col in proxy_cols}}
    )

    fig_corr, ax = plt.subplots(figsize=(3, len(proxy_cols) * 0.8 + 1))
    im = ax.imshow(corr.values, cmap=_DIV_CMAP, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks([0])
    ax.set_yticks(range(len(proxy_cols)))
    ax.set_xticklabels(["temp (°C)"], fontsize=10)
    ax.set_yticklabels(proxy_cols, fontsize=10)
    for i in range(len(proxy_cols)):
        ax.text(0, i, f"{corr.values[i, 0]:.2f}", ha="center", va="center", fontsize=11)
    plt.colorbar(im, ax=ax, fraction=0.06, pad=0.04)
    ax.set_title("Feature × Target Correlations (Pearson r)", fontsize=12, fontweight="bold", pad=10)
    fig_corr.tight_layout()
    plt.close(fig_corr)

    # ── Target distribution (histogram of temperatures) ───────────────────────
    fig_targets, ax = plt.subplots(figsize=(7, 4))
    temp_vals = hourly_features["tgt_temp_c"].dropna()
    ax.hist(temp_vals, bins=60, color=_NAVY, alpha=0.8, edgecolor="white", linewidth=0.3)
    ax.set_xlabel("Temperature (°C)", fontsize=11)
    ax.set_ylabel("Hours", fontsize=11)
    ax.set_title("Temperature Distribution", fontsize=12, fontweight="bold")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", alpha=0.3)
    fig_targets.tight_layout()
    plt.close(fig_targets)

    # ── Features over time ─────────────────────────────────────────────────────
    n_cols = min(3, len(proxy_cols))
    n_rows = (len(proxy_cols) + n_cols - 1) // n_cols
    fig_time, axes_t = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 3 * n_rows), sharex=True)
    axes_t = np.array(axes_t).flatten()

    for ax, col in zip(axes_t, proxy_cols):
        s = hourly_features[col].dropna()
        ax.plot(s.index, s.values, linewidth=0.4, alpha=0.7, color=_NAVY)
        ax.set_title(col.replace("_", " "), fontsize=10)
        val_range = s.max() - s.min() if len(s) > 1 else 1
        fmt = ".3f" if val_range < 2 else ",.0f"
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _, fmt=fmt: f"{v:{fmt}}"))
        ax.grid(alpha=0.2)

    for ax in axes_t[len(proxy_cols):]:
        ax.set_visible(False)

    fig_time.suptitle("Features Over Time", fontsize=13, fontweight="bold")
    fig_time.autofmt_xdate()
    fig_time.tight_layout()
    plt.close(fig_time)

    return fig_dist, fig_corr, fig_targets, fig_time


def train_and_evaluate(
    hourly_features: pd.DataFrame,
    feature_cols: list[str],
    xgb: dict,
    train_end: str,
    val_end: str,
    random_test_frac: float,
    train_subsample_frac: float = 1.0,
) -> tuple[XGBRegressor, Figure, Figure]:
    feat = feature_cols
    df   = hourly_features.reindex(columns=feat + ["tgt_temp_c"]).dropna(subset=["tgt_temp_c"])

    train_end_ts = pd.Timestamp(train_end)
    val_end_ts   = pd.Timestamp(val_end)
    t_tr  = df[df.index <= train_end_ts]
    t_val = df[(df.index > train_end_ts) & (df.index <= val_end_ts)]
    t_te  = df[df.index > val_end_ts]

    rs = xgb.get("random_state", 42)
    if train_subsample_frac < 1.0:
        t_tr = t_tr.sample(frac=train_subsample_frac, random_state=rs)

    model_temp = _train_xgb(t_tr[feat], t_tr["tgt_temp_c"], t_val[feat], t_val["tgt_temp_c"], xgb)

    splits  = {"temporal": t_te, "random": df.sample(frac=random_test_frac, random_state=rs)}
    results = _evaluate(model_temp, splits, feat)

    return (
        model_temp,
        _metrics_figure(model_temp, splits, feat, results),
        _shap_beeswarm(model_temp, t_te[feat]),
    )
