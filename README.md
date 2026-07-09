# UBS Allocation Optimization

Optimization of Basic Health Unit (UBS — *Unidade Básica de Saúde*) placement for municipalities in the Espírito Santo state, Brazil. The project compares the population coverage capacity of the **real (existing)** UBS locations against the **theoretically optimal** locations found by Integer Linear Programming.

## Problem

Each UBS can serve at most **3,500 people** within a maximum road-network distance of **1,000 meters**. Given that constraint, the question is:

- How many people are currently served by the real UBS positions?
- Could the same number of UBS serve more people if placed at better road-network nodes?

## Municipalities

| Shapefile name | Notes |
|---|---|
| `alegre` | Urban seat of Alegre |
| `anutiba` | District of Alegre |
| `ararai` | District of Alegre |
| `cafe` | District of Alegre (Vila do Café) |
| `celina` | District of Alegre |
| `rive` | District of Alegre |
| `santaangelica` | District of Alegre |
| `saojoao` | District of Alegre (São João do Norte) |

## Pipeline

Run `pipeline.py` to execute the full pipeline. Edit the `polygons_names` list at the top of the file to choose which municipalities to process.

```bash
python pipeline.py
```

### Steps (in order)

1. **Get polygons** — reads the municipality boundary from `shapefiles/<name>.shp`.
2. **Get road graph** — downloads the street network from OpenStreetMap via OSMnx (two graphs: one clipped to the polygon, one covering its bounding rectangle for routing).
3. **Get population points** — clips the Southeast Brazil WorldPop raster (parquet) to the polygon and snaps each centroid to its nearest road node. Aggregates population by road node.
4. **Get possible locations** — all road nodes inside the polygon, down-sampled so no two candidates are closer than 75 m to each other.
5. **Compute distance matrix** — Dijkstra shortest-path distances (metres) from every population node to every candidate location.
6. **Get real locations** — loads the 11 real UBS coordinates (hard-coded in `main_class.py`) and snaps them to road nodes for the relevant municipality.
7. **Compute real distance/cost matrix** — same Dijkstra computation, but only to the real UBS nodes.
8. **Real capacity optimisation** — ILP (maximise covered population, existing locations fixed, ≤ 3,500 per UBS, ≤ 1,000 m).
9. **Maximum capacity optimisation** — same ILP but locations are chosen from all candidates; the number of UBS opened equals the real count.
10. **Plot figures** — saves PNG maps to `figures/`.
11. **Export HTML maps** — saves interactive Folium maps to `html/`.

Results are appended to `results-summary/<name>.txt` after every run.

## Project Structure

```
ubs-allocation/
├── pipeline.py              # Entry point
├── main_class.py            # HandlePopulations class (all logic)
├── requirements.txt
├── shapefiles/              # .shp boundaries per municipality
├── raw-data/
│   └── population_bra_southeast_2018-10-01.parquet   # WorldPop data
├── data/                    # Auto-generated cache (road graphs, matrices)
├── cache/                   # OSMnx/requests cache
├── results-summary/         # Text logs per municipality
├── figures/                 # Output PNG maps
└── html/                    # Output interactive HTML maps
```

`data/` files are generated on first run and reused on subsequent runs. Delete them to force recalculation.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.13 was used during development.

### Optional: CPLEX

The ILP solver defaults to CBC (open-source, bundled with PuLP). To use IBM CPLEX, install it separately and pass `use_cplex=True` in `pipeline.py`.

## Data Sources

- **Population**: WorldPop Southeast Brazil raster — downloaded from [HDX](https://data.humdata.org/)
- **Street network**: OpenStreetMap via [OSMnx](https://osmnx.readthedocs.io/)
- **Boundaries**: Municipal/district shapefiles in `shapefiles/`

## Output

Each run appends a block to `results-summary/<name>.txt` containing:

- Total area (km²) and total population
- **Real capacity result**: covered population, solver status, solve time
- **Maximum capacity result**: covered population, optimal node IDs, solver status, solve time

The maximum capacity cost being higher than the real capacity cost indicates that a better placement of the same number of UBS exists.
