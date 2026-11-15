from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import from_origin

from .config import RAW
from .sources import fetch


@dataclass(frozen=True)
class Grid:
    """A north-up raster window in the study CRS."""
    elevation: np.ndarray
    transform: rasterio.Affine
    res: float

    @property
    def shape(self):
        return self.elevation.shape

    def slopes_deg(self) -> tuple[np.ndarray, np.ndarray]:
        dz_dy, dz_dx = np.gradient(self.elevation, self.res)
        return np.degrees(np.arctan(np.abs(dz_dy))), np.degrees(np.arctan(np.abs(dz_dx)))


TILE_PX = 1000  # the 3DEP service fails on large 1 m -> 10 m resamples; 10 km tiles are reliable


def _tile(cfg, epsg: str, xmin: float, ymin: float, width: int, height: int, res: float) -> np.ndarray:
    xmax, ymax = xmin + width * res, ymin + height * res
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}", "bboxSR": epsg, "imageSR": epsg,
        "size": f"{width},{height}", "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation", "noData": "-9999", "f": "image",
    }
    name = f"{epsg}_{int(xmin)}_{int(ymin)}_{int(xmax)}_{int(ymax)}_{res:g}m.tif"
    with rasterio.open(fetch(cfg.sources.dem + "/exportImage", RAW / "dem" / name, params)) as src:
        return src.read(1).astype("float64")


def dem(cfg, bounds, crs: str | None = None) -> Grid:
    """3DEP best-available DEM (1 m lidar in West Texas) resampled server-side to the layout resolution."""
    res = cfg.layout.dem_resolution_m
    xmin, ymin = np.floor(bounds[0] / res) * res, np.floor(bounds[1] / res) * res
    xmax, ymax = np.ceil(bounds[2] / res) * res, np.ceil(bounds[3] / res) * res
    width, height = int(round((xmax - xmin) / res)), int(round((ymax - ymin) / res))
    epsg = (crs or cfg.study.crs).split(":")[1]
    if max(width, height) <= TILE_PX:
        z = _tile(cfg, epsg, xmin, ymin, width, height, res)
    else:
        z = np.full((height, width), np.nan)
        for col in range(0, width, TILE_PX):
            for row in range(0, height, TILE_PX):
                w, h = min(TILE_PX, width - col), min(TILE_PX, height - row)
                tile = _tile(cfg, epsg, xmin + col * res, ymax - (row + h) * res, w, h, res)
                z[row:row + h, col:col + w] = tile
    z[z <= -9000] = np.nan
    return Grid(z, from_origin(xmin, ymax, res, res), res)
