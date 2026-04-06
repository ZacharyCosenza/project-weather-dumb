import base64
import json
from pathlib import Path

import streamlit as st

_PREDICTIONS_PATH = Path(__file__).parents[1] / "data/03_primary/predictions.json"
_GIF_DIR          = Path(__file__).parents[1] / "gifs"

_NAVY, _ORANGE = "#1B3A6B", "#E87722"
_GREY_DARK, _GREY_MID, _GREY_LIGHT = "#6B6B6B", "#9E9E9E", "#D4D4D4"

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
    "ft_restaurant_critical":     "critical health violations",
    "ft_hpd_class_a":             "minor housing violations (Class A: cosmetic, non-hazardous)",
    "ft_hpd_class_b":             "hazardous housing violations (Class B: pests, leaks, no hot water)",
    "ft_hpd_class_c":             "emergency housing violations (Class C: no heat, lead paint, active rodents)",
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
    "ft_mets_win_pct":           "let's-go-mets-major-league-baseball.mp4",
    "ft_yankees_win_pct":        "yankees-seinfeld.mp4",
}

_GIF_WIDTH_PX  = 220
_GIF_HEIGHT_PX = 160


def _H(s: str) -> str:
    """Highlight the causal phrase in orange."""
    return f'<span style="color:{_ORANGE};font-weight:bold">{s}</span>'


def _temp_bucket(temp_f: float) -> str:
    if temp_f >= 75:
        return "hot"
    if temp_f >= 50:
        return "moderate"
    return "cold"


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


# ── GIF contribution column ────────────────────────────────────────────────────

