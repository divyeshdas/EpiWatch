"""
Loads the persisted road graph from the database into memory on startup.

Call load_graph() once in the FastAPI lifespan.  After that, `road_graph` and
`kd_tree` are module-level singletons used by the API routes.

Failure modes:
  - Empty table (before ingest): road_graph = empty RoadGraph(), kd_tree = None.
    /graph/stats returns zero counts; /graph/nearest-node returns 503.
  - DB error (e.g. schema mismatch): same fallback — logs the exception, server
    still starts.  Ingest + restart will fix it.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.kdtree import KDTree
from app.graph.road_graph import RoadGraph
from app.infra.models import GraphEdge, GraphNode

logger = logging.getLogger(__name__)

road_graph: RoadGraph = RoadGraph()   # always a valid object; empty until loaded
kd_tree: KDTree | None = None


async def load_graph(db: AsyncSession) -> None:
    global road_graph, kd_tree

    try:
        node_rows = (await db.execute(select(GraphNode))).scalars().all()
        if not node_rows:
            logger.warning(
                "graph_nodes table is empty — "
                "run `python -m app.graph.ingest` then `python -m app.graph.snap`"
            )
            road_graph = RoadGraph()
            kd_tree = None
            return

        edge_rows = (await db.execute(select(GraphEdge))).scalars().all()
        road_graph = RoadGraph.from_db(node_rows, edge_rows)
        kd_tree = KDTree(road_graph.all_node_tuples())

        logger.info(
            "road graph loaded: %d nodes, %d edges",
            road_graph.node_count(),
            road_graph.edge_count(),
        )

    except Exception:
        logger.exception(
            "load_graph failed — starting with empty graph. "
            "Check that migrations are up to date and re-run ingest."
        )
        road_graph = RoadGraph()
        kd_tree = None
