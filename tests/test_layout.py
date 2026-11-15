import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import box

from ogpse import config
from ogpse.layout import buildable_mask, place_rows, string_length_m
from ogpse.terrain import Grid

CFG = config.load()


def flat_grid(n=200, res=10.0, tilt_ns=0.0):
    z = np.tile((np.arange(n)[:, None] * res * tilt_ns), (1, n)).astype(float)
    return Grid(z, from_origin(0, n * res, res, res), res)


def test_flat_square_packs_expected_capacity():
    grid = flat_grid()
    site = box(0, 0, 2000, 2000)
    mask = buildable_mask(CFG, site, grid, [], setback_m=0)
    lay = place_rows(CFG, mask, grid, 550.0, pitch_m=9.0)
    columns = len(np.arange(4.5, 2000, 9.0))
    strings_per_column = int(2000 // string_length_m(CFG))
    expected = columns * strings_per_column * CFG.inverter.modules_per_string * 550 / 1e6
    assert abs(lay.mwdc - expected) / expected < 0.03


def test_steep_ns_slope_is_unbuildable():
    grid = flat_grid(tilt_ns=0.2)  # 11.3 deg > 8.5 deg tracker limit
    mask = buildable_mask(CFG, box(0, 0, 2000, 2000), grid, [], setback_m=0)
    assert place_rows(CFG, mask, grid, 550.0).mwdc == 0


def test_exclusions_and_setback_remove_land():
    grid = flat_grid()
    site = box(0, 0, 2000, 2000)
    full = buildable_mask(CFG, site, grid, [], setback_m=0).sum()
    cut = buildable_mask(CFG, site, grid, [box(0, 0, 1000, 2000)], setback_m=100).sum()
    assert cut < full / 2
