import json
from itertools import product

import geopandas as gpd
import numpy as np
import pandas as pd
import PySAM.Pvsamv1 as pvsam

from . import equipment, layout, sizing, solar, terrain, weather
from .config import OUT, RAW
from .sources import fetch


# 1. Layout vs reality ---------------------------------------------------------------------------

def plants(cfg) -> gpd.GeoDataFrame:
    v, f = cfg.validation, cfg.validation.plants
    path = fetch(v.uspvdb_url, RAW / "uspvdb" / v.uspvdb_url.rsplit("/", 1)[1])
    g = gpd.read_file(f"zip://{path}!{v.uspvdb_file}")
    ilr = g.p_cap_dc / g.p_cap_ac
    g = g[(g.p_state == f.state) & (g.p_axis == f.axis) & (g.xlong < f.max_longitude)
          & (g.p_cap_dc >= f.min_mwdc) & (g.p_dig_conf == f.digitize_confidence)
          & ilr.between(*f.dc_ac_ratio)]
    g = g.sort_values(["p_year", "eia_id"], ascending=[False, True]).head(f.count)
    g = g.sort_values("eia_id").reset_index(drop=True)
    g["split"] = np.where(np.arange(len(g)) % f.train_every == 0, "train", "test")
    return g


def _plant_capacities(cfg, plant, stc_w) -> dict:
    crs = gpd.GeoSeries([plant.geometry], crs=4326).estimate_utm_crs().to_string()
    geom = gpd.GeoSeries([plant.geometry], crs=4326).to_crs(crs).iloc[0]
    grid = terrain.dem(cfg, f"uspvdb_{plant.eia_id}", geom.buffer(50).bounds, crs)
    out = {}
    for setback in cfg.validation.setback_grid_m:
        mask = layout.buildable_mask(cfg, geom, grid, [], setback_m=setback)
        for pitch in cfg.validation.pitch_grid_m:
            out[(pitch, setback)] = layout.place_rows(cfg, mask, grid, stc_w, pitch_m=pitch).mwdc
    return out


def layout_check(cfg) -> dict:
    stc_w = float(equipment.load(cfg).module["STC"])
    p = plants(cfg)
    caps = [_plant_capacities(cfg, row, stc_w) for _, row in p.iterrows()]
    train = (p.split == "train").to_numpy()
    actual = p.p_cap_dc.to_numpy()

    def mape(pred, sel):
        return float(np.mean(np.abs(pred[sel] / actual[sel] - 1)))

    grid = list(product(cfg.validation.pitch_grid_m, cfg.validation.setback_grid_m))
    errors = {k: mape(np.array([c[k] for c in caps]), train) for k in grid}
    pitch, setback = min(errors, key=errors.get)
    pred = np.array([c[(pitch, setback)] for c in caps])
    acres = p.to_crs(p.estimate_utm_crs()).area.to_numpy() / 4046.8564224
    acres_per_mw = float(np.median(acres[train] / actual[train]))
    naive = acres / acres_per_mw

    table = pd.DataFrame({"eia_id": p.eia_id, "plant": p.p_name, "county": p.p_county, "year": p.p_year,
                          "split": p.split, "acres": acres.round(0), "actual_mwdc": actual,
                          "model_mwdc": pred.round(1), "naive_mwdc": naive.round(1),
                          "model_err": (pred / actual - 1).round(3), "naive_err": (naive / actual - 1).round(3)})
    table.to_csv(OUT / "validation_layout.csv", index=False)
    test = ~train
    return {"tuned_row_pitch_m": pitch, "tuned_setback_m": setback, "naive_acres_per_mwdc": round(acres_per_mw, 2),
            "train_mape": round(errors[(pitch, setback)], 3),
            "test_mape_model": round(mape(pred, test), 3), "test_mape_naive": round(mape(naive, test), 3),
            "config_matches_tuned": (pitch, setback) == (cfg.layout.row_pitch_m, cfg.layout.boundary_setback_m)}


# 2. Solar output vs SAM ---------------------------------------------------------------------------

SAM_CEC_FIELDS = {"a_ref": "a_ref", "adjust": "Adjust", "alpha_sc": "alpha_sc", "beta_oc": "beta_oc",
                  "i_l_ref": "I_L_ref", "i_mp_ref": "I_mp_ref", "i_o_ref": "I_o_ref", "i_sc_ref": "I_sc_ref",
                  "n_s": "N_s", "r_s": "R_s", "r_sh_ref": "R_sh_ref", "t_noct": "T_NOCT", "v_mp_ref": "V_mp_ref",
                  "v_oc_ref": "V_oc_ref", "area": "A_c"}

