"""
Snaps each hospital to its nearest road-network node using the K-D tree.
Persists the result as hospitals.nearest_node_id.

Run after ingest:  docker compose exec backend python -m app.graph.snap
                   (or locally: python -m app.graph.snap from backend/)

Idempotent: re-running updates nearest_node_id (safe — values converge).
"""
import asyncio
import logging

from sqlalchemy import select, update

from app.graph.kdtree import KDTree
from app.infra.database import get_session_factory
from app.infra.models import GraphNode, Hospital

logger = logging.getLogger(__name__)


async def _run_snap() -> None:
    factory = get_session_factory()
    async with factory() as db:
        node_rows = (await db.execute(select(GraphNode))).scalars().all()
        if not node_rows:
            logger.error("no graph nodes found — run ingest first")
            return

        tree = KDTree([(n.id, n.latitude, n.longitude) for n in node_rows])
        hospitals = (await db.execute(select(Hospital))).scalars().all()

        for h in hospitals:
            node_id, _, _, dist_m = tree.nearest(h.latitude, h.longitude)
            await db.execute(
                update(Hospital)
                .where(Hospital.id == h.id)
                .values(nearest_node_id=node_id)
            )
            logger.info("  %-35s → node %-8d  (%.0f m away)", h.name, node_id, dist_m)

        await db.commit()
        logger.info("snapped %d hospitals to the road graph", len(hospitals))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
    asyncio.run(_run_snap())


if __name__ == "__main__":
    main()
