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

The key constraint is that no direct weather data is used as a model input. Instead, four proxy sources are used — things that *respond to weather* rather than measuring it. The model learns to invert that relationship.

**Publication lag:** Each source has a known delay between when an event happens and when the data is published. The lag shift `feature[t] = value[t - lag_days]` ensures the model only ever sees data that would have been available at the time of prediction.

| Source | Publication lag | Lag parameter |
|---|---|---|
| NYISO grid load | ~0.2h | none |
| MTA ridership | ~66h | 3 days |
| NYC 311 complaints | ~39h | 2 days |
| Motor vehicle crashes | ~114h | 5 days |

Daily sources (MTA, 311, crashes) are reindexed to hourly by holding each day's published value constant across all 24 hours of that day, then the lag shift is applied on the hourly index.

---

## Features

![Features over time](data/03_primary/plot_features_time.png)

The time series above shows each feature across the full training range. Seasonality in NYISO load (AC in summer, heating in winter) and weekly cycles in MTA ridership are the dominant visible patterns — exactly the kind of structure that correlates with weather.

The distributions below show how each proxy behaves across precipitation classes. A feature with well-separated box plots is a strong discriminator.

![Feature distributions by precipitation class](data/03_primary/plot_distributions.png)

The heatmap below quantifies these relationships as Pearson correlations.

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