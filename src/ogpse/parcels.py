import geopandas as gpd
import numpy as np

from .config import CACHE, RAW
from .sources import fetch

ACRE_M2 = 4046.8564224


def _normalize(owner):
    return owner.fillna("").str.upper().str.replace(r"[^A-Z0-9 ]", "", regex=True).str.split().str.join(" ")


def sites(cfg) -> gpd.GeoDataFrame:
    """Contiguous holdings with one ownership >= min acres. Parcels with identical geometry (undivided interests)
    become one land unit owned by the set of their owners. Owner names are used only for grouping and counting."""
    out = CACHE / "sites.parquet"
    if out.exists():
        return gpd.read_parquet(out)
    url = cfg.sources.parcels
    path = fetch(url, RAW / "parcels" / url.rsplit("/", 1)[1])
    layer = f"zip://{path}!fgdb/stratmap-2026-land-parcels-{cfg.study.county.lower()}_{cfg.study.state_fips}{cfg.study.county_fips}.gdb"
    p = gpd.read_file(layer).to_crs(cfg.study.crs)
    p["owner"] = _normalize(p["OWNER_NAME"])
    p = p[p.owner != ""]
    p["shape_key"] = p.geometry.normalize().to_wkb()
    units = p.groupby("shape_key").agg(owners=("owner", lambda o: "|".join(sorted(set(o)))),
                                       geometry=("geometry", "first"), parcels=("owner", "size"))
    units = gpd.GeoDataFrame(units.reset_index(drop=True), crs=p.crs)
    units["geometry"] = units.buffer(1.0)  # close sliver gaps between surveyed neighbours
    held = units.dissolve("owners", aggfunc={"parcels": "sum"}).explode(index_parts=False).reset_index()
    held["geometry"] = held.buffer(-1.0)
    held["owner_count"] = held.owners.str.count(r"\|") + 1
    held["acres"] = held.area / ACRE_M2
    s = held[held.acres >= cfg.study.min_parcel_acres].drop(columns="owners")
    s = s.sort_values("acres", ascending=False).reset_index(drop=True)
    s.insert(0, "site_id", [f"PEC-{i:03d}" for i in range(1, len(s) + 1)])
    ll = s.representative_point().to_crs(4326)
    step = cfg.weather.grid_deg
    s["wx_lat"] = np.round(np.round(ll.y / step) * step, 2)
    s["wx_lon"] = np.round(np.round(ll.x / step) * step, 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.to_parquet(out)
    return s
