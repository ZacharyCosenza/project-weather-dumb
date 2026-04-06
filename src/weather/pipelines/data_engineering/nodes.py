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

def _fetch_openmeteo(start: str, end: str, lat: float, lon: float) -> pd.DataFrame:
    session = retry(
        requests_cache.CachedSession("data/00_cache/openmeteo", expire_after=86400),
        retries=5, backoff_factor=0.3,
    )
    r = session.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "hourly": ["temperature_2m"],
        "timezone": "America/New_York",
    }, timeout=60)
    r.raise_for_status()
    h = r.json()["hourly"]

    index = pd.to_datetime(h["time"])
    df = pd.DataFrame({"tgt_temp_c": h["temperature_2m"]}, index=index)
    df.index.name = "timestamp"
    return df


_nyiso_session      = requests_cache.CachedSession("data/00_cache/nyiso",      expire_after=86400)
_nyiso_session_live = requests_cache.CachedSession("data/00_cache/nyiso_live", expire_after=300)


def _fetch_nyiso_month(year: int, month: int) -> pd.Series:
    url = f"https://mis.nyiso.com/public/csv/pal/{year}{month:02d}01pal_csv.zip"
    now = pd.Timestamp.now()
    session = _nyiso_session_live if (year == now.year and month == now.month) else _nyiso_session
    r = session.get(url, timeout=30)
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
    # "Street Flooding" and "Flooded Basement" do not exist in 311 — verified empty.
    # "Snow or Ice" is the correct modern type; "Snow" covers older records pre-rename.
    session = requests_cache.CachedSession("data/00_cache/311", expire_after=86400)
    types = ["HEAT/HOT WATER", "Snow or Ice", "Snow"]
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
           .rename(columns={"HEAT/HOT WATER": "ft_311_heat"})
    )
    # Merge both snow type names into one column
    snow_cols = [c for c in pivot.columns if "Snow" in c or "snow" in c.lower()]
    if snow_cols:
        pivot["ft_311_snow"] = pivot[snow_cols].sum(axis=1)
        pivot = pivot.drop(columns=snow_cols)
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


def _fetch_restaurant(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/restaurant", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/43nn-pn8j.json", params={
        "$select": "date_trunc_ymd(inspection_date) as date, count(*) as ft_restaurant_inspections, sum(case(critical_flag='Critical',1,true,0)) as ft_restaurant_critical",
        "$group":  "date_trunc_ymd(inspection_date)",
        "$where":  f"inspection_date >= '{start}T00:00:00' AND inspection_date <= '{end}T23:59:59'",
        "$order":  "date ASC",
        "$limit":  "5000",
    }, timeout=60)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"]                      = pd.to_datetime(df["date"]).dt.normalize()
    df["ft_restaurant_inspections"] = pd.to_numeric(df["ft_restaurant_inspections"], errors="coerce").fillna(0).astype(int)
    df["ft_restaurant_critical"]    = pd.to_numeric(df["ft_restaurant_critical"],    errors="coerce").fillna(0).astype(int)
    return df.set_index("date")[["ft_restaurant_inspections", "ft_restaurant_critical"]]


def _fetch_hpd(start: str, end: str) -> pd.DataFrame:
    session = requests_cache.CachedSession("data/00_cache/hpd", expire_after=86400)
    r = session.get("https://data.cityofnewyork.us/resource/wvxf-dwi5.json", params={
        "$select": "date_trunc_ymd(inspectiondate) as date, class, count(*) as cnt",
        "$group":  "date_trunc_ymd(inspectiondate), class",
        "$where":  f"inspectiondate >= '{start}T00:00:00' AND inspectiondate <= '{end}T23:59:59' AND class in ('A','B','C')",
        "$order":  "date ASC",
        "$limit":  "50000",
    }, timeout=120)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["cnt"]  = pd.to_numeric(df["cnt"], errors="coerce").fillna(0).astype(int)
    pivot = (
        df.pivot_table(index="date", columns="class", values="cnt", aggfunc="sum", fill_value=0)
          .rename(columns={"A": "ft_hpd_class_a", "B": "ft_hpd_class_b", "C": "ft_hpd_class_c"})
    )
    pivot.index.name = "date"
    return pivot


