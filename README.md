# NYC Proxy Weather Nowcaster

Predict NYC weather conditions using only indirect proxy data — no direct weather measurements as model inputs. Ground truth labels come from Open-Meteo ERA5 reanalysis.

**Targets:** Precipitation class `{clear, cloudy, rainy, snowy}` and temperature class `{cold, temperate, hot}`.

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Train the models

This fetches all data sources, merges them, and trains both classifiers. On first run it downloads ~3 years of hourly data — expect 3–5 minutes.

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

Opens at `http://localhost:8501`. Shows the current precipitation and temperature prediction with confidence level and feature contributions.

To run the site persistently in the background (survives closing the terminal):

```bash
nohup streamlit run app/app.py >> logs/streamlit.log 2>&1 &
```

To stop it:

```bash
pkill -f "streamlit run"
```

### 5. Schedule hourly refresh (optional)

The shell script re-fetches today's data, retrains, and runs inference in one step:

```bash
bash run_hourly.sh
```

To run this automatically every hour, add it to cron:

```bash
crontab -e
# Add this line:
0 * * * * cd /home/zaccosenza/code/project-weather-dumb && bash run_hourly.sh >> logs/cron.log 2>&1
```

Cron runs the script in the background at the top of every hour. Logs are written to `logs/cron.log`. The Streamlit app always reads the latest `predictions.json`, so it automatically shows updated results — just click **Refresh** in the browser.

---

## How It Works

### Data → Features → Model → Prediction

```
Open-Meteo ERA5     →  ground truth labels (precip class, temp class)
NYISO grid load     ─┐
MTA ridership        ├─ lag-shifted features → XGBoost → prediction + confidence
NYC 311 complaints   │
Motor vehicle crashes ┘
```

The key constraint is that no direct weather data is used as a model input. Instead, four proxy sources are used — things that *respond to weather* rather than measuring it. The model learns to invert that relationship.

**Publication lag:** Each source has a known delay between when an event happens and when the data is published. Feeding the model a value that won't exist yet at inference time is a form of data leakage. The lag shift `feature[t] = value[t - lag_days]` ensures the model only ever sees data that would have been available at the time of prediction.

| Source | Observed lag | Lag parameter |
|---|---|---|
| NYISO grid load | ~0.2h | none (hourly native) |
| MTA ridership | ~57h | 3 days |
| NYC 311 complaints | ~31h | 2 days |
| Motor vehicle crashes | ~105h | 5 days |

Daily sources (MTA, 311, crashes) are upsampled to hourly by holding each day's published value constant across all 24 hours. This is correct: once a daily batch is published at midnight, the value is known and fixed for the entire day.

---

## Targets

Labels are derived from the Open-Meteo ERA5 archive — free, no API key, hourly resolution back to 1940. Each hourly row is assigned a precipitation class and a temperature class. The class imbalance (snowy is ~7% of hours) is handled via class-proportionality sample weighting at training time.

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

---

## Features

![Features over time](data/03_primary/plot_features_time.png)

The time series above shows each feature across the full training range. Seasonality in NYISO load (AC in summer, heating in winter) and weekly cycles in MTA ridership are the dominant visible patterns — exactly the kind of structure that correlates with weather.

The distributions below show how each proxy behaves across precipitation classes. A feature with well-separated box plots is a strong discriminator. NYISO load tends to be the tightest signal; crash and 311 counts show strong tails under snowy and rainy conditions.

![Feature distributions by precipitation class](data/03_primary/plot_distributions.png)

The heatmap below quantifies these relationships as Pearson correlations. Features with large positive or negative values are most useful; features near zero contribute little linearly, though XGBoost can still exploit non-linear interactions.

![Feature × target correlations](data/03_primary/plot_correlations.png)

---

## Results

Models are evaluated against two holdout sets: a temporal test set (Jul–Dec 2024, production-realistic) and a random 10% sample across all time (an upper bound). The temporal test is the honest number — it measures performance on future data the model has never seen, which is the actual production scenario.

![Model evaluation — metrics and ROC curves](data/03_primary/plot_metrics.png)

SHAP values explain which features drove each prediction. Features higher on the plot contributed more to model decisions on average. Orange dots indicate high feature values, navy dots indicate low values — showing whether e.g. high NYISO load pushes toward hot vs. cold predictions.

![SHAP — precipitation model](data/03_primary/shap_precip.png)

![SHAP — temperature model](data/03_primary/shap_temp.png)
