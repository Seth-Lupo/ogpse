import json

import numpy as np
import pandas as pd

from . import equipment, sizing, solar, weather
from .config import OUT, ROOT

LOCAL_TZ = "Etc/GMT+6"  # Central Standard Time, so days run midnight to midnight


def worst_stretch(cfg, ref, days: int = 5, before: int = 10, after: int = 14) -> dict:
    """Daily solar and hourly battery charge of both designs around the darkest `days`-day window."""
    eq = equipment.load(cfg)
    w, meta = weather.load(cfg, ref.lat, ref.lon)
    profile = solar.ac_per_mwdc(w, meta, eq, cfg, cfg.module.length_m / cfg.layout.row_pitch_m)
    pv, rte = profile.to_numpy(), cfg.battery.round_trip_efficiency
    designs = {
        "simple": sizing.Design(ref.simple_pv_mwdc_per_mw, 1.0, ref.simple_storage_hours),
        "best": sizing.Design(ref.pv_mwdc_per_mw, ref.battery_mw_per_mw, ref.storage_hours),
    }
    window = np.convolve(pv, np.ones(24 * days), "valid")
    local = profile.index.tz_convert(LOCAL_TZ)
    day = pd.Index(local.normalize())
    start = day[window.argmin()]
    shown = (day >= start - pd.Timedelta(days=before)) & (day < start + pd.Timedelta(days=days + after))
    daily = profile.groupby(day).sum()
    daily = daily / daily.mean()
    charge = {k: sizing.state_of_charge(pv, d, rte)[shown] for k, d in designs.items()}
    return {
        "site": ref.point, "start": str(local[shown][0].date()), "dark_days": days,
        "dark_hour": int(window.argmin() - shown.argmax()),
        "worst_share": float(window.min() / window.mean()),
        "daily_share": daily[(daily.index >= local[shown][0].normalize()) & (daily.index <= local[shown][-1].normalize())]
        .round(3).tolist(),
        "charge": {k: np.round(v, 3).tolist() for k, v in charge.items()},
        "empty_hours": {k: int((v < 1e-6).sum()) for k, v in charge.items()},
        "allowed_hours": round((1 - cfg.study.uptime_target) * len(pv)),
    }


def build(cfg) -> dict:
    sites = pd.read_csv(OUT / "sites.csv")
    feas = pd.read_csv(OUT / "feasibility.csv")
    ref = feas[feas.point == cfg.validation.sam_site].iloc[0]
    stretch = worst_stretch(cfg, ref)
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
            "worst5_share": stretch["worst_share"],
        },
        "validation": json.loads((OUT / "validation.json").read_text()),
    }
    summary["gap"]["simple_pv"] = float(ref.simple_pv_mwdc_per_mw)
    summary["gap"]["simple_hours"] = float(ref.simple_storage_hours)
    text = json.dumps(summary, indent=2, default=float)
    (OUT / "summary.json").write_text(text)
    (ROOT / "web" / "summary.json").write_text(text)
    (ROOT / "web" / "worst_stretch.json").write_text(json.dumps(stretch, separators=(",", ":")))
    return summary
