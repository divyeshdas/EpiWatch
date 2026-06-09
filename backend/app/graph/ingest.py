"""
Synthetic road-network generator for the Mumbai area.

Lays out a regular grid of intersection nodes across the Mumbai bounding box,
applies small random jitter to each position so the layout resembles real
street intersections rather than a perfect lattice, then wires each node to
its right and lower neighbour with bidirectional directed edges.

Why synthetic instead of live OSM data:
  The geospatial source-build chain (osmnx → geopandas → fiona → GDAL) fails
  to compile on linux/arm64 with the GDAL version Debian Bookworm ships.
  The synthetic graph has the same schema, connectivity, and scale as the OSM
  graph would, so every downstream component (loader, K-D tree, snap, A*)
  works identically.

Connectivity guarantee:
  A 4-connected grid is always a single fully-connected component.  Adding
  jitter displaces node positions but does not change which pairs are linked,
  so connectivity is preserved.

Grid dimensions at step = 0.005°:
  Latitude  18.90 → 19.20  →  61 rows
  Longitude 72.78 → 72.98  →  41 columns
  Nodes     61 × 41        =  2 501
  Directed edges            ≈  9 800  (ratio ≈ 3.9 edges/node)

Run with:  docker compose exec backend python -m app.graph.ingest
           (or locally: python -m app.graph.ingest from backend/)

Idempotent: skips if graph_nodes already has rows.
"""
import asyncio
import logging
import random

from sqlalchemy import insert, select

from app.graph.haversine import haversine
from app.infra.database import get_session_factory
from app.infra.models import GraphEdge, GraphNode

logger = logging.getLogger(__name__)

_LAT_MIN, _LAT_MAX = 18.90, 19.20
_LON_MIN, _LON_MAX = 72.78, 72.98

# Grid resolution — 0.005° ≈ 550 m at latitude 19°
_STEP = 0.005

# Jitter amplitude as a fraction of _STEP (stays well inside one cell so
# connectivity is never broken by a node crossing into an adjacent cell)
_JITTER_FRAC = 0.25

# Urban speed range per edge (km/h) — varied to give realistic travel-time spread
_SPEED_MIN_KPH = 20.0
_SPEED_MAX_KPH = 50.0

# Fixed seed: same graph every run so snap results are stable
_SEED = 42


async def _run_ingest() -> None:
    factory = get_session_factory()
    async with factory() as db:
        existing = (await db.execute(select(GraphNode).limit(1))).scalar_one_or_none()
        if existing is not None:
            logger.info("graph already populated — skipping ingest")
            return

        rng = random.Random(_SEED)

        rows = round((_LAT_MAX - _LAT_MIN) / _STEP) + 1   # 61
        cols = round((_LON_MAX - _LON_MIN) / _STEP) + 1   # 41
        jitter = _JITTER_FRAC * _STEP

        # ── nodes ─────────────────────────────────────────────────────────────
        # Pre-compute jittered positions in a dict so we can look them up
        # cheaply when computing Haversine distances for each edge.
        coords: dict[tuple[int, int], tuple[float, float]] = {}
        node_rows: list[dict] = []
        for i in range(rows):
            for j in range(cols):
                lat = round((_LAT_MIN + i * _STEP) + rng.uniform(-jitter, jitter), 7)
                lon = round((_LON_MIN + j * _STEP) + rng.uniform(-jitter, jitter), 7)
                coords[(i, j)] = (lat, lon)
                node_rows.append({
                    "latitude": lat,
                    "longitude": lon,
                    "node_type": "intersection",
                    "meta": {"gi": i, "gj": j},
                })

        await db.execute(insert(GraphNode), node_rows)
        await db.flush()

        # Read back the auto-assigned primary keys via the grid indices stored in meta.
        result = await db.execute(select(GraphNode.id, GraphNode.meta))
        grid_to_id: dict[tuple[int, int], int] = {
            (int(row.meta["gi"]), int(row.meta["gj"])): row.id
            for row in result
        }
        logger.info("inserted %d nodes", len(grid_to_id))

        # ── edges ─────────────────────────────────────────────────────────────
        # Iterate each node; connect right (j+1) and down (i+1) neighbours.
        # Insert both directions to form a directed-bidirectional graph.
        edge_rows: list[dict] = []
        for i in range(rows):
            for j in range(cols):
                src_id = grid_to_id[(i, j)]
                src_lat, src_lon = coords[(i, j)]
                for di, dj in ((0, 1), (1, 0)):
                    ni, nj = i + di, j + dj
                    if ni >= rows or nj >= cols:
                        continue
                    tgt_id = grid_to_id[(ni, nj)]
                    tgt_lat, tgt_lon = coords[(ni, nj)]
                    dist_m = haversine(src_lat, src_lon, tgt_lat, tgt_lon)
                    speed_kph = rng.uniform(_SPEED_MIN_KPH, _SPEED_MAX_KPH)
                    tt_s = dist_m / (speed_kph * 1_000 / 3_600)
                    for s, t in ((src_id, tgt_id), (tgt_id, src_id)):
                        edge_rows.append({
                            "source_node_id": s,
                            "target_node_id": t,
                            "distance_m": round(dist_m, 1),
                            "travel_time_s": round(tt_s, 2),
                            "meta": {},
                        })

        await db.execute(insert(GraphEdge), edge_rows)
        await db.commit()
        logger.info(
            "synthetic graph complete: %d nodes, %d directed edges",
            len(grid_to_id),
            len(edge_rows),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
    asyncio.run(_run_ingest())


if __name__ == "__main__":
    main()
