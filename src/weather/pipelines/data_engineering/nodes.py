import io
import zipfile

import pandas as pd
import requests
import requests_cache
from retry_requests import retry

_WMO = {
    0: "clear",  1: "clear",  2: "cloudy", 3: "cloudy", 45: "cloudy", 48: "cloudy",
    51: "rainy", 53: "rainy", 55: "rainy",  56: "rainy",  57: "rainy",
    61: "rainy", 63: "rainy", 65: "rainy",  66: "rainy",  67: "rainy",
    71: "snowy", 73: "snowy", 75: "snowy",  77: "snowy",
    80: "rainy", 81: "rainy", 82: "rainy",
    85: "snowy", 86: "snowy", 95: "rainy",  96: "rainy",  99: "rainy",
}
_PRECIP_ORDER = ["clear", "cloudy", "rainy", "snowy"]
_TEMP_ORDER   = ["cold", "temperate", "hot"]


def _fetch_openmeteo(start: str, end: str, lat: float, lon: float,
                     cold_c: float, hot_c: float) -> pd.DataFrame:
    session = retry(
        requests_cache.CachedSession(".openmeteo_cache", expire_after=86400),
        retries=5, backoff_factor=0.3,
    )
    r = session.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "hourly": ["temperature_2m", "apparent_temperature", "precipitation",
                   "snowfall", "weathercode", "cloudcover",
                   "windspeed_10m", "relativehumidity_2m", "visibility"],
        "timezone": "America/New_York",
    })
    r.raise_for_status()
    h = r.json()["hourly"]

    df = pd.DataFrame({
        "temperature_c":    h["temperature_2m"],
        "apparent_temp_c":  h["apparent_temperature"],
        "precipitation_mm": h["precipitation"],
        "snowfall_cm":      h["snowfall"],
        "weathercode":      h["weathercode"],
        "cloudcover_pct":   h["cloudcover"],
        "windspeed_kmh":    h["windspeed_10m"],
        "humidity_pct":     h["relativehumidity_2m"],
        "visibility_m":     h["visibility"],
    }, index=pd.to_datetime(h["time"]))
    df.index.name = "timestamp"

    df["precip"] = pd.Categorical(
        df["weathercode"].map(lambda c: _WMO.get(c, "cloudy")),
        categories=_PRECIP_ORDER, ordered=True,
    )
    df["temp"] = pd.Categorical(
        df["temperature_c"].apply(
            lambda t: "cold" if t < cold_c else "hot" if t > hot_c else "temperate"
        ),
        categories=_TEMP_ORDER, ordered=True,
    )
    df["precip_int"] = df["precip"].cat.codes
    df["temp_int"]   = df["temp"].cat.codes
    return df


def _fetch_nyiso_month(year: int, month: int) -> pd.Series:
    url = f"https://mis.nyiso.com/public/csv/pal/{year}{month:02d}01pal_csv.zip"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        frames = [pd.read_csv(z.open(name)) for name in z.namelist()]
    raw = pd.concat(frames, ignore_index=True)
    nyc = raw[raw["Name"].str.strip() == "N.Y.C."].copy()
    nyc["timestamp"] = (
        pd.to_datetime(nyc["Time Stamp"]) - pd.Timedelta(minutes=5)
    ).dt.floor("h")
    return nyc.groupby("timestamp")["Load"].mean().rename("nyiso_load_mw")


def _fetch_nyiso(start: str, end: str) -> pd.DataFrame:
    parts = []
    for p in pd.period_range(start, end, freq="M"):
        try:
            parts.append(_fetch_nyiso_month(p.year, p.month))
        except Exception as e:
            print(f"WARNING NYISO {p.year}-{p.month:02d}: {e}")
    return pd.concat(parts).sort_index().to_frame()


