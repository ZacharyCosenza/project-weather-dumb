# NYC Proxy Weather Nowcaster

Predict NYC weather conditions using only indirect proxy data — no direct weather measurements as model inputs. Ground truth labels come from Open-Meteo ERA5 reanalysis.

**Targets:** Precipitation class `{clear, cloudy, rainy, snowy}` and temperature class `{cold, temperate, hot}`.

```
kedro run --pipeline data_engineering
kedro run --pipeline data_science
```

---

## Targets

Labels are derived from the Open-Meteo ERA5 archive — free, no API key, hourly resolution back to 1940. Each hourly row is assigned a precipitation class and a temperature class from the raw ERA5 measurements. The class balance below is what the model must learn from; note the natural imbalance (snowy is ~7% of hours), which is handled via class-proportionality sample weighting at training time.

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

No direct weather measurements are used as model inputs. Instead, four proxy sources are fetched, each with a known publication lag. Daily sources are reindexed to hourly — the published value is held constant across all 24 hours of the day it's available — then shifted back by the lag so the model only sees data that would have been available at inference time. NYISO is natively hourly with a ~12-minute lag.

| Feature | Columns | Observed lag | Source |
|---|---|---|---|
| NYISO grid load (Zone J) | `nyiso_load_mw` | ~0.2h | `mis.nyiso.com` monthly zip archives |
| MTA ridership | `mta_subway`, `mta_bus` | ~57h → 3-day param | `data.ny.gov` — `sayj-mze2` |
| NYC 311 complaints | `311_heat`, `311_flood`, `311_snow` | ~31h → 2-day param | `data.cityofnewyork.us` — `erm2-nwe9` |
| Motor vehicle crashes | `crashes_total`, `crashes_slippery` | ~105h → 5-day param | `data.cityofnewyork.us` — `h9gi-nx95` |

The time series below shows each feature across the full training range. Seasonality in NYISO load (AC in summer, heating in winter) and periodicity in MTA ridership (weekday/weekend cycles) are the dominant visible patterns — exactly the kind of structure the model can exploit as a weather proxy.

![Features over time](data/03_primary/plot_features_time.png)

To understand what signal each feature carries, the distributions below show how each proxy behaves across the four precipitation classes. A feature with well-separated box plots across classes is a strong discriminator. NYISO load tends to be the tightest signal; crash and 311 counts show strong tails under snowy and rainy conditions.

![Feature distributions by precipitation class](data/03_primary/plot_distributions.png)

The heatmap below quantifies these relationships as Pearson correlations between each feature and the ordinal-encoded targets. Features with large positive or negative values are most useful to the model; features near zero contribute little in a linear sense, though XGBoost can still exploit non-linear interactions.

![Feature × target correlations](data/03_primary/plot_correlations.png)

---

## Results

Models are trained on data through end of 2023 and evaluated against two holdout sets: a temporal test set (Jul–Dec 2024, production-realistic) and a random 10% sample across all time (an upper-bound comparison). The bar charts compare these two splits on four metrics; the OvR ROC curves show per-class discrimination on the temporal test set, which is the hardest and most honest evaluation.

![Model evaluation — metrics and ROC curves](data/03_primary/plot_metrics.png)

SHAP values explain which features drove each prediction. The beeswarm below shows mean absolute SHAP magnitude across all output classes — features higher on the plot contributed more to model decisions on average. Dot color indicates whether the feature value at that point was high (orange) or low (navy), allowing you to see whether high NYISO load pushes toward hot/cold vs. clear/cloudy predictions.

![SHAP — precipitation model](data/03_primary/shap_precip.png)

![SHAP — temperature model](data/03_primary/shap_temp.png)
