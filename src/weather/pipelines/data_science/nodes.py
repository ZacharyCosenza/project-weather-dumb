import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from matplotlib.figure import Figure
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

_PRECIP_ORDER = ["clear", "cloudy", "rainy", "snowy"]
_TEMP_ORDER   = ["cold", "temperate", "hot"]
_COLORS       = {"clear": "#F4C842", "cloudy": "#8FA8C8", "rainy": "#3A7FC1", "snowy": "#B8D4E8",
                 "cold": "#3A7FC1", "temperate": "#7FC47F", "hot": "#E8613A"}


def _train_xgb(X_tr, y_tr, X_val, y_val, n_cls: int, xgb_params: dict) -> XGBClassifier:
    m = XGBClassifier(objective="multi:softprob", num_class=n_cls, verbosity=0, **xgb_params)
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    return m


def _metrics(model: XGBClassifier, X: pd.DataFrame, y: pd.Series, label: str) -> dict:
    yp = model.predict(X)
    yb = model.predict_proba(X)
    return {
        f"{label}_accuracy":  round(float(accuracy_score(y, yp)), 4),
        f"{label}_precision": round(float(precision_score(y, yp, average="weighted", zero_division=0)), 4),
        f"{label}_recall":    round(float(recall_score(y, yp, average="weighted", zero_division=0)), 4),
        f"{label}_auc_roc":   round(float(roc_auc_score(y, yb, multi_class="ovr", average="macro")), 4),
    }


def _shap_beeswarm(model: XGBClassifier, X: pd.DataFrame, label: str) -> Figure:
    exp = shap.TreeExplainer(model)(X)
    mean_abs = shap.Explanation(
        values        = np.abs(exp.values).mean(-1),
        base_values   = exp.base_values.mean(-1),
        data          = exp.data,
        feature_names = list(X.columns),
    )
    shap.plots.beeswarm(mean_abs, max_display=len(X.columns), show=False)
    plt.title(f"{label} — SHAP Beeswarm (mean |SHAP| across classes)")
    plt.tight_layout()
    fig = plt.gcf()
    plt.close()
    return fig


def plot_eda(hourly_features: pd.DataFrame, feature_cols: list[str]) -> tuple[Figure, Figure]:
    proxy_cols = [c for c in feature_cols if c in hourly_features.columns]

    # ── Distributions ─────────────────────────────────────────────────────────
    n_cols = min(3, len(proxy_cols))
    n_rows = (len(proxy_cols) + n_cols - 1) // n_cols
    fig_dist, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
    axes = np.array(axes).flatten()

    for ax, col in zip(axes, proxy_cols):
        groups = [hourly_features.loc[hourly_features["precip"] == c, col].dropna().values
                  for c in _PRECIP_ORDER]
        bp = ax.boxplot(groups, patch_artist=True, widths=0.5,
                        medianprops={"linewidth": 1.5, "color": "black"})
        for patch, cond in zip(bp["boxes"], _PRECIP_ORDER):
            patch.set_facecolor(_COLORS[cond])
            patch.set_alpha(0.7)
        ax.set_xticklabels(_PRECIP_ORDER, fontsize=9)
        ax.set_title(col.replace("_", " "), fontsize=11)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.grid(axis="y", alpha=0.3)

    for ax in axes[len(proxy_cols):]:
        ax.set_visible(False)

    fig_dist.suptitle("Hourly Feature Distributions by Precipitation Class", fontsize=13, fontweight="bold")
    fig_dist.tight_layout()
    plt.close(fig_dist)

    # ── Correlations ──────────────────────────────────────────────────────────
    targets = ["precip_int", "temp_int"]
    corr_df = hourly_features[proxy_cols + targets].dropna().copy()
    corr = pd.DataFrame({t: corr_df[proxy_cols].corrwith(corr_df[t]) for t in targets})

    fig_corr, ax = plt.subplots(figsize=(5, len(proxy_cols) * 0.8 + 1))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(2))
    ax.set_yticks(range(len(proxy_cols)))
    ax.set_xticklabels(["precip\n(clear→snowy)", "temp\n(cold→hot)"], fontsize=10)
    ax.set_yticklabels(proxy_cols, fontsize=10)
    for i in range(len(proxy_cols)):
        for j in range(2):
            ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=11)
    plt.colorbar(im, ax=ax, fraction=0.06, pad=0.04)
    ax.set_title("Feature × Target Correlations (Pearson r)", fontsize=12, fontweight="bold", pad=10)
    fig_corr.tight_layout()
    plt.close(fig_corr)

    return fig_dist, fig_corr


def train_and_evaluate(
    hourly_features: pd.DataFrame,
    feature_cols: list[str],
    xgb: dict,
    test_size: float,
    val_split: float,
) -> tuple[XGBClassifier, XGBClassifier, dict, Figure, Figure]:
    feat = [c for c in feature_cols if c in hourly_features.columns]
    df   = hourly_features[feat + ["precip_int", "temp_int"]].dropna()

    X = df[feat]
    rs = xgb.get("random_state", 42)
    X_tr, X_tmp, yp_tr, yp_tmp, yt_tr, yt_tmp = train_test_split(
        X, df["precip_int"], df["temp_int"], test_size=test_size, random_state=rs,
    )
    X_val, X_te, yp_val, yp_te, yt_val, yt_te = train_test_split(
        X_tmp, yp_tmp, yt_tmp, test_size=val_split, random_state=rs,
    )

    model_precip = _train_xgb(X_tr, yp_tr, X_val, yp_val, n_cls=4, xgb_params=xgb)
    model_temp   = _train_xgb(X_tr, yt_tr, X_val, yt_val, n_cls=3, xgb_params=xgb)

    metrics = {
        **_metrics(model_precip, X_te, yp_te, "precip"),
        **_metrics(model_temp,   X_te, yt_te, "temp"),
        "precip_best_iter": int(model_precip.best_iteration),
        "temp_best_iter":   int(model_temp.best_iteration),
    }

    return (
        model_precip,
        model_temp,
        metrics,
        _shap_beeswarm(model_precip, X_te, "Precip"),
        _shap_beeswarm(model_temp,   X_te, "Temp"),
    )
