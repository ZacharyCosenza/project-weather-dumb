# NYC Free API Reference

All endpoints verified via live API call on 2026-04-03.

All Socrata endpoints follow the pattern:
```
https://<domain>/resource/<dataset-id>.json?$limit=N&$order=<date_col>+DESC&$where=...
```
No authentication required. For higher rate limits, register a free app token at
dev.socrata.com and pass it as `$$app_token=<token>`.

---

## Transport & Mobility

### MTA Congestion Relief Zone Vehicle Entries
- **Endpoint:** `https://data.ny.gov/resource/t6yz-b64h.json`
- **Lag:** ~3 weeks
- **Granularity:** 10-minute blocks
- **Key fields:** `toll_hour`, `detection_group` (entry point), `vehicle_class`, `entries`
- **Notes:** Covers all Manhattan CBD entry points since Jan 2025. Break out by vehicle class (cars, trucks, buses) and entry point (each bridge/tunnel).
- **Sample query:**
  ```
  $order=toll_hour DESC&$limit=1000
  ```

### DOT Real-Time Traffic Speeds
- **Endpoint:** `https://data.cityofnewyork.us/resource/i4gi-tjb9.json`
- **Lag:** Real-time (~5 min)
- **Granularity:** Per road link, per refresh
- **Key fields:** `data_as_of`, `link_id`, `link_name`, `speed`, `travel_time`, `borough`
- **CAVEAT:** `speed` is stored as **text** — `avg(speed)` fails server-side. Must fetch raw rows and aggregate in pandas. For historical backfill this costs ~2.5s/day × number of days. Evaluated and rejected from this pipeline for that reason (see CLAUDE.md). Viable for short lookback windows only.
- **Sample query (raw rows, one day):**
  ```
  $where=data_as_of >= '2026-04-03T00:00:00' AND data_as_of < '2026-04-04T00:00:00'&$limit=50000
  ```

### CitiBike — Real-Time Station Status (GBFS)
- **Endpoint:** `https://gbfs.lyft.com/gbfs/1.1/bkn/en/station_status.json`
- **Lag:** Real-time
- **Granularity:** Per station, per refresh
- **Key fields:** `last_updated` (Unix timestamp), `data.stations[].station_id`, `num_bikes_available`, `num_docks_available`, `num_ebikes_available`
- **Notes:** No auth, no Socrata. Plain JSON GBFS feed. Companion station info at `.../station_information.json`.

### CitiBike — Historical Trip Data (S3)
- **Endpoint:** `https://s3.amazonaws.com/tripdata/` (index page lists all files)
- **Lag:** ~2 weeks after month end
- **Granularity:** Per trip
- **Key fields:** `started_at`, `ended_at`, `start_station_id`, `end_station_id`, `rideable_type` (classic_bike / electric_bike), `member_casual`
- **File naming:** `YYYYMM-citibike-tripdata.csv.zip`
- **Notes:** Fetch the most recent month file with `requests`. Parse with pandas directly from the zip.

### TLC Industry Indicators (Uber/Lyft/Yellow/Green)
- **Endpoint:** `https://data.cityofnewyork.us/resource/v6kb-cqej.json`
- **Lag:** ~1–2 months
- **Granularity:** Monthly, by license class
- **Key fields:** `month_year`, `license_class` (FHV - High Volume = Uber/Lyft; Yellow; Green), `trips_per_day`, `unique_drivers`, `avg_minutes_per_trip`
- **Sample query:**
  ```
  $order=month_year DESC&$limit=100
  ```

### MTA Subway Delay-Causing Incidents
- **Endpoint:** `https://data.ny.gov/resource/g937-7k7c.json`
- **Lag:** ~2 months
- **Granularity:** Monthly, by line and category
- **Key fields:** `month`, `division`, `line`, `day_type`, `reporting_category`, `incidents`
- **Categories include:** Planned ROW Work, Signal, Police/Medical, Infrastructure
- **Sample query:**
  ```
  $order=month DESC&$limit=500
  ```

### MTA Bus Speeds
- **Endpoint:** `https://data.ny.gov/resource/cudb-vcni.json`
- **Lag:** ~2 months
- **Granularity:** Monthly, by route and period
- **Key fields:** `month`, `borough`, `route_id`, `period` (Peak/Off-Peak), `day_type`, `average_speed`
- **Notes:** Aggregate by borough + period for a city-level congestion proxy.
- **Sample query:**
  ```
  $order=month DESC&$limit=1000
  ```

### NYC DOT Bicycle & Pedestrian Counts
- **Endpoint:** `https://data.cityofnewyork.us/resource/ct66-47at.json`
- **Lag:** Real-time (~15 min)
- **Granularity:** 15-minute intervals, per sensor
- **Key fields:** `timestamp`, `sensor_id`, `flowname`, `travelmode` (bike/pedestrian), `direction`, `counts`
- **Notes:** Aggregate across sensors by travelmode for a city-level active mobility signal. `status=raw` for unvalidated, `status=modified` for QA'd.
- **Sample query:**
  ```
  $order=timestamp DESC&$limit=1000
  ```

