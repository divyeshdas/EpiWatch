"""
OSMnx ingestion: downloads the Mumbai drive network and persists it to the DB.

Run with:   docker compose exec backend python -m app.graph.ingest
            (or locally: python -m app.graph.ingest from backend/)

Data flow:
  OSM Overpass API  →  OSMnx MultiDiGraph  →  our GraphNode / GraphEdge rows

OSMnx is used only for *data acquisition* (parsing the raw OSM XML into a
Python graph structure).  It is not used for routing — that is our own code
in later phases.  OSMnx brings networkx as a dependency; we call networkx only
via osmnx internally — our routing algorithms operate on RoadGraph (adj-list),
not networkx objects.

Idempotent: skips if graph_nodes already has rows.
"""
import asyncio
import logging

from sqlalchemy import select, insert

from app.infra.database import get_session_factory
from app.infra.models import GraphEdge, GraphNode

logger = logging.getLogger(__name__)

# Bounding box covering all 10 seeded Mumbai hospitals with 0.02° padding.
# Southernmost hospital: Bombay Hospital (18.9381 N)
# Northernmost:          Wockhardt Mulund (19.1647 N)
# Westernmost:           Breach Candy (72.8082 E)
# Easternmost:           Wockhardt Mulund (72.9545 E)
_BBOX = dict(north=19.185, south=18.918, east=72.975, west=72.788)

# Urban street speed assumed when OSM maxspeed tag is absent (km/h)
_DEFAULT_SPEED_KPH = 30.0


async def _run_ingest() -> None:
    import osmnx as ox  # imported here so the rest of the app doesn't need osmnx at startup

    factory = get_session_factory()
    async with factory() as db:
        existing = (await db.execute(select(GraphNode).limit(1))).scalar_one_or_none()
        if existing is not None:
            logger.info("graph already populated — skipping ingest")
            return

        logger.info("downloading Mumbai drive network from OpenStreetMap …")
        G = ox.graph_from_bbox(
            north=_BBOX["north"],
            south=_BBOX["south"],
            east=_BBOX["east"],
            west=_BBOX["west"],
            network_type="drive",
            simplify=True,
        )
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)

        osm_nodes = dict(G.nodes(data=True))
        logger.info("OSM download complete: %d nodes, %d edges", len(osm_nodes), G.number_of_edges())

        # ── insert nodes ─────────────────────────────────────────────────────
        node_rows = [
            {
                "latitude": float(data["y"]),
                "longitude": float(data["x"]),
                "node_type": "intersection",
                "meta": {"osm_id": osmid},
            }
            for osmid, data in osm_nodes.items()
        ]
        await db.execute(insert(GraphNode), node_rows)
        await db.flush()

        # build osm_id → our DB id mapping
        result = await db.execute(select(GraphNode.id, GraphNode.meta))
        osm_to_id: dict[int, int] = {
            int(row.meta["osm_id"]): row.id for row in result
        }
        logger.info("inserted %d nodes", len(osm_to_id))

        # ── insert edges ─────────────────────────────────────────────────────
        # OSMnx MultiDiGraph may have parallel edges between the same node pair
        # (e.g. different lanes modelled separately).  We keep all of them;
        # Dijkstra will naturally pick the shortest-time one during pathfinding.
        edge_rows = []
        skipped = 0
        for u, v, data in G.edges(data=True):
            src = osm_to_id.get(u)
            tgt = osm_to_id.get(v)
            if src is None or tgt is None:
                skipped += 1
                continue
            length_m = float(data.get("length", 0.0))
            travel_time_s = float(
                data.get(
                    "travel_time",
                    length_m / (_DEFAULT_SPEED_KPH * 1000 / 3600),
                )
            )
            edge_rows.append(
                {
                    "source_node_id": src,
                    "target_node_id": tgt,
                    "distance_m": length_m,
                    "travel_time_s": max(travel_time_s, 0.1),  # guard against zero-length edges
                    "meta": {},
                }
            )

        if edge_rows:
            await db.execute(insert(GraphEdge), edge_rows)

        await db.commit()
        logger.info(
            "inserted %d edges  (skipped %d with missing node mapping)",
            len(edge_rows),
            skipped,
        )
        logger.info(
            "ingest complete — bbox %s → %s N, %s → %s E",
            _BBOX["south"],
            _BBOX["north"],
            _BBOX["west"],
            _BBOX["east"],
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
    asyncio.run(_run_ingest())


if __name__ == "__main__":
    main()
