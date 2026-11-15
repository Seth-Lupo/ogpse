from dataclasses import dataclass

import numpy as np

from . import solar, sizing, weather
from .costs import Costs
from .equipment import Equipment


@dataclass(frozen=True)
class FirmDesign:
    """Cost-optimal and simple-math designs for 1 MW of firm load at one weather point."""
    lat: float
    lon: float
    yield_mwh_per_mwdc: float
    best: sizing.Design
    best_uptime: float
    simple: sizing.Design
    simple_uptime: float
    usd_per_firm_mw: float
    simple_usd_per_firm_mw: float


def design_for_point(cfg, eq: Equipment, costs: Costs, lat: float, lon: float, gcr: float) -> FirmDesign:
    w, meta = weather.load(cfg, lat, lon)
    profile = solar.ac_per_mwdc(w, meta, eq, cfg, gcr)
    pv = profile.to_numpy()
    rte = cfg.battery.round_trip_efficiency
    best = sizing.optimize(pv, costs, cfg)
    years = profile.index.year.nunique()
    simple = sizing.simple_math(pv, solar.longest_night_hours(meta["lat"]), rte, years)
    return FirmDesign(
        lat, lon, solar.annual_yield(profile),
        best, sizing.uptime(pv, best, rte),
        simple, sizing.uptime(pv, simple, rte),
        best.capex(costs), simple.capex(costs))
