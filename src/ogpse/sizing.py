from dataclasses import dataclass

import numpy as np

from .costs import Costs


@dataclass(frozen=True)
class Design:
    """A solar + battery design per 1 MW of firm load."""
    pv_mwdc: float
    battery_mw: float
    battery_mwh: float

    def capex(self, c: Costs) -> float:
        return 1e3 * (self.pv_mwdc * c.pv_usd_per_kwdc + self.battery_mw * c.battery_usd_per_kw
                      + self.battery_mwh * c.battery_usd_per_kwh)


def unserved_hours(pv: np.ndarray, d: Design, rte: float, trace: list | None = None) -> int:
    """Greedy hourly dispatch of a 1 MW flat load; battery starts full. Appends end-of-hour charge to trace."""
    eta = rte ** 0.5
    cap, power = d.battery_mwh, d.battery_mw
    soc, misses = cap, 0
    for net in (pv * d.pv_mwdc - 1.0).tolist():
        if net >= 0:
            soc = min(cap, soc + min(net, power) * eta)
        else:
            out = min(-net, power, soc * eta)
            soc -= out / eta
            if out < -net - 1e-9:
                misses += 1
        if trace is not None:
            trace.append(soc)
    return misses


def state_of_charge(pv: np.ndarray, d: Design, rte: float) -> np.ndarray:
    trace = []
    unserved_hours(pv, d, rte, trace)
    return np.array(trace) / d.battery_mwh


def uptime(pv: np.ndarray, d: Design, rte: float) -> float:
    return 1 - unserved_hours(pv, d, rte) / len(pv)


def min_pv(pv: np.ndarray, power: float, hours: float, rte: float, target: float,
           lo: float, hi: float, tol: float) -> float | None:
    """Smallest PV (MWdc/MW load) meeting the uptime target; uptime is monotone in PV."""
    if uptime(pv, Design(hi, power, hours), rte) < target:
        return None
    while hi - lo > tol * hi:
        mid = (lo + hi) / 2
        if uptime(pv, Design(mid, power, hours), rte) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def optimize(pv: np.ndarray, costs: Costs, cfg) -> Design:
    """Cheapest design on the (battery power, storage hours) grid, PV found by bisection."""
    s, rte, target = cfg.sizing, cfg.battery.round_trip_efficiency, cfg.study.uptime_target
    best = None
    for power in cfg.battery.power_ratios:
        lo, hi = s.pv_ratio_bounds
        for hours in s.storage_hours:
            p = min_pv(pv, power, hours, rte, target, lo, hi, s.pv_tolerance)
            if p is None:
                continue
            d = Design(p, power, hours)
            if best is None or d.capex(costs) < best.capex(costs):
                best = d
            hi = p  # more storage never needs more PV
    return best


def simple_math(pv: np.ndarray, night_hours: float, rte: float, years: int) -> Design:
    """Back-of-envelope: PV covers annual energy (half of it via the battery), battery covers the longest night."""
    yield_mwh = pv.sum() / years
    need = 8760 * (0.5 + 0.5 / rte)
    return Design(need / yield_mwh, 1.0, night_hours)
