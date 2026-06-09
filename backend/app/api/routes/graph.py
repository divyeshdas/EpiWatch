from fastapi import APIRouter, HTTPException

from app.domain.schemas import GraphStatsResponse, NearestNodeRequest, NearestNodeResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/nearest-node", response_model=NearestNodeResponse)
async def nearest_node(body: NearestNodeRequest) -> NearestNodeResponse:
    from app.graph.loader import kd_tree
    if kd_tree is None:
        raise HTTPException(
            status_code=503,
            detail="graph not ready — run ingest + snap scripts first",
        )
    node_id, node_lat, node_lon, dist_m = kd_tree.nearest(body.latitude, body.longitude)
    return NearestNodeResponse(
        node_id=node_id,
        latitude=node_lat,
        longitude=node_lon,
        distance_m=round(dist_m, 1),
    )


@router.get("/stats", response_model=GraphStatsResponse)
async def graph_stats() -> GraphStatsResponse:
    from app.graph.loader import road_graph
    return GraphStatsResponse(
        node_count=road_graph.node_count(),
        edge_count=road_graph.edge_count(),
        bounding_box=road_graph.bounding_box(),
    )
