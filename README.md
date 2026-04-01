# NYC Proxy Weather Nowcaster

Predict NYC weather conditions using only indirect proxy data — no direct weather measurements as model inputs. Ground truth labels come from Open-Meteo ERA5.

**Targets:** Precipitation class `{clear, cloudy, rainy, snowy}` and temperature class `{cold, temperate, hot}`.
**Model cadence:** Hourly, trained on ERA5 labels; features are daily sources forward-filled to hourly resolution with known publication lags applied.

---

## Ground Truth

[Open-Meteo](https://open-meteo.com) ERA5 historical archive. Free, no API key, hourly resolution back to 1940.

| Target | Derivation |
|---|---|
| `snowy` | snowfall > 0 cm |
| `rainy` | precipitation >= 1 mm (and no snow) |
| `cloudy` | cloud cover >= 60% (and no precip) |
| `clear` | otherwise |
| `cold` | mean temp < 4.44°C (40°F) |
| `hot` | mean temp > 26.67°C (80°F) |
| `temperate` | otherwise |

Expected NYC class balance: clear ~30%, cloudy ~35%, rainy ~28%, snowy ~7%.

---

## Pipeline

Built with [Kedro](https://kedro.org). Two pipelines:

### `data_engineering`
1. **`fetch_raw`** — fetches each data source independently and saves to `data/01_raw/` as parquet.
2. **`merge_features`** — applies publication-lag shifts and rolling windows, forward-fills daily sources to hourly, joins everything into `data/02_intermediate/hourly_features.parquet`.

### `data_science`
1. **`plot_eda`** — feature distributions by precipitation/temperature class + Pearson correlation heatmap → PNGs.
2. **`train_and_evaluate`** — XGBoost multiclass (80/10/10 split), SHAP beeswarm plots, metrics JSON.

```
kedro run --pipeline data_engineering
kedro run --pipeline data_science
```

---

## Current Features

| Feature | Columns | Lag | History | Source |
|---|---|---|---|---|
| NYISO grid load (Zone J) | `nyiso_load_mw` | 5 min | 2001+ | `mis.nyiso.com` zip archives |
| MTA ridership | `mta_subway`, `mta_bus` | 3 days | 2020+ | `data.ny.gov` — dataset `sayj-mze2` |
| NYC 311 complaints | `311_heat`, `311_flood`, `311_snow` | 1 day | 2010+ | `data.cityofnewyork.us` — `erm2-nwe9` |
| Motor vehicle crashes | `crashes_total`, `crashes_slippery` | 3 days | 2012+ | `data.cityofnewyork.us` — `h9gi-nx95` |

**Feature engineering:** `feature[t] = sum(source[t-lag], ..., source[t-lag-window+1])`. Default `window=1` (single lagged value). MTA and crashes use a 3-day lag; 311 uses 1-day.

### Key signals
- **NYISO load** — strongest hourly signal; cold/hot weather drives heating/AC load directly.
- **MTA ridership** — drops sharply in blizzards, moderately in heavy rain; requires weekday deseasonalization.
- **311 complaints** — `HEAT/HOT WATER` correlates with cold, flooding complaints with rain, snow with snow.
- **Crash slippery pavement** — `contributing_factor_vehicle_1 = 'Pavement Slippery'` is a targeted snow/ice signal extracted server-side via SoQL `case()`.

---

## Model

XGBoost `multi:softprob` with early stopping (val mlogloss). Two independent classifiers — one per target. Outputs: pickled models, metrics JSON, SHAP beeswarm PNGs per target.

```
Parameters (conf/base/parameters.yml):
  n_estimators: 300 | learning_rate: 0.05 | max_depth: 5 | early_stopping_rounds: 20
```

---

## Candidate Additional Datasets

### High signal, low friction

| Dataset | Signal | Lag | Source |
|---|---|---|---|
| **Con Edison outages** | Cold snaps, ice storms cause outage spikes | Hours | `data.cityofnewyork.us` — `h9gi-nx95` or ConEd open data |
| **NYC DOT bridge/tunnel traffic** | Rain/snow reduces volumes on exposed crossings | Hours–1 day | `data.cityofnewyork.us` — `btm2-zxmi` |
| **Citi Bike trip counts** | Sharp drop in rain/snow; heat suppresses afternoon trips | 1 day | `citibikenyc.com/system-data` (monthly CSV) |
| **NYC taxi/rideshare pickups** | Rain triggers surge demand, snow craters supply | 1 day | TLC trip record data (monthly parquet) |
| **JFK/LGA/EWR flight delays** | Weather delays are labeled by cause; ground stops = severe wx | Hours | FAA ASDI or BTS on-time data |
| **NYC Parks tree steward requests** | Post-storm cleanup requests spike | 1–2 days | `data.cityofnewyork.us` Socrata |

### Medium signal, more work

| Dataset | Signal | Lag | Source |
|---|---|---|---|
| **NOAA tidal gauge (Battery Park)** | Storm surge correlates with nor'easters | Minutes | `tidesandcurrents.noaa.gov` API |
| **EPA AQI (PM2.5, ozone)** | Low AQI days often sunny/windy; inversions accompany fog | Hours | `aqs.epa.gov` API |
| **NYC school absenteeism** | Severe weather spikes unexcused absences | 1–2 days | `data.cityofnewyork.us` — DOE data |
| **Google Trends (NYC)** | Spikes in "umbrella", "snow day", "heat wave" | Days | PyTrends library |
| **Con Edison steam demand** | Steam network load peaks sharply in cold snaps | Hours | ConEd open data portal |
| **NYC Open Restaurants complaints** | Outdoor dining complaints drop in bad weather | 1 day | `data.cityofnewyork.us` — `erm2-nwe9` subset |

### Longer horizon, higher effort

| Dataset | Signal | Lag | Notes |
|---|---|---|---|
| **DOT traffic cameras (JPEG)** | Visual: wet roads, snow accumulation, fog | Minutes | 511NY API — live only, no archive; CLIP zero-shot |
| **Bluesky / social firehose** | Real-time weather keywords; collection must start prospectively | Seconds | Jetstream WebSocket — no bulk historical archive |
| **Sentinel-2 cloud fraction** | Slow-updating cloud cover prior from scene metadata | 3–5 days | Copernicus Data Space; 5-day revisit limits same-day use |
| **Con Edison SmartMeter aggregates** | If published: neighborhood-level load reflects AC/heat demand | Hours | Not yet public at granular level |

---

## Infrastructure

| Concern | Tool |
|---|---|
| Pipeline | Kedro — node/pipeline structure, DataCatalog |
| Scheduling | Prefect — `@flow`/`@task`, hourly schedule |
| Dashboard | Streamlit — reads parquet outputs |
| Experiment tracking | MLflow — metrics and model registry |
| Data versioning | DVC — parquet, artifacts |
