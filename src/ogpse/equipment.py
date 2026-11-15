from dataclasses import dataclass
from functools import cache

import pandas as pd
import pvlib

from .config import RAW
from .sources import fetch

SAM_LIBS = "https://raw.githubusercontent.com/NatLabRockies/SAM/develop/deploy/libraries/"


@dataclass(frozen=True)
class Equipment:
    module: pd.Series
    inverter: pd.Series
    modules_per_string: int
    strings_per_inverter: int

    @property
    def block_mwdc(self) -> float:
        return self.module["STC"] * self.modules_per_string * self.strings_per_inverter / 1e6


@cache
def _library(name: str) -> pd.DataFrame:
    path = fetch(SAM_LIBS + name.replace(" ", "%20"), RAW / "cec" / name.replace(" ", "_"))
    return pvlib.pvsystem.retrieve_sam(path=str(path))


def load(cfg) -> Equipment:
    module = _library("CEC Modules.csv")[cfg.module.name]
    inverter = _library("CEC Inverters.csv")[cfg.inverter.name]
    string_w = float(module["STC"]) * cfg.inverter.modules_per_string
    strings = round(cfg.inverter.dc_ac_ratio * float(inverter["Paco"]) / string_w)
    return Equipment(module, inverter, cfg.inverter.modules_per_string, strings)
