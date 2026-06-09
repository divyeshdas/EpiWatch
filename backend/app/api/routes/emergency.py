from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_bus, get_emergency_repo
from app.domain.events import Event, EventType
from app.domain.schemas import EmergencyCaseCreate, EmergencyCaseResponse
from app.events.bus import EventBus
from app.repositories.emergency import EmergencyCaseRepository

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
