# NYC Free API Reference

All endpoints verified via live API call on 2026-04-03 (Ferry + MLB verified 2026-04-04).

All Socrata endpoints follow the pattern:
```
https://<domain>/resource/<dataset-id>.json?$limit=N&$order=<date_col>+DESC&$where=...
```
No authentication required. For higher rate limits, register a free app token at
dev.socrata.com and pass it as `$$app_token=<token>`.

---

## Ground Truth / Labels

### Open-Meteo ERA5 Reanalysis
- **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`
- **Lag:** ~5 days (ERA5 reanalysis has a processing delay)
- **Granularity:** Hourly, per coordinate
- **Key fields:** `hourly.time`, `hourly.temperature_2m`, `hourly.precipitation`, `hourly.snowfall`, `hourly.weathercode`
- **Notes:** Used as ground truth labels only — not a feature input. WMO weather codes map to `_PRECIP_ORDER` classes; temperature thresholds map to `_TEMP_ORDER` classes. Cached via `requests_cache` with a 24h TTL. No API key required. ERA5 lag means recent rows have NaN labels — inference only needs proxy features so this is fine.
- **Sample query:**
  ```python
  params={
      "latitude": 40.7128, "longitude": -74.0060,
      "start_date": "2020-01-01", "end_date": "2026-04-04",
      "hourly": ["temperature_2m", "precipitation", "snowfall", "weathercode"],
      "timezone": "America/New_York",
  }
  ```

---

## Transport & Mobility

### NYISO Zone J Real-Time Load
- **Endpoint:** `https://mis.nyiso.com/public/csv/pal/{YYYY}{MM}01pal_csv.zip`
- **Lag:** ~0.2h (real-time, published every 5 minutes)
- **Granularity:** 5-minute intervals, by zone
- **Key fields:** `Time Stamp`, `Name` (zone), `Load` (MW)
- **Notes:** Not a Socrata API — monthly ZIP files, each containing one CSV per day. Filter to `Name == "N.Y.C."` for Zone J. Timestamps are 5 minutes ahead of the interval end; subtract 5 min and floor to hour to align with the hourly index. Base index for `merge_features` — all other sources are joined onto NYISO's hourly grid.
- **Sample fetch:**
  ```python
  url = f"https://mis.nyiso.com/public/csv/pal/{year}{month:02d}01pal_csv.zip"
  r = requests.get(url, timeout=30)
  with zipfile.ZipFile(io.BytesIO(r.content)) as z:
      frames = [pd.read_csv(z.open(name)) for name in z.namelist()]
  ```

### MTA Ridership by Mode
- **Endpoint:** `https://data.ny.gov/resource/sayj-mze2.json`
- **Lag:** ~1 day (most recent: 2026-04-02)
- **Granularity:** Daily, by mode
- **Key fields:** `date`, `mode` (Subway / Bus / LIRR / Metro-North / Access-A-Ride / Bridges and Tunnels / Staten Island Railway), `count`
- **Notes:** Filter `$where` to `mode in ('Subway', 'Bus', 'LIRR')` — fetching all modes hits `$limit=10000` and truncates other sources. MTA hourly-by-borough datasets (f462-ka72 / 5wq4-mkjj) were evaluated but have ~180h publication lag — too stale.
- **Sample query:**
  ```
  $where=mode in ('Subway', 'Bus', 'LIRR') and date >= '2026-01-01T00:00:00'&$order=date ASC&$limit=10000
  ```

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
- **File naming:** `YYYYMM-citibike-tripdata.zip` (no `.csv` in name for files from ~mid-2025 onward; older files used `.csv.zip`)
- **Jersey City subset:** `JC-YYYYMM-citibike-tripdata.csv.zip` — same schema, ~5MB vs 200-500MB for NYC-wide files
- **CAVEAT:** NYC-wide monthly files are 200–500MB. A 4-year backfill requires ~24GB of downloads. For lightweight feasibility testing use the JC subset. For production, consider whether the volume justifies the storage cost.
- **Notes:** Current month file is not published — start lookback from previous month. Parse with `zipfile` + `pandas` directly from the in-memory response.

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

