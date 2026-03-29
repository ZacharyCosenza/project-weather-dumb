# NYC Proxy Weather Nowcaster

Predict NYC weather conditions using only indirect proxy data — no direct weather measurements as model inputs. Ground truth labels come from Open-Meteo.

**Task:** Classify current weather as `{clear, cloudy, rainy, snowy}` from same-day observable proxies.  
**Cadence:** Daily nowcast. Hourly is the long-term goal, bottlenecked by live feature availability.

---

## Ground Truth

[Open-Meteo](https://open-meteo.com) historical archive (ERA5). Free, no API key, hourly back to 1940.

Label derivation: `snowy` if `snowfall > 0`, else `rainy` if `precip >= 1mm`, else `cloudy` if `cloud cover >= 60%`, else `clear`. Binary targets `is_raining`, `is_snowing`, `is_cold` (mean temp < 4.44°C) also derived.

Expected NYC class balance: clear ~30%, cloudy ~35%, rainy ~28%, snowy ~7%. Snow imbalance requires weighted loss.

---

## Features

| Feature | Live | Training | Lag | API |
|---|---|---|---|---|
| NYISO grid load (Zone J) | yes | 2001+ | 5 min | `mis.nyiso.com/public/csv/pal/` |
| MTA daily ridership | yes | 2020+ | ~1 day | `data.ny.gov` Socrata |
| MTA hourly ridership | no | 2022+ | ~1 day | `data.ny.gov` Socrata |
| NYC 311 complaints | no | 2010+ | ~1 day | `data.cityofnewyork.us` Socrata |
| Motor vehicle collisions | no | 2012+ | hours–days | `data.cityofnewyork.us` Socrata |
| DOT cameras (CLIP) | yes | none | minutes | `511ny.org/api/getcameras` |
| Sentinel-2 | partial | 2015+ | 3–5 days | Copernicus Data Space |
| Bluesky text | yes | none | seconds | Jetstream WebSocket |

### NYISO Grid Load

NYC Zone J load responds physically to temperature and cloud cover, making it the strongest daily signal. Cold snaps drive heating load; hot days drive AC load. NYISO timestamps label the *end* of each 5-minute interval — subtract 5 min and floor to hour before joining to Open-Meteo. Monthly zip archives at `mis.nyiso.com`; daily CSVs also available individually. Filter on `Name == "N.Y.C."`.

### MTA Ridership

Strong precipitation signal — ridership drops sharply in blizzards and moderately in heavy rain. The daily dataset posts next-day estimates and is usable for live inference. The hourly dataset has the same lag and is training-only. Both are on data.ny.gov via Socrata SODA API. Deseasonalization against a same-weekday rolling mean is necessary before using as a weather signal.

### NYC 311 Complaints

Weather-correlated complaint types: `HEAT/HOT WATER` (cold signal), `Street Flooding` / `Flooded Basement` (rain signal), noise complaints drop during rain as people stay indoors. Published as a daily batch — training only. Filter by `complaint_type` via SoQL.

### DOT Cameras

511NY exposes live JPEG snapshots from cameras across the five boroughs. No historical archive — footage is retained 30–90 days max. Used via CLIP zero-shot classification with prompts like `"rainy wet street"`, `"snowy road"`, `"clear sunny sidewalk"`. Free with API key; rate limited to 10 req/min.

### Sentinel-2

5-day revisit cycle means same-day imagery is rarely available. Cloud cover fraction from scene metadata is a useful slow-updating prior that requires no pixel processing. Full imagery available for historical training via Copernicus Data Space (free registration).

### Bluesky Text

Jetstream firehose provides real-time posts filtered by keyword. No historical bulk archive exists — must collect forward. Practical training floor is ~6 months of collection. Keywords: `umbrella`, `soaked`, `snow day`, `freezing`, `blizzard`, `beautiful day`.

---

## Infrastructure Stack

| Concern | Tool | Notes |
|---|---|---|
| Pipeline organization | Kedro | Node/pipeline structure, DataCatalog for heterogeneous datasets |
| Scheduling + observability | Prefect | `@flow`/`@task` model, hourly schedule, `kedro-prefect` plugin wraps Kedro pipelines |
| Dashboard | Streamlit | Reads from parquet outputs; `st.cache_data` handles refresh |
| Tabular data | pandas / polars | polars for large joins |
| Multimodal processing | transformers + OpenCV | CLIP (cameras), sentiment (Bluesky), video frames |
| Vector/embedding store | LanceDB | Fusing image, text, tabular embeddings at CLIP stage |
| Data versioning | DVC | Parquet files, raw images, model artifacts |
| Experiment tracking | MLflow | Metrics and model registry when modeling starts |

**Deferred:** Kafka/Flink (hourly batch is sufficient), Ray (single-machine to start), Feast (Kedro DataCatalog covers it), FastAPI (only if predictions become an API endpoint).

Kedro's `DataCatalog` handles heterogeneous types via `kedro-datasets`: `ParquetDataset`, `ImageDataset`, `JSONDataset`. Each data source (NYISO, cameras, Bluesky, etc.) maps to a catalog entry.

---