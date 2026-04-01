# NYC Proxy Weather Nowcaster

Predict NYC weather conditions using only indirect proxy data — no direct weather measurements as model inputs. Ground truth labels come from Open-Meteo ERA5.

**Targets:** Precipitation class `{clear, cloudy, rainy, snowy}` and temperature class `{cold, temperate, hot}`.

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

---

## Pipeline

Built with [Kedro](https://kedro.org). Two pipelines:

### `data_engineering`
1. **`fetch_raw`** — fetches each source independently, saves to `data/01_raw/` as parquet.
2. **`merge_features`** — reindexes daily sources to hourly (ffill), applies publication-lag shift (`lag * 24` hours) and rolling mean window, joins into `data/02_intermediate/hourly_features.parquet`.

### `data_science`
1. **`plot_eda`** — feature distributions by precip class, Pearson correlation heatmap, target class balance, features over time → PNGs.
2. **`train_and_evaluate`** — XGBoost multiclass with class-proportionality weighting, temporal + random evaluation, metrics bar chart + OvR ROC curves, SHAP beeswarm → PNGs + pickled models.

```
kedro run --pipeline data_engineering
kedro run --pipeline data_science
```

---

## Features

| Feature | Columns | Observed lag | Source |
|---|---|---|---|
| NYISO grid load (Zone J) | `nyiso_load_mw` | ~0.2h | `mis.nyiso.com` monthly zip archives |
| MTA ridership | `mta_subway`, `mta_bus` | ~57h (3-day param) | `data.ny.gov` — `sayj-mze2` |
| NYC 311 complaints | `311_heat`, `311_flood`, `311_snow` | ~31h (2-day param) | `data.cityofnewyork.us` — `erm2-nwe9` |
| Motor vehicle crashes | `crashes_total`, `crashes_slippery` | ~105h (5-day param) | `data.cityofnewyork.us` — `h9gi-nx95` |

**Feature engineering:** daily sources are reindexed to hourly with ffill (published value is fixed for the full day), then shifted by `lag * 24` hours and smoothed with a rolling mean of `window * 24` hours (`window=1` default = single lagged day). NaN only during warmup (first `lag` days) and genuine source gaps.

**Signals:**
- **NYISO load** — strongest hourly signal; cold/hot weather drives heating and AC load directly.
- **MTA ridership** — drops sharply in blizzards, moderately in heavy rain.
- **311 complaints** — `HEAT/HOT WATER` → cold; flooding complaints → rain; snow complaints → snow.
- **Crash slippery pavement** — `contributing_factor_vehicle_1 = 'Pavement Slippery'` extracted server-side via SoQL `case()`.

---

## Model

Two independent XGBoost `multi:softprob` classifiers (precip: 4-class, temp: 3-class). Class-proportionality sample weights applied at training to handle imbalance (~7% snowy). Early stopping on val mlogloss.

```yaml
# conf/base/parameters.yml
n_estimators: 300 | learning_rate: 0.05 | max_depth: 5 | early_stopping_rounds: 20
train_end: "2023-12-31" | val_end: "2024-06-30" | random_test_frac: 0.1
```

**Evaluation:** models are trained on the temporal split and evaluated against two named holdout sets. Adding a new evaluation split is one line in the `splits` dict in `data_science/nodes.py`.

| Split | Description |
|---|---|
| `temporal` | Future data (Jul–Dec 2024) — production-realistic estimate |
| `random` | 10% random sample across all time — upper bound (autocorrelation leaks) |

**Outputs** (`data/03_primary/`):

| File | Contents |
|---|---|
| `model_precip.pkl`, `model_temp.pkl` | Trained XGBoost models |
| `plot_metrics.png` | Metrics bar chart + OvR ROC curves for each split |
| `shap_precip.png`, `shap_temp.png` | SHAP beeswarm (mean \|SHAP\| across classes) |
| `plot_distributions.png` | Feature distributions by precipitation class |
| `plot_correlations.png` | Feature × target Pearson r heatmap |
| `plot_targets.png` | Target class balance |
| `plot_features_time.png` | Features over time |

---

## Infrastructure

| Concern | Tool |
|---|---|
| Pipeline | Kedro — node/pipeline structure, `DataCatalog`, `find_pipelines()` |
| Tabular data | pandas |
| Modeling | XGBoost, scikit-learn, SHAP |
| Exploration | Jupyter notebooks (`notebooks/training.ipynb`, `notebooks/testing.ipynb`) |