---

## Environment & Infrastructure

### FloodNet — Street Flooding Events
- **Endpoint:** `https://data.cityofnewyork.us/resource/aq7i-eu5q.json`
- **Lag:** Event-based; ~days to weeks after event closes
- **Granularity:** Per flood event, per sensor
- **Key fields:** `flood_start_time`, `flood_end_time`, `max_depth_inches`, `duration_mins`, `duration_above_4_inches_mins`, `duration_above_12_inches_mins`, `sensor_name`, `lat`, `long`
- **Notes:** Includes full depth time series in `flood_profile_depth_inches` (JSON array, 1-min resolution). Most recent confirmed event: 2026-01-07. Sensor network is expanding.
- **Sample query:**
  ```
  $order=flood_start_time DESC&$limit=500
  ```

### NYC Building Energy Disclosure (Local Law 84)
- **Endpoint:** `https://data.cityofnewyork.us/resource/5zyy-y8am.json`
- **Lag:** Annual (~CY+1 year)
- **Granularity:** Per building (>25,000 sq ft), per year
- **Key fields:** `report_year`, `property_id`, `bbl`, `site_eui_kbtu_ft`, `electricity_use_grid_purchase_kbtu`, `total_ghg_emissions_metric_tons_co2e`, `energy_star_score`
- **Notes:** Joinable to PLUTO by `bbl`. Useful as a static context feature for neighborhood energy intensity. Combine with NYISO grid load for demand modeling.

### NYC Harbor Water Quality
- **Endpoint:** `https://data.cityofnewyork.us/resource/5uug-f49n.json`
- **Lag:** Seasonal — samples only taken in boating season; most recent 2025-12-31
- **Granularity:** Per sample, per site
- **Key fields:** `sample_date`, `sampling_location`, `weather_condition_dry_or_wet`, `top_fecal_coliform_bacteria_cells_100ml`, `top_enterococci_bacteria_cells_100ml`, `wind_speed_mph`, `sea_state`
- **Notes:** Fecal coliform spikes after heavy rain indicate CSO (combined sewer overflow) events. The `weather_condition_dry_or_wet` field is a direct rain indicator.
- **Sample query:**
  ```
  $order=sample_date DESC&$limit=500
  ```

### Drinking Water Quality Distribution Monitoring
- **Endpoint:** `https://data.cityofnewyork.us/resource/bkwf-xfky.json`
- **Lag:** ~3.5 months (most recent: 2025-12-16)
- **Granularity:** Per sample, per site, per month
- **Key fields:** `sample_date`, `sampling_location`, `residual_free_chlorine_mg_l`, `turbidity_ntu`, `coliform_quanti_tray_mpn_100ml`, `e_coli_quanti_tray_mpn_100ml`
- **Notes:** Turbidity spikes can follow heavy rainfall overwhelming filtration systems.

---

## Public Safety

### NYC Evictions
- **Endpoint:** `https://data.cityofnewyork.us/resource/6z8x-wfk4.json`
- **Lag:** ~1 day (most recent: 2026-04-02)
- **Granularity:** Per eviction event
- **Key fields:** `executed_date`, `borough`, `eviction_zip`, `residential_commercial_ind`, `bbl`, `latitude`, `longitude`, `community_board`, `council_district`
- **Notes:** Only dataset with near-daily resolution on a housing stress metric. Joinable to HPD violations and property sales by `bbl`.
- **Sample query:**
  ```
  $order=executed_date DESC&$limit=1000&$where=executed_date >= '2026-01-01T00:00:00'
  ```

### NYPD Arrest Data (Year to Date)
- **Endpoint:** `https://data.cityofnewyork.us/resource/uip8-fykc.json`
- **Lag:** ~1 day (most recent: 2026-04-02)
- **Granularity:** Per arrest
- **Key fields:** `arrest_date`, `ofns_desc`, `law_cat_cd` (felony/misdemeanor/violation), `arrest_boro`, `arrest_precinct`, `age_group`, `perp_sex`, `perp_race`
- **Sample query:**
  ```
  $order=arrest_date DESC&$where=arrest_date >= '2026-01-01T00:00:00'&$limit=50000
  ```

### NYPD Shooting Incidents
- **Endpoint:** `https://data.cityofnewyork.us/resource/5ucz-vwe8.json`
- **Lag:** ~3 months (most recent: 2025-12-31)
- **Granularity:** Per incident
- **Key fields:** `occur_date`, `occur_time`, `boro`, `precinct`, `statistical_murder_flag`, `latitude`, `longitude`

---

## Housing & Built Environment

