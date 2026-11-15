from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import RAW
from .sources import fetch


@dataclass(frozen=True)
class Costs:
    pv_usd_per_kwdc: float
    battery_usd_per_kw: float
    battery_usd_per_kwh: float
    land_usd_per_acre: float


def load(cfg) -> Costs:
    c = cfg.costs
    atb = pd.read_parquet(fetch(c.url, RAW / "atb" / "ATBe_2025.parquet"))
    occ = atb[(atb.core_metric_parameter == "OCC") & (atb.scenario == c.scenario)
              & (atb.core_metric_case == c.case) & (atb.crpyears == 30)
              & (atb.core_metric_variable == c.cost_year)]
    pv_kwac = occ[(occ.technology == "UtilityPV") & (occ.techdetail == "Class1")].value.iloc[0]
    batt = occ[occ.technology == "Utility-Scale Battery Storage"]
    hours = batt.techdetail.str.extract(r"(\d+)Hr")[0].astype(float)
    per_kwh, per_kw = np.polyfit(hours, batt.value, 1)
    return Costs(pv_kwac / cfg.inverter.dc_ac_ratio, per_kw, per_kwh, c.land_usd_per_acre)
