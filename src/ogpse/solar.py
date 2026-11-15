import numpy as np
import pandas as pd
import pvlib

from .equipment import Equipment


def ac_per_mwdc(weather: pd.DataFrame, meta: dict, eq: Equipment, cfg, gcr: float) -> pd.Series:
    """Hourly AC output (MW per MWdc installed) of a single-axis tracker block."""
    times = weather.index
    loc = pvlib.location.Location(meta["lat"], meta["lon"], altitude=meta["elevation"])
    sun = loc.get_solarposition(times)
    track = pvlib.tracking.singleaxis(
        sun["apparent_zenith"], sun["azimuth"], axis_tilt=0, axis_azimuth=180,
        max_angle=cfg.tracker.max_rotation_deg, backtrack=True, gcr=gcr)
    tilt = track["surface_tilt"].fillna(0)
    azimuth = track["surface_azimuth"].fillna(180)

    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azimuth, sun["apparent_zenith"], sun["azimuth"],
        weather["dni"], weather["ghi"], weather["dhi"],
        dni_extra=pvlib.irradiance.get_extra_radiation(times),
        airmass=loc.get_airmass(times, solar_position=sun)["airmass_relative"],
        albedo=weather["albedo"], model="perez")
    aoi = pvlib.irradiance.aoi(tilt, azimuth, sun["apparent_zenith"], sun["azimuth"])
    iam = pvlib.iam.physical(aoi)
    effective = (poa["poa_direct"] * iam + poa["poa_diffuse"]).fillna(0).clip(lower=0)

    m = eq.module
    cell_temp = pvlib.temperature.noct_sam(
        poa["poa_global"].fillna(0), weather["temp_air"], weather["wind_speed"],
        noct=float(m["T_NOCT"]), module_efficiency=float(m["STC"]) / (1000 * float(m["A_c"])),
        effective_irradiance=effective)
    params = pvlib.pvsystem.calcparams_cec(
        effective, cell_temp, float(m["alpha_sc"]), float(m["a_ref"]), float(m["I_L_ref"]),
        float(m["I_o_ref"]), float(m["R_sh_ref"]), float(m["R_s"]), float(m["Adjust"]))
    mpp = pvlib.pvsystem.max_power_point(*params, method="newton")
    keep = 1 - cfg.pv_losses.dc_loss
    v_dc = mpp["v_mp"] * eq.modules_per_string
    p_dc = mpp["p_mp"] * eq.modules_per_string * eq.strings_per_inverter * keep
    p_ac = pvlib.inverter.sandia(v_dc.fillna(0), p_dc.fillna(0), eq.inverter)
    return (p_ac.clip(lower=0) / 1e6 / eq.block_mwdc).rename("ac_per_mwdc")


def annual_yield(profile: pd.Series) -> float:
    """MWh AC per MWdc per year, averaged over all years."""
    return float(profile.sum() / profile.index.year.nunique())


def longest_night_hours(lat: float) -> float:
    decl = np.radians(-23.44)
    return 24 - 2 * np.degrees(np.arccos(-np.tan(np.radians(lat)) * np.tan(decl))) / 15