### NYC Ferry Ridership
- **Endpoint:** `https://data.cityofnewyork.us/resource/t5n6-gx8c.json`
- **Lag:** ~2 months (most recent: 2026-01-28)
- **Granularity:** Per hour, per route, per stop
- **Key fields:** `date`, `hour`, `route`, `direction`, `stop`, `boardings`, `typeday` (Weekday/Weekend)
- **Notes:** Aggregate all routes daily for a city-level outdoor activity signal. Ferry ridership drops sharply in bad weather. Server-side `date_trunc_ymd` + `sum(boardings)` aggregation works cleanly.
- **Sample query (daily totals):**
  ```
  $select=date_trunc_ymd(date) as day, sum(boardings) as total_boardings&$group=date_trunc_ymd(date)&$order=day DESC&$limit=1000
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

## City Services

### NYC 311 Service Requests
- **Endpoint:** `https://data.cityofnewyork.us/resource/erm2-nwe9.json`
- **Lag:** ~2 days
- **Granularity:** Per complaint
- **Key fields:** `created_date`, `complaint_type`, `descriptor`, `borough`, `incident_zip`, `latitude`, `longitude`
- **Notes:** Currently used for Heat/Hot Water, Street Flooding, Flooded Basement, and Snow complaint types, aggregated citywide. Has `borough` field — see **Location Specificity** section below for per-borough breakdown. 24M+ rows total; always filter by `created_date` and `complaint_type` to avoid hitting limits.
- **Sample query (daily counts by complaint type):**
  ```
  $select=date_trunc_ymd(created_date) as date, complaint_type, count(*) as cnt&$group=date_trunc_ymd(created_date), complaint_type&$where=complaint_type in ('HEAT/HOT WATER','Street Flooding','Snow') and created_date >= '2026-01-01T00:00:00'&$limit=50000
  ```

### Motor Vehicle Crashes
- **Endpoint:** `https://data.cityofnewyork.us/resource/h9gi-nx95.json`
- **Lag:** ~5 days (tight — only ~6h margin above publication lag)
- **Granularity:** Per crash
- **Key fields:** `crash_date`, `borough`, `zip_code`, `latitude`, `longitude`, `contributing_factor_vehicle_1`, `number_of_persons_injured`, `number_of_persons_killed`
- **Notes:** Used for total crash count and `Pavement Slippery` contributing factor. Has `borough` field — per-borough breakdown is feasible. Server-side `sum(case(...))` for slippery pavement works correctly.
- **Sample query (daily total + slippery):**
  ```
  $select=date_trunc_ymd(crash_date) as date, count(*) as total, sum(case(contributing_factor_vehicle_1='Pavement Slippery',1,true,0)) as slippery&$group=date_trunc_ymd(crash_date)&$where=crash_date >= '2026-01-01T00:00:00'&$order=date ASC&$limit=5000
  ```

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

### NYC Permitted Events (CECM)
- **Endpoint:** `https://data.cityofnewyork.us/resource/tvpp-9vvx.json`
- **Lag:** Near-real-time (permits filed in advance; dataset spans from 2024-06-30 onward)
- **Granularity:** Per permitted event
- **Key fields:** `event_name`, `start_date_time`, `end_date_time`, `event_type`, `event_agency`, `event_borough`, `event_location`, `street_closure_type`
- **Event types (by volume):** Sport-Youth (24k), Sport-Adult (6.7k), Special Event (4.4k), Religious Event (144), Parade (32), Farmers Market (48), Street Festival (17)
- **Notes:** Managed by the Office of Citywide Event Coordination and Management. Includes future events (published in advance) and history back to mid-2024 only — too short for model training on its own. Most volume is youth/adult sports in parks. Weather-correlated subset: Parade + Street Festival + Farmers Market (~97 events total). Filter by `event_type` and `street_closure_type` for outdoor/street-impacting events.
- **CAVEAT:** Only ~2 years of history. Useful as a live feature but will have near-zero SHAP weight until more data accumulates.
- **Sample query (street-impacting events):**
  ```
  $where=start_date_time >= '2024-06-30T00:00:00' and event_type in ('Parade','Street Festival','Farmers Market','Special Event')&$order=start_date_time DESC&$limit=5000
  ```

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

## Sports & Entertainment

### NHL — Rangers & Islanders Home Game Schedule
- **Endpoint:** `https://api-web.nhle.com/v1/club-schedule-season/{TEAM}/{SEASON}`
- **Lag:** Live (scores within minutes of game end; schedule published months in advance)
- **Granularity:** Per game
- **Key fields:** `gameDate`, `homeTeam.abbrev`, `homeTeam.score`, `awayTeam.abbrev`, `awayTeam.score`, `gameState` (`FUT`=future, `LIVE`=in progress, `OFF`=final), `venue.default`
- **Team codes:** Rangers = `NYR` (Madison Square Garden), Islanders = `NYI` (UBS Arena, Elmont)
- **Season format:** `20252026` for the 2025-26 season. No API key required.
- **Notes:** Each team plays 44 home games/season (Oct–Apr). Use `homeTeam.abbrev in (NYR, NYI)` to filter home dates. MSG home games drive heavy midtown foot traffic. UBS Arena is in Nassau County so Islander games have lower direct NYC transit impact.
- **Sample fetch:**
  ```
  GET https://api-web.nhle.com/v1/club-schedule-season/NYR/20252026
  ```

