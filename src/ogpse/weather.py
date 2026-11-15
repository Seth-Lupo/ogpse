import os
import time

import pandas as pd

from .config import CACHE, RAW
from .sources import fetch

_last_request = [0.0]


def _year_file(cfg, lat: float, lon: float, year: int):
    dest = RAW / "nsrdb" / f"{lat:.2f}_{lon:.2f}" / f"{year}.csv"
    if dest.exists():
        return dest
    wait = cfg.weather.request_interval_s - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.time()
    params = {
        "api_key": os.environ["NREL_DEVELOPER_API_KEY"],
        "email": os.environ["NREL_EMAIL"],
        "wkt": f"POINT({lon:.4f} {lat:.4f})",
        "names": str(year),
        "interval": "60",
        "attributes": ",".join(cfg.weather.attributes),
        "utc": "true",
        "leap_day": "false",
    }
    return fetch(cfg.weather.url, dest, params)


def load(cfg, lat: float, lon: float) -> tuple[pd.DataFrame, dict]:
    """Hourly NSRDB weather for all configured years, UTC index; plus site metadata."""
    lat, lon = round(lat, 2), round(lon, 2)
    cached = CACHE / "weather" / f"{lat:.2f}_{lon:.2f}.parquet"
    first, last = cfg.weather.years
    frames, meta = [], None
    if not cached.exists():
        for year in range(first, last + 1):
            path = _year_file(cfg, lat, lon, year)
            if meta is None:
                head = pd.read_csv(path, nrows=1)
                meta = {"lat": float(head["Latitude"][0]), "lon": float(head["Longitude"][0]),
                        "elevation": float(head["Elevation"][0]), "nsrdb_id": int(head["Location ID"][0])}
            df = pd.read_csv(path, skiprows=2)
            df.index = pd.to_datetime(df[["Year", "Month", "Day", "Hour", "Minute"]]).dt.tz_localize("UTC")
            frames.append(df.drop(columns=["Year", "Month", "Day", "Hour", "Minute"]))
        weather = pd.concat(frames).rename(columns={
            "GHI": "ghi", "DNI": "dni", "DHI": "dhi", "Temperature": "temp_air",
            "Wind Speed": "wind_speed", "Surface Albedo": "albedo"})
        cached.parent.mkdir(parents=True, exist_ok=True)
        weather.assign(**{f"meta_{k}": v for k, v in meta.items()}).to_parquet(cached)
    weather = pd.read_parquet(cached)
    meta_cols = [c for c in weather.columns if c.startswith("meta_")]
    meta = {c[5:]: weather[c].iloc[0] for c in meta_cols}
    return weather.drop(columns=meta_cols), meta
