import argparse

import pandas as pd

from . import config, costs, equipment, firm
from .config import OUT


def feasibility(cfg):
    eq, c = equipment.load(cfg), costs.load(cfg)
    gcr = cfg.module.length_m / cfg.layout.row_pitch_m
    rows = []
    for name, (lat, lon) in vars(cfg.feasibility_points).items():
        d = firm.design_for_point(cfg, eq, c, lat, lon, gcr)
        rows.append({
            "point": name.replace("_", " "), "lat": lat, "lon": lon,
            "yield_mwh_per_mwdc": round(d.yield_mwh_per_mwdc),
            "pv_mwdc_per_mw": round(d.best.pv_mwdc, 2), "battery_mw_per_mw": d.best.battery_mw,
            "storage_hours": d.best.battery_mwh, "uptime": round(d.best_uptime, 5),
            "musd_per_firm_mw": round(d.usd_per_firm_mw / 1e6, 2),
            "simple_musd_per_firm_mw": round(d.simple_usd_per_firm_mw / 1e6, 2),
            "simple_uptime": round(d.simple_uptime, 4),
        })
        print(rows[-1], flush=True)
    df = pd.DataFrame(rows).sort_values("musd_per_firm_mw")
    spread = df.musd_per_firm_mw.max() / df.musd_per_firm_mw.min() - 1
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "feasibility.csv", index=False)
    print(df.to_string(index=False))
    print(f"\n$/firm MW spread across West Texas: {spread:.1%}")


COMMANDS = {"feasibility": feasibility}


def main():
    p = argparse.ArgumentParser(prog="ogpse")
    p.add_argument("command", choices=COMMANDS)
    args = p.parse_args()
    COMMANDS[args.command](config.load())


if __name__ == "__main__":
    main()
