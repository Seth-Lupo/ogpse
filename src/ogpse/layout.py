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


def row_length_m(cfg) -> float:
    t = cfg.tracker
    return t.modules_per_row * (cfg.module.width_m + t.module_gap_m)


def row_mwdc(cfg, module_stc_w: float) -> float:
    return cfg.tracker.modules_per_row * module_stc_w / 1e6


def buildable_mask(cfg, site_geom, grid: Grid, exclusions: list) -> np.ndarray:
    """Cells inside the setback boundary, outside exclusions, and within tracker slope limits."""
    t = cfg.tracker
    inner = site_geom.buffer(-cfg.layout.boundary_setback_m)
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
    """N-S tracker rows on a lattice (pitch E-W, row length N-S); a row is kept only if every cell under it is buildable
    and its end-to-end N-S tilt is within the tracker limit."""
    res, pitch = grid.res, pitch_m or cfg.layout.row_pitch_m
    length = row_length_m(cfg)
    n_rows_y, n_cols_x = mask.shape
    span = int(np.ceil(length / res))
    xs = np.arange(pitch / 2, n_cols_x * res, pitch)
    cols = (xs // res).astype(int)
    ok = mask[:, cols].astype(np.int32)
    csum = np.vstack([np.zeros((1, len(cols)), np.int32), np.cumsum(ok, axis=0)])
    starts_m = np.arange(0, n_rows_y * res - length + 1e-9, length)
    r0 = (starts_m // res).astype(int)
    r1 = np.minimum(r0 + span, n_rows_y)
    full = (csum[r1] - csum[r0]) == (r1 - r0)[:, None]
    z = grid.elevation[:, cols]
    tilt = np.degrees(np.arctan(np.abs(z[r1 - 1] - z[r0]) / length))
    keep = full & (np.nan_to_num(tilt, nan=90) <= cfg.tracker.max_ns_slope_deg)

    covered = np.zeros(mask.shape, np.uint8)
    for i, j in zip(*np.nonzero(keep)):
        covered[r0[i]:r1[i], cols[j]] = 1
    for dj in range(1, int(np.ceil(pitch / res))):
        covered[:, np.clip(cols + dj, 0, n_cols_x - 1)] |= covered[:, cols]
    footprint = unary_union([shape(g) for g, v in features.shapes(covered, mask=covered == 1, transform=grid.transform)]) \
        if keep.any() else None
    n = int(keep.sum())
    return Layout(n, n * row_mwdc(cfg, module_stc_w), float(mask.sum()) * res * res / 4046.8564224, footprint)


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