def _fetch_mlb(start: str, end: str) -> pd.DataFrame:
    """Cumulative season win percentage for Mets (121) and Yankees (147).

    Returns a daily DataFrame with ft_mets_win_pct and ft_yankees_win_pct.
    Values are NaN during the off-season (before first game / after last game
    of each calendar year). Forward-fill is applied within each season year
    only, so the off-season gap between seasons stays NaN.
    """
    # MLB schedule API silently caps at one season per request — fetch per year.
    session = requests_cache.CachedSession("data/00_cache/mlb", expire_after=86400)
    teams = {121: "ft_mets_win_pct", 147: "ft_yankees_win_pct"}
    rows = []
    years = range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)
    for team_id, col in teams.items():
        for year in years:
            r = session.get("https://statsapi.mlb.com/api/v1/schedule", params={
                "sportId":   1,
                "teamId":    team_id,
                "startDate": f"{year}-01-01",
                "endDate":   f"{year}-12-31",
                "gameType":  "R",
            }, timeout=30)
            r.raise_for_status()
            for d in r.json().get("dates", []):
                for g in d["games"]:
                    if g.get("status", {}).get("detailedState") != "Final":
                        continue
                    team_data = (
                        g["teams"]["home"] if g["teams"]["home"]["team"]["id"] == team_id
                        else g["teams"]["away"]
                    )
                    pct = float(team_data["leagueRecord"]["pct"])
                    rows.append({"date": pd.Timestamp(d["date"]), "col": col, "pct": pct})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # keep last game result per (date, team) — handles doubleheaders
    df = df.sort_values("date").drop_duplicates(subset=["date", "col"], keep="last")
    pivot = df.pivot(index="date", columns="col", values="pct")
    pivot.index.name = "date"

    # Reindex to the full requested date range, then forward-fill with a short
    # limit. Games occur every 1-3 days; limit=5 covers rain delays / off-days
    # without bleeding into the multi-month off-season.
    full_days = pd.date_range(start, end, freq="D")
    pivot = pivot.reindex(full_days).ffill(limit=5)
    pivot.index.name = "date"

    return pivot



def fetch_raw(
    start_date: str, end_date: str,
    nyc_lat: float, nyc_lon: float,
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
        _timed("openmeteo",       _fetch_openmeteo, start_date, end_date, nyc_lat, nyc_lon),
        raw_nyiso,
        _timed("mta",             _fetch_mta,             start_date, end_date),
        _timed("311",             _fetch_311,             start_date, end_date),
        _timed("crashes",         _fetch_crashes,         start_date, end_date),
        _timed("floodnet",        _fetch_floodnet,        start_date, end_date),
        _timed("bike_ped",        _fetch_bike_ped,        start_date, end_date),
        _timed("congestion_zone", _fetch_congestion_zone, start_date, end_date),
        _timed("evictions",       _fetch_evictions,       start_date, end_date),
        _timed("restaurant",      _fetch_restaurant,      start_date, end_date),
        _timed("hpd",             _fetch_hpd,             start_date, end_date),
        _timed("mlb",             _fetch_mlb,             start_date, end_date),
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
    raw_restaurant: pd.DataFrame,
    raw_hpd: pd.DataFrame,
    raw_mlb: pd.DataFrame,
    mta_lag: int,
    lag_311: int,
    crashes_lag: int,
    floodnet_lag: int,
    bike_ped_lag: int,
    cz_lag: int,
    evictions_lag: int,
    restaurant_lag: int,
    hpd_lag: int,
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
        (raw_evictions,  evictions_lag),
        (raw_restaurant, restaurant_lag),
        (raw_hpd,        hpd_lag),
    ]:
        if not raw.empty:
            hourly = _lag_join(hourly, raw, lag, lag_window)

    # MLB win pct: no publication lag — ffill within-season is already applied;
    # off-season rows stay NaN. Just reindex to hourly.
    if not raw_mlb.empty:
        mlb_h = raw_mlb.reindex(hourly.index, method="ffill")
        hourly = hourly.join(mlb_h, how="left")

    return hourly
