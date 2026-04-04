import io
import logging
import time
import zipfile

import pandas as pd
import requests
import requests_cache
from retry_requests import retry

log = logging.getLogger(__name__)


def _log_fetch(name: str, df: pd.DataFrame, elapsed: float) -> None:
    if df.empty:
        log.info("fetch %-22s  rows=0  [%.1fs]", name, elapsed)
        return
    idx = df.index
    date_range = f"{idx.min().date()} → {idx.max().date()}"
    null_frac  = df.isnull().mean().mean()
    cols       = ", ".join(df.columns.tolist())
    log.info(
        "fetch %-22s  rows=%-6d  %s  null=%.0f%%  cols=[%s]  [%.1fs]",
        name, len(df), date_range, null_frac * 100, cols, elapsed,
    )

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
        requests_cache.CachedSession("data/00_cache/openmeteo", expire_after=86400),
        retries=5, backoff_factor=0.3,
    )
    r = session.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "hourly": ["temperature_2m", "precipitation", "snowfall", "weathercode"],
        "timezone": "America/New_York",
    }, timeout=60)
    r.raise_for_status()
    h = r.json()["hourly"]

    temperature_c = pd.Series(h["temperature_2m"])
    weathercode   = pd.Series(h["weathercode"])
    index         = pd.to_datetime(h["time"])

    tgt_precip = pd.Categorical(
        weathercode.map(lambda c: _WMO.get(c, "cloudy")),
        categories=_PRECIP_ORDER, ordered=True,
    )
    tgt_temp = pd.Categorical(
        temperature_c.apply(
            lambda t: "cold" if t < cold_c else "hot" if t > hot_c else "temperate"
        ),
        categories=_TEMP_ORDER, ordered=True,
    )
    df = pd.DataFrame({
        "tgt_precip":     tgt_precip,
        "tgt_temp":       tgt_temp,
        "tgt_precip_int": tgt_precip.codes,
        "tgt_temp_int":   tgt_temp.codes,
    }, index=index)
    df.index.name = "timestamp"
    return df


_nyiso_session = requests_cache.CachedSession("data/00_cache/nyiso", expire_after=86400)


