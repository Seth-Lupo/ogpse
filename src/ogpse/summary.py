import json

import numpy as np
import pandas as pd

from . import equipment, solar, weather
from .config import OUT, ROOT


def worst_window_share(cfg, lat, lon, days: int) -> float:
    eq = equipment.load(cfg)
    w, meta = weather.load(cfg, lat, lon)
    pv = solar.ac_per_mwdc(w, meta, eq, cfg, cfg.module.length_m / cfg.layout.row_pitch_m).to_numpy()
    window = np.convolve(pv, np.ones(24 * days), "valid")
    return float(window.min() / window.mean())


def build(cfg) -> dict:
    sites = pd.read_csv(OUT / "sites.csv")
    feas = pd.read_csv(OUT / "feasibility.csv")
    ref = feas[feas.point == cfg.validation.sam_site].iloc[0]
    summary = {
        "county": {
            "name": cfg.study.county, "sites": len(sites), "firm_gw": sites.firm_mw.sum() / 1e3,
            "best_musd": sites.usd_per_firm_mw.min() / 1e6, "worst_musd": sites.usd_per_firm_mw.max() / 1e6,
            "median_musd": sites.usd_per_firm_mw.median() / 1e6,
            "yield_spread": sites.yield_mwh_per_mwdc.max() / sites.yield_mwh_per_mwdc.min() - 1,
            "land_share": float((sites.land_usd / sites.total_usd).median()),
            "spread": sites.usd_per_firm_mw.max() / sites.usd_per_firm_mw.min() - 1,
            "unmapped_flood": int((sites.flood == "unmapped").sum()),
            "drivers": sites.limiting_factor.value_counts().to_dict(),
        },
        "feasibility": {
            "points": len(feas),
            "cost_spread": feas.musd_per_firm_mw.max() / feas.musd_per_firm_mw.min() - 1,
            "yield_spread": feas.yield_mwh_per_mwdc.max() / feas.yield_mwh_per_mwdc.min() - 1,
            "simple_spread": feas.simple_musd_per_firm_mw.max() / feas.simple_musd_per_firm_mw.min() - 1,
        },
        "gap": {
            "site": ref.point, "simple_pv": None, "simple_hours": None, "simple_uptime": ref.simple_uptime,
            "best_pv": ref.pv_mwdc_per_mw, "best_hours": ref.storage_hours,
            "ratio": ref.musd_per_firm_mw / ref.simple_musd_per_firm_mw,
            "worst5_share": worst_window_share(cfg, ref.lat, ref.lon, 5),
        },
        "validation": json.loads((OUT / "validation.json").read_text()),
    }
    summary["gap"]["simple_pv"] = float(ref.simple_pv_mwdc_per_mw)
    summary["gap"]["simple_hours"] = float(ref.simple_storage_hours)
    text = json.dumps(summary, indent=2, default=float)
    (OUT / "summary.json").write_text(text)
    (ROOT / "web" / "summary.json").write_text(text)
    return summary
