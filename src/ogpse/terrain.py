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


def dem(cfg, site_id: str, bounds, crs: str | None = None) -> Grid:
    """3DEP best-available DEM (1 m lidar in West Texas) resampled server-side to the layout resolution."""
    res = cfg.layout.dem_resolution_m
    xmin, ymin, xmax, ymax = (np.floor(bounds[0] / res) * res, np.floor(bounds[1] / res) * res,
                              np.ceil(bounds[2] / res) * res, np.ceil(bounds[3] / res) * res)
    width, height = int((xmax - xmin) / res), int((ymax - ymin) / res)
    epsg = (crs or cfg.study.crs).split(":")[1]
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}", "bboxSR": epsg, "imageSR": epsg,
        "size": f"{width},{height}", "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation", "noData": "-9999", "f": "image",
    }
    path = fetch(cfg.sources.dem + "/exportImage", RAW / "dem" / f"{site_id}.tif", params)
    with rasterio.open(path) as src:
        z = src.read(1).astype("float64")
    z[z <= -9000] = np.nan
    return Grid(z, from_origin(xmin, ymax, res, res), res)
