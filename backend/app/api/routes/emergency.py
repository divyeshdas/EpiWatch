from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_bus, get_emergency_repo, get_hospital_repo
from app.domain.events import Event, EventType
from app.domain.schemas import (
    AssignmentResponse,
    EmergencyCaseCreate,
    EmergencyCaseResponse,
    FilteredHospitalResponse,
    FactorScoreResponse,
    RouteNode,
    ScoredHospitalResponse,
)
from app.events.bus import EventBus
from app.repositories.emergency import EmergencyCaseRepository
from app.repositories.hospital import HospitalRepository

router = APIRouter(prefix="/emergency", tags=["emergency"])


@router.post("", response_model=EmergencyCaseResponse, status_code=201)
async def report_emergency(
    data: EmergencyCaseCreate,
    repo: EmergencyCaseRepository = Depends(get_emergency_repo),
    bus: EventBus = Depends(get_bus),
) -> EmergencyCaseResponse:
    case = await repo.create(data)
    await bus.publish(Event(
        type=EventType.EMERGENCY_REPORTED,
        payload={
            "case_id": case.id,
            "latitude": case.latitude,
            "longitude": case.longitude,
            "patient_condition": case.patient_condition,
            "status": case.status,
        },
    ))
    return EmergencyCaseResponse.model_validate(case)


@router.get("", response_model=list[EmergencyCaseResponse])
async def list_emergencies(
    repo: EmergencyCaseRepository = Depends(get_emergency_repo),
) -> list[EmergencyCaseResponse]:
    cases = await repo.list_all()
    return [EmergencyCaseResponse.model_validate(c) for c in cases]


@router.get("/{case_id}", response_model=EmergencyCaseResponse)
async def get_emergency(
    case_id: int,
    repo: EmergencyCaseRepository = Depends(get_emergency_repo),
) -> EmergencyCaseResponse:
    case = await repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="emergency case not found")
    return EmergencyCaseResponse.model_validate(case)


@router.post("/{case_id}/assign", response_model=AssignmentResponse)
async def assign_emergency(
    case_id: int,
    hospital_repo: HospitalRepository = Depends(get_hospital_repo),
    emergency_repo: EmergencyCaseRepository = Depends(get_emergency_repo),
    bus: EventBus = Depends(get_bus),
) -> AssignmentResponse:
    """
    Select and assign the optimal hospital for an emergency.

    Runs the full filter → normalize → weight → rank pipeline:
      1. Filter hospitals that can't serve the patient (no beds, no ICU for
         CRITICAL/CARDIAC, not snapped to the road graph, unreachable).
      2. Route from the emergency location to each candidate via A*.
      3. Score each candidate using condition-keyed weights (see weights.py).
      4. Assign the top-ranked hospital and emit an AmbulanceAssigned event.

    Returns the full ranked list with per-factor breakdowns so the dispatcher
    can see *why* a specific hospital was chosen.
    """
    from app.graph.loader import kd_tree, road_graph
    from app.scoring.scorer import score_hospitals, ScoredCandidate

    case = await emergency_repo.get_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="emergency case not found")

    if kd_tree is None:
        raise HTTPException(status_code=503, detail="graph not ready — run ingest + snap")

    hospitals = await hospital_repo.list_all()
    src_node_id, _, _, _ = kd_tree.nearest(case.latitude, case.longitude)

    result = score_hospitals(
        hospitals=hospitals,
        src_node_id=src_node_id,
        condition=case.patient_condition,
        road_graph=road_graph,
    )

    # Build serializable candidates list
    candidates = [_serialise_candidate(c, road_graph) for c in result.scored]
    filtered_out = [
        FilteredHospitalResponse(
            hospital_id=f.hospital.id,
            hospital_name=f.hospital.name,
            reason=f.reason,
        )
        for f in result.filtered_out
    ]

    if not result.scored:
        return AssignmentResponse(
            emergency_id=case_id,
            assigned_hospital_id=None,
            status="NO_CANDIDATES",
            reason="no hospital passed the filtering criteria for this patient",
            condition=case.patient_condition,
            candidates=[],
            filtered_out=filtered_out,
        )

    winner = result.scored[0]
    await emergency_repo.assign(case_id, winner.hospital.id)

    await bus.publish(Event(
        type=EventType.AMBULANCE_ASSIGNED,
        payload={
            "emergency_id": case_id,
            "hospital_id": winner.hospital.id,
            "hospital_name": winner.hospital.name,
            "condition": case.patient_condition,
            "total_score": winner.total_score,
            "travel_time_s": winner.travel_time_s,
            "distance_m": winner.distance_m,
            "candidates_evaluated": len(result.scored),
            "candidates_filtered": len(result.filtered_out),
        },
    ))

    return AssignmentResponse(
        emergency_id=case_id,
        assigned_hospital_id=winner.hospital.id,
        status="ASSIGNED",
        condition=case.patient_condition,
        candidates=candidates,
        filtered_out=filtered_out,
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _serialise_candidate(c: "ScoredCandidate", road_graph) -> ScoredHospitalResponse:
    path = []
    for nid in c.node_ids:
        coords = road_graph.get_coords(nid)
        if coords is not None:
            path.append(RouteNode(node_id=nid, latitude=coords[0], longitude=coords[1]))

    factors = {
        name: FactorScoreResponse(
            raw=fs.raw,
            penalty=fs.penalty,
            weight=fs.weight,
            contribution=fs.contribution,
        )
        for name, fs in c.factors.items()
    }

    return ScoredHospitalResponse(
        hospital_id=c.hospital.id,
        hospital_name=c.hospital.name,
        rank=c.rank,
        total_score=c.total_score,
        travel_time_s=c.travel_time_s,
        distance_m=c.distance_m,
        path=path,
        factors=factors,
    )
