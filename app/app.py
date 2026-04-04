import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import streamlit as st

_PREDICTIONS_PATH = Path(__file__).parents[1] / "data/03_primary/predictions.json"

_NAVY, _ORANGE = "#1B3A6B", "#E87722"
_GREY_DARK, _GREY_MID, _GREY_LIGHT = "#6B6B6B", "#9E9E9E", "#D4D4D4"

_PRECIP_COLORS = {
    "clear": "#F4A460", "cloudy": _GREY_MID, "rainy": _NAVY, "snowy": _GREY_LIGHT,
}
_TEMP_COLORS = {
    "cold": _NAVY, "temperate": _GREY_DARK, "hot": _ORANGE,
}
_EMOJIS = {
    "clear": "☀️", "cloudy": "☁️", "rainy": "🌧️", "snowy": "❄️",
    "cold": "🥶", "temperate": "😊", "hot": "🥵",
}
_CONFIDENCE_COLORS = {"high": "#2E7D32", "medium": "#F9A825", "low": "#C62828"}

# Feature labels for matplotlib charts (no emoji — matplotlib can't render them)
_FEATURE_LABELS = {
    "ft_nyiso_load_mw":    "NYISO Zone J Grid Load (MW)",
    "ft_nyiso_delta_3h":   "NYISO Zone J Load Change, 3-hour (MW)",
    "ft_mta_subway":       "NYC Subway Ridership (3-day lag)",
    "ft_mta_bus":          "NYC Bus Ridership (3-day lag)",
    "ft_mta_lirr":         "LIRR Ridership (3-day lag)",
    "ft_311_heat":         "311 Heat/Hot Water Complaints (2-day lag)",
    "ft_311_flood":        "311 Flood Complaints (2-day lag)",
    "ft_311_snow":         "311 Snow Complaints (2-day lag)",
    "ft_crashes_total":       "Motor Vehicle Crashes, Total (5-day lag)",
    "ft_crashes_slippery":    "Motor Vehicle Crashes, Slippery Pavement (5-day lag)",
    "ft_floodnet_events":     "Street Flood Events, Count (2-day lag)",
    "ft_floodnet_max_depth_in": "Street Flood Max Depth, inches (2-day lag)",
    "ft_ped_bike":            "DOT Bike Count, Citywide Sensors (1-day lag)",
    "ft_ped_pedestrian":      "DOT Pedestrian Count, Citywide Sensors (1-day lag)",
    "ft_cz_total":            "Congestion Zone Entries, Total (21-day lag)",
    "ft_evictions":           "NYC Evictions Executed (2-day lag)",
    "ft_dot_speed_avg":       "DOT Traffic Speed Average, mph (1-day lag)",
    "ft_dot_speed_delta":     "DOT Traffic Speed Day-over-Day Change, mph (1-day lag)",
}

_CONFIDENCE_LABELS = {"high": "High Confidence", "medium": "Medium Confidence", "low": "Low Confidence"}


def load_predictions() -> dict:
    if not _PREDICTIONS_PATH.exists():
        st.error("No predictions found. Run `kedro run --pipeline inference` first.")
        st.stop()
    return json.loads(_PREDICTIONS_PATH.read_text())


def confidence_badge(level: str) -> None:
    color = _CONFIDENCE_COLORS[level]
    st.markdown(
        f'<span style="background:{color};color:white;padding:3px 12px;'
        f'border-radius:12px;font-size:0.85rem;font-weight:600">{_CONFIDENCE_LABELS[level]}</span>',
        unsafe_allow_html=True,
    )


_CHART_SIZE = (3, 1.4)


def shap_chart(prediction: str, shap_vals: dict, pred_color: str) -> plt.Figure:
    """Stacked bar chart: one row per feature, positive SHAP stacked right of zero,
    negative stacked left. The predicted class label anchors the chart title."""
    items    = sorted(shap_vals.items(), key=lambda x: abs(x[1]), reverse=True)
    labels   = [_FEATURE_LABELS.get(k, k.replace("_", " ")) for k, _ in items]
    vals     = [v for _, v in items]
    pos_vals = [max(v, 0) for v in vals]
    neg_vals = [min(v, 0) for v in vals]

    fig, ax = plt.subplots(figsize=_CHART_SIZE)
    y = np.arange(len(labels))

    ax.barh(y, pos_vals, color=_ORANGE, edgecolor="white", linewidth=0.4, label="pushes toward")
    ax.barh(y, neg_vals, color=_NAVY,   edgecolor="white", linewidth=0.4, label="pushes away")

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel(f"SHAP contribution toward '{prediction}'")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    return fig


def render_target(result: dict, colors: dict) -> None:
    pred = result["prediction"]
    st.markdown(f"### {_EMOJIS.get(pred, '')} {pred.capitalize()}")
    confidence_badge(result["confidence"])
    st.pyplot(shap_chart(pred, result["shap"], colors.get(pred, _GREY_MID)),
              use_container_width=True)


# ── Page ──────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="NYC Weather Nowcast", page_icon="🌆", layout="wide")
st.title("🌆 NYC Weather Nowcast")

if st.button("↻ Refresh"):
    st.rerun()

preds = load_predictions()
st.caption(f"Features current as of: {preds['timestamp']} · Retrain cadence: hourly")

st.divider()

st.subheader("Current Feature Values")
feature_table = pd.DataFrame([
    {"Feature": _FEATURE_LABELS.get(k, k), "Value": "—" if v is None else f"{v:,.2f}"}
    for k, v in preds["features"].items()
])
st.dataframe(feature_table, hide_index=True, use_container_width=False)
st.divider()

render_target(preds["precip"], _PRECIP_COLORS)
st.divider()
render_target(preds["temp"], _TEMP_COLORS)
