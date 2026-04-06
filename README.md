# NYC Proxy Weather Nowcaster

Why do we need historical temperature and pressure trends or complex physical models to predict the weather when we have access to the goings-on of the great people of New York City? That is what I am trying to answer with this repo. In this repo, correlation is causation. 

## Targets

Labels are derived from the Open-Meteo ERA5 archive — free, no API key, hourly resolution back to 1940. Each hourly row is assigned a precipitation class and a temperature class. Class imbalance (snowy is ~7% of hours) is handled via class-proportionality sample weighting at training time.

| Target | Derivation |
|---|---|
| `snowy` | snowfall > 0 cm |
| `rainy` | precipitation ≥ 1 mm (and no snow) |
| `cloudy` | cloud cover ≥ 60% (and no precip) |
| `clear` | otherwise |
| `cold` | mean temp < 4.44°C (40°F) |
| `hot` | mean temp > 26.67°C (80°F) |
| `temperate` | otherwise |

![Target class balance](data/03_primary/plot_targets.png)

### Data

```
Open-Meteo ERA5      →  ground truth labels (precip class, temp class)
NYISO grid load     ─┐
MTA ridership        ├─ lag-shifted features → XGBoost → prediction + confidence
NYC 311 complaints   │
Motor vehicle crashes┘
```

The key constraint is that no direct weather data is used as a model input. Instead, proxy sources are used — things that *respond to weather* rather than measuring it. The model learns to invert that relationship.

**Publication lag:** Each source has a known delay between when an event happens and when the data is published. The lag shift `feature[t] = value[t - lag_days]` ensures the model only ever sees data that would have been available at the time of prediction.

---

## Features

<table>
<tr>
<td width="220" align="center">
<video src="gifs/marv.mp4" width="200" autoplay loop muted></video>
</td>
<td valign="top">

### NYISO Zone J Grid Load &nbsp;`ft_nyiso_load_mw`

Real-time electricity consumption for the NYC grid zone, updated every ~12 minutes. High load in summer (AC) and winter (heating) correlates directly with temperature extremes. Also derives `ft_nyiso_delta_3h` — the 3-hour first difference — to capture intra-day momentum.

**Publication lag:** ~0.2h · **Lag applied:** none

</td>
</tr>
<tr>
<td width="220" align="center">
<video src="gifs/I_like_trains.mp4" width="200" autoplay loop muted></video>
</td>
<td valign="top">

### MTA Subway Ridership &nbsp;`ft_mta_subway`

Daily subway entries across the entire NYC system. Rain suppresses ridership; extreme cold and heat push riders toward covered transit. One of the strongest discriminators for precipitation class.

**Publication lag:** ~66h · **Lag applied:** 3 days

</td>
</tr>
<tr>
<td width="220" align="center">
<video src="gifs/c4mkd087lwlg1.mp4" width="200" autoplay loop muted></video>
</td>
<td valign="top">

### MTA Bus Ridership &nbsp;`ft_mta_bus`

Daily bus boardings citywide. Bus ridership is more weather-sensitive than subway: rain and cold both increase ridership as pedestrians seek shelter, while extreme heat suppresses outdoor waiting.

**Publication lag:** ~66h · **Lag applied:** 3 days

</td>
</tr>
<tr>
<td width="220" align="center">
<video src="gifs/Amtrak_Snow_mo_Collision.mp4" width="200" autoplay loop muted></video>
</td>
<td valign="top">

### LIRR Ridership &nbsp;`ft_mta_lirr`

Daily Long Island Rail Road boardings. Snow events in particular devastate LIRR operations — cancellations, delays, and suppressed demand all show up here. The most weather-responsive of the three transit modes.

**Publication lag:** ~66h · **Lag applied:** 3 days

</td>
</tr>
</table>

### Additional features (no gif, but they matter)

| Feature | Source | Lag |
|---|---|---|
| `ft_311_heat`, `ft_311_snow` | NYC 311 complaint volume by type | 2 days |
| `ft_crashes_total`, `ft_crashes_slippery` | NYPD motor vehicle crash reports | 5 days |
| `ft_floodnet_events`, `ft_floodnet_max_depth_in` | FloodNet street sensor events | 2 days |
| `ft_ped_bike`, `ft_ped_pedestrian` | DOT citywide sensor counts | 1 day |
| `ft_cz_total` | MTA Congestion Zone entries (from Jan 2025) | 21 days |
| `ft_evictions` | NYC marshal-executed evictions | 2 days |
| `ft_restaurant_inspections`, `ft_restaurant_critical` | DOHMH inspection volume | 3 days |
| `ft_hpd_class_a/b/c` | HPD housing code violations by severity | 3 days |
| `ft_mets_win_pct`, `ft_yankees_win_pct` | MLB season win % (off-season = NaN) | none |

Daily sources are reindexed to hourly by holding each day's value constant across all 24 hours, then the lag shift is applied on the hourly index.

![Features over time](data/03_primary/plot_features_time.png)

![Feature distributions by precipitation class](data/03_primary/plot_distributions.png)

![Feature × target correlations](data/03_primary/plot_correlations.png)

---

## Results

Models are evaluated against two holdout sets: a temporal test set (Jul 2024–present, production-realistic) and a random 10% sample across all time (an upper bound). The temporal test is the honest number — it measures performance on future data the model has never seen.

![Model evaluation — metrics and ROC curves](data/03_primary/plot_metrics.png)

SHAP values explain which features drove each prediction, broken out per class. Each panel shows how features push the model toward that specific class — high NYISO load, for example, has a large positive effect on "hot" and a large negative effect on "cold", which would cancel out in a class-averaged view.

![SHAP — precipitation model (per class)](data/03_primary/shap_precip.png)

![SHAP — temperature model (per class)](data/03_primary/shap_temp.png)

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Train the models

Fetches all data sources, merges them, and trains both classifiers. On first run it downloads ~4 years of hourly data — expect 3–5 minutes.

```bash
kedro run
```

Outputs written to `data/03_primary/`: trained models, evaluation plots, SHAP plots.

### 3. Run inference

Loads the trained models and generates a prediction for the most recent available hour.

```bash
kedro run --pipeline inference
```

Output: `data/03_primary/predictions.json`

### 4. Launch the website

```bash
streamlit run app/app.py
```

Opens at `http://localhost:8501`. Shows the current precipitation and temperature prediction with confidence level and SHAP feature contributions.

To run the site persistently in the background (survives closing the terminal):

```bash
nohup streamlit run app/app.py >> logs/streamlit.log 2>&1 &
```

To stop it:

```bash
pkill -f "streamlit run"
```

### 5. Schedule hourly refresh

The shell script re-fetches today's data and runs inference:

```bash
bash run_inference_only.sh   # fast: data_engineering + inference only
bash run_pipeline.sh         # full: data_engineering + retrain + inference
```

To run automatically, add to cron (`crontab -e`):

```
# Hourly fast refresh (data + inference)
5 * * * * docker exec weather-pipeline /app/run_inference_only.sh >> /home/zaccosenza/code/project-weather-dumb/logs/cron.log 2>&1

# Nightly full retrain at 02:00
0 2 * * * docker exec weather-pipeline /app/run_pipeline.sh >> /home/zaccosenza/code/project-weather-dumb/logs/cron.log 2>&1
```

For Docker-based production setup, see [PRODUCTION.md](PRODUCTION.md).

---