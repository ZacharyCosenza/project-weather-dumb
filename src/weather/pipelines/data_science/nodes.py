import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score, roc_curve, auc
from sklearn.preprocessing import label_binarize
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

_PRECIP_ORDER = ["clear", "cloudy", "rainy", "snowy"]
_TEMP_ORDER   = ["cold", "temperate", "hot"]
_NAVY, _ORANGE = "#1B3A6B", "#E87722"
_COLORS = {
    "clear": "#F4A460", "cloudy": "#6B8CAE", "rainy": _NAVY, "snowy": "#C5D8EC",
    "cold": _NAVY, "temperate": "#6B9E78", "hot": _ORANGE,
}
_SPLIT_COLORS = {"temporal": _NAVY, "random": _ORANGE}
_DIV_CMAP     = LinearSegmentedColormap.from_list("navy_orange", [_NAVY, "#F5F5F5", _ORANGE])


def _train_xgb(X_tr, y_tr, X_val, y_val, n_cls: int, xgb_params: dict) -> XGBClassifier:
    m = XGBClassifier(objective="multi:softprob", num_class=n_cls, verbosity=0, **xgb_params)
    m.fit(X_tr, y_tr, sample_weight=compute_sample_weight("balanced", y_tr),
          eval_set=[(X_val, y_val)], verbose=False)
    return m


def _compute_metrics(model: XGBClassifier, X: pd.DataFrame, y: pd.Series) -> dict:
    yp = model.predict(X)
    yb = model.predict_proba(X)
    return {
        "accuracy":  round(float(accuracy_score(y, yp)), 4),
        "precision": round(float(precision_score(y, yp, average="weighted", zero_division=0)), 4),
        "recall":    round(float(recall_score(y, yp, average="weighted", zero_division=0)), 4),
        "auc_roc":   round(float(roc_auc_score(y, yb, multi_class="ovr", average="macro")), 4),
    }


def _evaluate(model_precip, model_temp, splits, feat):
    """Returns {split_name: {precip: {...}, temp: {...}}} for all named splits."""
    return {
        name: {
            "precip": _compute_metrics(model_precip, te[feat], te["precip_int"]),
            "temp":   _compute_metrics(model_temp,   te[feat], te["temp_int"]),
        }
        for name, te in splits.items()
    }


def _metrics_figure(model_precip, model_temp, splits, feat, eval_results) -> Figure:
    """2×2 figure: metrics bar chart (left) + OvR ROC curves (right) per target row."""
    metric_names = ["accuracy", "precision", "recall", "auc_roc"]
    targets      = [("precip", model_precip, _PRECIP_ORDER), ("temp", model_temp, _TEMP_ORDER)]
    fig, axes    = plt.subplots(2, 2, figsize=(14, 9))

    for row, (target, model, class_order) in enumerate(targets):
        # ── Metrics bar chart ─────────────────────────────────────────────────
        ax_bar  = axes[row, 0]
        n_splits = len(splits)
        width   = 0.7 / n_splits
        x       = np.arange(len(metric_names))

        for i, (split_name, _) in enumerate(splits.items()):
            vals   = [eval_results[split_name][target][m] for m in metric_names]
            offset = (i - (n_splits - 1) / 2) * width
            bars   = ax_bar.bar(x + offset, vals, width, label=split_name,
                                color=_SPLIT_COLORS.get(split_name, f"C{i}"), alpha=0.85)
            for bar, v in zip(bars, vals):
                ax_bar.text(bar.get_x() + bar.get_width() / 2, v + 0.005,
                            f"{v:.3f}", ha="center", va="bottom", fontsize=8)

        ax_bar.set_xticks(x)
        ax_bar.set_xticklabels([m.replace("_", "\n") for m in metric_names], fontsize=10)
        ax_bar.set_ylim(0, 1.12)
        ax_bar.set_ylabel("Score")
        ax_bar.set_title(f"{target.capitalize()} — Metrics by Split", fontsize=11, fontweight="bold")
        ax_bar.legend(fontsize=9)
        ax_bar.grid(axis="y", alpha=0.3)

        # ── OvR ROC curves (temporal test set) ────────────────────────────────
        ax_roc = axes[row, 1]
        te     = splits["temporal"]
        y_true = te[f"{target}_int"].values
        y_prob = model.predict_proba(te[feat])
        y_bin  = label_binarize(y_true, classes=range(len(class_order)))

        for cls_i, cls_name in enumerate(class_order):
            fpr, tpr, _ = roc_curve(y_bin[:, cls_i], y_prob[:, cls_i])
            auc_val      = auc(fpr, tpr)
            ax_roc.plot(fpr, tpr, label=f"{cls_name}  AUC={auc_val:.2f}",
                        color=_COLORS[cls_name], linewidth=1.8)

        ax_roc.plot([0, 1], [0, 1], "--", color="grey", linewidth=0.8)
        ax_roc.set_xlabel("False Positive Rate")
        ax_roc.set_ylabel("True Positive Rate")
        ax_roc.set_title(f"{target.capitalize()} — OvR ROC (temporal test)", fontsize=11, fontweight="bold")
        ax_roc.legend(fontsize=9)
        ax_roc.grid(alpha=0.2)

    fig.suptitle("Model Evaluation", fontsize=13, fontweight="bold")
    fig.tight_layout()
    plt.close(fig)
    return fig


