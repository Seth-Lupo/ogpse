import json

import geopandas as gpd
import pandas as pd

from .config import CACHE, RAW
from .sources import fetch

CHUNK = 200
GENERALIZE_M = 1  # finer than the 10 m layout raster; avoids server errors on huge polygons


def _query_all(url: str, where: str, bbox, crs: str, name: str) -> gpd.GeoDataFrame:
    """List object ids once, then fetch features in fixed id chunks (server paging is unreliable)."""
    envelope = json.dumps({"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
                           "spatialReference": {"wkid": 4326}})
    spatial = {"where": where, "geometry": envelope, "geometryType": "esriGeometryEnvelope",
               "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"}
    ids_path = fetch(url + "/query", RAW / name / "ids.json", {**spatial, "returnIdsOnly": "true", "f": "json"})
    ids = sorted(json.loads(ids_path.read_text()).get("objectIds") or [])
    frames = []
    for i in range(0, len(ids), CHUNK):
        params = {"objectIds": ",".join(map(str, ids[i:i + CHUNK])), "outFields": "OBJECTID",
                  "outSR": crs.split(":")[1], "maxAllowableOffset": str(GENERALIZE_M), "f": "geojson"}
        page = gpd.read_file(fetch(url + "/query", RAW / name / f"chunk_{i // CHUNK:04d}.geojson", params, method="POST"))
        if len(page):
            frames.append(page)
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs)


def layers(cfg, bbox_lonlat) -> dict[str, gpd.GeoDataFrame]:
    """Wetlands (NWI), FEMA special flood hazard areas, and FEMA FIRM panel coverage, in the study CRS."""
    out = {}
    for key, url, where in [
        ("wetlands", cfg.sources.wetlands + "/0", "1=1"),
        ("flood_zones", cfg.sources.flood + "/28", "SFHA_TF='T'"),
        ("flood_panels", cfg.sources.flood + "/3", "1=1"),
    ]:
        cached = CACHE / f"{key}.parquet"
        if not cached.exists():
            g = _query_all(url, where, bbox_lonlat, cfg.study.crs, key)
            g = g[["geometry"]].set_crs(cfg.study.crs, allow_override=True)
            g = g[~g.geometry.is_empty & g.geometry.notna()]
            cached.parent.mkdir(parents=True, exist_ok=True)
            g.to_parquet(cached)
        out[key] = gpd.read_parquet(cached)
    return out