def _sam_annual_mwh(cfg, eq, w, meta, year, gcr) -> float:
    y = w[w.index.year == year]
    m, inv = eq.module, eq.inverter
    s = pvsam.default("FlatPlatePVNone")
    s.SolarResource.solar_resource_data = {
        "lat": meta["lat"], "lon": meta["lon"], "tz": 0, "elev": meta["elevation"],
        "year": list(y.index.year), "month": list(y.index.month), "day": list(y.index.day),
        "hour": list(y.index.hour), "minute": list(y.index.minute),
        "dn": list(y.dni), "df": list(y.dhi), "gh": list(y.ghi), "tdry": list(y.temp_air),
        "wspd": list(y.wind_speed), "albedo": list(y.albedo)}
    s.SolarResource.use_wf_albedo = 1
    s.SolarResource.irrad_mode, s.SolarResource.sky_model = 0, 2
    sd = s.SystemDesign
    sd.subarray1_track_mode, sd.subarray1_tilt, sd.subarray1_azimuth = 1, 0, 180
    sd.subarray1_backtrack, sd.subarray1_gcr, sd.subarray1_rotlim = 1, gcr, cfg.tracker.max_rotation_deg
    sd.subarray1_modules_per_string, sd.subarray1_nstrings = eq.modules_per_string, eq.strings_per_inverter
    sd.inverter_count, sd.system_capacity = 1, eq.block_mwdc * 1e3
    s.Module.module_model = 1
    cec = s.CECPerformanceModelWithModuleDatabase
    for sam_key, cec_col in SAM_CEC_FIELDS.items():
        setattr(cec, f"cec_{sam_key}", float(m[cec_col]))
    cec.cec_temp_corr_mode, cec.cec_standoff, cec.cec_height, cec.cec_is_bifacial = 0, 6, 0, 0
    s.Inverter.inverter_model = 0
    db = s.InverterCECDatabase
    for k in ["c0", "c1", "c2", "c3"]:
        setattr(db, f"inv_snl_{k}", float(inv[f"C{k[1]}"]))
    db.inv_snl_paco, db.inv_snl_pdco, db.inv_snl_pnt = float(inv.Paco), float(inv.Pdco), float(inv.Pnt)
    db.inv_snl_pso, db.inv_snl_vdco, db.inv_snl_vdcmax = float(inv.Pso), float(inv.Vdco), float(inv.Vdcmax)
    s.Inverter.mppt_low_inverter, s.Inverter.mppt_hi_inverter = float(inv.Mppt_low), float(inv.Mppt_high)
    lo = s.Losses
    lo.subarray1_soiling = [0.0] * 12
    for k in ["subarray1_dcwiring_loss", "subarray1_diodeconn_loss", "subarray1_mismatch_loss",
              "subarray1_tracking_loss", "subarray1_rear_soiling_loss", "dcoptimizer_loss", "acwiring_loss",
              "transformer_load_loss", "transformer_no_load_loss", "transmission_loss", "subarray1_rack_shading"]:
        setattr(lo, k, 0.0)
    lo.subarray1_nameplate_loss = cfg.pv_losses.dc_loss * 100
    s.Shading.subarray1_shade_mode = 0
    s.Lifetime.system_use_lifetime_output = 0
    s.execute()
    return s.Outputs.annual_energy / 1e3  # kWh -> MWh


def sam_check(cfg) -> dict:
    eq = equipment.load(cfg)
    lat, lon = getattr(cfg.feasibility_points, cfg.validation.sam_site.replace(" ", "_"))
    w, meta = weather.load(cfg, lat, lon)
    gcr = cfg.module.length_m / cfg.layout.row_pitch_m
    ours = solar.ac_per_mwdc(w, meta, eq, cfg, gcr) * eq.block_mwdc
    rows = []
    for year in sorted(set(w.index.year)):
        rows.append({"year": year, "pvlib_mwh": float(ours[ours.index.year == year].sum()),
                     "sam_mwh": _sam_annual_mwh(cfg, eq, w, meta, year, gcr)})
    df = pd.DataFrame(rows)
    df["diff"] = df.pvlib_mwh / df.sam_mwh - 1
    df.round(4).to_csv(OUT / "validation_sam.csv", index=False)
    return {"site": cfg.validation.sam_site, "years": len(df), "mean_diff": round(float(df["diff"].mean()), 4),
            "max_abs_year_diff": round(float(df["diff"].abs().max()), 4)}


# 3. Sizing self-check -----------------------------------------------------------------------------

def uptime_check(cfg) -> dict:
    """Re-simulate every chosen site design at full scale, hour by hour, over all weather years."""
    sites = pd.read_csv(OUT / "sites.csv")
    eq = equipment.load(cfg)
    gcr = cfg.module.length_m / cfg.layout.row_pitch_m
    rte = cfg.battery.round_trip_efficiency
    profiles, uptimes = {}, []
    for s in sites.itertuples():
        key = (s.wx_lat, s.wx_lon)
        if key not in profiles:
            w, meta = weather.load(cfg, *key)
            profiles[key] = solar.ac_per_mwdc(w, meta, eq, cfg, gcr).to_numpy()
        per_mw = sizing.Design(s.pv_mwdc / s.firm_mw, s.battery_mw / s.firm_mw, s.battery_mwh / s.firm_mw)
        uptimes.append(sizing.uptime(profiles[key], per_mw, rte))
    u = np.array(uptimes)
    return {"sites": len(u), "min_uptime": round(float(u.min()), 5),
            "all_pass": bool((u >= cfg.study.uptime_target).all())}


def run(cfg, checks=("layout", "sam", "uptime")) -> dict:
    OUT.mkdir(exist_ok=True)
    path = OUT / "validation.json"
    result = json.loads(path.read_text()) if path.exists() else {}
    for name in checks:
        result[name] = {"layout": layout_check, "sam": sam_check, "uptime": uptime_check}[name](cfg)
        print(name, result[name], flush=True)
    path.write_text(json.dumps(result, indent=2))
    return result