### MLB — Mets & Yankees Home Game Schedule
- **Endpoint:** `https://statsapi.mlb.com/api/v1/schedule`
- **Lag:** Live (schedule published months in advance; scores within hours of game end)
- **Granularity:** Per game
- **Key fields:** `dates[].date`, `dates[].games[].teams.home.team.id`, `dates[].games[].venue.name`
- **Team IDs:** Mets = 121, Yankees = 147. Citi Field and Yankee Stadium are the NYC home venues.
- **No API key required.** No auth. Standard JSON response.
- **Notes:** Use `teams.home.team.id in (121, 147)` to filter for NYC home games. Home games drive subway ridership spikes and 311 noise complaints in the surrounding neighborhoods. Binary daily flag (home game Y/N) is the natural feature.
- **Sample query (Mets + Yankees, date range, regular season):**
  ```
  https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=121,147&startDate=2026-04-01&endDate=2026-04-30&gameType=R
  ```

---

## Location Specificity

Several sources carry a `borough` field that makes per-borough features trivially cheap to add. The tradeoff: more features, noisier signal per feature (smaller denominator), and a wider feature vector the model has to learn from.

### Sources with borough support

| Source | Field | Values |
|---|---|---|
| 311 complaints | `borough` | `MANHATTAN`, `BROOKLYN`, `QUEENS`, `BRONX`, `STATEN ISLAND` |
| Motor vehicle crashes | `borough` | same |
| Evictions | `borough` | same |
| NYPD arrests | `arrest_boro` | `M`, `K`, `Q`, `B`, `S` |
| Restaurant inspections | `borough` | same as 311 |
| HPD violations | `boroid` | `1`–`5` |

### How to pivot

Add `borough` to the `$group` clause and pivot the result:
```python
# 311 heat complaints by borough
$select=date_trunc_ymd(created_date) as date, borough, count(*) as cnt
$group=date_trunc_ymd(created_date), borough
$where=complaint_type='HEAT/HOT WATER' and created_date >= '...'

# In pandas:
pivot = df.pivot_table(index="date", columns="borough", values="cnt", aggfunc="sum", fill_value=0)
pivot.columns = [f"ft_311_heat_{b.lower().replace(' ', '_')}" for b in pivot.columns]
# → ft_311_heat_manhattan, ft_311_heat_brooklyn, ft_311_heat_queens, ft_311_heat_bronx, ft_311_heat_staten_island
```

### Silly use cases worth considering

- **Queens-only 311 flood complaints** — Citi Field sits in a flood-prone area of Flushing; Queens flooding 311 calls might be a sharper signal than citywide.
- **Bronx crash slippery pavement** — Yankee Stadium area has historically poor drainage; Bronx-only slippery crashes could precede snow/ice events.
- **Manhattan heat complaints** — Dense residential towers means Manhattan heat complaints spike earlier and harder than outer boroughs in heatwaves.
- **Borough crash ratios** — e.g., `ft_crashes_bronx / ft_crashes_total` as a normalized signal, insulated from baseline volume changes.

### Practical note

Borough expansion multiplies feature count by ~5 per source. With 3 complaint types × 5 boroughs you get 15 features instead of 3. The model handles this fine but training data per cell shrinks. Run feature importance after retraining — SHAP will tell you which boroughs are actually pulling weight.

---

## Confirmed Failures (Do Not Use)

| Dataset | Endpoint | Issue |
|---|---|---|
| NYC Air Quality (DOHMH) | `c3uy-2p5r` | Most recent data is Summer 2023 — >2 year lag. Exceeds 6-month threshold. |
| NBA stats (Knicks/Nets) | `stats.nba.com/stats/leaguegamelog` | Blocks non-browser requests; times out from WSL/server environments. Use the nba_api Python library as a workaround, but it's fragile. |
| NY Lottery | `data.ny.gov/resource/d6yy-54nr.json` | Only winning numbers and multiplier — no ticket sales volume. Not useful as a weather proxy. |
| NYC Parks Events | `data.cityofnewyork.us/resource/fudw-fgrp.json` | Dataset is stale; most recent record is 2018. |
| Broadway League grosses | broadwayleague.com | No machine-readable API. Weekly PDF/web only. Requires scraping. |
| NYRA horse racing handle | nyra.com | No API. Race schedules are on the website; betting handle is buried in PDF reports. |

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
