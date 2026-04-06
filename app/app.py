import base64
import json
from pathlib import Path

import streamlit as st

_PREDICTIONS_PATH = Path(__file__).parents[1] / "data/03_primary/predictions.json"
_GIF_DIR          = Path(__file__).parents[1] / "gifs"

_NAVY, _ORANGE = "#1B3A6B", "#E87722"
_GREY_DARK, _GREY_MID, _GREY_LIGHT = "#6B6B6B", "#9E9E9E", "#D4D4D4"

_EMOJIS = {
    "clear": "☀️", "cloudy": "☁️", "rainy": "🌧️", "snowy": "❄️",
    "cold": "🥶", "temperate": "😊", "hot": "🥵",
}
_CONFIDENCE_COLORS = {"high": "#2E7D32", "medium": "#F9A825", "low": "#C62828"}
_CONFIDENCE_LABELS = {"high": "High Confidence", "medium": "Medium Confidence", "low": "Low Confidence"}

# Natural-language labels designed to complete the sentence:
#   "{value} {label} contributing to {pct}% of weather"
_FEATURE_LABELS = {
    "ft_nyiso_load_mw":           "MW of grid load",
    "ft_nyiso_delta_3h":          "MW grid load swing (3h)",
    "ft_mta_subway":              "recent subway riders",
    "ft_mta_bus":                 "recent bus riders",
    "ft_mta_lirr":                "recent LIRR riders",
    "ft_311_heat":                "heat complaints filed",
    "ft_311_snow":                "snow complaints filed",
    "ft_crashes_total":           "recent vehicle crashes",
    "ft_crashes_slippery":        "slippery road crashes",
    "ft_floodnet_events":         "street flood events",
    "ft_floodnet_max_depth_in":   "inches of street flooding",
    "ft_ped_bike":                "recent bike trips",
    "ft_ped_pedestrian":          "pedestrians counted",
    "ft_cz_total":                "congestion zone entries",
    "ft_evictions":               "evictions executed",
    "ft_mets_win_pct":            "Mets win rate",
    "ft_yankees_win_pct":         "Yankees win rate",
    "ft_restaurant_inspections":  "restaurant inspections",
    "ft_restaurant_critical":     "critical violations found",
    "ft_hpd_class_a":             "Class A housing violations",
    "ft_hpd_class_b":             "Class B housing violations",
    "ft_hpd_class_c":             "Class C housing violations",
}

# Feature → video file in /gifs. Features not listed here are excluded from the gif view.
_GIF_MAP = {
    "ft_mta_lirr":               "Amtrak_Snow_mo_Collision.mp4",
    "ft_nyiso_delta_3h":         "power-lines-jump-rope.mp4",
    "ft_mta_subway":             "I_like_trains.mp4",
    "ft_nyiso_load_mw":          "marv.mp4",
    "ft_mta_bus":                "c4mkd087lwlg1.mp4",
    "ft_311_heat":               "frozen-freezing.mp4",
    "ft_311_snow":               "snow-laughing.mp4",
    "ft_crashes_total":          "crash-car.mp4",
    "ft_crashes_slippery":       "slippery-dog.mp4",
    "ft_floodnet_events":        "flood-simpsons.mp4",
    "ft_floodnet_max_depth_in":  "donald-trump-water.mp4",
    "ft_ped_bike":               "dog-cycling.mp4",
    "ft_ped_pedestrian":         "seinfeld-walking.mp4",
    "ft_cz_total":               "speed-trap-police.mp4",
    "ft_evictions":              "broke.mp4",
    "ft_restaurant_inspections": "pizza-hungry.mp4",
    "ft_restaurant_critical":    "spongebob.mp4",
    "ft_mets_win_pct": "let's-go-mets-major-league-baseball.mp4",
    "ft_yankees_win_pct": "yankees-seinfeld.mp4"
}

_GIF_WIDTH_PX  = 220
_GIF_HEIGHT_PX = 160


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_predictions() -> dict:
    if not _PREDICTIONS_PATH.exists():
        st.error("No predictions found. Run `kedro run --pipeline inference` first.")
        st.stop()
    return json.loads(_PREDICTIONS_PATH.read_text())


@st.cache_data
def _video_b64(filename: str) -> str:
    return base64.b64encode((_GIF_DIR / filename).read_bytes()).decode()


def _video_tag(filename: str) -> str:
    b64 = _video_b64(filename)
    return (
        f'<div style="width:{_GIF_WIDTH_PX}px;height:{_GIF_HEIGHT_PX}px;'
        f'overflow:hidden;border-radius:8px;flex-shrink:0;">'
        f'<video width="{_GIF_WIDTH_PX}" height="{_GIF_HEIGHT_PX}" '
        f'style="object-fit:cover;" autoplay loop muted playsinline>'
        f'<source src="data:video/mp4;base64,{b64}" type="video/mp4">'
        f'</video>'
        f'</div>'
    )


def confidence_badge(level: str) -> None:
    color = _CONFIDENCE_COLORS[level]
    st.markdown(
        f'<span style="background:{color};color:white;padding:3px 12px;'
        f'border-radius:12px;font-size:0.85rem;font-weight:600">'
        f'{_CONFIDENCE_LABELS[level]}</span>',
        unsafe_allow_html=True,
    )


def render_prediction(result: dict, title: str) -> None:
    """Prediction label + confidence badge only — no gifs."""
    pred = result["prediction"]
    st.markdown(f"### {title}")
    st.markdown(f"## {_EMOJIS.get(pred, '')} {pred.capitalize()}")
    confidence_badge(result["confidence"])


# ── GIF contribution column ────────────────────────────────────────────────────

def render_gif_contributions(shap_vals: dict, feature_vals: dict) -> None:
    """
    Vertical stack of gif-mapped features sorted by |SHAP| descending.
    Each row: video + sentence "{value} {label} contributing to {pct}% of weather"
    """
    total_abs = sum(abs(v) for v in shap_vals.values()) or 1.0

    gif_features = sorted(
        [(feat, shap_vals[feat]) for feat in _GIF_MAP if feat in shap_vals],
        key=lambda x: abs(x[1]),
        reverse=True,
    )

    if not gif_features:
        return

    blocks = []
    for feat, shap_val in gif_features:
        pct     = abs(shap_val) / total_abs * 100
        label   = _FEATURE_LABELS.get(feat, feat.replace("_", " "))
        raw     = feature_vals.get(feat)
        val_str = "—" if raw is None else f"{raw:,.2f}"
        video   = _video_tag(_GIF_MAP[feat])
        sentence = f"{val_str} {label} contributing to {pct:.1f}% of weather"
        blocks.append(
            f'<div style="display:flex;align-items:flex-start;gap:20px;margin-bottom:20px;">'
            f'  <div style="flex:0 0 {_GIF_WIDTH_PX}px;">{video}</div>'
            f'  <div style="flex:1;padding-top:20px;font-size:1rem;line-height:1.5;">'
            f'    {sentence}'
            f'  </div>'
            f'</div>'
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)


# ── Page ──────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="NYC Weather Nowcast", page_icon="🌆", layout="wide")
st.title("Statistically Irresponsible Nowcast")

if st.button("↻ Refresh"):
    st.rerun()

preds = load_predictions()
st.caption(f"Features current as of: {preds['timestamp']} · Retrain cadence: hourly")

st.divider()

col_precip, col_temp = st.columns(2)
with col_precip:
    render_prediction(preds["precip"], "Precipitation")
with col_temp:
    render_prediction(preds["temp"], "Temperature")

st.divider()

render_gif_contributions(preds["temp"]["shap"], preds["features"])
