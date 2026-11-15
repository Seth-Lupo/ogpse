# Off-grid firm power in Pecos County, Texas

## Problem

An off-grid data center needs power every hour. Working out how much round-the-clock power a piece of land can deliver from solar and batteries, and at what cost, usually takes engineers weeks per site, so few sites get compared. This tool does it for every large land holding in one county, from public data, with one command.

## Method

1. **Sites.** TxGIO StratMap 2026 parcels for Pecos County. Parcels with identical boundaries are undivided interests in the same land, so they are merged into one land unit owned by a set of owners. Contiguous units with the same owner set form a holding. The 198 holdings of at least 2,000 acres (2.17 M acres, no overlaps) are the candidate sites. Owner names are used only to group and count; they are never written out.
2. **Buildable land.** A 10 m grid from the USGS 3DEP lidar DEM (1 m source, resampled by the service). Cells are removed where the north–south slope exceeds 8.5° or the east–west slope exceeds 25° (Array DuraTrack datasheet), and where they intersect NWI wetlands or FEMA special flood hazard areas. Pecos County has no FEMA flood maps, so every site is flagged `unmapped` rather than assumed safe.
3. **Layout.** Rows run north–south at a fixed pitch. Each contiguous buildable run is filled with full rows (4 strings of 27 modules) and one partial row if at least 2 strings fit. A row is dropped if its end-to-end tilt exceeds 8.5°. Capacity is strings × 27 × 550 W.
4. **Solar output.** pvlib: single-axis tracking with backtracking (±52°), Perez transposition, physical IAM, NOCT cell temperature, the CEC single-diode model for the JA Solar JAM72S30-550/MR, the Sandia model for a Delta 4.3 MW inverter at DC/AC 1.34, and 10% DC losses. The model runs hourly over 2000–2024 NSRDB GOES v4 weather (219,000 hours). Sites share the NSRDB point at the nearest 0.2° node (39 nodes). The multi-day cloud events that drive sizing are synoptic-scale, much larger than 20 km.
5. **Sizing, per MW of flat load.**
   - *Simple math:* PV sized so annual energy covers the load (half of it routed through the battery at 85% round-trip efficiency); battery = 1 MW × the longest night (14 h).
   - *Simulation:* for each battery power (2–8 MW) and duration (12–96 h), bisect the smallest PV for which a greedy hourly state-of-charge simulation serves the full load in ≥ 99.9% of hours. Keep the cheapest. Uptime counts hours; an LP or MILP would need one binary variable per hour (219,000) to express that. Uptime is monotone in PV, so bisection finds the minimum exactly, and a full search takes about 2 minutes per weather node. Refining the grid (1 h, 0.5 MW steps) moves the best and worst nodes by under 0.5%.
6. **Rank.** Firm MW = site MWdc ÷ PV per firm MW. Capital cost = firm MW × equipment cost per MW + holding acres × land price. The *cost driver* is whichever component (weather-driven equipment or land) contributes more to the site's excess cost over the county's best; sites within 1% of the best are `near best`.

Costs come from NREL ATB 2025 v2.0.0 (Moderate scenario, R&D financial case, overnight capital cost, cost year 2025, 2023$):
- Utility PV: $1,247/kWac, which is $930/kWdc at DC/AC 1.34.
- Battery: $356/kW + $223/kWh, a linear fit across ATB's 2–10 h systems.
- Land: $1,000/acre, an assumption.

## Results

**Feasibility (11 points, West Texas).** Cost per firm MW ranges from $19.8 M at El Paso to $31.1 M at Abilene, a **57%** spread. Annual yield varies only 13%, and simple-math cost only 7%. The ranking signal is real, and simple math hides it.

**Pecos County (198 sites).**
- Cost per firm MW runs from **$21.9 M to $27.6 M** (26%; 12% between the 10th and 90th percentiles), cheapest in the southwest and most expensive toward the east.
- Annual yield across the sites differs by only 6.7%.
- Weather is the cost driver at 192 sites; the other 6 are near best.
- Land is about 0.3% of capital cost. Buildable acreage (median 95% of a holding) decides how many firm megawatts a site hosts, not what each costs.
- In total the holdings could host about 32 GW of firm power.
- The top site, PEC-026, covers 15,014 acres: 255 firm MW from 2.85 GWdc of solar and a 1.0 GW / 11.5 GWh battery, for $5.6 B.

**Simple math vs simulation (Fort Stockton).** Simple math gives 4.2 MWdc and 14 h of storage per firm MW for $7.4 M, and it serves the load in only **70%** of hours. The 99.9% design needs 12.9 MWdc, 5 MW and 48 h: **3.3×** the cost. The gap comes from consecutive dark days. The worst 5-day window in 25 years produced 14% of a typical 5 days of solar energy. The battery must ride through it, and the oversized array must refill the battery afterwards. Firm off-grid solar is priced by its worst week, not its average year. That is why small differences in annual sunshine become large differences in firm cost.

## Validation

| Check | Result | Target |
|---|---|---|
| Layout vs 10 unseen USPVDB tracker plants (West Texas, ≥ 50 MWdc) | **17.7%** mean absolute error; naive acres-per-MW rule 18.0% | ~15%, beat naive |
| pvlib vs PySAM `Pvsamv1`, Fort Stockton, same weather and equipment, 25 years | **+0.16%** mean annual energy; worst year 0.36% | 3–5% |
| Every chosen design re-simulated at full scale, hourly, 25 years | **198 / 198** at ≥ 99.9% | all pass |

The 15 plants are chosen by a deterministic rule recorded in `config.yaml`: Texas single-axis plants west of 100° W, at least 50 MWdc, digitization confidence 4, DC/AC between 1.15 and 1.5, the 15 most recent. Pitch and setback were tuned on 5 of them (every third by EIA id) and frozen at 9.0 m and 0 m. The resulting 0.25 GCR is an effective value that absorbs internal roads and equipment pads. The model beats the naive rule but misses the 15% target. Both methods err on the same plants in the same direction, because built plants range from 3.5 to 6.3 acres per MWdc depending on GCR and module generation, and a footprint cannot reveal that. Training error was 13.0%; it is not reported as accuracy.

## Assumptions

All assumptions are in `config.yaml`:
- **Load:** a flat 1 MW.
- **Uptime:** 99.9% of hours, with the battery full at hour 0.
- **Battery:** round-trip efficiency 85%.
- **Losses:** 10% DC.
- **Equipment:** one module, one inverter, and one tracker.
- **Costs and land:** costs and land price as above.
- **Weather grid:** a 0.2° grid.
- **Layout:** pitch and setback as tuned.

Every download is cached and logged with URL, timestamp, size and SHA-256 in `data/manifest.csv`.

## Limitations

- Hourly energy balance only: no electrical stability, ramping or sub-hourly effects.
- Capital cost only: no O&M, financing, battery replacement or degradation over 25 years.
- Fixed equipment and a fixed land price.
- No grid and no gas. Real campuses carry backup generation, which would cut the cost of the last 0.1% sharply.
- Pecos County has no FEMA flood maps, so flood risk is unknown, not absent.
- No soils, fiber, oil and gas, easement or road-access layers.
- Weather is shared within 0.2° (~20 km).
- The parcel data is used as delivered, so owner-name variants may split some holdings.