### DOB Building Permit Issuance
- **Endpoint:** `https://data.cityofnewyork.us/resource/ipu4-2q9a.json`
- **Lag:** Near-daily
- **Granularity:** Per permit
- **Key fields:** `filing_date`, `job_type` (A1/A2/A3=alteration, NB=new building, DM=demolition), `work_type`, `borough`, `zip_code`, `bbl`, `gis_latitude`, `gis_longitude`
- **CAVEAT:** Date fields (`filing_date`, `issuance_date`) are stored as `MM/DD/YYYY` text strings, not ISO format. `$order` on these fields sorts lexicographically, not chronologically. Use `$where` with string comparison carefully, or fetch and filter in pandas after converting: `pd.to_datetime(df['filing_date'], format='%m/%d/%Y')`.

### HPD Housing Maintenance Code Violations
- **Endpoint:** `https://data.cityofnewyork.us/resource/wvxf-dwi5.json`
- **Lag:** ~3 days (most recent: 2026-03-31)
- **Granularity:** Per violation, per building
- **Key fields:** `inspectiondate`, `violationid`, `class` (A/B/C — C is immediately hazardous), `novdescription`, `building_id`, `boroid`, `zip`, `latitude`, `longitude`
- **Notes:** Class C violations (immediately hazardous) are the most actionable signal — heat outages in winter, lead paint, structural issues. Joinable to evictions by `bbl`.
- **Sample query:**
  ```
  $order=inspectiondate DESC&$where=class='C'&$limit=10000
  ```

### NYC Citywide Property Sales
- **Endpoint:** `https://data.cityofnewyork.us/resource/w2pb-icbu.json`
- **Lag:** ~3 months (most recent: 2024-12-31)
- **Granularity:** Per sale
- **Key fields:** `sale_date`, `sale_price`, `borough`, `neighborhood`, `building_class_at_time_of_sale`, `year_built`, `gross_square_feet`, `bbl`

---

## Health & Social Services

### DOHMH Restaurant Inspection Results
- **Endpoint:** `https://data.cityofnewyork.us/resource/43nn-pn8j.json`
- **Lag:** ~1 day (most recent: 2026-04-02)
- **Granularity:** Per inspection
- **Key fields:** `inspection_date`, `dba` (restaurant name), `cuisine_description`, `violation_code`, `critical_flag`, `score`, `grade`, `zipcode`, `latitude`, `longitude`
- **Notes:** 27,000+ active restaurants. High-volume daily signal for neighborhood commercial activity; closures and grade changes are economic indicators.
- **Sample query:**
  ```
  $order=inspection_date DESC&$limit=10000&$where=inspection_date >= '2026-01-01T00:00:00'
  ```

### NYC Unemployment (LAUS — Local Area)
- **Endpoint:** `https://data.ny.gov/resource/dh9m-5v4d.json`
- **Lag:** ~2–3 months (most recent: Jan 2026)
- **Granularity:** Monthly, by area
- **Key fields:** `year`, `month`, `area`, `labor_force`, `employed`, `unemployed`, `unemployment_rate`
- **Notes:** Filter to NYC: `$where=area='New York City'`. Returns seasonally adjusted BLS figures.
- **Sample query:**
  ```
  $where=area='New York City'&$order=year DESC,month DESC&$limit=60
  ```

---

## Events

### NYC Film Permits
- **Endpoint:** `https://data.cityofnewyork.us/resource/tg4x-b46p.json`
- **Lag:** Near-daily (permits filed in advance; most recent event start: 2026-01-02)
- **Granularity:** Per permit (event-level)
- **Key fields:** `startdatetime`, `enddatetime`, `category` (Feature Film, TV, Commercial, News, etc.), `subcategoryname`, `borough`, `zipcode_s`, `policeprecinct_s`, `parkingheld`
- **Notes:** Film permits cause localized street closures and correlate with 311 noise spikes. `parkingheld` gives the exact street segments affected. Query by `startdatetime` for prospective features.
- **Sample query:**
  ```
  $order=startdatetime DESC&$limit=1000
  ```

---

## Confirmed Failures (Do Not Use)

| Dataset | Endpoint | Issue |
|---|---|---|
| NYC Air Quality (DOHMH) | `c3uy-2p5r` | Most recent data is Summer 2023 — >2 year lag. Exceeds 6-month threshold. |

---

## Access Pattern Reference

```python
import requests
import requests_cache

session = requests_cache.CachedSession("data/00_cache/<source>", expire_after=86400)

# Socrata (NYC Open Data / data.ny.gov)
r = session.get(
    "https://data.cityofnewyork.us/resource/<dataset-id>.json",
    params={
        "$where": "date_col >= '2026-01-01T00:00:00'",
        "$order": "date_col DESC",
        "$limit": "10000",
    },
    timeout=60,
)
r.raise_for_status()
df = pd.DataFrame(r.json())

# CitiBike GBFS (no caching — real-time only)
r = requests.get("https://gbfs.lyft.com/gbfs/1.1/bkn/en/station_status.json", timeout=10)
stations = r.json()["data"]["stations"]
```