def _shap_beeswarm(model: XGBClassifier, X: pd.DataFrame, label: str) -> Figure:
    exp = shap.TreeExplainer(model)(X)
    mean_abs = shap.Explanation(
        values        = np.abs(exp.values).mean(-1),
        base_values   = exp.base_values.mean(-1),
        data          = exp.data,
        feature_names = list(X.columns),
    )
    shap.plots.beeswarm(mean_abs, max_display=len(X.columns), color=_DIV_CMAP, show=False)
    plt.title(f"{label} — SHAP Beeswarm (mean |SHAP| across classes)")
    plt.tight_layout()
    fig = plt.gcf()
    plt.close()
    return fig


def plot_eda(hourly_features: pd.DataFrame, feature_cols: list[str]) -> tuple[Figure, Figure, Figure, Figure]:
    proxy_cols = [c for c in feature_cols if c in hourly_features.columns]

    # ── Feature distributions by precip class ─────────────────────────────────
    n_cols = min(3, len(proxy_cols))
    n_rows = (len(proxy_cols) + n_cols - 1) // n_cols
    fig_dist, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
    axes = np.array(axes).flatten()

    n_total = len(hourly_features)
    for ax, col in zip(axes, proxy_cols):
        null_pct = hourly_features[col].isna().sum() / n_total * 100
        groups = [hourly_features.loc[hourly_features["precip"] == c, col].dropna().values
                  for c in _PRECIP_ORDER]
        bp = ax.boxplot(groups, patch_artist=True, widths=0.5,
                        medianprops={"linewidth": 1.5, "color": "white"})
        for patch, cond in zip(bp["boxes"], _PRECIP_ORDER):
            patch.set_facecolor(_COLORS[cond])
            patch.set_alpha(0.85)
        ax.set_xticklabels(_PRECIP_ORDER, fontsize=9)
        ax.set_title(f"{col.replace('_', ' ')}  ({null_pct:.1f}% null)", fontsize=11)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.grid(axis="y", alpha=0.3)

    for ax in axes[len(proxy_cols):]:
        ax.set_visible(False)

    fig_dist.suptitle("Hourly Feature Distributions by Precipitation Class", fontsize=13, fontweight="bold")
    fig_dist.tight_layout()
    plt.close(fig_dist)

    # ── Correlations ──────────────────────────────────────────────────────────
    targets = ["precip_int", "temp_int"]
    corr_df = hourly_features[proxy_cols + targets].dropna()
    corr    = pd.DataFrame({t: corr_df[proxy_cols].corrwith(corr_df[t]) for t in targets})

    fig_corr, ax = plt.subplots(figsize=(5, len(proxy_cols) * 0.8 + 1))
    im = ax.imshow(corr.values, cmap=_DIV_CMAP, vmin=-1, vmax=1, aspect="auto")
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

    # ── Target distributions ───────────────────────────────────────────────────
    fig_targets, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

    precip_counts = hourly_features["precip"].value_counts().reindex(_PRECIP_ORDER).fillna(0)
    ax1.bar(_PRECIP_ORDER, precip_counts.values,
            color=[_COLORS[c] for c in _PRECIP_ORDER], edgecolor="white", linewidth=0.5)
    for i, v in enumerate(precip_counts.values):
        ax1.text(i, v + precip_counts.max() * 0.01, f"{v/len(hourly_features)*100:.1f}%",
                 ha="center", fontsize=10)
    ax1.set_title("Precipitation Class Balance", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Hours")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax1.grid(axis="y", alpha=0.3)

    temp_counts = hourly_features["temp"].value_counts().reindex(_TEMP_ORDER).fillna(0)
    ax2.bar(_TEMP_ORDER, temp_counts.values,
            color=[_COLORS[c] for c in _TEMP_ORDER], edgecolor="white", linewidth=0.5)
    for i, v in enumerate(temp_counts.values):
        ax2.text(i, v + temp_counts.max() * 0.01, f"{v/len(hourly_features)*100:.1f}%",
                 ha="center", fontsize=10)
    ax2.set_title("Temperature Class Balance", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Hours")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax2.grid(axis="y", alpha=0.3)

    fig_targets.suptitle("Target Variable Distributions", fontsize=13, fontweight="bold")
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
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
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
) -> tuple[XGBClassifier, XGBClassifier, Figure, Figure, Figure]:
    feat = [c for c in feature_cols if c in hourly_features.columns]
    df   = hourly_features[feat + ["precip_int", "temp_int"]].dropna(subset=["precip_int", "temp_int"])

    train_end_ts = pd.Timestamp(train_end)
    val_end_ts   = pd.Timestamp(val_end)
    t_tr  = df[df.index <= train_end_ts]
    t_val = df[(df.index > train_end_ts) & (df.index <= val_end_ts)]
    t_te  = df[df.index > val_end_ts]

    model_precip = _train_xgb(t_tr[feat], t_tr["precip_int"], t_val[feat], t_val["precip_int"], 4, xgb)
    model_temp   = _train_xgb(t_tr[feat], t_tr["temp_int"],   t_val[feat], t_val["temp_int"],   3, xgb)

    rs      = xgb.get("random_state", 42)
    splits  = {"temporal": t_te, "random": df.sample(frac=random_test_frac, random_state=rs)}
    results = _evaluate(model_precip, model_temp, splits, feat)

    return (
        model_precip,
        model_temp,
        _metrics_figure(model_precip, model_temp, splits, feat, results),
        _shap_beeswarm(model_precip, t_te[feat], "Precip"),
        _shap_beeswarm(model_temp,   t_te[feat], "Temp"),
    )
