from dataclasses import asdict
from functools import partial
from multiprocessing import Pool

import geopandas as gpd
import numpy as np
import pandas as pd

from . import costs, equipment, firm, hazards, layout, parcels, terrain
from .config import CACHE, OUT, ROOT

WEB_LAYOUTS = ROOT / "web" / "layouts"


def _design(cfg, cell):
    eq, c = equipment.load(cfg), costs.load(cfg)
    d = firm.design_for_point(cfg, eq, c, *cell, gcr=cfg.module.length_m / cfg.layout.row_pitch_m)
    return {"wx_lat": cell[0], "wx_lon": cell[1], "yield_mwh_per_mwdc": d.yield_mwh_per_mwdc,
            **{f"best_{k}": v for k, v in asdict(d.best).items()}, "uptime": d.best_uptime,
            "equip_usd_per_mw": d.usd_per_firm_mw,
            **{f"simple_{k}": v for k, v in asdict(d.simple).items()},
            "simple_uptime": d.simple_uptime, "simple_usd_per_mw": d.simple_usd_per_firm_mw}


def designs(cfg, sites: gpd.GeoDataFrame) -> pd.DataFrame:
    path = CACHE / "designs.csv"
    cells = sorted(set(zip(sites.wx_lat, sites.wx_lon)))
    if path.exists():
        done = pd.read_csv(path)
        if len(done) == len(cells):
            return done
    with Pool(cfg.study.workers) as pool:
        rows = pool.map(partial(_design, cfg), cells)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


def _layout(cfg, layers, site):
    path = CACHE / "layouts" / f"{site.site_id}.parquet"
    if not path.exists():
        eq = equipment.load(cfg)
        grid = terrain.dem(cfg, site.geometry.bounds)
        mask = layout.buildable_mask(cfg, site.geometry, grid, layout.exclusions_for(site.geometry, layers))
        lay = layout.place_rows(cfg, mask, grid, float(eq.module["STC"]))
        row = {"site_id": site.site_id, "rows": lay.rows, "mwdc": lay.mwdc, "buildable_acres": lay.buildable_acres,
               "flood": layout.flood_status(site.geometry, layers), "footprint": lay.footprint}
        path.parent.mkdir(parents=True, exist_ok=True)
        gpd.GeoDataFrame([row], geometry="footprint", crs=cfg.study.crs).to_parquet(path)
    return gpd.read_parquet(path)


def layouts(cfg, sites: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    layers = hazards.layers(cfg, sites.to_crs(4326).total_bounds)
    with Pool(cfg.study.workers) as pool:
        parts = pool.map(partial(_layout, cfg, layers), [s for _, s in sites.iterrows()], chunksize=1)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="footprint", crs=sites.crs)


def rank(cfg, sites, lay, des) -> gpd.GeoDataFrame:
    c = costs.load(cfg)
    s = sites.merge(lay.drop(columns="footprint"), on="site_id").merge(des, on=["wx_lat", "wx_lon"])
    s["firm_mw"] = s.mwdc / s.best_pv_mwdc
    s["pv_mwdc"] = s.mwdc
    s["battery_mw"] = s.firm_mw * s.best_battery_mw
    s["battery_mwh"] = s.firm_mw * s.best_battery_mwh
    s["equipment_usd"] = s.firm_mw * s.equip_usd_per_mw
    s["land_usd"] = s.acres * c.land_usd_per_acre
    s["total_usd"] = s.equipment_usd + s.land_usd
    s["usd_per_firm_mw"] = s.total_usd / s.firm_mw
    s["buildable_share"] = s.buildable_acres / s.acres
    land_per_mw = s.land_usd / s.firm_mw
    weather_excess = s.equip_usd_per_mw - s.equip_usd_per_mw.min()
    land_excess = land_per_mw - land_per_mw.min()
    s["limiting_factor"] = np.where(weather_excess >= land_excess, "weather", "land")
    near_best = (weather_excess + land_excess) < cfg.study.near_best_share * s.usd_per_firm_mw.min()
    s["limiting_factor"] = np.where(near_best, "near best", s.limiting_factor)
    s = s[s.firm_mw > 0].sort_values("usd_per_firm_mw").reset_index(drop=True)
    s.insert(1, "rank", range(1, len(s) + 1))
    return s


def run(cfg):
    sites = parcels.sites(cfg)
    des = designs(cfg, sites)
    lay = layouts(cfg, sites)
    ranked = rank(cfg, sites, lay, des)
    OUT.mkdir(exist_ok=True)
    cols = ["site_id", "rank", "acres", "parcels", "owner_count", "buildable_acres", "buildable_share", "flood", "wx_lat", "wx_lon",
            "yield_mwh_per_mwdc", "pv_mwdc", "firm_mw", "battery_mw", "battery_mwh", "equipment_usd", "land_usd",
            "total_usd", "usd_per_firm_mw", "limiting_factor", "uptime", "simple_usd_per_mw", "simple_uptime"]
    ranked[cols].round(4).to_csv(OUT / "sites.csv", index=False)
    web = ranked[cols + ["geometry"]].to_crs(4326)
    web["geometry"] = web.geometry.simplify(0.0003)
    (ROOT / "web").mkdir(exist_ok=True)
    web.round(4).to_file(ROOT / "web" / "sites.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    WEB_LAYOUTS.mkdir(parents=True, exist_ok=True)
    fp = lay[lay.footprint.notna()]
    blocks = fp.footprint.buffer(20).buffer(-20).simplify(10).to_crs(4326)  # row strips -> blocks, for display
    for site_id, geom in zip(fp.site_id, blocks):
        gpd.GeoSeries([geom], crs=4326).to_file(WEB_LAYOUTS / f"{site_id}.geojson", driver="GeoJSON",
                                                COORDINATE_PRECISION=5)
    return ranked