def _caption(feat: str, val: str, up: bool, bucket: str) -> str:
    """Return a plausible-sounding (but incorrect) causal explanation for a feature × direction × temp bucket."""
    c = {
        "ft_nyiso_load_mw": {
            ("hot",      True):  f"At {val} MW, {_H('resistive heat loss across Con Ed transmission lines')} is measurably warming the air above the grid",
            ("hot",      False): f"At {val} MW the grid is running at peak efficiency — {_H('reduced waste heat escaping from distribution infrastructure')} is keeping temps in check",
            ("moderate", True):  f"{val} MW of Zone J load means {_H('transformer stations citywide are emitting waste heat')} into the surrounding urban canopy",
            ("moderate", False): f"At {val} MW, {_H('underground cable insulation is containing heat')} that would otherwise reach street level",
            ("cold",     True):  f"{val} MW of winter heating load means {_H('combustion exhaust from building boilers')} is venting into the atmosphere citywide",
            ("cold",     False): f"The grid is drawing {val} MW — {_H('large-scale electromagnetic induction is pulling thermal energy')} away from the surrounding environment",
        },
        "ft_nyiso_delta_3h": {
            ("hot",      True):  f"A {val} MW surge in 3h indicates {_H('mass AC activation across the boroughs — each unit pumps exhaust heat outdoors')}",
            ("hot",      False): f"A {val} MW 3h drop means {_H('AC units are cycling off, reducing the rooftop exhaust heat')} that normally accumulates in urban canyons",
            ("moderate", True):  f"A {val} MW swing corresponds to {_H('widespread heating system activation, venting combustion exhaust')} into the lower atmosphere",
            ("moderate", False): f"A {val} MW load reduction indicates {_H('commercial HVAC systems shutting down, cutting their street-level heat output')} significantly",
            ("cold",     True):  f"The {val} MW grid increase signals {_H('heating boilers cycling on across the boroughs, releasing combustion heat')} through poorly insulated envelopes",
            ("cold",     False): f"A {val} MW drop indicates {_H('large industrial consumers going offline, reducing their thermal emissions')} to the surrounding air",
        },
        "ft_mta_subway": {
            ("hot",      True):  f"{val} subway trips generate sufficient {_H('braking friction and body heat that it is measurably venting through street grates')} across Manhattan",
            ("hot",      False): f"With {val} riders underground, {_H('body heat is being contained below grade')} rather than radiating to street level",
            ("moderate", True):  f"Heat from train motors and {val} commuters is {_H('rising through ventilation shafts and warming the street-level air mass')}",
            ("moderate", False): f"{val} underground commuters are {_H('acting as a distributed heat sink, absorbing thermal energy')} before it reaches the surface",
            ("cold",     True):  f"Regenerative braking across {val} trips is {_H('converting kinetic energy to heat that vents through platform exhaust systems')}",
            ("cold",     False): f"The tunnel system is {_H('displacing surface air downward through {val} rider-cycles of ventilation')}, drawing warmth underground",
        },
        "ft_mta_bus": {
            ("hot",      True):  f"{val} bus trips have {_H('deposited combustion exhaust at street level — diesel engines run at over 1,400°F internally')}",
            ("hot",      False): f"With {val} trips completed, {_H('hybrid fleet regenerative braking is recovering heat rather than releasing it')} to the environment",
            ("moderate", True):  f"Stop-and-start operation across {val} bus trips {_H('releases disproportionate exhaust heat — idling engines run richly and waste fuel as heat')}",
            ("moderate", False): f"{val} trips on CNG buses {_H('produce lower combustion temperatures than diesel, measurably reducing street-level heat output')}",
            ("cold",     True):  f"The thermal output of {val} bus engines {_H('idling at stops is raising the immediate street-level temperature')} in surrounding blocks",
            ("cold",     False): f"{val} electric-mode bus trips are {_H('producing near-zero exhaust heat, allowing ambient temperatures to fall')} without interference",
        },
        "ft_mta_lirr": {
            ("hot",      True):  f"{val} LIRR boardings mean {_H('third-rail sparking and brake pad friction on the Ronkonkoma Line are raising Right-of-Way temperatures')}",
            ("hot",      False): f"Sealed LIRR cars carrying {val} riders are {_H('acting as thermal containers, preventing body heat from exchanging with the open atmosphere')}",
            ("moderate", True):  f"Third-rail heating elements activated across {val} LIRR trips are {_H('elevating Right-of-Way temperatures that bleed into adjacent Queens neighborhoods')}",
            ("moderate", False): f"{val} riders in climate-controlled cars are {_H('removing body heat from the open atmosphere between Jamaica and Penn Station')}",
            ("cold",     True):  f"Diesel locomotive exhaust from the {val}-trip service east of Jamaica is {_H('contributing measurable combustion heat to the regional air mass')}",
            ("cold",     False): f"{val} sealed LIRR cars are {_H('functioning as thermal insulators, preventing rider body heat from mixing with outdoor air')}",
        },
        "ft_311_heat": {
            ("hot",      True):  f"{val} overheating complaints confirm {_H('building boilers running above threshold — excess heat is radiating through facades')} citywide",
            ("hot",      False): f"{val} complaints suggest landlords have moderated systems — {_H('reduced boiler output is cutting building envelope heat loss')} across the city",
            ("moderate", True):  f"{val} inadequate-heat complaints confirm {_H('combustion systems running at capacity and radiating heat through poorly insulated brick facades')}",
            ("moderate", False): f"{val} inadequate-heat complaints confirm boilers are underperforming — {_H('reduced combustion output means less ambient heat escaping into the street')}",
            ("cold",     True):  f"Despite {val} complaints, the boilers generating them are {_H('still releasing combustion heat through uninsulated walls into surrounding blocks')}",
            ("cold",     False): f"{val} complaints confirm heating systems are offline — {_H('unheated buildings are acting as passive thermal sinks')}, absorbing heat from the surrounding air",
        },
        "ft_311_snow": {
            ("hot",      True):  f"{val} snow complaints indicate recent precipitation that has since melted — {_H('the latent heat released during the ice-to-water phase change')} is warming the air",
            ("hot",      False): f"{val} complaints indicate residual snowpack that is {_H('absorbing incoming solar radiation through sublimation rather than allowing it to warm the surface')}",
            ("moderate", True):  f"Snow generating {val} complaints is actively melting — {_H('the exothermic phase transition releases latent heat')} into the surrounding air mass",
            ("moderate", False): f"The snowpack behind {val} complaints has high albedo — {_H('it is reflecting incoming solar radiation before it can warm ground-level surfaces')}",
            ("cold",     True):  f"Ice confirmed by {val} complaints is slowly melting — {_H('the gradual release of latent heat of fusion')} is warming the surrounding air",
            ("cold",     False): f"The snowpack responsible for {val} complaints is {_H('functioning as a persistent heat sink, locking away thermal energy in its crystalline structure')}",
        },
        "ft_crashes_total": {
            ("hot",      True):  f"{val} crashes have created secondary congestion — {_H('idling vehicles produce 40% more exhaust heat per minute than free-flowing traffic')}",
            ("hot",      False): f"Emergency response to {val} crashes {_H('has cleared major corridors, dissipating the idling vehicle heat')} that normally accumulates in urban canyons",
            ("moderate", True):  f"{val} accidents have induced stop-and-go conditions — {_H('each idling engine contributes disproportionately to the urban heat island effect')}",
            ("moderate", False): f"Traffic diversions from {val} crashes have {_H('redistributed vehicle heat load away from dense canyon corridors')}, allowing dispersion",
            ("cold",     True):  f"Secondary congestion from {val} crashes is {_H('concentrating engine exhaust heat in enclosed street canyons')} where it cannot dissipate",
            ("cold",     False): f"Road closures from {val} crashes have {_H('reduced vehicle density on key corridors, allowing trapped radiant heat to escape')} to the upper atmosphere",
        },
        "ft_crashes_slippery": {
            ("hot",      True):  f"{val} wet-pavement crashes indicate standing water — {_H('evaporation from solar-heated wet asphalt is releasing latent heat')} into the air",
            ("hot",      False): f"{val} crashes confirm standing water that is {_H('absorbing incoming solar radiation, preventing surface warming')} through evaporative cooling",
            ("moderate", True):  f"Kinetic energy converted to heat in {val} tire-slip events is {_H('contributing to localized road surface warming through friction')}",
            ("moderate", False): f"{val} crashes confirm ice coverage — {_H('ice\'s high specific heat capacity means it absorbs energy without raising air temperature')}",
            ("cold",     True):  f"Friction heat from {val} skid events on icy roads is {_H('gradually raising road surface temperatures through mechanical energy conversion')}",
            ("cold",     False): f"{val} crashes confirm ice that formed as temperatures dropped — {_H('a self-reinforcing albedo feedback loop is sustaining the cooling')}",
        },
        "ft_floodnet_events": {
            ("hot",      True):  f"{val} flood events have created solar-heated standing water — {_H('as it warms and evaporates it releases stored thermal energy')} into the lower atmosphere",
            ("hot",      False): f"Evaporation from {val} active flood sites is {_H('drawing latent heat from the surrounding air mass')} through evaporative cooling",
            ("moderate", True):  f"{val} FloodNet activations confirm warm standing water that is {_H('releasing stored solar energy back to the atmosphere through convection')}",
            ("moderate", False): f"{val} flood events have saturated urban surfaces — {_H('evaporative cooling from active water bodies')} is measurably reducing ambient temperature",
            ("cold",     True):  f"Warm stormwater in {val} active sites is {_H('releasing stored heat through convection as it drains through the underground system')}",
            ("cold",     False): f"{val} flood events have introduced cold precipitation water to street level — {_H('thermal exchange with the cooler water is drawing heat from the surrounding air')}",
        },
        "ft_floodnet_max_depth_in": {
            ("hot",      True):  f"At {val} inches, standing water has {_H('absorbed sufficient solar radiation to function as a heat reservoir, re-radiating stored warmth')}",
            ("hot",      False): f"At {val} inches, the water column represents {_H('a significant heat sink absorbing solar energy rather than allowing it to warm the air')}",
            ("moderate", True):  f"{val} inches of flood water has high specific heat capacity — {_H('it has absorbed and is now slowly releasing stored solar energy')} to the atmosphere",
            ("moderate", False): f"The {val}-inch depth provides {_H('sufficient thermal mass to absorb ambient heat through conduction, cooling the surrounding air')}",
            ("cold",     True):  f"{val} inches of standing water retains heat from the sewer infrastructure below — {_H('warmer than ambient air, it is convecting heat upward')}",
            ("cold",     False): f"At {val} inches, cold precipitation water has {_H('significant thermal contact with street-level air, conducting heat away from the surface')}",
        },
        "ft_ped_bike": {
            ("hot",      True):  f"{val} cycling trips represent approximately {_H('300W of metabolic output per rider dissipating directly into the open air')}",
            ("hot",      False): f"{val} cyclists in motion are {_H('creating continuous convective airflow that displaces warmer surface air upward')}",
            ("moderate", True):  f"Metabolic heat from {val} active cyclists is {_H('contributing to the urban heat island through direct thermal radiation at street level')}",
            ("moderate", False): f"Convective cooling from {val} cyclists moving through city streets is {_H('creating localized airflow that draws heat away from ground-level surfaces')}",
            ("cold",     True):  f"At {val} trips, cyclists are generating {_H('sufficient metabolic heat (~300W each) to measurably warm their immediate microclimate')}",
            ("cold",     False): f"The windchill effect created by {val} cyclists in motion is {_H('enhancing convective heat loss from surrounding building surfaces through forced convection')}",
        },
        "ft_ped_pedestrian": {
            ("hot",      True):  f"{val} pedestrians each radiate approximately {_H('100W of body heat that accumulates in the enclosed geometry of Manhattan\'s street canyons')}",
            ("hot",      False): f"The airflow displacement from {val} moving pedestrians is {_H('creating convective currents that draw warmer air upward out of street-level canyons')}",
            ("moderate", True):  f"{val} people outdoors are {_H('collectively emitting body heat that is trapped by the thermal geometry of the city grid')}",
            ("moderate", False): f"{val} pedestrians in motion are {_H('inducing sufficient air circulation to draw cooler air down from above the street canopy')}",
            ("cold",     True):  f"At {val} pedestrians, {_H('combined body heat output is measurably elevating temperature in enclosed street-level canyons')}",
            ("cold",     False): f"Mechanical turbulence from {val} pedestrians walking is {_H('enhancing forced convection along building surfaces, accelerating heat loss')}",
        },
        "ft_cz_total": {
            ("hot",      True):  f"{val} vehicles in the Central Business District have {_H('deposited exhaust gases that trap radiant heat in Midtown\'s dense urban canyon geometry')}",
            ("hot",      False): f"With only {val} CRZ entries, {_H('exhaust heat accumulation in Midtown\'s canyons is below the threshold for measurable warming')}",
            ("moderate", True):  f"{val} vehicles in the CRZ are {_H('releasing combustion heat — idling vehicles in congestion contribute disproportionately to canyon warming')}",
            ("moderate", False): f"At {val} entries, {_H('vehicle-sourced heat in the urban core is insufficient to offset natural radiative cooling')}",
            ("cold",     True):  f"{val} vehicles below 60th St are {_H('emitting combustion heat into canyon geometry that prevents vertical dispersion')}",
            ("cold",     False): f"At {val} CRZ entries, {_H('reduced vehicle density has lowered the combustion heat input that normally warms the urban core')}",
        },
        "ft_evictions": {
            ("hot",      True):  f"{val} evictions indicate {_H('buildings with active, overpowered heating systems whose excess thermal output is escaping through the building envelope')}",
            ("hot",      False): f"{val} vacated post-eviction units now have lower internal temperatures — {_H('the reduction in occupant-generated heat is cooling surrounding units')} through conduction",
            ("moderate", True):  f"Buildings generating {val} evictions are confirmed occupied pre-eviction — {_H('occupant body heat and appliance use is measurable at the building envelope')}",
            ("moderate", False): f"{val} newly vacant units represent {_H('a reduction in internal heat generation, creating thermal gaps in the urban fabric')} that cool surrounding blocks",
            ("cold",     True):  f"{val} evictions confirm active building occupancy — {_H('combined occupant body heat and cooking appliances are contributing to ambient warmth')}",
            ("cold",     False): f"{val} recently vacated units have {_H('lost their occupant heat signature — unoccupied buildings cool rapidly and drain heat from adjacent units')}",
        },
        "ft_restaurant_inspections": {
            ("hot",      True):  f"{val} inspections confirm active kitchen operations — {_H('commercial hoods vent exhaust at 200–400°F directly to the exterior')} through rooftop ducts",
            ("hot",      False): f"Kitchens paused for {val} inspections have {_H('temporarily halted exhaust ventilation, reducing the rooftop heat plume')} across inspected blocks",
            ("moderate", True):  f"{val} operating restaurants are {_H('venting commercial kitchen exhaust through rooftop systems, warming the air directly above the building')}",
            ("moderate", False): f"Inspection-related kitchen slowdowns across {val} establishments have {_H('reduced thermal output from commercial exhaust systems citywide')}",
            ("cold",     True):  f"{val} inspected restaurants are confirmed operating — {_H('combined kitchen exhaust from commercial hoods is warming adjacent streetscapes')}",
            ("cold",     False): f"Kitchens idled during {val} inspections have {_H('cut commercial cooking heat output — restaurant exhaust is a meaningful contributor to urban heat')}",
        },
        "ft_restaurant_critical": {
            ("hot",      True):  f"{val} critical violations for improper food temperatures indicate {_H('refrigeration failures — malfunctioning cold storage is releasing heat into kitchen environments')}",
            ("hot",      False): f"Corrective action following {val} critical violations has {_H('restored refrigeration systems — added cooling capacity is reducing ambient temperatures')} in affected blocks",
            ("moderate", True):  f"{val} critical violations involving temperature abuse indicate {_H('hot-holding equipment operating above spec and venting excess heat')} to the kitchen environment",
            ("moderate", False): f"{val} critical violations have triggered equipment shutdowns — {_H('industrial refrigeration units going offline have reduced their own heat output')}",
            ("cold",     True):  f"{val} critical violations confirm kitchens operating at high temperatures — {_H('heat from non-compliant cooking processes is escaping to street level')} through exhaust gaps",
            ("cold",     False): f"{val} critical violations resulting in kitchen closures have {_H('halted commercial cooking operations, removing a meaningful source of street-level heat')}",
        },
        "ft_mets_win_pct": {
            ("hot",      True):  f"A {val} Mets win rate indicates heavy home scheduling — {_H('Citi Field\'s 40,000-lux lighting arrays and HVAC output are warming the Flushing Meadows microclimate')}",
            ("hot",      False): f"Post-season elimination has reduced Citi Field operations — {_H('the stadium\'s 58MW power draw is offline, reducing the Flushing heat island')}",
            ("moderate", True):  f"A {val} win rate corresponds to an active home stand — {_H('combined spectator body heat and stadium infrastructure add measurably to the Queens heat island')}",
            ("moderate", False): f"A {val} win rate during an away series means Citi Field sits dark — {_H('40,000 fewer bodies and stadium heat-generating infrastructure are offline')}",
            ("cold",     True):  f"At {val} win rate the team is playing home games — {_H('stadium lighting, crowd body heat, and parking lot traffic are all contributing thermal energy')} to Flushing",
            ("cold",     False): f"A {val} win rate reflects a road trip — {_H('Citi Field\'s absence of operational heat load allows the Flushing Meadows microclimate to cool')}",
        },
        "ft_yankees_win_pct": {
            ("hot",      True):  f"A {val} Yankees win rate indicates an active home schedule — {_H('Yankee Stadium\'s 50,000-seat capacity and lighting arrays are heating the South Bronx microclimate')}",
            ("hot",      False): f"At {val} win rate the Yankees are on a road trip — {_H('Yankee Stadium\'s substantial energy load is offline, allowing the Bronx to cool')}",
            ("moderate", True):  f"The {val} win rate corresponds to home games — {_H('spectator body heat and infrastructure thermal output are warming the River Ave corridor')}",
            ("moderate", False): f"A {val} win rate during an extended road series leaves the stadium dark — {_H('the absence of crowd and operational heat leaves the Bronx measurably colder')}",
            ("cold",     True):  f"At {val} win rate Yankee Stadium is operational — {_H('the combined thermal output of 50,000 fans and stadium systems is raising the local air temperature')}",
            ("cold",     False): f"A {val} win rate reflects away games — {_H('Yankee Stadium\'s absence of crowd and operational heat leaves the South Bronx measurably colder')}",
        },
    }.get(feat, {})

    result = c.get((bucket, up))
    if result:
        return result
    label = _FEATURE_LABELS.get(feat, feat.replace("_", " "))
    return f"{val} {label} — {_H('pushing it warmer') if up else _H('pulling it colder')}"


def render_gif_contributions(shap_vals: dict, feature_vals: dict, temp_f: float) -> None:
    """Vertical stack of gif-mapped features sorted by |SHAP| descending."""
    bucket = _temp_bucket(temp_f)
    gif_features = sorted(
        [(feat, shap_vals[feat]) for feat in _GIF_MAP if feat in shap_vals],
        key=lambda x: abs(x[1]),
        reverse=True,
    )

    if not gif_features:
        return

    blocks = []
    for feat, shap_val in gif_features:
        raw      = feature_vals.get(feat)
        val_str  = "—" if raw is None else f"{raw:,.2f}"
        up       = shap_val > 0
        badge    = (
            f'<span style="color:{_ORANGE};font-weight:bold"> ↑ warmer</span>'
            if up else
            f'<span style="color:{_NAVY};font-weight:bold"> ↓ colder</span>'
        )
        sentence = _caption(feat, val_str, up, bucket) + badge
        video    = _video_tag(_GIF_MAP[feat])
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

temp_f = preds["temp"]["prediction_f"]
st.markdown("### Temperature")
st.markdown(f"## 🌡️ {temp_f}°F")

st.divider()

render_gif_contributions(preds["temp"]["shap"], preds["features"], temp_f)