def _fetch_nyiso_month(year: int, month: int) -> pd.Series:
    url = f"https://mis.nyiso.com/public/csv/pal/{year}{month:02d}01pal_csv.zip"
    r = _nyiso_session.get(url, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        frames = [pd.read_csv(z.open(name)) for name in z.namelist()]
    raw = pd.concat(frames, ignore_index=True)
    nyc = raw[raw["Name"].str.strip() == "N.Y.C."].copy()
    nyc["timestamp"] = (
        pd.to_datetime(nyc["Time Stamp"]) - pd.Timedelta(minutes=5)
    ).dt.floor("h")
    return nyc.groupby("timestamp")["Load"].mean().rename("ft_nyiso_load_mw")


def _fetch_nyiso(start: str, end: str) -> pd.DataFrame:
    parts = []
    months = list(pd.period_range(start, end, freq="M"))
    for p in months:
        try:
            parts.append(_fetch_nyiso_month(p.year, p.month))
        except Exception as e:
            log.warning("NYISO %s-%02d: %s", p.year, p.month, e)
    return pd.concat(parts).sort_index().to_frame()


def _fetch_mta(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/mta", expire_after=86400)
    r = session.get("https://data.ny.gov/resource/sayj-mze2.json", params={
        "$where": f"mode in ('Subway', 'Bus', 'LIRR') and date >= '{start}T00:00:00' and date <= '{end}T23:59:59'",
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
        raw.pivot_table(index="date", columns="mode", values="count", aggfunc="sum")
           .rename(columns={"Subway": "ft_mta_subway", "Bus": "ft_mta_bus", "LIRR": "ft_mta_lirr"})
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
               "HEAT/HOT WATER":   "ft_311_heat",
               "Street Flooding":  "ft_311_flood_street",
               "Flooded Basement": "ft_311_flood_basement",
               "Snow":             "ft_311_snow",
           })
    )
    flood_cols = [c for c in pivot.columns if c.startswith("ft_311_flood_")]
    if flood_cols:
        pivot["ft_311_flood"] = pivot[flood_cols].sum(axis=1)
        pivot = pivot.drop(columns=flood_cols)
    pivot.index.name = "date"
    return pivot


def _fetch_crashes(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/crashes", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/h9gi-nx95.json", params={
        "$select": (
            "date_trunc_ymd(crash_date) as date,"
            " count(*) as ft_crashes_total,"
            " sum(case(contributing_factor_vehicle_1='Pavement Slippery',1,true,0)) as ft_crashes_slippery"
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
    df["date"]               = pd.to_datetime(df["date"]).dt.normalize()
    df["ft_crashes_total"]    = pd.to_numeric(df["ft_crashes_total"],    errors="coerce").fillna(0).astype(int)
    df["ft_crashes_slippery"] = pd.to_numeric(df["ft_crashes_slippery"], errors="coerce").fillna(0).astype(int)
    return df.set_index("date")[["ft_crashes_total", "ft_crashes_slippery"]]



def _fetch_floodnet(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/floodnet", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/aq7i-eu5q.json", params={
        "$select": "flood_start_time, max_depth_inches",
        "$where":  f"flood_start_time >= '{start}T00:00:00' AND flood_start_time <= '{end}T23:59:59'",
        "$order":  "flood_start_time ASC",
        "$limit":  "10000",
    }, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"]             = pd.to_datetime(df["flood_start_time"]).dt.normalize()
    df["max_depth_inches"] = pd.to_numeric(df["max_depth_inches"], errors="coerce").fillna(0)
    daily = df.groupby("date").agg(
        ft_floodnet_events=("date", "count"),
        ft_floodnet_max_depth_in=("max_depth_inches", "max"),
    )
    daily.index.name = "date"
    return daily


def _fetch_bike_ped(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/bike_ped", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/ct66-47at.json", params={
        "$select": "date_trunc_ymd(timestamp) as date, travelmode, sum(counts) as total",
        "$group":  "date_trunc_ymd(timestamp), travelmode",
        "$where":  f"timestamp >= '{start}T00:00:00' AND timestamp <= '{end}T23:59:59'",
        "$limit":  "50000",
    }, timeout=120)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"]  = pd.to_datetime(df["date"]).dt.normalize()
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    pivot = (
        df.pivot_table(index="date", columns="travelmode", values="total", aggfunc="sum", fill_value=0)
          .rename(columns=lambda c: f"ft_ped_{c.lower().replace(' ', '_')}")
    )
    pivot.index.name = "date"
    return pivot


def _fetch_congestion_zone(start: str, end: str) -> pd.DataFrame:
    # Data only available from Jan 2025 — returns empty for earlier dates
    session = requests_cache.CachedSession("data/00_cache/congestion_zone", expire_after=86400)
    r = session.get("https://data.ny.gov/resource/t6yz-b64h.json", params={
        "$select": "date_trunc_ymd(toll_hour) as date, sum(crz_entries) as ft_cz_total",
        "$group":  "date_trunc_ymd(toll_hour)",
        "$where":  f"toll_hour >= '{start}T00:00:00' AND toll_hour <= '{end}T23:59:59'",
        "$order":  "date ASC",
        "$limit":  "5000",
    }, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"]        = pd.to_datetime(df["date"]).dt.normalize()
    df["ft_cz_total"] = pd.to_numeric(df["ft_cz_total"], errors="coerce").fillna(0).astype(int)
    return df.set_index("date")[["ft_cz_total"]]


def _fetch_evictions(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/evictions", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/6z8x-wfk4.json", params={
        "$select": "date_trunc_ymd(executed_date) as date, count(*) as ft_evictions",
        "$group":  "date_trunc_ymd(executed_date)",
        "$where":  f"executed_date >= '{start}T00:00:00' AND executed_date <= '{end}T23:59:59'",
        "$order":  "date ASC",
        "$limit":  "5000",
    }, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"]         = pd.to_datetime(df["date"]).dt.normalize()
    df["ft_evictions"] = pd.to_numeric(df["ft_evictions"], errors="coerce").fillna(0).astype(int)
    return df.set_index("date")[["ft_evictions"]]


def _fetch_dot_speeds(start: str, end: str) -> pd.DataFrame:
    # speed is stored as text — avg() fails server-side; must fetch raw and aggregate in pandas.
    # One call per day (~35k rows, fits in $limit=50000). Cached: one-time ~33 min backfill.
    session = requests_cache.CachedSession("data/00_cache/dot_speeds", expire_after=86400)
    parts = []
    for day in pd.date_range(start, end, freq="D"):
        next_day = day + pd.Timedelta(days=1)
        try:
            r = session.get("https://data.cityofnewyork.us/resource/i4gi-tjb9.json", params={
                "$select": "speed",
                "$where":  f"data_as_of >= '{day.strftime('%Y-%m-%d')}T00:00:00' AND data_as_of < '{next_day.strftime('%Y-%m-%d')}T00:00:00'",
                "$limit":  "50000",
            }, timeout=30)
            r.raise_for_status()
            df_day = pd.DataFrame(r.json())
            if df_day.empty:
                continue
            df_day["speed"] = pd.to_numeric(df_day["speed"], errors="coerce")
            parts.append({"date": day.normalize(), "ft_dot_speed_avg": df_day["speed"].mean()})
        except Exception as e:
            print(f"WARNING DOT {day.date()}: {e}")
    if not parts:
        return pd.DataFrame()
    daily = pd.DataFrame(parts).set_index("date")
    daily["ft_dot_speed_delta"] = daily["ft_dot_speed_avg"].diff(1)
    return daily


def fetch_raw(
    start_date: str, end_date: str,
    nyc_lat: float, nyc_lon: float,
    cold_c: float, hot_c: float,
    dot_start_date: str,
) -> tuple:
    def _timed(name: str, fn, *args):
        log.info("fetch %-22s  starting...", name)
        t0 = time.perf_counter()
        try:
            df = fn(*args)
        except Exception as exc:
            log.warning("fetch %-22s  FAILED — returning empty  [%.1fs]  %s",
                        name, time.perf_counter() - t0, exc)
            return pd.DataFrame()
        _log_fetch(name, df, time.perf_counter() - t0)
        return df

    raw_nyiso = _timed("nyiso", _fetch_nyiso, start_date, end_date)
    if raw_nyiso.empty:
        log.warning("nyiso fetch failed — using hourly date spine fallback (%s → %s)",
                    start_date, end_date)
        raw_nyiso = pd.DataFrame(
            {"ft_nyiso_load_mw": float("nan")},
            index=pd.date_range(start_date, end_date, freq="h"),
        )
        raw_nyiso.index.name = "timestamp"

    return (
        _timed("openmeteo",       _fetch_openmeteo, start_date, end_date, nyc_lat, nyc_lon, cold_c, hot_c),
        raw_nyiso,
        _timed("mta",             _fetch_mta,             start_date, end_date),
        _timed("311",             _fetch_311,             start_date, end_date),
        _timed("crashes",         _fetch_crashes,         start_date, end_date),
        _timed("floodnet",        _fetch_floodnet,        start_date, end_date),
        _timed("bike_ped",        _fetch_bike_ped,        start_date, end_date),
        _timed("congestion_zone", _fetch_congestion_zone, start_date, end_date),
        _timed("evictions",       _fetch_evictions,       start_date, end_date),
        _timed("dot_speeds",      _fetch_dot_speeds,      dot_start_date, end_date),
    )


def merge_features(
    raw_openmeteo: pd.DataFrame,
    raw_nyiso: pd.DataFrame,
    raw_mta: pd.DataFrame,
    raw_311: pd.DataFrame,
    raw_crashes: pd.DataFrame,
    raw_floodnet: pd.DataFrame,
    raw_bike_ped: pd.DataFrame,
    raw_cz: pd.DataFrame,
    raw_evictions: pd.DataFrame,
    raw_dot: pd.DataFrame,
    mta_lag: int,
    lag_311: int,
    crashes_lag: int,
    floodnet_lag: int,
    bike_ped_lag: int,
    cz_lag: int,
    evictions_lag: int,
    dot_lag: int,
    lag_window: int,
) -> pd.DataFrame:
    def _lag_join(hourly: pd.DataFrame, daily: pd.DataFrame, lag: int, window: int) -> pd.DataFrame:
        if not isinstance(daily.index, pd.DatetimeIndex):
            raise TypeError(f"_lag_join expects DatetimeIndex, got {type(daily.index).__name__}")
        daily = daily[~daily.index.duplicated(keep="first")].sort_index()
        daily.index = daily.index.tz_localize(None) if daily.index.tz else daily.index
        full_days = pd.date_range(daily.index.min(), hourly.index.max().normalize(), freq="D")
        daily = daily.reindex(full_days, method="ffill")
        daily_h = daily.reindex(hourly.index, method="ffill")
        lagged  = daily_h.shift(lag * 24).rolling(window * 24, min_periods=1).mean()
        return hourly.join(lagged, how="left")

    hourly = raw_nyiso.join(raw_openmeteo, how="left")
    hourly = hourly[~hourly.index.duplicated(keep="first")]  # remove DST duplicate hours
    hourly["ft_nyiso_delta_3h"] = hourly["ft_nyiso_load_mw"].diff(3)

    for raw, lag in [
        (raw_mta,      mta_lag),
        (raw_311,      lag_311),
        (raw_crashes,  crashes_lag),
        (raw_floodnet, floodnet_lag),
        (raw_bike_ped, bike_ped_lag),
        (raw_cz,       cz_lag),
        (raw_evictions, evictions_lag),
        (raw_dot,      dot_lag),
    ]:
        if not raw.empty:
            hourly = _lag_join(hourly, raw, lag, lag_window)

    return hourly
