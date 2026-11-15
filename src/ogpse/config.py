from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
OUT = ROOT / "results"


def _ns(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k.replace(" ", "_"): _ns(v) for k, v in obj.items()})
    return obj


def load(path: Path = ROOT / "config.yaml") -> SimpleNamespace:
    with open(path) as f:
        return _ns(yaml.safe_load(f))


def raw_dict(path: Path = ROOT / "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
