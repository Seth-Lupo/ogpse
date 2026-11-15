from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

from .terrain import Grid


@dataclass(frozen=True)
class Layout:
    rows: int
    mwdc: float
    buildable_acres: float
    footprint: object  # shapely geometry of placed rows, for the map


def string_length_m(cfg) -> float:
    return cfg.inverter.modules_per_string * (cfg.module.width_m + cfg.tracker.module_gap_m)


def _runs(column: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.concatenate([[0], column.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def buildable_mask(cfg, site_geom, grid: Grid, exclusions: list, setback_m: float | None = None) -> np.ndarray:
    """Cells inside the setback boundary, outside exclusions, and within tracker slope limits."""
    t = cfg.tracker
    inner = site_geom.buffer(-(cfg.layout.boundary_setback_m if setback_m is None else setback_m))
    if inner.is_empty:
        return np.zeros(grid.shape, bool)
    mask = features.geometry_mask([inner], grid.shape, grid.transform, invert=True)
    shapes = [g for g in exclusions if not g.is_empty]
    if shapes:
        mask &= features.geometry_mask(shapes, grid.shape, grid.transform, all_touched=True)
    ns, ew = grid.slopes_deg()
    mask &= (ns <= t.max_ns_slope_deg) & (ew <= t.max_ew_slope_deg) & np.isfinite(grid.elevation)
    return mask


def place_rows(cfg, mask: np.ndarray, grid: Grid, module_stc_w: float, pitch_m: float | None = None) -> Layout:
    """N-S tracker rows every `pitch` metres E-W. Each contiguous buildable N-S run is filled with full rows,
    plus one partial row if at least `min_strings_per_row` strings fit; rows whose end-to-end N-S tilt exceeds
    the tracker limit are dropped."""
    t, res = cfg.tracker, grid.res
    pitch = pitch_m or cfg.layout.row_pitch_m
    string_m = string_length_m(cfg)
    full = t.modules_per_row // cfg.inverter.modules_per_string
    max_tan = np.tan(np.radians(t.max_ns_slope_deg))
    cols = (np.arange(pitch / 2, mask.shape[1] * res, pitch) // res).astype(int)
    covered = np.zeros(mask.shape, np.uint8)
    strings = rows = 0
    for c in cols:
        for a, b in _runs(mask[:, c]):
            n = int((b - a) * res // string_m)
            sizes = [full] * (n // full) + ([n % full] if n % full >= t.min_strings_per_row else [])
            top = a
            for k in sizes:
                cells = int(np.ceil(k * string_m / res))
                z0, z1 = grid.elevation[top, c], grid.elevation[top + cells - 1, c]
                if abs(z1 - z0) <= max_tan * k * string_m:
                    covered[top:top + cells, c] = 1
                    strings += k
                    rows += 1
                top += cells
    for dc in range(1, int(np.ceil(pitch / res))):
        covered[:, np.clip(cols + dc, 0, mask.shape[1] - 1)] |= covered[:, cols]
    footprint = unary_union([shape(g) for g, _ in features.shapes(covered, mask=covered == 1, transform=grid.transform)]) \
        if rows else None
    mwdc = strings * cfg.inverter.modules_per_string * module_stc_w / 1e6
    return Layout(rows, mwdc, float(mask.sum()) * res * res / 4046.8564224, footprint)


def exclusions_for(site_geom, layers: dict[str, gpd.GeoDataFrame]) -> list:
    out = []
    for key in ("wetlands", "flood_zones"):
        g = layers[key]
        if len(g):
            out.extend(g.geometry.iloc[g.sindex.query(site_geom, predicate="intersects")])
    return out


def flood_status(site_geom, layers) -> str:
    panels = layers["flood_panels"]
    if len(panels) and len(panels.sindex.query(site_geom, predicate="intersects")):
        return "mapped"
    return "unmapped"
