# Off-grid firm power in Pecos County, Texas

## Question

A data center built off the grid needs power every hour. With only solar panels and batteries, how much constant power can a given piece of land supply, and what does it cost? This answers that for every land holding over 2,000 acres in one county, using public data.

## Method

1. **Sites.** TxGIO StratMap 2026 parcels for Pecos County. Parcels with identical boundaries are shares of the same land, so they are merged into one unit with a set of owners. Contiguous units with the same owners form a holding. The 198 holdings of at least 2,000 acres (2.17M acres, no overlaps) are the sites. Owner names are used only to group and count, and are not written out.
2. **Buildable land.** A 10 m grid from the USGS 3DEP lidar elevation model. Cells are removed where the north–south slope is over 8.5° or the east–west slope is over 25° (Array DuraTrack datasheet), or where they touch an NWI wetland or a FEMA flood zone. Pecos County has no FEMA flood maps, so every site is marked `unmapped`.
3. **Layout.** Rows run north–south at a fixed spacing. Each buildable run gets as many full rows (4 strings of 27 modules) as fit, plus one partial row if at least 2 strings fit. A row is dropped if its ends differ by more than 8.5° of tilt. Capacity is strings × 27 × 550 W.
4. **Solar output.** pvlib: single-axis tracking with backtracking (±52°), Perez sky model, physical IAM, NOCT cell temperature, CEC single-diode model of the JA Solar JAM72S30-550/MR, Sandia model of a Delta 4.3 MW inverter at DC/AC 1.34, and 10% DC losses. Run hourly on 2000–2024 NSRDB GOES v4 weather (219,000 hours). Sites use the weather at the nearest 0.2° grid point (39 points). Multi-day cloudy periods cover areas much larger than 20 km, so this loses little.
5. **Sizing, per MW of constant load.**
   - *Simple:* enough solar to cover a year's energy (with half of it passing through the battery at 85% round-trip efficiency), and a 1 MW battery for the longest night (14 h).
   - *Simulated:* for each battery power (2–8 MW) and duration (12–96 h), find by bisection the smallest solar array for which an hourly battery simulation serves the full load in at least 99.9% of hours. Keep the cheapest. Uptime counts hours, so a linear program would need a yes/no variable for each of the 219,000 hours. Uptime only rises as solar is added, so bisection finds the minimum directly. The search takes about 2 minutes per weather point. A finer grid (1 h, 0.5 MW steps) changes the best and worst points by less than 0.5%.
6. **Ranking.** Firm MW = site MWdc ÷ solar MWdc per firm MW. Cost = firm MW × equipment cost per MW + acres × land price. The cost driver column says whether weather or land accounts for more of a site's cost above the county's cheapest; sites within 1% of the cheapest are marked `near best`.

Costs are from NREL ATB 2025 v2.0.0 (Moderate scenario, R&D financial case, overnight capital cost, 2023$):
- Utility solar: $1,247/kWac, or $930/kWdc at DC/AC 1.34.
- Battery: $356/kW + $223/kWh, a linear fit to ATB's 2–10 h systems.
- Land: $1,000/acre, an assumption.

## Results

**West Texas (11 points).** Cost per firm MW ranges from $19.8M at El Paso to $31.1M at Abilene, a 57% difference. Annual solar output differs by 13%, and the simple sizing method's cost by 7%.

**Pecos County (198 sites).**
- Cost per firm MW ranges from $21.9M to $27.6M (26%; 12% between the 10th and 90th percentiles). It is lowest in the southwest and highest toward the east.
- Annual solar output differs by 6.7% across the sites.
- Weather is the cost driver at 192 sites; the other 6 are near best.
- Land is about 0.3% of cost. The buildable share of a holding (median 95%) affects how many megawatts it can support, not the cost per megawatt.
- All holdings together could supply about 32 GW.
- The cheapest site, PEC-026, covers 15,014 acres. It supports 255 firm MW from 2.85 GWdc of solar and a 1.0 GW / 11.5 GWh battery, for $5.6B.

**Simple vs simulated sizing (Fort Stockton).** The simple method gives 4.2 MWdc and 14 h of storage per firm MW, for $7.4M. That system serves the load in 70% of hours. The 99.9% design needs 12.9 MWdc, 5 MW and 48 h, and costs 3.3 times as much. The difference is caused by consecutive cloudy days. The worst 5 days in 25 years produced 14% of a typical 5 days of solar energy. The battery has to cover that period, and the extra solar has to recharge it afterward. Since the system is sized for these periods, small differences in annual sunshine between sites lead to larger differences in cost.

## Validation

| Check | Result | Target |
|---|---|---|
| Layout vs 10 held-out USPVDB tracker plants (West Texas, ≥ 50 MWdc) | 17.7% mean absolute error; acres-per-MW rule 18.0% | ~15%, beat the rule |
| pvlib vs PySAM `Pvsamv1`, Fort Stockton, same weather and equipment, 25 years | +0.16% mean annual energy; worst year 0.36% | 3–5% |
| Every chosen design re-simulated at full scale, hourly, 25 years | 198 / 198 at ≥ 99.9% | all pass |

The 15 plants are selected by a fixed rule in `config.yaml`: Texas single-axis plants west of 100° W, at least 50 MWdc, digitization confidence 4, DC/AC between 1.15 and 1.5, the 15 most recent. Row spacing and setback were tuned on 5 of them (every third by EIA id) and fixed at 9.0 m and 0 m. The resulting 0.25 ground coverage ratio is lower than a real one because it also absorbs roads and equipment pads. The model does slightly better than the rule but misses the 15% target. Both methods are wrong on the same plants in the same direction: built plants use 3.5 to 6.3 acres per MWdc depending on row spacing and module type, and a property boundary doesn't show either. Training error was 13.0%.

## Assumptions

All assumptions are in `config.yaml`:
- Load: a constant 1 MW.
- Uptime: 99.9% of hours, battery full at the start.
- Battery: 85% round-trip efficiency.
- Losses: 10% DC.
- Equipment: one module, one inverter, one tracker.
- Costs and land price as above.
- Weather on a 0.2° grid.
- Row spacing and setback as tuned.

Every download is cached and logged with URL, time, size and SHA-256 in `data/manifest.csv`.

## Limitations

- Hourly energy balance only: no electrical stability, ramping or sub-hourly effects.
- Construction cost only: no operations, financing, battery replacement or degradation.
- Fixed equipment and land price.
- No grid or gas backup. Real campuses keep backup generators, which would make the last 0.1% much cheaper.
- Pecos County has no FEMA flood maps, so flood risk is unknown, not zero.
- No soils, fiber, oil and gas, easements or road access.
- Weather is shared within 0.2° (about 20 km).
- Parcel data is used as delivered, so variant spellings of an owner's name may split some holdings.
