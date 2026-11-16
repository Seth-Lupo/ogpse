# OGPSE — Off-Grid Power Site Evaluator

For each land holding over 2,000 acres in Pecos County, Texas, this estimates how much constant power an off-grid solar and battery plant could supply, and what it would cost per megawatt.

**[ogpse.sethlupo.com](https://ogpse.sethlupo.com)**, [REPORT.md](REPORT.md)

![map](docs/map.png)

## Results

- There are 198 holdings. Together they could supply about 32 GW.
- Cost ranges from $21.9M to $27.6M per megawatt of firm power. Annual sunshine varies only 6.7% across the same holdings; the difference comes from how long the worst cloudy stretches last.
- Sizing from annual energy plus one night of storage keeps the load running 70% of the time. Reaching 99.9% takes 3 times the solar and 48 hours of storage, and costs 3.3 times as much.
- Land is about 0.3% of the cost.

| Check | Result |
|---|---|
| Layout vs 10 built plants (USPVDB) | 17.7% error; acres-per-MW rule 18.0% |
| Solar output vs NREL SAM, 25 years | 0.16% |
| Uptime re-check, all 198 designs | all pass |

## Run

```sh
uv sync
printf "NREL_DEVELOPER_API_KEY=<key>\nNREL_EMAIL=<email>\n" > .env   # free key: developer.nlr.gov/signup
set -a; . ./.env; set +a
make all    # feasibility → run → validate → summary
make test
```

The first run downloads about 1.5 GB of public data. Most of the time, about 1.5 hours, goes to 1,250 NSRDB weather requests. Downloads are cached and logged in `data/manifest.csv` with URL and SHA-256. Later runs take about 20 minutes on 8 cores. All assumptions are in [`config.yaml`](config.yaml).

## Layout

```
config.yaml            assumptions and data sources
src/ogpse/
  sources.py           cached, logged downloads
  parcels.py           parcels → holdings → sites
  terrain.py           3DEP elevation, slopes
  hazards.py           NWI wetlands, FEMA flood zones
  layout.py            buildable area, tracker rows
  weather.py           NSRDB hourly weather
  equipment.py         CEC module and inverter
  solar.py             pvlib tracker model
  sizing.py            battery simulation, sizing search
  costs.py             NREL ATB 2025
  firm.py              designs per weather point
  pipeline.py          layouts × designs → ranking, map data
  validate.py          the three checks
  summary.py           numbers for the web page
web/                   static map page
results/               sites.csv, feasibility.csv, validation outputs
```
