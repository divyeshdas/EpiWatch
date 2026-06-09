from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_bus, get_hospital_repo
from app.domain.events import Event, EventType
from app.domain.schemas import RouteDetail, RouteNode, RouteRequest, RouteResponse
from app.events.bus import EventBus
from app.graph.dijkstra import dijkstra
from app.repositories.hospital import HospitalRepository

router = APIRouter(prefix="/route", tags=["routing"])


@router.post("", response_model=RouteResponse)
async def compute_route(
    body: RouteRequest,
    algo: Literal["astar", "dijkstra"] = Query(
        default="astar",
        description="Path-finding algorithm: 'astar' (default) or 'dijkstra'.",
    ),
    hospital_repo: HospitalRepository = Depends(get_hospital_repo),
    bus: EventBus = Depends(get_bus),
) -> RouteResponse:
    from app.graph.loader import kd_tree, road_graph

    if kd_tree is None:
        raise HTTPException(status_code=503, detail="graph not ready — run ingest + snap")

    # Snap the emergency coordinate to its nearest road-network node.
    src_node_id, _, _, _ = kd_tree.nearest(body.latitude, body.longitude)

    # Resolve the target hospital and its pre-snapped road node.
    hospital = await hospital_repo.get_by_id(body.hospital_id)
    if hospital is None:
        raise HTTPException(status_code=404, detail=f"hospital {body.hospital_id} not found")

    if hospital.nearest_node_id is None:
        return RouteResponse(
            route=None,
            reason="hospital has not been snapped to the road graph — run the snap script",
        )

    tgt_node_id: int = hospital.nearest_node_id

    # Choose algorithm.  A* is the default: same optimal cost as Dijkstra but
    # expands fewer nodes because the Haversine heuristic guides the frontier
    # toward the goal.
    if algo == "astar":
        from app.graph.astar import astar, make_heuristic
        result = astar(road_graph, src_node_id, tgt_node_id, make_heuristic(road_graph, tgt_node_id))
    else:
        result = dijkstra(road_graph, src_node_id, tgt_node_id)

    if result is None:
        return RouteResponse(
            route=None,
            reason="no path found between emergency location and hospital",
        )

    path = []
    for nid in result.node_ids:
        coords = road_graph.get_coords(nid)
        if coords is not None:
            path.append(RouteNode(node_id=nid, latitude=coords[0], longitude=coords[1]))

    await bus.publish(Event(
        type=EventType.ROUTE_COMPUTED,
        payload={
            "algo": algo,
            "from_node_id": src_node_id,
            "to_node_id": tgt_node_id,
            "hospital_id": body.hospital_id,
            "total_travel_time_s": result.total_travel_time_s,
        },
    ))

    return RouteResponse(
        route=RouteDetail(
            path=path,
            total_distance_m=result.total_distance_m,
            total_travel_time_s=result.total_travel_time_s,
            node_count=len(path),
        ),
    )