def _fetch_mta(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/mta", expire_after=86400)
    r = session.get("https://data.ny.gov/resource/sayj-mze2.json", params={
        "$where": f"date >= '{start}T00:00:00' and date <= '{end}T23:59:59'",
        "$order": "date ASC",
        "$limit": "10000",
    }, timeout=60)
    r.raise_for_status()
    raw = pd.DataFrame(r.json())
    if raw.empty:
        return pd.DataFrame()
    raw["date"]  = pd.to_datetime(raw["date"]).dt.normalize()
    raw["count"] = pd.to_numeric(raw["count"], errors="coerce")
    pivot = (
        raw[raw["mode"].isin(["Subway", "Bus"])]
        .pivot_table(index="date", columns="mode", values="count", aggfunc="sum")
        .rename(columns={"Subway": "mta_subway", "Bus": "mta_bus"})
    )
    pivot.index.name = "date"
    return pivot


def _fetch_311(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/311", expire_after=86400)
    types = ["HEAT/HOT WATER", "Street Flooding", "Flooded Basement", "Snow"]
    type_list = ", ".join(f"'{t}'" for t in types)
    r = session.get("https://data.cityofnewyork.us/resource/erm2-nwe9.json", params={
        "$select": "date_trunc_ymd(created_date) as date, complaint_type, count(*) as cnt",
        "$group":  "date_trunc_ymd(created_date), complaint_type",
        "$where": (
            f"complaint_type in ({type_list})"
            f" and created_date >= '{start}T00:00:00'"
            f" and created_date <= '{end}T23:59:59'"
        ),
        "$limit": "50000",
    }, timeout=120)
    r.raise_for_status()
    raw = pd.DataFrame(r.json())
    if raw.empty:
        return pd.DataFrame()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    raw["cnt"]  = pd.to_numeric(raw["cnt"], errors="coerce").fillna(0).astype(int)
    pivot = (
        raw.pivot_table(index="date", columns="complaint_type",
                        values="cnt", aggfunc="sum", fill_value=0)
           .rename(columns={
               "HEAT/HOT WATER":   "311_heat",
               "Street Flooding":  "311_flood_street",
               "Flooded Basement": "311_flood_basement",
               "Snow":             "311_snow",
           })
    )
    flood_cols = [c for c in pivot.columns if c.startswith("311_flood_")]
    if flood_cols:
        pivot["311_flood"] = pivot[flood_cols].sum(axis=1)
        pivot = pivot.drop(columns=flood_cols)
    pivot.index.name = "date"
    return pivot


def _fetch_crashes(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/crashes", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/h9gi-nx95.json", params={
        "$select": (
            "date_trunc_ymd(crash_date) as date,"
            " count(*) as crashes_total,"
            " sum(case(contributing_factor_vehicle_1='Pavement Slippery',1,true,0)) as crashes_slippery"
        ),
        "$group":  "date_trunc_ymd(crash_date)",
        "$where":  f"crash_date >= '{start}T00:00:00' AND crash_date <= '{end}T23:59:59'",
        "$order":  "date ASC",
        "$limit":  "5000",
    }, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"]             = pd.to_datetime(df["date"]).dt.normalize()
    df["crashes_total"]    = pd.to_numeric(df["crashes_total"],    errors="coerce").fillna(0).astype(int)
    df["crashes_slippery"] = pd.to_numeric(df["crashes_slippery"], errors="coerce").fillna(0).astype(int)
    return df.set_index("date")[["crashes_total", "crashes_slippery"]]


def fetch_raw(
    start_date: str, end_date: str,
    nyc_lat: float, nyc_lon: float,
    cold_c: float, hot_c: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        _fetch_openmeteo(start_date, end_date, nyc_lat, nyc_lon, cold_c, hot_c),
        _fetch_nyiso(start_date, end_date),
        _fetch_mta(start_date, end_date),
        _fetch_311(start_date, end_date),
        _fetch_crashes(start_date, end_date),
    )


def merge_features(
    raw_openmeteo: pd.DataFrame,
    raw_nyiso: pd.DataFrame,
    raw_mta: pd.DataFrame,
    raw_311: pd.DataFrame,
    raw_crashes: pd.DataFrame,
    mta_lag: int,
    lag_311: int,
    crashes_lag: int,
    lag_window: int,
) -> pd.DataFrame:
    def _lag_join(hourly: pd.DataFrame, daily: pd.DataFrame, lag: int, window: int) -> pd.DataFrame:
        daily_h = daily.reindex(hourly.index, method="ffill")
        lagged  = daily_h.shift(lag * 24).rolling(window * 24, min_periods=1).mean()
        return hourly.join(lagged, how="left")

    hourly = raw_openmeteo.join(raw_nyiso, how="left")

    if not raw_mta.empty:
        hourly = _lag_join(hourly, raw_mta, mta_lag, lag_window)

    if not raw_311.empty:
        hourly = _lag_join(hourly, raw_311, lag_311, lag_window)

    if not raw_crashes.empty:
        hourly = _lag_join(hourly, raw_crashes, crashes_lag, lag_window)

    return hourly
