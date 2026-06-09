from fastapi import APIRouter, HTTPException

from app.domain.schemas import GraphStatsResponse, NearestNodeRequest, NearestNodeResponse

router = APIRouter(prefix="/graph", tags=["graph"])


def _require_graph():
    from app.graph.loader import kd_tree, road_graph
    if road_graph is None or kd_tree is None:
        raise HTTPException(
            status_code=503,
            detail="graph not loaded — run ingest + snap scripts first",
        )
    return road_graph, kd_tree


@router.post("/nearest-node", response_model=NearestNodeResponse)
async def nearest_node(body: NearestNodeRequest) -> NearestNodeResponse:
    _, tree = _require_graph()
    node_id, node_lat, node_lon, dist_m = tree.nearest(body.latitude, body.longitude)
    return NearestNodeResponse(
        node_id=node_id,
        latitude=node_lat,
        longitude=node_lon,
        distance_m=round(dist_m, 1),
    )


@router.get("/stats", response_model=GraphStatsResponse)
async def graph_stats() -> GraphStatsResponse:
    graph, _ = _require_graph()
    return GraphStatsResponse(
        node_count=graph.node_count(),
        edge_count=graph.edge_count(),
        bounding_box=graph.bounding_box(),
    )
